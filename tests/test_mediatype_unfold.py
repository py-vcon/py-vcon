# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" A mediatype folded over several lines (as in an email header) is unfolded """

import copy
import pytest
import vcon
import vcon.migrate_0_4_0
import tests.common_utils

START = "2023-01-01T10:00:00.000+00:00"
FOLDED = "multipart/mixed;\r\n\tboundary=\"x\""
UNFOLDED = "multipart/mixed; boundary=\"x\""


def make_vcon() -> vcon.Vcon:
  v = vcon.Vcon()
  v.set_uuid("example.com")
  v.set_party_parameter("tel", "+15551110000")
  v.set_party_parameter("tel", "+15552220000")
  return(v)


ADDERS = {
  "text": lambda v, media_type: v.dialog[v.add_text_dialog_inline("hi", START, 0, 0, media_type)],
  "recording_inline": lambda v, media_type:
    v.dialog[v.add_recording_dialog_inline(b"\x00\x01", START, 1, [0, 1], media_type, "a.wav")],
  "recording_external": lambda v, media_type:
    v.dialog[v.add_recording_dialog_external(b"\x00\x01", START, 1, [0, 1], "https://example.com/a.wav",
      media_type, "a.wav")],
  "attachment": lambda v, media_type:
    v.attachments[v.add_attachment_inline(b"a", START, 0, media_type, "a.txt",
      dialog = v.add_text_dialog_inline("hi", START, 0, 0, "text/plain"))],
  "analysis": lambda v, media_type:
    v.analysis[v.add_analysis(None, "summary", "text", "vendor", mediatype = media_type, encoding = "none",
      sessions = v.add_session())],
  "analysis_transcript": lambda v, media_type: (v.add_analysis_transcript(
    v.add_text_dialog_inline("hi", START, 0, 0, "text/plain"), "text", "vendor", encoding = "none",
    mediatype = media_type), v.analysis[-1])[1]
  }


@pytest.mark.parametrize("method", sorted(ADDERS))
def test_folded_mediatype_unfolded(method):
  v = make_vcon()
  assert(ADDERS[method](v, FOLDED)["mediatype"] == UNFOLDED)


@pytest.mark.parametrize("method", sorted(ADDERS))
def test_unfolded_mediatype_unchanged(method):
  v = make_vcon()
  assert(ADDERS[method](v, UNFOLDED)["mediatype"] == UNFOLDED)
  v = make_vcon()
  assert(ADDERS[method](v, "text/plain")["mediatype"] == "text/plain")


def test_converter_unfolds_mediatype():
  vcon_dict = {"vcon": "0.4.0", "uuid": "01a07da8-c2bb-83e5-b9a2-279e0d16bc46", "created_at": START,
    "parties": [{"tel": "+15551110000"}, {"tel": "+15552220000"}],
    "dialog": [{"type": "text", "start": START, "parties": [0, 1], "mediatype": FOLDED,
      "encoding": "none", "body": "hi"}],
    "attachments": [{"dialog": 0, "party": 0, "start": START, "mediatype": FOLDED, "encoding": "none", "body": "a"}],
    "analysis": [{"type": "summary", "dialog": 0, "vendor": "v", "mediatype": FOLDED, "encoding": "none",
      "body": "s"}]}
  before = copy.deepcopy(vcon_dict)
  result = vcon.migrate_0_4_0.migrate_0_4_0_vcon(vcon_dict)
  assert(vcon_dict == before)
  for array_name in ["dialog", "attachments", "analysis"]:
    assert(result[array_name][0]["mediatype"] == UNFOLDED), array_name
  tests.common_utils.assert_valid_vcon(result)


@pytest.mark.parametrize("path", ["examples/b_email_acct_prob_image.vcon", "examples/ab_email_acct_prob_thread.vcon"])
def test_draft_email_examples_unfolded(path):
  example = tests.common_utils.load_draft_0_4_0_example(path)
  assert(any(["\n" in dialog.get("mediatype", "") for dialog in example["dialog"]]))
  loaded = vcon.Vcon()
  loaded.loadd(example)
  assert(all(["\n" not in dialog.get("mediatype", "") for dialog in loaded.dialog]))
