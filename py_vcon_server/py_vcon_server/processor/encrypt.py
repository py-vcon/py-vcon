# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" Registration for the JWE encryption **VconProcessor** """
import py_vcon_server.processor
import py_vcon_server.processor.builtin.encrypt

init_options = py_vcon_server.processor.builtin.encrypt.EncryptInitOptions()

py_vcon_server.processor.VconProcessorRegistry.register(
      init_options,
      "encrypt",
      "py_vcon_server.processor.builtin.encrypt",
      "Encrypt"
      )

