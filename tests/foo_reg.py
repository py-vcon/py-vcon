""" Registration for bad implementations of FilterPlugin Foo """

import typing
import vcon.filter_plugins

init_options: typing.Dict[str, typing.Any] = {}

vcon.filter_plugins.FilterPluginRegistry.register(
  "foop",
  "tests.foo",
  "Foo",
  "Does foo",
  init_options
  )


vcon.filter_plugins.FilterPluginRegistry.register(
  "foonoinittype",
  "tests.foo",
  "FooNoInit",
  "Does foo",
  init_options
  )
#print(vcon.filter_plugins.FilterPluginRegistry.get_names())

