# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" Deepgram audio transcription filter plugin registration """
import os
import datetime
import vcon.filter_plugins
import vcon.accessors

deepgram_key = os.getenv("DEEPGRAM_KEY", "")
# Register the Deepgram filter plugin
init_options = {"deepgram_key": deepgram_key}

vcon.filter_plugins.FilterPluginRegistry.register(
  "deepgram",
  "vcon.filter_plugins.impl.deepgram",
  "Deepgram",
  "Deepgram RESTful service implemented transcription of audio dialog recordings",
  init_options
  )

# Implement an accessor for the Deepgram transcription format
class DeepgramTranscriptAccessor(vcon.accessors.TranscriptAccessor):
  def get_text(self):
    """
    Get speaker, text and time stamps for Whisper transcript.

    Currently diarization is not supported for Whisper so there
    is only one text chunk, not a chunk per speaker and spoken
    segment.
    """
    if(self._analysis_dict["type"].lower() == "transcript" and
      (self._analysis_dict["vendor"].lower() == "deepgram" and
        self._analysis_dict["product"].lower() == "transcription" and
        self._analysis_dict["schema"].lower() == "deepgram_prerecorded")
      ):

      text_list = []
      dialog_start = datetime.datetime.fromisoformat(vcon.utils.cannonize_date(self._dialog_dict["start"]))
      # get diarization if provided
      if(self._analysis_dict["body"]["results"]["channels"][0]["alternatives"][0].get("paragraphs", None) is not None):
        for paragraph in self._analysis_dict["body"]["results"]["channels"][0]["alternatives"][0]["paragraphs"]["paragraphs"]:
          text_dict = {}
          text_dict["parties"] = paragraph["speaker"]
          relative_start = paragraph["start"]
          text_dict["start"] = (dialog_start + datetime.timedelta(0, relative_start)).isoformat()
          relative_end = paragraph["end"]
          text_dict["duration"] = relative_end - relative_start
          sentence_list = [d["text"] for d in paragraph["sentences"]]
          text_dict["text"] = "  ".join(sentence_list)
          text_list.append(text_dict)

      else:
        text_dict["parties"] = self._dialog_dict["parties"]
        text_dict["text"] = self._analysis_dict["body"]["results"]["channels"][0]["alteratives"]["transcript"]
        relative_start = self._analysis_dict["body"]["channels"][0]["alteratives"]["words"][0]["start"]
        text_dict["start"] = (dialog_start + datetime.timedelta(0, relative_start)).isoformat()
        relative_end = self._analysis_dict["body"]["channels"][0]["alternatives"]["words"][-1]["end"]
        text_dict["duration"] = relative_end - relative_start
        text_list.append(text_dict)

      return(text_list)

    return([])


# Register an accessor for the Deepgram transcription format
vcon.accessors.transcript_accessors[("deepgram", "transcription", "deepgram_prerecorded")] = DeepgramTranscriptAccessor

