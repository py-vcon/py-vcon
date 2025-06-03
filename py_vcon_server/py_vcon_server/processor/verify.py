# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" Registration for the JWS verification **VconProcessor** """
import py_vcon_server.processor
import py_vcon_server.processor.builtin.verify

init_options = py_vcon_server.processor.builtin.verify.VerifyInitOptions()

py_vcon_server.processor.VconProcessorRegistry.register(
      init_options,
      "verify",
      "py_vcon_server.processor.builtin.verify",
      "Verify"
      )

