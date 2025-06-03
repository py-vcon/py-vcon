# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" Registration for the JWS signing **VconProcessor** """
import py_vcon_server.processor
import py_vcon_server.processor.builtin.sign

init_options = py_vcon_server.processor.builtin.sign.SignInitOptions()

py_vcon_server.processor.VconProcessorRegistry.register(
      init_options,
      "sign",
      "py_vcon_server.processor.builtin.sign",
      "Sign"
      )

