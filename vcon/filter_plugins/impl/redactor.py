# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" FilterPlugin for redacting PII from VCon """
import typing
import pydantic
import vcon.filter_plugins


logger = vcon.build_logger(__name__)

class RedactorInitOptions(
  vcon.filter_plugins.FilterPluginInitOptions,
  title = "Redaction **FilterPlugin** intialization object"
  ):
  """
  A **RedactionInitOptions** object is provided to the
  **Redaction FilterPlugin.__init__** method when it is first loaded.  Its
  attributes effect how the registered **FilterPlugin** functions.
  """
  redaction_key: str = pydantic.Field(
    title = "**Redaction** API key",
    description = """
The **redaction_key** is a sample key needed to use this **FilterPlugin**.
""",
    example = "123456789e96a1da774e57abcdefghijklmnop",
    default = ""
    )


class RedactorOptions(
  vcon.filter_plugins.TranscribeOptions,
  title = "Redaction filter method options"
  ):
  """
  Options for redacting PII data in the recording **dialog** objects.  
  The resulting transcription(s) are added as transcript **analysis** 
  objects in this **Vcon**
  """


class Redactor(vcon.filter_plugins.FilterPlugin):
  """
  **FilterPlugin** to for transcription using **Deepgram** 
  """
  init_options_type = RedactorInitOptions

  def __init__(
    self,
    init_options: RedactorInitOptions
    ):
    """
    Parameters:
      init_options (RedactorInitOptions) - the initialization options for the **Deepgram** transcription plugin
    """
    super().__init__(
      init_options,
      RedactorOptions
      )


  def request_redaction(
    self,
    recording_data: typing.Dict[str, typing.Any]
    ) -> typing.Dict[str, typing.Any]:
    """ synchronous post of deepgram transcrtion request """

    return("redaction_done")


  async def filter(
    self,
    in_vcon: vcon.Vcon,
    options: RedactorOptions
    ) -> vcon.Vcon:
    """
    Redact the recording dialog objects.

    Parameters:
      options (RedactionOptions)

    Returns:
      the modified Vcon with added redacted analysis objects for the recording dialogs.
    """
    out_vcon = in_vcon

    if(in_vcon.dialog is None):
      return(out_vcon)

    dialog_indices = self.slice_indices(
      options.input_dialogs,
      len(in_vcon.dialog),
      "RedactorOptions.input_dialogs"
      )

    # no dialogs
    if(len(dialog_indices) == 0):
      return(out_vcon)

    for dialog_index in dialog_indices:
      dialog = in_vcon.dialog[dialog_index]
      if(dialog["type"] == "recording"):
        transcript_index = in_vcon.find_transcript_for_dialog(
          dialog_index,
          True,
          [
            ("deepgram", "transcription", "deepgram_prerecorded")
          ]
          )

        # We have not already transcribed this dialog
        if(transcript_index is None):
          print("recording is not transcribed")

    return(out_vcon)

