# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" JQ defined vCon Redaction plugin registration """
import typing
import vcon.filter_plugins

# Register plugin
registration_options: typing.Dict[str, typing.Any] = {}
vcon.filter_plugins.FilterPluginRegistry.register(
  "jq_redaction",
  "vcon.filter_plugins.impl.jq_redaction",
  "JqRedaction",
  "redacts a vCon using JQ defined query",
  registration_options
  )

