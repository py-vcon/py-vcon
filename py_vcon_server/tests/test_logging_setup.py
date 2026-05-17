# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
Unit tests for the py_vcon_server package's logging setup.

Verifies:

  1. Records emitted through py_vcon_server.logging_utils.init_logger
     are serialized as JSON with the expected LogRecord-derived fields.

  2. Every record carries service="py_vcon_server".

  3. instance_id is absent from records when settings.INSTANCE_ID is
     empty (the default), and present with the correct value when it
     is set.

  4. Records from vcon library code (e.g. vcon.filter_plugins) also
     carry service="py_vcon_server" thanks to the filter attached to
     vcon's own handlers by py_vcon_server.

  5. pytest's caplog fixture sees py_vcon_server records, which means
     records propagate up the logger hierarchy.
"""

import io
import json
import logging

import pytest

import py_vcon_server
import py_vcon_server.logging_utils
import py_vcon_server.settings


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _find_py_vcon_server_json_handler(start_logger):
  """
  Walk up the logger hierarchy from start_logger and return the
  StreamHandler whose formatter is a pythonjsonlogger JsonFormatter.
  This is the handler that py_vcon_server.logging_utils.init_logger
  attached on the py_vcon_server package root logger.

  Skips other handlers (e.g. pytest's caplog handlers on the root).
  """
  import pythonjsonlogger.json

  current = start_logger
  while current is not None:
    for h in current.handlers:
      if (isinstance(h, logging.StreamHandler)
          and hasattr(h, "stream")
          and isinstance(h.formatter, pythonjsonlogger.json.JsonFormatter)):
        return h
    current = current.parent
  return None


def _emit_and_capture_json(logger, message, level=logging.WARNING):
  """
  Temporarily redirect the py_vcon_server JSON handler's stream to
  an in-memory buffer, emit a record, and return the parsed JSON.
  """
  handler = _find_py_vcon_server_json_handler(logger)
  assert handler is not None, (
      "no py_vcon_server JSON StreamHandler found in logger chain "
      "for {}".format(logger.name)
    )

  buffer = io.StringIO()
  saved_stream = handler.stream
  handler.stream = buffer
  try:
    logger.log(level, message)
  finally:
    handler.stream = saved_stream

  lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
  assert lines, "no log line emitted"
  return json.loads(lines[-1])


# ----------------------------------------------------------------------
# JSON format and required fields
# ----------------------------------------------------------------------


def test_py_vcon_server_log_records_are_json_with_expected_fields():
  """
  Records emitted via init_logger include all required LogRecord
  fields plus the service field added by _ServiceFilter.
  """
  logger = py_vcon_server.logging_utils.init_logger(
      "py_vcon_server.test_json_fields"
    )
  record = _emit_and_capture_json(logger, "json format check")

  expected_keys = {
      "process",
      "levelname",
      "message",
      "pathname",
      "module",
      "lineno",
      "timestamp",
      "service",
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
# service field
# ----------------------------------------------------------------------


def test_service_field_is_py_vcon_server():
  """
  Every py_vcon_server log record carries service="py_vcon_server".
  """
  logger = py_vcon_server.logging_utils.init_logger(
      "py_vcon_server.test_service_field"
    )
  record = _emit_and_capture_json(logger, "service field check")
  assert record["service"] == "py_vcon_server", (
      "expected service='py_vcon_server', got {!r}".format(
        record.get("service")
      )
    )


# ----------------------------------------------------------------------
# instance_id field
# ----------------------------------------------------------------------


def test_instance_id_absent_when_setting_is_empty(monkeypatch):
  """
  When settings.INSTANCE_ID is empty (the default), records do not
  include an instance_id field at all -- avoids noisy null fields
  in Loki and matches the design that absent instance_id is omitted.

  Tests _ServiceFilter directly because the running filter was
  constructed at module-load time before this monkeypatch could
  take effect.  Constructing a fresh filter with the monkeypatched
  setting verifies the construction-time capture logic.
  """
  monkeypatch.setattr(py_vcon_server.settings, "INSTANCE_ID", "")
  filt = py_vcon_server.logging_utils._ServiceFilter()

  record = logging.LogRecord(
      name="py_vcon_server.test_instance_absent",
      level=logging.INFO,
      pathname=__file__,
      lineno=1,
      msg="x",
      args=None,
      exc_info=None,
    )
  filt.filter(record)
  assert not hasattr(record, "instance_id"), (
      "instance_id should be absent when settings.INSTANCE_ID is empty"
    )
  assert record.service == "py_vcon_server"


def test_instance_id_present_when_setting_is_set(monkeypatch):
  """
  When settings.INSTANCE_ID is non-empty, freshly-constructed
  _ServiceFilter captures it and stamps it onto records.
  """
  monkeypatch.setattr(
      py_vcon_server.settings, "INSTANCE_ID", "test-instance-01"
    )
  filt = py_vcon_server.logging_utils._ServiceFilter()

  record = logging.LogRecord(
      name="py_vcon_server.test_instance_present",
      level=logging.INFO,
      pathname=__file__,
      lineno=1,
      msg="x",
      args=None,
      exc_info=None,
    )
  filt.filter(record)
  assert getattr(record, "instance_id", None) == "test-instance-01", (
      "expected instance_id='test-instance-01', got {!r}".format(
        getattr(record, "instance_id", None)
      )
    )
  assert record.service == "py_vcon_server"


# ----------------------------------------------------------------------
# vcon library records carry py_vcon_server's service label
# ----------------------------------------------------------------------


def test_vcon_library_records_carry_py_vcon_server_service():
  """
  vcon library records flow through vcon's own stderr JSON handler
  (vcon installs that handler on the 'vcon' logger).  After
  py_vcon_server.logging_utils.init_logger has run, a _ServiceFilter
  is attached to vcon's handlers so records emitted there get
  service='py_vcon_server'.
  """
  import pythonjsonlogger.json

  # Ensure init_logger has run for py_vcon_server -- it normally
  # runs at py_vcon_server import time but call it again to be sure
  # the filter has been attached to vcon's handlers.
  py_vcon_server.logging_utils.init_logger("py_vcon_server")

  vcon_logger = logging.getLogger("vcon")

  # Find the JSON handler on the vcon logger.
  vcon_handler = None
  for h in vcon_logger.handlers:
    if (isinstance(h, logging.StreamHandler)
        and hasattr(h, "stream")
        and isinstance(h.formatter, pythonjsonlogger.json.JsonFormatter)):
      vcon_handler = h
      break
  assert vcon_handler is not None, (
      "vcon logger has no JSON StreamHandler -- "
      "vcon's own build_logger may not have run"
    )

  buffer = io.StringIO()
  saved_stream = vcon_handler.stream
  vcon_handler.stream = buffer
  try:
    logging.getLogger("vcon.some_module").warning("vcon record")
  finally:
    vcon_handler.stream = saved_stream

  lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
  assert lines, "no log line emitted on vcon's handler"
  record = json.loads(lines[-1])
  assert record.get("service") == "py_vcon_server", (
      "vcon library record should carry service='py_vcon_server', "
      "got service={!r}".format(record.get("service"))
    )


# ----------------------------------------------------------------------
# Propagation: caplog visibility
# ----------------------------------------------------------------------


def test_caplog_captures_py_vcon_server_records(caplog):
  """
  pytest's caplog fixture must see records emitted via
  py_vcon_server.logging_utils.init_logger.  Required for unit
  tests in py_vcon_server to assert on log content (the failures
  in test_metrics.py and test_processor_registration.py that
  prompted this work).
  """
  logger = py_vcon_server.logging_utils.init_logger(
      "py_vcon_server.test_caplog_visibility"
    )
  marker = "py_vcon_server record visible to caplog"
  with caplog.at_level(logging.DEBUG, logger="py_vcon_server"):
    logger.error(marker)
  messages = [r.message for r in caplog.records]
  assert any(marker in m for m in messages), (
      "caplog did not capture record from "
      "py_vcon_server.logging_utils.init_logger; got messages: {}".format(
        messages
      )
    )
