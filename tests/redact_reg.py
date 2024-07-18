""" Registration for bad implementations of FilterPlugin Redact """

import typing
import vcon.filter_plugins

init_options: typing.Dict[str, typing.Any] = {}

vcon.filter_plugins.FilterPluginRegistry.register(
  "redact",
  "tests.redact",
  "Redact",
  "Does redaction",
  init_options
  )

#print(vcon.filter_plugins.FilterPluginRegistry.get_names())

