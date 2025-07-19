# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" Registration for the create appended**VconProcessor** """
import py_vcon_server.processor
import py_vcon_server.processor.builtin.create_appended

init_options = py_vcon_server.processor.builtin.create_appended.AppendedInitOptions()

py_vcon_server.processor.VconProcessorRegistry.register(
      init_options,
      "create_appended",
      "py_vcon_server.processor.builtin.create_appended",
      "Appended"
      )

