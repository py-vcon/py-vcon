# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
Unit tests for the vcon package's logging setup.

Verifies the four invariants we require of vcon logging:

  1. Log output goes to stderr, never stdout.  stdout is reserved for
     the vcon CLI's JSON output and any pollution there breaks pipes.

  2. The format is JSON with the expected LogRecord fields
     (process, levelname, message, pathname, module, lineno, timestamp).

  3. The standard pytest caplog fixture sees vcon log records, which
     means records propagate up the logger hierarchy as expected and
     unit tests can assert on log output.

  4. Records emitted from any vcon submodule reach the same output
     destination -- whether the module uses vcon.logging_utils.build_logger
     or plain logging.getLogger(__name__).

These tests are written to pass under the target logging topology and
will fail in informative ways if any of the invariants regresses.
"""

import io
import json
import logging
import sys

import pytest

import vcon
import vcon.logging_utils


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _all_vcon_handlers():
  """
  Walk every logger named under the 'vcon' hierarchy and return the
  combined list of handlers attached to any of them.  Includes the
  'vcon' root logger itself.
  """
  collected = []
  manager = logging.Logger.manager
  for name in list(manager.loggerDict.keys()):
    if name == "vcon" or name.startswith("vcon."):
      lg = logging.getLogger(name)
      for h in lg.handlers:
        collected.append((name, h))
  # vcon root logger is in loggerDict only after first access; ensure
  # it is included.
  for h in logging.getLogger("vcon").handlers:
    pair = ("vcon", h)
    if pair not in collected:
      collected.append(pair)
  return collected


# ----------------------------------------------------------------------
# Invariant 1: stderr destination, no stdout pollution
# ----------------------------------------------------------------------


def test_vcon_handlers_write_to_stderr():
  """
  Every StreamHandler attached anywhere under the vcon logger
  hierarchy must target sys.stderr.  A handler on sys.stdout
  would corrupt the vcon CLI's JSON output stream.
  """
  offenders = []
  for logger_name, handler in _all_vcon_handlers():
    if isinstance(handler, logging.StreamHandler):
      stream = getattr(handler, "stream", None)
      if stream is sys.stdout:
        offenders.append(logger_name)
  assert offenders == [], (
      "vcon loggers must not write to stdout (would break the CLI); "
      "offending loggers: {}".format(offenders)
    )


def test_logging_does_not_pollute_stdout(capsys):
  """
  Emitting log records via vcon.logging_utils.build_logger must
  produce zero bytes on stdout.  This is the property the CLI
  depends on.
  """
  logger = vcon.logging_utils.build_logger("vcon.test_stdout_isolation")
  logger.warning("test message that must not appear on stdout")
  captured = capsys.readouterr()
  assert captured.out == "", (
      "vcon logging wrote to stdout: {!r}".format(captured.out)
    )


# ----------------------------------------------------------------------
# Invariant 2: JSON format with expected fields
# ----------------------------------------------------------------------


def _emit_and_capture_json(logger, message):
  """
  Capture the JSON output emitted via vcon's own handler.  Locates
  the vcon handler by finding the StreamHandler on the 'vcon'
  logger (or any ancestor up to the root) whose formatter is a
  pythonjsonlogger JsonFormatter -- this is the one vcon installed.
  Other handlers in the chain (pytest's stream/null handlers) are
  skipped.
  """
  import pythonjsonlogger.json

  found_handler = None
  current = logger
  while current is not None:
    for h in current.handlers:
      if (isinstance(h, logging.StreamHandler)
          and hasattr(h, "stream")
          and isinstance(h.formatter, pythonjsonlogger.json.JsonFormatter)):
        found_handler = h
        break
    if found_handler is not None:
      break
    current = current.parent

  # DEBUG
  if False:
    print("DEBUG: starting logger:", logger.name, "found_handler:", found_handler)
    c = logger
    while c is not None:
      print("DEBUG: checking", c.name, "handlers:", c.handlers,
            "formatters:", [type(h.formatter).__name__ if h.formatter else None for h in c.handlers])
      c = c.parent

    assert found_handler is not None, (
        "no vcon JSON StreamHandler found in logger chain for {}".format(
          logger.name
        )
      )

  buffer = io.StringIO()
  saved_stream = found_handler.stream
  found_handler.stream = buffer
  try:
    logger.warning(message)
  finally:
    found_handler.stream = saved_stream

  lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
  assert lines, "no log line emitted"
  return json.loads(lines[-1])


def test_vcon_log_records_are_json_with_expected_fields():
  """
  Records emitted through vcon.logging_utils.build_logger are
  serialized as JSON with the expected LogRecord-derived fields.
  """
  logger = vcon.logging_utils.build_logger("vcon.test_json_fields")
  record = _emit_and_capture_json(logger, "json format check")

  expected_keys = {
      "process",
      "levelname",
      "message",
      "pathname",
      "module",
      "lineno",
      "timestamp",
    }
  missing = expected_keys - set(record.keys())
  assert missing == set(), (
      "JSON log record missing expected fields {}: got keys {}".format(
        sorted(missing), sorted(record.keys())
      )
    )

  assert record["message"] == "json format check"
  assert record["levelname"] == "WARNING"


# ----------------------------------------------------------------------
# Invariant 3: pytest caplog sees vcon records
# ----------------------------------------------------------------------


def test_caplog_captures_vcon_build_logger_records(caplog):
  """
  pytest's caplog fixture must see records emitted via
  vcon.logging_utils.build_logger.  This proves records reach the
  root logger via propagation, which is required for unit tests
  in vcon (and downstream packages) to assert on log content.
  """
  logger = vcon.logging_utils.build_logger("vcon.test_caplog_build_logger")
  marker = "build_logger record visible to caplog"
  with caplog.at_level(logging.DEBUG, logger="vcon"):
    logger.error(marker)
  messages = [r.message for r in caplog.records]
  assert any(marker in m for m in messages), (
      "caplog did not capture record from vcon.logging_utils.build_logger; "
      "got messages: {}".format(messages)
    )


def test_caplog_captures_vcon_submodule_records(caplog):
  """
  Records emitted from a vcon submodule logger (which uses plain
  logging.getLogger(__name__) but is now routed through vcon's
  hierarchy) must also be visible to caplog.  This mirrors what
  vcon.http_lb does.
  """
  logger = logging.getLogger("vcon.http_lb")
  marker = "http_lb-style record visible to caplog"
  with caplog.at_level(logging.DEBUG, logger="vcon"):
    logger.error(marker)
  messages = [r.message for r in caplog.records]
  assert any(marker in m for m in messages), (
      "caplog did not capture record from a vcon submodule logger; "
      "got messages: {}".format(messages)
    )


# ----------------------------------------------------------------------
# Invariant 4: import-time records present
# ----------------------------------------------------------------------


def test_vcon_package_root_has_handler():
  """
  The vcon package root logger must have at least one handler so
  that records emitted during 'import vcon' (e.g. plugin
  registration) have somewhere to go.  Without this, import-time
  errors from filter_plugins or http_lb would be silently dropped.
  """
  root = logging.getLogger("vcon")
  # Either the 'vcon' logger has its own handler, or an ancestor
  # does.  In the standalone case (vcon CLI / vcon tests) 'vcon'
  # should have its own; under a service like py_vcon_server, an
  # ancestor may have one and 'vcon' may not.
  has_handler = bool(root.handlers)
  if not has_handler:
    ancestor = root.parent
    while ancestor is not None:
      if ancestor.handlers:
        has_handler = True
        break
      ancestor = ancestor.parent
  assert has_handler, (
      "no handler anywhere in the vcon logger chain; "
      "import-time log messages would be lost"
    )
