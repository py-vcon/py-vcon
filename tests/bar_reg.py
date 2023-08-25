import vcon.filter_plugins

init_options = vcon.filter_plugins.FilterPluginInitOptions()
vcon.filter_plugins.FilterPluginRegistry.register(
  "barp",
  "tests.bar",
  "Foo",
  "Does bar",
  init_options
  )


#print(vcon.filter_plugins.FilterPluginRegistry.get_names())

