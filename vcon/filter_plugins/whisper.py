# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" Whisper audio transcription filter plugin registration """
import datetime
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
      ((self._analysis_dict["vendor"].lower() == "openai" and
        self._analysis_dict["product"].lower() == "whisper" and
        self._analysis_dict["schema"].lower() == "whisper_word_timestamps") or
      (self._analysis_dict["vendor"].lower() == "whisper" and # older, incorrect labeling
        self._analysis_dict["schema"].lower() == "whisper_word_timestamps")
      )):

      # TODO: need to get diarization working on Whisper
      text_dict = {}
      text_dict["parties"] = self._dialog_dict["parties"]
      text_dict["text"] = self._analysis_dict["body"]["text"]
      dialog_start = datetime.datetime.fromisoformat(vcon.utils.cannonize_date(self._dialog_dict["start"]))
      relative_start = self._analysis_dict["body"]["segments"][0]["start"]
      text_dict["start"] = (dialog_start + datetime.timedelta(0, relative_start)).isoformat()
      relative_end = self._analysis_dict["body"]["segments"][-1]["end"]
      text_dict["duration"] = relative_end - relative_start

      return([text_dict])

    return([])


# Register an accessor for the Whisper transcription format
# legacy for upward compatibility:
vcon.accessors.transcript_accessors[("whisper", "", "whisper_word_timestamps")] = WhisperTranscriptAccessor
# correct labeling
vcon.accessors.transcript_accessors[("openai", "whisper", "whisper_word_timestamps")] = WhisperTranscriptAccessor

