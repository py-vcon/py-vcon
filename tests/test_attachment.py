# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" Unit tests for Attachment Object references to Dialog and Session Objects """

import os
import shutil
import sys
import pytest
import vcon
import tests.common_utils

START = "2022-06-21T13:53:26-04:00"
ZOOM_MEETING_RECORDING = "tests/zoom/Zoom recording to computer 09 18 23"


def make_vcon() -> vcon.Vcon:
  """ two parties, two text Dialogs in two Sessions """
  v = vcon.Vcon()
  v.set_uuid("example.com")
  v.set_party_parameter("tel", "+15551110000")
  v.set_party_parameter("tel", "+15552220000")
  v.add_dialog_inline_text("Hello", START, 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.add_dialog_inline_text("Again", START, 0, 1, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  return(v)


def add_notes(v : vcon.Vcon, **references) -> int:
  return(v.add_attachment_inline(b"notes", START, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN, "notes.txt", **references))


def test_dialog_only():
  v = make_vcon()
  assert(add_notes(v, dialog = 1) == 0)
  assert(v.attachments[0]["dialog"] == 1)
  assert("session" not in v.attachments[0])
  tests.common_utils.assert_valid_vcon(v.dumpd())


def test_session_only():
  v = make_vcon()
  add_notes(v, session = 1)
  add_notes(v, session = [0, 1])
  assert(v.attachments[0]["session"] == 1)
  assert(v.attachments[1]["session"] == [0, 1])
  assert("dialog" not in v.attachments[0])
  tests.common_utils.assert_valid_vcon(v.dumpd())


def test_dialog_and_session():
  v = make_vcon()
  add_notes(v, dialog = 0, session = 0)
  assert(v.attachments[0]["dialog"] == 0)
  assert(v.attachments[0]["session"] == 0)
  assert(list(v.attachments[0].keys())[:4] == ["start", "party", "dialog", "session"])
  tests.common_utils.assert_valid_vcon(v.dumpd())


@pytest.mark.parametrize("label, references, message", [
    ("neither", {}, "must reference a dialog, a session or both"),
    ("dialog past the end", {"dialog": 2}, "does not exist"),
    ("session past the end", {"session": 2}, "does not exist"),
    ("session in list past the end", {"session": [0, 2]}, "does not exist"),
    ("empty session list", {"session": []}, "at least one")
  ])
def test_raises(label, references, message):
  v = make_vcon()
  with pytest.raises(AttributeError, match = message):
    add_notes(v, **references)
  assert(len(v.attachments) == 0), label


def test_party_past_the_end():
  v = make_vcon()
  with pytest.raises(AttributeError, match = "does not exist"):
    v.add_attachment_inline(b"notes", START, 2, vcon.Vcon.MEDIATYPE_TEXT_PLAIN, dialog = 0)
  assert(len(v.attachments) == 0)


def test_purpose():
  v = make_vcon()
  add_notes(v, dialog = 0, purpose = "Meeting notes, draft 2")
  add_notes(v, dialog = 0)
  assert(v.attachments[0]["purpose"] == "Meeting notes, draft 2")
  assert("purpose" not in v.attachments[1])
  tests.common_utils.assert_valid_vcon(v.dumpd())


@pytest.mark.asyncio
async def test_zoom_attachment(capsys, tmp_path):
  """ a Zoom import references its attachments from the meeting Session and an empty Party """
  import vcon.cli

  zoom_dir = os.path.join(str(tmp_path), "zoom")
  shutil.copytree(ZOOM_MEETING_RECORDING, zoom_dir)
  with open(os.path.join(zoom_dir, "agenda.txt"), "w") as agenda_file:
    agenda_file.write("1. colors\\n2. drinks\\n")

  await vcon.cli.main(["-n", "add", "in-zoom", zoom_dir])
  out_vcon_json, error = capsys.readouterr()
  print("stderr: {}".format(error), file = sys.stderr)
  out_vcon = vcon.Vcon()
  out_vcon.loads(out_vcon_json)

  assert(len(out_vcon.attachments) == 1)
  attachment = out_vcon.attachments[0]
  assert(attachment["filename"] == "agenda.txt")
  assert(attachment["body"] == "1. colors\\n2. drinks\\n")
  assert(attachment["session"] == 0)
  assert(out_vcon.parties[attachment["party"]] == {})
  # the chat senders keep their indices
  assert(out_vcon.parties[0]["name"] == "Daniel Petrie")
  assert(len(out_vcon.sessions) == 1)
  if(out_vcon.uuid is None):
    out_vcon.set_uuid("vcon.dev")
  tests.common_utils.assert_valid_vcon(out_vcon.dumpd())
