""" VconProcessor binding for the Vcon Whisper filter_plugin """

import typing
import asyncio
import pydantic
import py_vcon_server.processor

__version__ = "0.0.1"

class WhisperInitOptions(py_vcon_server.processor.VconProcessorInitOptions):
  model_size: typing.Optional[str] = pydantic.Field(
    title = "Whisper model size to use",
    #description = "vCon format version,
    default = "base",
    examples = ["tiny", "base"]
    )
  

class WhisperOptions(py_vcon_server.processor.VconProcessorOptions):
  pass
  # TODO: add options for sepcifying which dialogs to transcribe
  # TODO: add options for specifying which types of transcription output are desired


class Whisper(py_vcon_server.processor.VconProcessor):
  """ Whisper OpenAI transcription binding for **VconProcessor** """
  def __init__(
    self,
    init_options: WhisperInitOptions
    ):
    super().__init__(
      "transcribe Vcon dialogs using Vcon Whisper filter_plugin",
      None,
      __version__,
      init_options,
      WhisperOptions,
      True # modifies a Vcon
      )

    #TODO: register different Vcon filter_plugin for each model size

  async def process(self,
    processor_input: py_vcon_server.processor.VconProcessorIO,
    options: WhisperOptions
    ) -> py_vcon_server.processor.VconProcessorIO:

    # TODO: check for options on which dialogs to transcribe
    # e.g.:
    # options = {"llanguage" : "en", "model_size" : "base", "output_options" : ["vendor", "word_srt", "word_ass"], "whisper" : { "language" : "en"} }
    #  if(options.tel is not None and
    #    options.tel != ""):
    vcon_whisper_options = {}

    index = options.input_vcon_index
    in_vcon = await processor_input.get_vcon(index)

    out_vcon = in_vcon.whisper(vcon_whisper_options)

    await processor_input.update_vcon(out_vcon)

    return(processor_input)

