# Copyright (C) 2024 SIPez LLC.  All rights reserved.
""" Redaction filter plugin registration """
import os
import vcon.filter_plugins

logger = vcon.build_logger(__name__)

init_options = {"redaction_key": "12345"}

vcon.filter_plugins.FilterPluginRegistry.register(
  "redactor",
  "vcon.filter_plugins.impl.redactor",
  "redactor",
  "Redactor",
  init_options
  )
