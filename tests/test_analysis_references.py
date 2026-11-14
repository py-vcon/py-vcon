# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" Unit tests for Analysis Object references to Dialog, Session, Attachment and Analysis Objects """

import logging
import pytest
import vcon
import tests.common_utils

START = "2022-06-21T13:53:26-04:00"
REFERENCES = ["dialog", "sessions", "attachment", "analysis"]


def make_vcon() -> vcon.Vcon:
  """ two text Dialogs in two Sessions, two Attachments, two Analysis Objects """
  v = vcon.Vcon()
  v.set_uuid("example.com")
  v.set_party_parameter("tel", "+15551110000")
  v.add_dialog_inline_text("Hello", START, 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.add_dialog_inline_text("Again", START, 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  for index in range(2):
    v.add_attachment_inline(b"notes", START, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN, dialog = index)
    v.add_analysis(index, "summary", "summary {}".format(index), "test_vendor", None, "none")
  return(v)


def add_summary(v : vcon.Vcon, dialog_index = None, **references) -> int:
  return(v.add_analysis(dialog_index, "summary", "a summary", "test_vendor", None, "none", **references))


def present(analysis : dict) -> list:
  return([name for name in REFERENCES if(name in analysis)])


def test_dialog_only():
  v = make_vcon()
  index = add_summary(v, 1)
  assert(v.analysis[index]["dialog"] == 1)
  assert(present(v.analysis[index]) == ["dialog"])
  tests.common_utils.assert_valid_vcon(v.dumpd())


@pytest.mark.parametrize("name, value", [
    ("sessions", 1), ("sessions", [0, 1]),
    ("attachment", 0), ("attachment", [0, 1]),
    ("analysis", 1), ("analysis", [0, 1])
  ])
def test_one_reference(name, value):
  v = make_vcon()
  index = add_summary(v, **{name: value})
  assert(v.analysis[index][name] == value)
  assert(present(v.analysis[index]) == [name])
  tests.common_utils.assert_valid_vcon(v.dumpd())


def test_all_references():
  v = make_vcon()
  index = add_summary(v, [0, 1], sessions = 0, attachment = 1, analysis = [0, 1])
  assert(present(v.analysis[index]) == REFERENCES)
  assert(list(v.analysis[index].keys())[:5] == ["type", "dialog", "sessions", "attachment", "analysis"])
  tests.common_utils.assert_valid_vcon(v.dumpd())


def test_no_reference_warns(caplog):
  v = make_vcon()
  with caplog.at_level(logging.WARNING):
    index = add_summary(v)
  assert(present(v.analysis[index]) == [])
  assert("references no dialog, sessions, attachment or analysis" in caplog.text)


@pytest.mark.parametrize("label, dialog_index, references", [
    ("dialog", 2, {}),
    ("dialog in list", [0, 2], {}),
    ("sessions", None, {"sessions": 2}),
    ("attachment", None, {"attachment": [1, 2]}),
    ("analysis", None, {"analysis": 3}),
    ("empty list", None, {"sessions": []})
  ])
def test_out_of_range(label, dialog_index, references):
  v = make_vcon()
  with pytest.raises(AttributeError):
    add_summary(v, dialog_index, **references)
  assert(len(v.analysis) == 2), label


def test_analysis_may_not_reference_itself():
  v = make_vcon()
  with pytest.raises(AttributeError, match = "does not exist"):
    add_summary(v, analysis = 2)
  assert(len(v.analysis) == 2)


def test_returns_index():
  v = make_vcon()
  assert(add_summary(v, 0) == 2)
  assert(add_summary(v, 1) == 3)
