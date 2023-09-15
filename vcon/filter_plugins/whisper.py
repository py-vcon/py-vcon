""" Whisper audio transcription filter plugin registration """
import vcon.filter_plugins
import vcon.accessors

# Register the whisper filter plugin
init_options = {"model_size": "base"}

vcon.filter_plugins.FilterPluginRegistry.register(
  "whisper",
  "vcon.filter_plugins.impl.whisper",
  "Whisper",
  "OpenAI Whisper implemented transcription of audio dialog recordings using model size: \"base\"",
  init_options
  )

# Make this the default transcribe type filter plugin
vcon.filter_plugins.FilterPluginRegistry.set_type_default_name("transcribe", "whisper")

# Implement an accessor for the Whisper transcription format
class WhisperTranscriptAccessor(vcon.accessors.TranscriptAccessor):
  def get_text(self):
    """
    Get speaker, text and time stamps for Whisper transcript.

    Currently diarization is not supported for Whisper so there
    is only one text chunk, not a chunk per speaker and spoken
    segment.
    """
    if(self._analysis_dict["type"].lower() == "transcript" and
      self._analysis_dict["vendor"].lower() == "whisper" and
      self._analysis_dict["schema"].lower() == "whisper_word_timestamps"
      ):

      # TODO: need to get diarization working on Whisper
      text_dict = {}
      text_dict["party"] = self._dialog_dict["parties"]
      text_dict["text"] = self._analysis_dict["body"]["text"]
      text_dict["start"] = self._analysis_dict["body"]["dddd"]
      text_dict["duration"] = self._analysis_dict["body"]["dddd"]

      return([text_dict])

    return([])


# Register an accessor for the Whisper transcription format
# legacy for upward compatibility:
vcon.accessors.transcript_accessors[("whisper", "", "whisper_word_timestamps")] = WhisperTranscriptAccessor
# correct labeling
vcon.accessors.transcript_accessors[("openai", "whisper", "whisper_word_timestamps")] = WhisperTranscriptAccessor

