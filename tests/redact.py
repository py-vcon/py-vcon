import vcon.filter_plugins
import pydantic

class RedactInitOptions(vcon.filter_plugins.FilterPluginInitOptions):
  redaction_key: str = pydantic.Field(
    title = "**Redaction** API key",
    description = "The **redaction_key** is a sample key needed to use this **FilterPlugin**.",
    example = "123456789e96a1da774e57abcdefghijklmnop",
    default = ""
    )


class RedactOptions(vcon.filter_plugins.FilterPluginOptions):
  """
  Options for redacting PII data in the recording **dialog** objects.  
  The resulting transcription(s) are added as transcript **analysis** 
  objects in this **Vcon**
  """


class Redact(vcon.filter_plugins.FilterPlugin):
  """ Invalid class: did not implement filter """
  init_options_type = RedactInitOptions

  def __init__(self, options):
    super().__init__(
      options,
      RedactOptions)
    print("Redact plugin created with options: {}".format(options))

  async def filter(
    self,
    in_vcon: vcon.Vcon,
    options: RedactOptions
    ) -> vcon.Vcon:
    out_vcon = in_vcon
    return(out_vcon)