# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.

""" Registration for the JinjaReport **VconProcessor** """
import py_vcon_server.processor

init_options = py_vcon_server.processor.VconProcessorInitOptions()

py_vcon_server.processor.VconProcessorRegistry.register(
      init_options,
      "jinja_report",
      "py_vcon_server.processor.builtin.jinja_report",
      "JinjaReport"
      )
