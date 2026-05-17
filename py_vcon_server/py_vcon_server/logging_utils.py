# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
import sys
import logging
import pythonjsonlogger.json
import py_vcon_server.settings


class _ServiceFilter(logging.Filter):
  """
  Injects service and (optionally) instance_id into every LogRecord
  so they appear as top-level fields in the JSON output.
  service and instance_id are captured once at filter creation from settings.
  """

  def __init__(self):
    super().__init__()
    self._service = py_vcon_server.settings.SERVICE_NAME
    self._instance_id = py_vcon_server.settings.INSTANCE_ID

  def filter(self, record):
    record.service = self._service
    if self._instance_id:
      record.instance_id = self._instance_id
    return True



def _attach_service_filter_to_handlers(logger_name):
  """
  Walk the named logger's handlers and add a _ServiceFilter to each.
  Used so that records emitted via vcon's own handlers carry the
  service field added by this server.

  Filters on a handler are called for every record that reaches the
  handler regardless of which logger originated it -- including
  records that propagate from child loggers.  Filters on a logger
  itself are NOT applied to propagated records, so the filter must
  go on the handler, not the logger.
  """
  target = logging.getLogger(logger_name)
  for handler in target.handlers:
    # Avoid attaching twice on re-invocation (e.g. fork inheritance).
    if not any(isinstance(f, _ServiceFilter) for f in handler.filters):
      handler.addFilter(_ServiceFilter())


def init_logger(name):
  """
  Initialize and return a named logger with JSON output.

  At top of file:
    logger = init_logger(__name__)

  Use as:
    logger.debug("foo: {}".format(foo))
    logger.exception("exception: {}".format(e))

  Behavior: installs a single JSON handler on the py_vcon_server
  package root logger on first call.  Subsequent calls for child
  module names return their logger; records propagate up to the
  package root handler.  Skips the root logger when walking
  ancestors so that pytest's caplog handlers do not suppress our
  own handler setup.
  """
  logger = logging.getLogger(name)

  # If this logger already has its own handler, return as-is.
  if logger.handlers:
    return logger

  # Walk up named ancestors (skip the root logger).  If any named
  # ancestor has a handler, records will propagate there.  Skip
  # the root logger because pytest, logging.basicConfig, and
  # similar framework code attach handlers there that should not
  # suppress our own handler installation.
  ancestor = logger.parent
  while ancestor is not None and ancestor.name != "root":
    if ancestor.handlers:
      # A named ancestor (e.g. py_vcon_server) already has the
      # handler.  Still ensure vcon's handlers carry the service
      # filter -- safe to call repeatedly.
      _attach_service_filter_to_handlers("vcon")
      _attach_service_filter_to_handlers("vcon.filter_plugins")
      return logger
    ancestor = ancestor.parent

  # No named ancestor has a handler -- install one on this logger.
  level = getattr(logging, py_vcon_server.settings.LOG_LEVEL.upper(), logging.DEBUG)
  logger.setLevel(level)

  handler = logging.StreamHandler(sys.stdout)
  handler.setLevel(level)
  handler.addFilter(_ServiceFilter())

  formatter = pythonjsonlogger.json.JsonFormatter(
      "%(process)d %(levelname)s %(message)s %(pathname)s %(module)s %(lineno)d",
      timestamp=True
    )
  handler.setFormatter(formatter)
  logger.addHandler(handler)

  # Stamp service/instance_id onto records emitted through the vcon
  # library's own handlers.
  _attach_service_filter_to_handlers("vcon")
  _attach_service_filter_to_handlers("vcon.filter_plugins")

  return logger

