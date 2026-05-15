# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
Shared logger setup for the vcon package.

build_logger is re-exported from vcon/__init__.py so existing callers using
vcon.build_logger(__name__) continue to work unchanged.

TODO: When touching files that call vcon.build_logger, consider migrating
the call site to vcon.logging_utils.build_logger directly.  The re-export
keeps both paths working indefinitely; this is cosmetic only.

Output goes to stderr because stdout is reserved for the vcon CLI
(piping stdout through the CLI would be broken by log lines on stdout).
"""

import sys
import logging
import pythonjsonlogger.json


def build_logger(name):
  logger = logging.getLogger(name)

  if not logger.handlers:
    logger.setLevel(logging.DEBUG)

    # Output to stdout WILL BREAK the Vcon CLI.
    # MUST use stderr.
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.DEBUG)
    formatter = pythonjsonlogger.json.JsonFormatter(
        "%(process)d %(levelname)s %(message)s %(pathname)s %(module)s %(lineno)d",
        timestamp=True
      )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False

  return logger
