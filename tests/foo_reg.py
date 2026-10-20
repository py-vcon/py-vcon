# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
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


# Add to tests/foo_reg.py after the existing registrations:
vcon.filter_plugins.FilterPluginRegistry.register(
  "badclass",
  "tests.foo",           # module exists
  "NoSuchClass",         # class does not exist
  "bad class name test",
  {}
  )


