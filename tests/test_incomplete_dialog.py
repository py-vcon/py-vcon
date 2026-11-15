# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" Unit tests for incomplete Dialog Objects """

import logging
import pytest
import vcon
import vcon.parameter_registry
import tests.common_utils

START = "2022-06-21T13:53:26-04:00"
START_UTC = "2022-06-21T17:53:26.000+00:00"
CONTENT = ["body", "url", "mediatype", "filename", "encoding", "content_hash"]


def make_vcon() -> vcon.Vcon:
  v = vcon.Vcon()
  v.set_uuid("example.com")
  for tel in ["+15551110000", "+15552220000", "+15553330000"]:
    v.set_party_parameter("tel", tel)
  return(v)


def test_busy():
  v = make_vcon()
  dialog_index = v.add_incomplete_dialog("busy", START, 12, caller = 0, receivers = [1, 2])
  assert(dialog_index == 0)
  assert(v.dialog[0] == {"type": "incomplete", "start": START_UTC, "duration": 12, "parties": 0,
    "disposition": "busy"})
  assert(len(v.sessions) == 1)
  assert(v.sessions[0]["parties"] == [0, 1, 2])
  assert(v.sessions[0]["dialog"] == [0])
  assert("originator" not in v.sessions[0])
  tests.common_utils.assert_valid_vcon(v.dumpd())


def test_placeholder():
  v = make_vcon()
  assert(v.add_incomplete_dialog("failed") == 0)
  assert(v.dialog[0] == {"type": "incomplete", "disposition": "failed"})
  assert(v.sessions[0]["dialog"] == [0])
  tests.common_utils.assert_valid_vcon(v.dumpd())


def test_existing_session():
  v = make_vcon()
  v.add_text_dialog_inline("Hello", START, 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.add_dialog_to_session(0, 0, receivers = [0, 1])
  assert(v.sessions[0]["parties"] == [0, 1])

  dialog_index = v.add_incomplete_dialog("no-answer", START, caller = 0, receivers = [1, 2], session = 0)
  assert(dialog_index == 1)
  assert(len(v.sessions) == 1)
  assert(v.sessions[0]["dialog"] == [0, 1])
  assert(v.sessions[0]["parties"] == [0, 1, 2])
  tests.common_utils.assert_valid_vcon(v.dumpd())


def test_caller_becomes_originator():
  v = make_vcon()
  v.add_session(parties = [1])
  v.add_incomplete_dialog("hung-up", START, caller = 2, receivers = [1], session = 0)
  assert(v.sessions[0]["originator"] == 2)
  assert(v.sessions[0]["parties"] == [1, 2])


@pytest.fixture
def disposition_extension():
  vcon.parameter_registry.register_extension({"name": "TEST_DISPOSITION", "description": "test",
    "change_controller": "py-vcon", "specification": "tests/test_incomplete_dialog.py", "critical": False},
    [{"parent": "Dialog->disposition", "name": "test-blocked", "description": "call blocked"}])
  yield "TEST_DISPOSITION"
  vcon.parameter_registry.unregister_extension("TEST_DISPOSITION")


def test_extension_disposition(disposition_extension, caplog):
  v = make_vcon()
  with caplog.at_level(logging.WARNING):
    v.add_incomplete_dialog("test-blocked", START, caller = 0)
  assert([record for record in caplog.records if(record.levelno >= logging.WARNING)] == [])
  assert(v.dialog[0]["disposition"] == "test-blocked")
  assert(v.extensions == [disposition_extension])

  with caplog.at_level(logging.WARNING):
    v.add_incomplete_dialog("my-disposition", START, caller = 0)
  assert("Dialog disposition: \"my-disposition\" is not defined" in caplog.text)
  assert(v.dialog[1]["disposition"] == "my-disposition")
  assert(v.extensions == [disposition_extension])


def test_core_dispositions():
  assert(vcon.Vcon.DIALOG_DISPOSITIONS == [row["name"] for row in vcon.parameter_registry.get_rows("Dialog->disposition")])


@pytest.mark.parametrize("label, kwargs, message", [
    ("caller", {"caller": 3}, "does not exist"),
    ("receiver", {"receivers": [1, 3]}, "does not exist"),
    ("session", {"session": 0}, "does not exist"),
    ("negative duration", {"duration": -1}, "non-negative"),
    ("caller cannot be originator", {"caller": 2, "session": 0}, "has originator: 1")
  ])
def test_raises(label, kwargs, message):
  v = make_vcon()
  if(label == "caller cannot be originator"):
    v.add_text_dialog_inline("Hello", START, 0, 1, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  with pytest.raises(AttributeError, match = message):
    v.add_incomplete_dialog("busy", START, **kwargs)
  assert(len([dialog for dialog in v.dialog if(dialog["type"] == "incomplete")]) == 0), label
  assert(len(v.sessions) == (1 if label == "caller cannot be originator" else 0)), label


def test_no_content():
  v = make_vcon()
  v.add_incomplete_dialog("voicemail-no-message", START, 30, caller = 0, receivers = [1])
  assert([name for name in CONTENT if(name in v.dialog[0])] == [])


def test_returns_index():
  v = make_vcon()
  assert(v.add_incomplete_dialog("busy") == 0)
  assert(v.add_incomplete_dialog("busy") == 1)


def test_vcon_without_dialog_array():
  """ a loaded vCon may have no dialog array """
  v = make_vcon()
  del v._vcon_dict["dialog"]
  assert(v.add_incomplete_dialog("busy") == 0)
  assert(v.dialog == [{"type": "incomplete", "disposition": "busy"}])
