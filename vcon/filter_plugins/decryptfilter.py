# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" JWE decrypting of vCon filter plugin registration """
import os
import datetime
import vcon.filter_plugins

# Register the DecryptFilterPlugin for JWE decryption
init_options = {}

vcon.filter_plugins.FilterPluginRegistry.register(
  "decryptfilter",
  "vcon.filter_plugins.impl.decrypt_filter_plugin",
  "DecryptFilterPlugin",
  "encrypt vCon using JWE",
  init_options
  )

