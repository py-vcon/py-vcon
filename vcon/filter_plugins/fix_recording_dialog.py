# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" Fix Recording Dialog plugin registration """
import typing
import vcon.filter_plugins

# Register plugin
registration_options: typing.Dict[str, typing.Any] = {}
vcon.filter_plugins.FilterPluginRegistry.register(
  "fix_recording_dialog",
  "vcon.filter_plugins.impl.fix_recording_dialog",
  "FixRecordingDialog",
  "Fix dialog info post record (duration and content_hash)",
  registration_options
  )

