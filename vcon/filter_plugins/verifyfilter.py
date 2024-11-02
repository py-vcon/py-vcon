# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" JWS verification of vCon filter plugin registration """
import os
import datetime
import vcon.filter_plugins

# Register the verify filter plugin
init_options = {}

vcon.filter_plugins.FilterPluginRegistry.register(
  "verifyfilter",
  "vcon.filter_plugins.impl.verify_filter_plugin",
  "VerifyFilterPlugin",
  "verify JWS signed vCon",
  init_options
  )

