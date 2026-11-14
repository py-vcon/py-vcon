# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" Unit tests for Dialog Object redacted_segments """

import pytest
import vcon
import vcon.parameter_registry
import tests.common_utils

START = "2022-06-21T13:53:26-04:00"
START_UTC = "2022-06-21T17:53:26.000+00:00"


def make_vcon(parties = [0, 1]) -> vcon.Vcon:
  """ two parties, a text Dialog (0), a recording Dialog (1) with the given parties """
  v = vcon.Vcon()
  v.set_uuid("example.com")
  v.set_party_parameter("tel", "+15551110000")
  v.set_party_parameter("tel", "+15552220000")
  v.add_dialog_inline_text("Hello", START, 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.add_dialog_inline_recording(b"\x00\x01", START, 30, 0, "audio/x-wav", "a.wav")
  v._vcon_dict["dialog"][1]["parties"] = parties
  return(v)


def test_add_segments():
  v = make_vcon()
  assert(v.add_dialog_redacted_segment(1, "2022-06-21T13:53:30-04:00", 2.5) == 0)
  assert(v.dialog[1]["redacted_segments"] == [
    {"start": "2022-06-21T17:53:30.000+00:00", "end": "2022-06-21T17:53:32.500+00:00"}])
  tests.common_utils.assert_valid_vcon(v.dumpd())

  assert(v.add_dialog_redacted_segment(1, "2022-06-21T13:53:40-04:00", 1, parties = [1]) == 1)
  assert([segment["start"] for segment in v.dialog[1]["redacted_segments"]] ==
    ["2022-06-21T17:53:30.000+00:00", "2022-06-21T17:53:40.000+00:00"])
  # parties only when given
  assert("parties" not in v.dialog[1]["redacted_segments"][0])
  assert(v.dialog[1]["redacted_segments"][1]["parties"] == [1])
  tests.common_utils.assert_valid_vcon(v.dumpd())


def test_channel():
  v = make_vcon()
  v.add_dialog_redacted_segment(1, START, 1)
  v.add_dialog_redacted_segment(1, START, 1, channel = 1)
  assert("channel" not in v.dialog[1]["redacted_segments"][0])
  assert(v.dialog[1]["redacted_segments"][1]["channel"] == 1)
  tests.common_utils.assert_valid_vcon(v.dumpd())

  rows = [row for row in vcon.parameter_registry.get_rows("Redacted_segments") if(row["name"] == "channel")]
  assert(len(rows) == 1)
  assert(rows[0]["iana"] is False and rows[0]["legacy"] is False)
  assert("proposed" in rows[0]["description"])


@pytest.mark.parametrize("label, parties, last_ok, first_bad", [
    ("int: one channel", 0, 0, 1),
    ("list with a list", [0, [0, 1]], 1, 2),
    ("list with a null", [0, None], 1, 2),
    ("flat list: number unknown", [0, 1], 99, None)
  ])
def test_channel_range(label, parties, last_ok, first_bad):
  v = make_vcon(parties)
  v.add_dialog_redacted_segment(1, START, 1, channel = last_ok)
  if(first_bad is not None):
    with pytest.raises(AttributeError, match = "is not in dialog"):
      v.add_dialog_redacted_segment(1, START, 1, channel = first_bad)
  with pytest.raises(AttributeError, match = "non-negative"):
    v.add_dialog_redacted_segment(1, START, 1, channel = -1)
  assert(len(v.dialog[1]["redacted_segments"]) == 1), label


@pytest.mark.parametrize("label, prepare, call, message", [
    ("text Dialog", None, lambda v: v.add_dialog_redacted_segment(0, START, 1), "is not a recording"),
    ("incomplete Dialog", lambda v: v._vcon_dict["dialog"].append({"type": "incomplete", "disposition": "busy"}),
      lambda v: v.add_dialog_redacted_segment(2, START, 1), "its type is: incomplete"),
    ("empty Dialog", lambda v: v._vcon_dict["dialog"].append({}),
      lambda v: v.add_dialog_redacted_segment(2, START, 1), "its type is: None"),
    ("index past the end", None, lambda v: v.add_dialog_redacted_segment(2, START, 1), "does not exist"),
    ("negative duration", None, lambda v: v.add_dialog_redacted_segment(1, START, -1), "non-negative"),
    ("party past the end", None, lambda v: v.add_dialog_redacted_segment(1, START, 1, parties = [0, 2]),
      "does not exist"),
    ("parties not a list", None, lambda v: v.add_dialog_redacted_segment(1, START, 1, parties = 0), "must be a list")
  ])
def test_raises(label, prepare, call, message):
  v = make_vcon()
  if(prepare is not None):
    prepare(v)
  with pytest.raises(AttributeError, match = message):
    call(v)
  for dialog in v.dialog:
    assert("redacted_segments" not in dialog), label


def test_zero_duration():
  v = make_vcon()
  v.add_dialog_redacted_segment(1, START, 0)
  assert(v.dialog[1]["redacted_segments"] == [{"start": START_UTC, "end": START_UTC}])
