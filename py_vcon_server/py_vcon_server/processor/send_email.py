# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.

""" Registration for the SendEmail **VconProcessor** """
import py_vcon_server.processor

init_options = py_vcon_server.processor.VconProcessorInitOptions()

py_vcon_server.processor.VconProcessorRegistry.register(
      init_options,
      "send_email",
      "py_vcon_server.processor.builtin.send_email",
      "SendEmail"
      )

