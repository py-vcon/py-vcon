# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.

import os
import importlib
import py_vcon_server

os.environ["PLUGIN_PATHS"] = "tests/processors,ddd"

def test_plugin_path():
  try:
    proc = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("test_add_party")
    assert(proc is None)
  except py_vcon_server.processor.VconProcessorNotRegistered as not_found:
    # expected
    pass

  # Force a reload as we have changed the PLUGIN_PATHS env var
  importlib.reload(py_vcon_server.settings)
  importlib.reload(py_vcon_server)

  proc = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("test_add_party")
  assert(proc is not None)

