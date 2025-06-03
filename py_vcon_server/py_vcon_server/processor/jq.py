# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.

""" Registration for the JQProcessor **VconProcessor** """
import py_vcon_server.processor

init_options = py_vcon_server.processor.VconProcessorInitOptions()

py_vcon_server.processor.VconProcessorRegistry.register(
      init_options,
      "jq",
      "py_vcon_server.processor.builtin.jq",
      "JQProcessor"
      )

