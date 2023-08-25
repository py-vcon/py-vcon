import vcon.filter_plugins

class FooInitOptions(vcon.filter_plugins.FilterPluginInitOptions):
  pass


class FooOptions(vcon.filter_plugins.FilterPluginOptions):
  pass


class Foo(vcon.filter_plugins.FilterPlugin):
  """ Invalid class: did not implement filter """
  init_options_type = FooInitOptions

  def __init__(self, options):
    super().__init__(
      options,
      FooOptions)
    print("foo plugin created with options: {}".format(options))


class FooNoInit(vcon.filter_plugins.FilterPlugin):
  """ Invalid class: did not implement filter and did not define init_options_type """
  def __init__(self, options):
    super().__init__(
      options,
      FooOptions)
    print("foo plugin created with options: {}".format(options))

