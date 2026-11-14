# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" Unit tests for Event Objects """

import logging
import pytest
import vcon
import vcon.parameter_registry
import tests.common_utils


START = "2022-06-21T13:53:26-04:00"
START_UTC = "2022-06-21T17:53:26.000+00:00"


def make_vcon(num_sessions : int = 1) -> vcon.Vcon:
  """ three parties and one text Dialog in each of num_sessions Sessions """
  v = vcon.Vcon()
  v.set_uuid("example.com")
  v.set_party_parameter("tel", "+15551110000")
  v.set_party_parameter("tel", "+15552220000")
  v.set_party_parameter("tel", "+15553330000")
  for session_index in range(num_sessions):
    v.add_dialog_inline_text("Hello", START, 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  return(v)


def add_recording(v : vcon.Vcon, parties) -> int:
  """ add a recording Dialog with the given parties, return its index """
  dialog_index = v.add_dialog_inline_recording(b"\x00\x01", START, 10, 0, "audio/x-wav", "a.wav")
  v._vcon_dict["dialog"][dialog_index]["parties"] = parties
  return(dialog_index)


@pytest.mark.parametrize("event_type", vcon.Vcon.EVENT_PARTY_TYPES)
def test_party_events(event_type):
  v = make_vcon(2)
  method = getattr(v, "add_{}_event".format(event_type))
  session_before = dict(v.sessions[0])

  assert(method(START, 0, 1) == 0)
  assert(v.events[0] == {"type": event_type, "time": START_UTC, "sessions": 0, "party": 1})
  assert(list(v.events[0].keys()) == ["type", "time", "sessions", "party"])
  assert(method(START, [0, 1], 2) == 1)
  assert(v.events[1]["sessions"] == [0, 1])
  # Session Objects are not modified
  assert(v.sessions[0] == session_before)
  tests.common_utils.assert_valid_vcon(v.dumpd())


@pytest.mark.parametrize("event_type", vcon.Vcon.EVENT_KEY_TYPES)
def test_key_events(event_type):
  v = make_vcon()
  method = getattr(v, "add_{}_event".format(event_type))
  assert(method(START, 0, 0, "5") == 0)
  assert(v.events[0] == {"type": event_type, "time": START_UTC, "sessions": 0, "party": 0, "button": "5"})
  tests.common_utils.assert_valid_vcon(v.dumpd())

  with pytest.raises(TypeError):
    method(START, 0, 0)
  for button in [None, ""]:
    with pytest.raises(AttributeError, match = "button is required"):
      method(START, 0, 0, button)
  assert(len(v.events) == 1)


def test_transfer_events():
  v = make_vcon(3)
  assert(v.add_consultation_start_event(START, 0, 1, 0, 2, 1) == 0)
  assert(v.add_consultative_transfer_event(START, 0, 1, 0, 2, 1, 2) == 1)
  assert(v.add_blind_transfer_event(START, 0, 1, 0, 2, 2) == 2)
  assert(v.add_transfer_abandoned_event(START, 0, 1, 0) == 3)
  assert(v.add_transfer_abandoned_event(START, 0, 1, 0, transfer_target = 2, consultation = 1) == 4)

  assert(v.events[0] == {"type": "consultation-start", "time": START_UTC, "sessions": 0, "party": 1,
    "transferee": 0, "transfer_target": 2, "consultation": 1})
  assert(list(v.events[1].keys()) ==
    ["type", "time", "sessions", "party", "transferee", "transfer_target", "consultation", "target_session"])
  assert(v.events[2] == {"type": "blind-transfer", "time": START_UTC, "sessions": 0, "party": 1,
    "transferee": 0, "transfer_target": 2, "target_session": 2})
  # transfer-abandoned optional arguments only when given
  assert(v.events[3] == {"type": "transfer-abandoned", "time": START_UTC, "sessions": 0, "party": 1,
    "transferee": 0})
  assert(v.events[4]["transfer_target"] == 2 and v.events[4]["consultation"] == 1)
  tests.common_utils.assert_valid_vcon(v.dumpd())

  # sessions must be the single index of the original call
  for method, arguments in [
      (v.add_consultation_start_event, (START, [0], 1, 0, 2, 1)),
      (v.add_blind_transfer_event, (START, [0], 1, 0, 2, 2)),
      (v.add_consultative_transfer_event, (START, [0], 1, 0, 2, 1, 2)),
      (v.add_transfer_abandoned_event, (START, [0], 1, 0))
    ]:
    with pytest.raises(AttributeError, match = "single index"):
      method(*arguments)
  assert(len(v.events) == 5)


def test_channel_contributors_event():
  v = make_vcon()
  dialog_index = add_recording(v, [0, 1])

  assert(v.add_channel_contributors_event(START, dialog_index, 0) == 0)
  assert(v.events[0] == {"type": "channel-contributors", "time": START_UTC, "dialog": dialog_index, "channel": 0})
  assert(v.add_channel_contributors_event(START, dialog_index, 1, 2) == 1)
  assert(v.events[1]["contributors"] == 2)
  assert(v.add_channel_contributors_event(START, dialog_index, 1, [1, 2]) == 2)
  assert(v.events[2] == {"type": "channel-contributors", "time": START_UTC, "dialog": dialog_index,
    "channel": 1, "contributors": [1, 2]})
  tests.common_utils.assert_valid_vcon(v.dumpd())

  # not a recording, an empty Dialog, a missing Dialog
  with pytest.raises(AttributeError, match = r"dialog\[0\] is not a recording Dialog Object"):
    v.add_channel_contributors_event(START, 0, 0)
  v._vcon_dict["dialog"].append({})
  with pytest.raises(AttributeError, match = "is not a recording Dialog Object, its type is: None"):
    v.add_channel_contributors_event(START, 2, 0)
  with pytest.raises(AttributeError, match = "does not exist"):
    v.add_channel_contributors_event(START, 3, 0)
  # a contributor which does not exist
  with pytest.raises(AttributeError, match = "does not exist"):
    v.add_channel_contributors_event(START, dialog_index, 0, [0, 3])
  assert(len(v.events) == 3)


@pytest.mark.parametrize("label, parties, last_ok, first_bad", [
    ("int: one channel", 1, 0, 1),
    ("list with a list", [0, [1, 2]], 1, 2),
    ("list with a null", [0, None, 2], 2, 3),
    ("flat list: number unknown", [0, 1], 99, None)
  ])
def test_channel_range(label, parties, last_ok, first_bad):
  v = make_vcon()
  dialog_index = add_recording(v, parties)
  v.add_channel_contributors_event(START, dialog_index, last_ok)
  if(first_bad is not None):
    with pytest.raises(AttributeError, match = "is not in dialog"):
      v.add_channel_contributors_event(START, dialog_index, first_bad)
  with pytest.raises(AttributeError, match = "non-negative"):
    v.add_channel_contributors_event(START, dialog_index, -1)
  assert(len(v.events) == 1), label


@pytest.mark.parametrize("label, call", [
    ("session", lambda v: v.add_join_event(START, 2, 0)),
    ("session in list", lambda v: v.add_mute_event(START, [0, 2], 0)),
    ("empty sessions list", lambda v: v.add_hold_event(START, [], 0)),
    ("party", lambda v: v.add_drop_event(START, 0, 3)),
    ("key party", lambda v: v.add_keydown_event(START, 0, 3, "1")),
    ("transferor", lambda v: v.add_blind_transfer_event(START, 0, 3, 0, 2, 1)),
    ("transferee", lambda v: v.add_blind_transfer_event(START, 0, 1, 3, 2, 1)),
    ("transfer_target", lambda v: v.add_blind_transfer_event(START, 0, 1, 0, 3, 1)),
    ("target_session", lambda v: v.add_blind_transfer_event(START, 0, 1, 0, 2, 2)),
    ("consultation", lambda v: v.add_consultation_start_event(START, 0, 1, 0, 2, 2)),
    ("original session", lambda v: v.add_transfer_abandoned_event(START, 2, 1, 0)),
    ("abandoned consultation", lambda v: v.add_transfer_abandoned_event(START, 0, 1, 0, consultation = 2)),
    ("dialog", lambda v: v.add_channel_contributors_event(START, 5, 0))
  ])
def test_invalid_indices(label, call):
  v = make_vcon(2)
  with pytest.raises(AttributeError):
    call(v)
  assert("events" not in v._vcon_dict), label


@pytest.fixture
def event_extensions():
  extension = {"description": "test", "change_controller": "py-vcon",
    "specification": "tests/test_event.py"}
  vcon.parameter_registry.register_extension(dict(extension, name = "TEST_EVENTS", critical = False),
    [{"parent": "Event->type", "name": "test-paused", "description": "x"},
     {"parent": "Event", "name": "reason", "description": "x"}])
  vcon.parameter_registry.register_extension(dict(extension, name = "TEST_CRIT_EVENTS", critical = True),
    [{"parent": "Event->type", "name": "test-crit", "description": "x"}])
  yield
  vcon.parameter_registry.unregister_extension("TEST_EVENTS")
  vcon.parameter_registry.unregister_extension("TEST_CRIT_EVENTS")


def test_add_event_core_type_raises():
  v = make_vcon()
  for event_type in vcon.Vcon.EVENT_CORE_TYPES:
    with pytest.raises(AttributeError, match = "Use add_{}_event".format(event_type.replace("-", "_"))):
      v.add_event(event_type, START, sessions = 0, party = 0)
    # the named method exists
    assert(callable(getattr(v, "add_{}_event".format(event_type.replace("-", "_")))))
  assert("events" not in v._vcon_dict)


def test_add_event_extension_type(event_extensions, caplog):
  v = make_vcon(2)
  with caplog.at_level(logging.WARNING):
    assert(v.add_event("test-paused", START, sessions = 0, party = 0, reason = "privacy") == 0)
  assert(caplog.text == "")
  assert(v.events[0] == {"type": "test-paused", "time": START_UTC, "sessions": 0, "party": 0, "reason": "privacy"})
  assert(v.extensions == ["TEST_EVENTS"])
  assert("critical" not in v._vcon_dict)

  # a critical extension is also added to critical
  v.add_event("test-crit", START, sessions = 1)
  assert(v.extensions == ["TEST_EVENTS", "TEST_CRIT_EVENTS"])
  assert(v.critical == ["TEST_CRIT_EVENTS"])

  # a list of Dialog indices is accepted for an extension type
  v.add_event("test-paused", START, dialog = [0, 1])
  assert(v.events[2]["dialog"] == [0, 1])
  with pytest.raises(AttributeError, match = "does not exist"):
    v.add_event("test-paused", START, dialog = [0, 2])
  assert(len(v.events) == 3)


def test_add_event_unregistered_type(caplog):
  v = make_vcon()
  with caplog.at_level(logging.WARNING):
    v.add_event("x-recording-paused", START, sessions = 0, party = 0)
  assert("Event type: \"x-recording-paused\" is not defined" in caplog.text)
  assert(v.events[0]["type"] == "x-recording-paused")
  assert("extensions" not in v._vcon_dict)


def test_applicability_table_removed():
  assert(not hasattr(vcon.Vcon, "EVENT_PARAMETER_APPLICABILITY"))


def test_set_event_parameter():
  v = make_vcon()
  v.add_join_event(START, 0, 0)
  assert(v.set_event_parameter("dialog", 0, 0) == 0)
  assert(v.events[0]["dialog"] == 0)
  with pytest.raises(AttributeError):
    v.set_event_parameter("dialog", 0, 1)
