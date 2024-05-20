# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.

""" Registration for the SetParameters **VconProcessor** """
import py_vcon_server.processor

init_options = py_vcon_server.processor.VconProcessorInitOptions()

py_vcon_server.processor.VconProcessorRegistry.register(
      init_options,
      "set_parameters",
      "py_vcon_server.processor.builtin.set_parameters",
      "SetParameters"
      )

