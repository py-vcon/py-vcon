# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" Impl module that mirrors the whisper.py production failure pattern.

Mirrors vcon/filter_plugins/impl/whisper.py's top-level guarded import:

    try:
      import stable_whisper
    except Exception as e:
      logger.info("please install stable_whisper: ...")
      raise e

When stable_whisper is uninstalled, ModuleNotFoundError propagates out
of this module's top-level, which then propagates out of any registration
file that does "import vcon.filter_plugins.impl.whisper" at its own top
level (like py_vcon_server/processor/whisper_base.py).

This fixture simulates the same failure by importing a module that
does not exist.  Lives flat in tests/ (not in tests/scanner_fixtures/)
so that pkgutil.iter_modules() over the fixtures directory does not
try to import this file directly.
"""

try:
  import scanner_module_that_does_not_exist_for_test_purposes
except Exception as e:
  raise e
