# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" Registration for the JWE decryption **VconProcessor** """
import py_vcon_server.processor
import py_vcon_server.processor.builtin.decrypt

init_options = py_vcon_server.processor.builtin.decrypt.DecryptInitOptions()

py_vcon_server.processor.VconProcessorRegistry.register(
      init_options,
      "decrypt",
      "py_vcon_server.processor.builtin.decrypt",
      "Decrypt"
      )

