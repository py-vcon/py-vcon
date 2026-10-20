# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" Registration file that mirrors py_vcon_server/processor/whisper_base.py.

Like whisper_base.py, this file does an eager top-level import of an
impl module that fails to import.  The exception propagates out of
this registration file's import before the VconProcessorRegistry.register()
call below is reached.

The scanner db.import_bindings() must:
  1. Catch this exception
  2. Log an ERROR level message identifying the failed module
  3. Continue iterating to the next file in the directory

If the scanner propagates this exception, no further registration
files in the same directory will be loaded -- which is the production
failure when whisper deps are missing.
"""

import scanner_impl_raises

import py_vcon_server.processor

py_vcon_server.processor.VconProcessorRegistry.register(
    py_vcon_server.processor.VconProcessorInitOptions(),
    "scanner_unreachable_registration",
    "scanner_impl_raises",
    "Unreachable"
    )
