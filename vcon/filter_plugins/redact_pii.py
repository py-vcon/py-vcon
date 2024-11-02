# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" Redact PII plugin registration """
import typing
import vcon.filter_plugins

# Register plugin
registration_options: typing.Dict[str, typing.Any] = {}
vcon.filter_plugins.FilterPluginRegistry.register(
  "redact_pii",
  "vcon.filter_plugins.impl.redact_pii",
  "RedactPii",
  "Adds analysis object to vcon with PII labels and redacted dialog",
  registration_options
  )

