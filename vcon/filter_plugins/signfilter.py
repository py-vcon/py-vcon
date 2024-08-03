# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" JWS signing of vCon filter plugin registration """
import os
import datetime
import vcon.filter_plugins

# Register the Sign ilter plugin
init_options = {}

vcon.filter_plugins.FilterPluginRegistry.register(
  "signfilter",
  "vcon.filter_plugins.impl.SignFilterPlugin",
  "SignFilterPlugin",
  "sign vCon using JWS",
  init_options
  )

