# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" JWE encrypting of vCon filter plugin registration """
import os
import datetime
import vcon.filter_plugins

# Register the EncryptFilterPlugin for JWE encrypting
init_options = {}

vcon.filter_plugins.FilterPluginRegistry.register(
  "encryptfilter",
  "vcon.filter_plugins.impl.encrypt_filter_plugin",
  "EncryptFilterPlugin",
  "encrypt vCon using JWE",
  init_options
  )

