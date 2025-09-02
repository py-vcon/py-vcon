# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" create appended filter_plugin registration """
import os
import datetime
import vcon.filter_plugins

# Register the AppendedFilterPlugin for creating appendable copies
init_options = {}

vcon.filter_plugins.FilterPluginRegistry.register(
  "create_appended",
  "vcon.filter_plugins.impl.create_appended",
  "AppendedFilterPlugin",
  "create appendable copy of vCOn",
  init_options
  )

