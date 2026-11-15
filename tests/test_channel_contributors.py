# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" Unit tests for the contributors of recording channels over time """

import pytest
import vcon
import vcon.accessors
import vcon.filter_plugins.deepgram


START = "2022-06-21T17:53:26.000+00:00"


def at(seconds : float) -> str:
  """ RFC3339 time the given seconds after START """
  return("2022-06-21T17:53:{:06.3f}+00:00".format(26 + seconds))


def make_vcon(parties) -> vcon.Vcon:
  """ four parties, a text Dialog and a recording Dialog (index 1) with the given parties """
  v = vcon.Vcon()
  v.set_uuid("example.com")
  for number in range(4):
    v.set_party_parameter("tel", "+1555000000{}".format(number))
  v.add_text_dialog_inline("Hello", START, 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  dialog_index = v.add_recording_dialog_inline(b"\x00\x01", START, 30, 0, "audio/x-wav", "a.wav")
  v._vcon_dict["dialog"][dialog_index]["parties"] = parties
  return(v)


def test_no_events_multichannel():
  v = make_vcon([0, [1, 2], None])
  assert(v.get_channel_contributors(1, 0, 3, START) == 0)
  assert(v.get_channel_contributors(1, 1, 3, at(5), 10) == [1, 2])
  assert(v.get_channel_contributors(1, 2, 3, at(5)) is None)
  # no element for the channel
  v = make_vcon([0])
  assert(v.get_channel_contributors(1, 1, 2, START) is None)


@pytest.mark.parametrize("parties", [[0, 1], 0, [0, [1, 2]]])
def test_no_events_single_channel(parties):
  v = make_vcon(parties)
  assert(v.get_channel_contributors(1, 0, 1, START) == parties)
  assert(v.get_channel_contributors(1, 0, 1, at(5), 20) == parties)


def test_one_event():
  v = make_vcon([0, 1])
  v.add_channel_contributors_event(at(10), 1, 1, 2)
  # before, at and after the Event
  assert(v.get_channel_contributors(1, 1, 2, at(5)) == 1)
  assert(v.get_channel_contributors(1, 1, 2, at(5), 4) == 1)
  assert(v.get_channel_contributors(1, 1, 2, at(10)) == 2)
  assert(v.get_channel_contributors(1, 1, 2, at(15), 5) == 2)
  # a span across the Event: both
  assert(v.get_channel_contributors(1, 1, 2, at(5), 10) == [1, 2])
  # a span ending at the Event: the old party only
  assert(v.get_channel_contributors(1, 1, 2, at(5), 5) == 1)
  # epoch and datetime start
  start = vcon.utils.date_to_datetime(at(12))
  assert(v.get_channel_contributors(1, 1, 2, start) == 2)
  assert(v.get_channel_contributors(1, 1, 2, start.timestamp()) == 2)
  # the other channel is unchanged
  assert(v.get_channel_contributors(1, 0, 2, at(15)) == 0)


def test_events_in_any_order():
  v = make_vcon([0, 1])
  v.add_channel_contributors_event(at(20), 1, 1, [2, 3])
  v.add_channel_contributors_event(at(10), 1, 1, 2)
  assert(v.get_channel_contributors(1, 1, 2, at(15)) == 2)
  assert(v.get_channel_contributors(1, 1, 2, at(25)) == [2, 3])
  assert(v.get_channel_contributors(1, 1, 2, at(5), 20) == [1, 2, 3])


def test_event_without_contributors():
  v = make_vcon([0, 1])
  # null contributors written directly, absent contributors from the method
  v.add_channel_contributors_event(at(10), 1, 1, 2)
  v._vcon_dict["events"][-1]["contributors"] = None
  v.add_channel_contributors_event(at(20), 1, 0)
  assert(v.get_channel_contributors(1, 1, 2, at(15)) is None)
  assert(v.get_channel_contributors(1, 0, 2, at(25)) is None)
  # a span from nobody to someone
  v.add_channel_contributors_event(at(30), 1, 0, 3)
  assert(v.get_channel_contributors(1, 0, 2, at(25), 10) == 3)
  # a span from someone to nobody
  assert(v.get_channel_contributors(1, 0, 2, at(15), 10) == 0)
  # a single channel recording: the whole parties value until the Event
  v = make_vcon([0, 1])
  v.add_channel_contributors_event(at(10), 1, 0)
  assert(v.get_channel_contributors(1, 0, 1, at(5)) == [0, 1])
  assert(v.get_channel_contributors(1, 0, 1, at(15)) is None)


def test_other_channel_or_dialog_events():
  v = make_vcon([0, 1])
  v.add_channel_contributors_event(at(10), 1, 0, 3)
  dialog_index = v.add_recording_dialog_inline(b"\x00\x01", START, 30, [2, 3], "audio/x-wav", "b.wav")
  v.add_channel_contributors_event(at(10), dialog_index, 1, 0)
  assert(v.get_channel_contributors(1, 1, 2, at(15)) == 1)
  assert(v.get_channel_contributors(dialog_index, 0, 2, at(15)) == 2)


@pytest.mark.parametrize("dialog_index, channel, num_channels, duration", [
  (0, 0, 1, None),   # text Dialog
  (2, 0, 1, None),   # past the end
  (-1, 0, 1, None),
  (1, 2, 2, None),   # channel past num_channels
  (1, -1, 2, None),
  (1, 0, 0, None),   # no channels
  (1, 0, 2, -1)      # negative duration
  ])
def test_errors(dialog_index, channel, num_channels, duration):
  v = make_vcon([0, 1])
  with pytest.raises(AttributeError):
    v.get_channel_contributors(dialog_index, channel, num_channels, START, duration)


def test_empty_dialog_raises():
  v = make_vcon([0, 1])
  v.clear_dialog(1)
  with pytest.raises(AttributeError):
    v.get_channel_contributors(1, 0, 1, START)


def deepgram_channel(sentences):
  """ a Deepgram channel with one paragraph of the given (text, start) sentences """
  return({"alternatives": [{
      "transcript": " ".join([text for text, start in sentences]),
      "words": [{"word": "x", "start": sentences[0][1], "end": sentences[-1][1] + 1.0}],
      "paragraphs": {"paragraphs": [{"speaker": 0, "start": sentences[0][1], "end": sentences[-1][1] + 1.0,
        "sentences": [{"text": text, "start": start, "end": start + 1.0} for text, start in sentences]}]}
    }]})


def add_deepgram_transcript(v : vcon.Vcon, dialog_index : int, channels : list) -> None:
  v._vcon_dict["analysis"].append({
    "type": "transcript", "dialog": dialog_index, "vendor": "deepgram", "product": "transcription",
    "schema": "deepgram_prerecorded", "encoding": "json",
    "body": {"results": {"channels": channels}}
    })


@pytest.mark.asyncio
async def test_deepgram_two_channels():
  v = make_vcon([0, 1])
  add_deepgram_transcript(v, 1, [
    deepgram_channel([("first", 1.0), ("second", 20.0)]),
    deepgram_channel([("reply", 5.0)])
    ])

  # no Events: each channel's parties element, as before
  texts = await v.get_dialog_text(1, True, False)
  assert([(text["text"], text["parties"]) for text in texts] == [("first", 0), ("second", 0), ("reply", 1)])

  # channel 0 is handed to party 2 at 10 seconds
  v.add_channel_contributors_event(at(10), 1, 0, 2)
  texts = await v.get_dialog_text(1, True, False)
  assert([(text["text"], text["parties"]) for text in texts] == [("first", 0), ("second", 2), ("reply", 1)])

  # not diarized: the channel text spans the Event
  for channel in v._vcon_dict["analysis"][0]["body"]["results"]["channels"]:
    del channel["alternatives"][0]["paragraphs"]
  texts = await v.get_dialog_text(1, True, False)
  assert([text["parties"] for text in texts] == [[0, 2], 1])

  # no parties element for channel 1
  v._vcon_dict["dialog"][1]["parties"] = [0]
  texts = await v.get_dialog_text(1, True, False)
  assert([text["parties"] for text in texts] == [[0, 2], None])


def test_deepgram_accessor_default_contributors():
  """ built directly, the accessor uses the Dialog parties only """
  v = make_vcon([0, 1])
  add_deepgram_transcript(v, 1, [
    deepgram_channel([("first", 1.0), ("second", 20.0)]),
    deepgram_channel([("reply", 5.0)])
    ])
  v.add_channel_contributors_event(at(10), 1, 0, 2)
  accessor = vcon.filter_plugins.deepgram.DeepgramTranscriptAccessor(v.dialog[1], v.analysis[0])
  assert([text["parties"] for text in accessor.get_text()] == [0, 0, 1])
  assert(accessor.channel_contributors(1, 2, START) == 1)
  assert(accessor.channel_contributors(2, 3, START) is None)
  assert(accessor.channel_contributors(0, 1, START) == [0, 1])


class OldStyleAccessor(vcon.accessors.TranscriptAccessor):
  """ an accessor written before channel_contributors existed """
  def get_text(self):
    return([{"parties": self._dialog_dict["parties"], "text": self._analysis_dict["body"],
      "start": self._dialog_dict["start"], "duration": 1}])


class UnrelatedAccessor():
  """ an accessor not derived from TranscriptAccessor """
  def __init__(self, dialog_dict, analysis_dict):
    self._text = analysis_dict["body"]

  def get_text(self):
    return([{"parties": 0, "text": self._text, "start": START, "duration": 1}])


@pytest.mark.asyncio
@pytest.mark.parametrize("accessor_class", [OldStyleAccessor, UnrelatedAccessor])
async def test_old_style_accessor(accessor_class):
  key = ("test_vendor", "test_product", "test_schema")
  vcon.accessors.transcript_accessors[key] = accessor_class
  try:
    v = make_vcon([0, 1])
    v._vcon_dict["analysis"].append({"type": "transcript", "dialog": 1, "vendor": "test_vendor",
      "product": "test_product", "schema": "test_schema", "encoding": "none", "body": "old text"})
    texts = await v.get_dialog_text(1, True, False)
    assert(len(texts) == 1)
    assert(texts[0]["text"] == "old text")
  finally:
    del vcon.accessors.transcript_accessors[key]
