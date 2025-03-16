# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" Whisper transcriptiont FilterPlugin implentation """
import os
import sys
import typing
import tempfile
import contextlib
import pydantic
import vcon
import vcon.filter_plugins

logger = vcon.build_logger(__name__)

try:
  import stable_whisper
except Exception as e:
  #patch_url = "https://raw.githubusercontent.com/jianfch/stable-ts/main/stable_whisper.py"
  #print("Please download and install stable_whipser from: {}".format(patch_url))
  logger.info("please install stable_whisper:  \"pip3 install stable-ts\"")
  raise e


class WhisperInitOptions(vcon.filter_plugins.FilterPluginInitOptions, title = "Whisper **FilterPlugin** intialization object"):
  """
  A **WhisperInitOptions** object is provided to the
  **Whisper FilterPlugin.__init__** method when it is first loaded.  Its
  attributes effect how the registered **FilterPlugin** functions.
  """
  model_size: str = pydantic.Field(
    title = "**Whisper** model size name",
    description = """
Model size name to use for transcription", (e.g. "tiny", "base") as defined on
https://github.com/openai/whisper#available-models-and-languages
""",
    default = "base",
    examples = [ "tiny", "base" ]
    )


class WhisperOptions(vcon.filter_plugins.TranscribeOptions):
  """
  Options for transcribing the one or all dialogs in a **Vcon** using the **OpenAI Whisper** implementation.
  """
  output_types: typing.List[str] = pydantic.Field(
    title = "transcription output types",
    description = """
List of output types to generate.  Current set of value supported are:

  * "vendor" - add the Whisper specific JSON format transcript as an analysis object
  * "word_srt" - add a .srt file with timing on a word or small phrase basis as an analysis object
  * "word_ass" - add a .ass file with sentence and highlighted word timeing as an analysis object
       Not specifing "output_type" assumes all of the above will be output, each as a separate analysis object.
""",
    default = ["vendor", "word_srt", "word_ass"]
    )


