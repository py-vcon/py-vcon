# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" Registration for the create amended **VconProcessor** """
import py_vcon_server.processor
import py_vcon_server.processor.builtin.create_amended

init_options = py_vcon_server.processor.builtin.create_amended.AmendedInitOptions()

py_vcon_server.processor.VconProcessorRegistry.register(
      init_options,
      "create_amended",
      "py_vcon_server.processor.builtin.create_amended",
      "Amended"
      )

