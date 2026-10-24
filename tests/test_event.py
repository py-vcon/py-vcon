# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" Unit tests for Event Objects """

import logging
import pytest
import vcon


START = "2022-06-21T13:53:26-04:00"
START_UTC = "2022-06-21T17:53:26.000+00:00"


def make_vcon(num_sessions : int = 1) -> vcon.Vcon:
  v = vcon.Vcon()
  v.set_party_parameter("tel", "+15551110000")
  v.set_party_parameter("tel", "+15552220000")
  v.set_party_parameter("tel", "+15553330000")
  for session_index in range(num_sessions):
    v.add_dialog_inline_text("Hello", START, 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  return(v)


def test_add_party_event():
  v = make_vcon()
  assert("events" not in v._vcon_dict)
  session_before = dict(v.sessions[0])

  assert(v.add_event("join", START, 0, 1) == 0)
  assert(v.events[0] == {"type": "join", "time": START_UTC, "sessions": 0, "party": 1})
  assert(list(v.events[0].keys()) == ["type", "time", "sessions", "party"])
  # Session Objects are not modified
  assert(v.sessions[0] == session_before)

  assert(v.add_event("drop", START, [0], 1, dialog = 0) == 1)
  assert(v.events[1]["sessions"] == [0])
  assert(v.events[1]["dialog"] == 0)


def test_event_multiple_sessions():
  v = make_vcon(2)
  v.add_event("hold", START, [0, 1], 0)
  assert(v.events[0]["sessions"] == [0, 1])


def test_key_event():
  v = make_vcon()
  v.add_event("keydown", START, 0, 0, button = "5")
  assert(v.events[0]["button"] == "5")

  with pytest.raises(AttributeError, match = "button is required"):
    v.add_event("keyup", START, 0, 0)
  with pytest.raises(AttributeError, match = "button is not allowed"):
    v.add_event("join", START, 0, 0, button = "5")


def test_transfer_events():
  v = make_vcon(3)
  v.add_event("consultation-start", START, 0, 1, transferee = 0, transfer_target = 2, consultation = 1)
  v.add_event("consultative-transfer", START, 0, 1, transferee = 0, transfer_target = 2,
    consultation = 1, target_session = 2)
  v.add_event("blind-transfer", START, 0, 1, transferee = 0, transfer_target = 2, target_session = 2)
  v.add_event("transfer-abandoned", START, 0, 1, transferee = 0)
  assert(len(v.events) == 4)
  assert(list(v.events[1].keys()) ==
    ["type", "time", "sessions", "party", "transferee", "transfer_target", "consultation", "target_session"])

  with pytest.raises(AttributeError, match = "transferee is required"):
    v.add_event("blind-transfer", START, 0, 1, transfer_target = 2, target_session = 2)
  with pytest.raises(AttributeError, match = "consultation is not allowed"):
    v.add_event("blind-transfer", START, 0, 1, transferee = 0, transfer_target = 2,
      target_session = 2, consultation = 1)
  with pytest.raises(AttributeError, match = "dialog is not allowed"):
    v.add_event("transfer-abandoned", START, 0, 1, transferee = 0, dialog = 0)
  with pytest.raises(AttributeError, match = "not a list"):
    v.add_event("transfer-abandoned", START, [0], 1, transferee = 0)
  with pytest.raises(AttributeError, match = "transferee is not allowed"):
    v.add_event("join", START, 0, 1, transferee = 0)
  assert(len(v.events) == 4)


def test_event_invalid_indices():
  v = make_vcon()
  with pytest.raises(AttributeError):
    v.add_event("join", START, 1, 0)
  with pytest.raises(AttributeError):
    v.add_event("join", START, [0, 1], 0)
  with pytest.raises(AttributeError):
    v.add_event("join", START, [], 0)
  with pytest.raises(AttributeError):
    v.add_event("join", START, 0, 3)
  with pytest.raises(AttributeError):
    v.add_event("join", START, 0, 0, dialog = 1)
  with pytest.raises(AttributeError):
    v.add_event("blind-transfer", START, 0, 0, transferee = 5, transfer_target = 2, target_session = 0)
  with pytest.raises(AttributeError):
    v.add_event("blind-transfer", START, 0, 0, transferee = 1, transfer_target = 2, target_session = 4)
  assert("events" not in v._vcon_dict)


def test_extension_event_type(caplog):
  v = make_vcon()
  with caplog.at_level(logging.WARNING):
    v.add_event("x-recording-paused", START, 0, 0, reason = "privacy")
  assert("x-recording-paused" in caplog.text)
  assert(v.events[0]["reason"] == "privacy")

  caplog.clear()
  v._vcon_dict["extensions"] = ["X"]
  with caplog.at_level(logging.WARNING):
    v.add_event("x-recording-resumed", START, 0, 0)
  assert("not a core type" not in caplog.text)


def test_set_event_parameter():
  v = make_vcon()
  v.add_event("join", START, 0, 0)
  assert(v.set_event_parameter("dialog", 0, 0) == 0)
  assert(v.events[0]["dialog"] == 0)
  with pytest.raises(AttributeError):
    v.set_event_parameter("dialog", 0, 1)