class Whisper(vcon.filter_plugins.FilterPlugin):
  """
  **FilterPlugin** to generate transcriptions for a **Vcon**
  """
  init_options_type = WhisperInitOptions
  supported_options = [ "language" ]
  _supported_media = [
    vcon.Vcon.MEDIATYPE_AUDIO_WAV,
    vcon.Vcon.MEDIATYPE_AUDIO_MP3,
    vcon.Vcon.MEDIATYPE_AUDIO_MP4,
    vcon.Vcon.MEDIATYPE_VIDEO_MP4
    ]

  def __init__(
    self,
    init_options: WhisperInitOptions
    ):
    """
    Parameters:
      init_options (WhisperInitOptions) - the initialization options for the Whisper trascription plugin
    """
    super().__init__(
      init_options,
      WhisperOptions
      )
    # make model size configurable
    self.whisper_model_size = init_options.model_size
    logger.info("Initializing whisper model size: {}".format(self.whisper_model_size))
    self.whisper_model = stable_whisper.load_model(self.whisper_model_size)
    #stable_whisper.modify_model(self.whisper_model)

  async def filter(
    self,
    in_vcon: vcon.Vcon,
    options: WhisperOptions
    ) -> vcon.Vcon:
    """
    Transcribe recording dialogs in given Vcon using the Whisper implementation
`
    Parameters:
      options (WhisperOptions)

      options.output_types List[str] - list of output types to generate.  Current set
      of value supported are:

       * "vendor" - add the Whisper specific JSON format transcript as an analysis object
       * "word_srt" - add a .srt file with timing on a word or small phrase basis as an analysis object
       * "word_ass" - add a .ass file with sentence and highlighted word timeing as an analysis object

      Not specifing "output_type" assumes all of the above will be output, each as a separate analysis object.

    Returns:
      the modified Vcon with added analysis objects for the transcription.
    """
    out_vcon = in_vcon
    output_types = options.output_types
    if(output_types is None or len(output_types) == 0):
      output_types = ["vendor", "word_srt", "word_ass"]
    logger.info("whisper output_types: {}".format(output_types))

    if(in_vcon.dialog is None):
      return(out_vcon)

    dialog_indices = self.slice_indices(
      options.input_dialogs,
      len(in_vcon.dialog),
      "WhisperOptions.input_dialogs"
      )

    for dialog_index in dialog_indices:
      dialog = in_vcon.dialog[dialog_index]
      #print("dialog keys: {}".format(dialog.keys()))
      if(dialog["type"] == "recording"):
        # we have not already created a whisper transcript
        wwt_index = in_vcon.find_transcript_for_dialog(
          dialog_index,
          True,
          [
            ("whisper", "", "whisper_word_timestamps"), # old mislabeled
            ("openai", "whisper", "whisper_word_timestamps")
          ]
          )
        wws_index = in_vcon.find_transcript_for_dialog(
          dialog_index,
          True,
          [
            ("whisper", "", "whisper_word_srt"), # old mislabeled
            ("openai", "whisper", "whisper_word_srt")
          ]
          )
        wwa_index = in_vcon.find_transcript_for_dialog(
          dialog_index,
          True,
          [
            ("whisper", "", "whisper_word_ass"), # old mislabeled
            ("openai", "whisper", "whisper_word_ass")
          ]
          )
        media_type = dialog["mediatype"]
        logger.debug("found: wtt: {} wws: {} wwa: {}".format(wwt_index, wws_index, wwa_index))
        # if requesting transcript type that does not exist already
        if(((wwt_index is None and "vendor" in output_types) or
          (wws_index is None and "word_srt" in output_types) or
          (wwa_index is None and "word_ass" in output_types)) and
          media_type in self._supported_media
          ):

          body_bytes = await in_vcon.get_dialog_body(dialog_index)
          if(body_bytes is not None and len(body_bytes)):
            with tempfile.TemporaryDirectory() as temp_dir:
              transcript = None
              suffix = vcon.Vcon.get_media_extension(media_type)
              with tempfile.NamedTemporaryFile(prefix= temp_dir + os.sep, suffix = suffix) as temp_audio_file:
                temp_audio_file.write(body_bytes)
                #rate, samples = scipy.io.wavfile.read(body_io)
                # ts_num=7 is num of timestamps to get, so 7 is more than the default of 5
                # stab=True  is disable stabilization so you can do it later with different settings
                #transcript = self.whisper_model.transcribe(samples, ts_num=7, stab=False)

                # whisper has some print statements that we want to go to stderr

                model = self.whisper_model

                with contextlib.redirect_stdout(sys.stderr):

                  # loading a different model is expensive.  Its better to register
                  # multiple instance of whisper plugin with different names and models.
                  if(hasattr(options, "model_size")):
                    logger.warning(
                      "Ignoring whisper options attribute: model_size: {}, model size must be set in whipser initialization.  Using model size: {}".format(

                      options.model_size,
                      self.whisper_model_size
                      ))

                  whisper_options = {}
                  for field_value in options:
                    key = field_value[0]
                    if(key in self.supported_options):
                      whisper_options[key] = field_value[1]
                  logger.debug("providing whisper options: {}".format(whisper_options))

                  transcript = model.transcribe(temp_audio_file.name, **whisper_options)
                  logger.debug("whisper transcript type: {}".format(type(transcript)))
                  # Newer version of whisper returns object instead of dict
                  if(not isinstance(transcript, dict)):
                    transcript = transcript.to_dict()
                  # dict_keys(['text', 'segments', 'language'])
              # aggressive allows more variation
              #stabilized_segments = stable_whisper.stabilize_timestamps(transcript["segments"], aggressive=True)
              #transcript["segments"] = stabilized_segments
              # stable_segments = stable_whisper.stabilize_timestamps(transcript, top_focus=True)
              # transcript["stable_segments"] = stable_segments

              # need to add transcription to dialog.analysis
              # if time stamp transcript does not already exist and requested
              analysis_extras = {
                "product": "whisper"
              }
              if(wwt_index is None and "vendor" in output_types):
                out_vcon.add_analysis_transcript(
                  dialog_index,
                  transcript,
                  "openai",
                  "whisper_word_timestamps",
                  **analysis_extras
                  )

              # if srt does not already exist and requested
              if(wws_index is None and "word_srt" in output_types):
                with tempfile.NamedTemporaryFile(prefix= temp_dir + os.sep, suffix=".srt") as temp_srt_file:
                  # stable_whisper has some print statements that we want to go to stderr
                  with contextlib.redirect_stdout(sys.stderr):
                    # Function name changed in version 2.X
                    if(int(stable_whisper.__version__.split('.')[0]) >= 2):
                      func = stable_whisper.result_to_srt_vtt
                    else:
                      func = stable_whisper.results_to_word_srt
                    logger.debug("starting srt")
                    func(transcript, temp_srt_file.name)
                  srt_bytes = temp_srt_file.read()
                  # TODO: should body be json.loads'd
                  out_vcon.add_analysis_transcript(
                    dialog_index,
                    srt_bytes.decode("utf-8"),
                    "openai",
                    "whisper_word_srt",
                    encoding = "none",
                    **analysis_extras
                    )

              # if ass does not already exist and requested
              if(wwa_index is None and "word_ass" in output_types):
                # Getting junk on stdout from stable_whisper.  Redirect it.
                with contextlib.redirect_stdout(sys.stderr):
                  with tempfile.NamedTemporaryFile(prefix= temp_dir + os.sep, suffix=".ass") as temp_ass_file:
                    if(int(stable_whisper.__version__.split('.')[0]) >= 2):
                      func = stable_whisper.result_to_ass
                    else:
                      func = stable_whisper.results_to_sentence_word_ass
                    logger.debug("starting ass")
                    func(transcript, temp_ass_file.name)
                    ass_bytes = temp_ass_file.read()
                    # TODO: should body be json.loads'd
                    out_vcon.add_analysis_transcript(
                      dialog_index,
                      ass_bytes.decode("utf-8"),
                      "openai",
                      "whisper_word_ass",
                      encoding = "none",
                      **analysis_extras
                      )
              logger.debug("done with whisper transcription")

          else:
            pass # ignore??

        else:
          logger.warning("unsupported media type: {} in dialog[{}], skipped whisper transcription".format(dialog["mediatype"], dialog_index))

    return(out_vcon)

