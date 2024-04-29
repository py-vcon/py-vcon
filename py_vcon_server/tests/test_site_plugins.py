# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.

import os
import importlib
import py_vcon_server

ORIGINAL_PLUGIN_PATHS = os.getenv("PLUGIN_PATHS", None)

def test_plugin_path():
  try:
    assert("test_processors" not in os.getenv("PLUGIN_PATHS", "").split(","))
    assert("test_processors" not in py_vcon_server.settings.PLUGIN_PATHS)
    proc = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("test_add_party")
    assert(proc is None)
  except py_vcon_server.processor.VconProcessorNotRegistered as not_found:
    # expected
    pass

  # Force a reload as we have changed the PLUGIN_PATHS env var
  os.environ["PLUGIN_PATHS"] = "test_processors,ddd"
  importlib.reload(py_vcon_server.settings)
  importlib.reload(py_vcon_server)
  assert("test_processors" in py_vcon_server.settings.PLUGIN_PATHS)
  if(ORIGINAL_PLUGIN_PATHS is None):
    del os.environ["PLUGIN_PATHS"]
  else:
    os.environ["PLUGIN_PATHS"] = ORIGINAL_PLUGIN_PATHS

  proc = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("test_add_party")
  assert(proc is not None)

