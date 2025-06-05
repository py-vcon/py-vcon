""" Registration for the example addon **filter_plugin** """
import vcon.filter_plugins

# Register my filter plugin
vcon.filter_plugins.FilterPluginRegistry.register(
    "my_filter", # name to register and refer to and implied method name
    "vcon.filter_plugins_addons.my_filter_impl.my_filter", # module implementation to load
    "MyFilter", # filter_plugin class in above module
    "add party or set parameters", # short description
    {} # default initialization options
  )

