# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" Registration for the test AddParty **VconProcessor** """
import py_vcon_server.processor

init_options = py_vcon_server.processor.VconProcessorInitOptions()

py_vcon_server.processor.VconProcessorRegistry.register(
      init_options,
      "test_add_party",
      "processors_good",
      "AddParty"
      )

