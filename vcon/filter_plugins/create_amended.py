# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" create amended filter_plugin registration """
import os
import datetime
import vcon.filter_plugins

# Register the AmendedFilterPlugin for creating amendable copies
init_options = {}

vcon.filter_plugins.FilterPluginRegistry.register(
  "create_amended",
  "vcon.filter_plugins.impl.create_amended",
  "AmendedFilterPlugin",
  "create appendable copy of vCon",
  init_options
  )

