import vcon.filter_plugins

class RedactInitOptions(vcon.filter_plugins.FilterPluginInitOptions):
  pass


class RedactOptions(vcon.filter_plugins.FilterPluginOptions):
  pass


class Redact(vcon.filter_plugins.FilterPlugin):
  """ Invalid class: did not implement filter """
  init_options_type = RedactInitOptions

  def __init__(self, options):
    super().__init__(
      options,
      RedactOptions)
    print("Redact plugin created with options: {}".format(options))

