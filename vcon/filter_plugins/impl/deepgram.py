""" FilterPlugin for Deepgram transcription """
import typing
import json
import pydantic
import requests
import vcon.filter_plugins
import deepgram

logger = vcon.build_logger(__name__)


class DeepgramInitOptions(
  vcon.filter_plugins.FilterPluginInitOptions,
  title = "Deepgram transcription **FilterPlugin** intialization object"
  ):
  """
  A **DeepgramInitOptions** object is provided to the
  **Deepgram FilterPlugin.__init__** method when it is first loaded.  Its
  attributes effect how the registered **FilterPlugin** functions.
  """
  deepgram_key: str = pydantic.Field(
    title = "**Deepgram API key",
    description = """
The **deepgram_key** is used to access the Deepgram RESTful transcription service.
It is required to use this **FilterPlugin**.

You can get one at: https://console.deepgram.com/signup?jump=keys
""",
    example = "123456789e96a1da774e57abcdefghijklmnop",
    default = ""
    )


class DeepgramOptions(
  vcon.filter_plugins.TranscribeOptions,
  title = "Deepgram transcription filter method options"
  ):
  """
  Options for transcribing the recording **dialog** objects using
  Deepgram transcription service.  The resulting transcription(s)
  are added as transcript **analysis** objects in this **Vcon**

  More details on the OpenAI specific parameters can be found here:
  https://developers.deepgram.com/reference/pre-recorded
  """


class Deepgram(vcon.filter_plugins.FilterPlugin):
  """
  **FilterPlugin** to for transcription using **Deepgram** 
  """
  init_options_type = DeepgramInitOptions

  def __init__(
    self,
    init_options: DeepgramInitOptions
    ):
    """
    Parameters:
      init_options (DeepgramInitOptions) - the initialization options for the **Deepgram** transcription plugin
    """
    super().__init__(
      init_options,
      DeepgramOptions
      )

    if(init_options.deepgram_key is None or
      init_options.deepgram_key == ""):
      logger.warning("Deepgram plugin: key not set.  Plugin will be a no-op")
      self.deepgram_client = None

    else:
      self.deepgram_client = deepgram.Deepgram(init_options.deepgram_key)




  def request_transcribe(
    self,
    recording_data: typing.Dict[str, typing.Any],
    transcribe_options: typing.Dict[str, typing.Any]
    ) -> typing.Dict[str, typing.Any]:
    """ synchronous post of deepgram transcrtion request """
    url = "https://api.deepgram.com/v1/listen"
    headers = {
      "accept": "application/json",
      "content-type": recording_data["mimetype"],
      "Authorization": "Token " + self._init_options.deepgram_key
      }
    requests_options = {
      "timeout": 20
      }

    response = requests.post(
      url,
      params = transcribe_options,
      #json = recording_data,
      data = recording_data["buffer"],
      headers = headers,
      **requests_options
      )

    if(response.status_code >= 300):
      logger.warning("request to: {} with {} failed: {}: {}".format(
        url,
        transcribe_options,
        response.status_code,
        response.content
        ))
      raise Exception("request to Deepgram options: {} failed: {}".format(
        transcribe_options,
        response.status_code
        ))

    return(json.loads(response.content))


  def filter(
    self,
    in_vcon: vcon.Vcon,
    options: DeepgramOptions
    ) -> vcon.Vcon:
    """
    Transcribe the recording dialog objects using **Deepgram**.

    Parameters:
      options (DeepgramOptions)

    Returns:
      the modified Vcon with added transcript analysis objects for the recording dialogs.
    """
    out_vcon = in_vcon

    if(in_vcon.dialog is None):
      return(out_vcon)

    dialog_indices = self.slice_indices(
      options.input_dialogs,
      len(in_vcon.dialog),
      "DeepgramOptions.input_dialogs"
      )

    # no dialogs
    if(len(dialog_indices) == 0):
      return(out_vcon)

    if(self.deepgram_client is None):
      logger.warning("Deepgram.filter: deepgram_key is not set, no transcription performed")
      return(out_vcon)

    analysis_extras = {
      "product": "transcription"
      }

    # TODO add some of these to DeepgramOptions
    transcribe_options = {
      'language': 'en',
      'model': 'nova',
      'punctuate': 'true',
      'smart_format': 'true',
      'diarize': 'true'
      }

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
          recording_bytes = in_vcon.get_dialog_body(dialog_index)

          recording_data = {
            "buffer": recording_bytes,
            "mimetype": dialog["mimetype"]
            }

          transcript_dict = self.request_transcribe(
            recording_data,
            transcribe_options
            )

          # For now make synch.
          # transcript_dict = await self.deepgram_client.transcription.prerecorded(
          #   recording_data,
          #   transcribe_options
          #   )
          # logger.debug("deepgram return type: {} value: {}".format(type(transcript_dict), transcript_dict))
          out_vcon.add_analysis_transcript(
            dialog_index,
            transcript_dict,
            "deepgram",
            "deepgram_prerecorded",
            **analysis_extras
            )

    return(out_vcon)

