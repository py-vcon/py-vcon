# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.

""" Registration for the text PII redactor **VconProcessor** """
import py_vcon_server.processor

init_options = py_vcon_server.processor.VconProcessorInitOptions()

py_vcon_server.processor.VconProcessorRegistry.register(
      init_options,
      "text_pii_redactor",
      "py_vcon_server.processor.builtin.text_pii_redactor",
      "TextPiiRedactor"
      )

