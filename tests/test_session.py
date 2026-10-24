# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" Unit tests for Session Objects """

import json
import logging
import warnings
import cbor2
import pytest
import vcon


START_1 = "2022-06-21T13:53:26-04:00"
START_1_UTC = "2022-06-21T17:53:26.000+00:00"
START_EARLIER_UTC = "2022-06-21T17:53:20.000+00:00"
START_LATER_UTC = "2022-06-21T17:54:00.000+00:00"

SMTP_MESSAGE = (
  "From: Bob <b@example.com>\r\n"
  "To: Alice <a@example.com>\r\n"
  "Subject: Test\r\n"
  "Date: Fri, 23 Sep 2022 21:44:25 +0000\r\n"
  "Message-ID: <test.1@example.com>\r\n"
  "Content-Type: text/plain\r\n"
  "\r\n"
  "Hello\r\n"
  )


def make_two_party_vcon() -> vcon.Vcon:
  v = vcon.Vcon()
  v.set_party_parameter("tel", "+15551110000")
  v.set_party_parameter("tel", "+15552220000")
  return(v)


def make_three_party_vcon() -> vcon.Vcon:
  v = make_two_party_vcon()
  v.set_party_parameter("tel", "+15553330000")
  return(v)


def test_add_session_parameters():
  v = make_two_party_vcon()
  assert("sessions" not in v._vcon_dict)

  session_index = v.add_session()
  assert(session_index == 0)
  assert(v.sessions[0] == {})

  session_index = v.add_session(
    parties = [1, 0],
    start = START_1,
    duration = 10,
    originator = 0,
    session_id = {"local": "abc", "remote": "def"},
    sessions = [{"session": 0, "type": "peer"}]
    )
  assert(session_index == 1)
  session = v.sessions[1]
  assert(session["parties"] == [1, 0])
  assert(session["start"] == START_1_UTC)
  assert(session["duration"] == 10)
  assert(session["originator"] == 0)
  assert(session["session_id"] == {"local": "abc", "remote": "def"})
  assert(session["sessions"] == [{"session": 0, "type": "peer"}])
  assert("dialog" not in session)


def test_add_session_invalid_indices():
  v = make_two_party_vcon()
  with pytest.raises(AttributeError):
    v.add_session(dialog = [0])
  with pytest.raises(AttributeError):
    v.add_session(parties = [2])
  with pytest.raises(AttributeError):
    v.add_session(originator = 5)
  assert("sessions" not in v._vcon_dict)


def test_sessions_and_events_not_added_until_used():
  v = make_two_party_vcon()
  assert(len(v.sessions) == 0)
  assert(len(v.events) == 0)
  v.set_uuid("example.com")
  vcon_dict = v.dumpd()
  assert("sessions" not in vcon_dict)
  assert("events" not in vcon_dict)


def test_add_dialog_creates_session():
  v = make_two_party_vcon()
  dialog_index = v.add_dialog_inline_recording(b"1234", START_1, 4.72, [0, 1], vcon.Vcon.MEDIATYPE_AUDIO_WAV)
  assert(dialog_index == 0)
  assert(len(v.sessions) == 1)
  assert(v.sessions[0] == {"start": START_1_UTC, "duration": 4.72, "parties": [0, 1], "dialog": [0]})
  # core parameters in schema order
  assert(list(v.sessions[0].keys()) == ["start", "duration", "parties", "dialog"])

  dialog_index = v.add_dialog_external_recording(b"1234", START_1, 33.12, [0, 1],
    "https://example.com/rec.wav", vcon.Vcon.MEDIATYPE_AUDIO_WAV)
  assert(dialog_index == 1)
  assert(len(v.sessions) == 2)
  assert(v.sessions[1]["dialog"] == [1])

  dialog_index = v.add_dialog_inline_text("Hi", START_1, 0, 1, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  assert(dialog_index == 2)
  assert(len(v.sessions) == 3)
  assert(v.sessions[2] == {"start": START_1_UTC, "duration": 0, "parties": [1], "dialog": [2]})

  dialog_index = v.add_dialog_inline_email_message(SMTP_MESSAGE)
  assert(dialog_index == 3)
  assert(len(v.sessions) == 4)
  assert(v.sessions[3]["dialog"] == [3])


def test_add_dialog_to_given_session():
  v = make_two_party_vcon()
  v.add_dialog_inline_text("Hi", START_1, 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  dialog_index = v.add_dialog_inline_text("Hello", START_LATER_UTC, 0, 1,
    vcon.Vcon.MEDIATYPE_TEXT_PLAIN, session = 0)
  assert(dialog_index == 1)
  assert(len(v.sessions) == 1)
  assert(v.sessions[0]["dialog"] == [0, 1])
  assert(v.sessions[0]["parties"] == [0, 1])
  assert(v.sessions[0]["start"] == START_1_UTC)
  assert(v.sessions[0]["duration"] == 34)


def test_add_dialog_invalid_session_does_not_modify():
  v = make_two_party_vcon()
  with pytest.raises(AttributeError):
    v.add_dialog_inline_text("Hi", START_1, 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN, session = 0)
  with pytest.raises(AttributeError):
    v.add_dialog_inline_recording(b"1234", START_1, 4.72, [0, 1], vcon.Vcon.MEDIATYPE_AUDIO_WAV, session = 0)
  with pytest.raises(AttributeError):
    v.add_dialog_external_recording(b"1234", START_1, 4.72, [0, 1],
      "https://example.com/rec.wav", vcon.Vcon.MEDIATYPE_AUDIO_WAV, session = 0)
  with pytest.raises(AttributeError):
    v.add_dialog_inline_email_message(SMTP_MESSAGE, session = 0)
  assert(len(v.dialog) == 0)
  assert(len(v.parties) == 2)
  assert("sessions" not in v._vcon_dict)


def test_add_dialog_to_session_no_duplicates():
  v = make_two_party_vcon()
  v.add_dialog_inline_text("Hi", START_1, 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.add_dialog_to_session(0, 0)
  v.add_dialog_to_session(0, 0, receivers = [0, 1])
  assert(v.sessions[0]["dialog"] == [0])
  assert(v.sessions[0]["parties"] == [0, 1])


def test_add_dialog_to_session_invalid_indices():
  v = make_two_party_vcon()
  v.add_dialog_inline_text("Hi", START_1, 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  with pytest.raises(AttributeError):
    v.add_dialog_to_session(1, 0)
  with pytest.raises(AttributeError):
    v.add_dialog_to_session(0, 1)
  with pytest.raises(AttributeError):
    v.add_dialog_to_session(0, 0, receivers = [2])


def test_receivers_flattened_from_multichannel_parties():
  v = make_three_party_vcon()
  v.add_dialog_inline_recording(b"1234", START_1, 5, [[0, 2], None, 1], vcon.Vcon.MEDIATYPE_AUDIO_WAV)
  assert(v.sessions[0]["parties"] == [0, 2, 1])


def test_receivers_from_dialog_parties_not_range_checked():
  # Parties may be added after the dialog which references them
  v = vcon.Vcon()
  v.add_dialog_inline_text("Hi", START_1, 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  assert(v.sessions[0]["parties"] == [0])


def test_flatten_party_indices():
  assert(vcon.utils.flatten_party_indices(None) == [])
  assert(vcon.utils.flatten_party_indices(1) == [1])
  assert(vcon.utils.flatten_party_indices([0, 1]) == [0, 1])
  assert(vcon.utils.flatten_party_indices([[0, 2], 1]) == [0, 2, 1])
  assert(vcon.utils.flatten_party_indices([0, None, 1]) == [0, 1])
  assert(vcon.utils.flatten_party_indices([[0, 1], [1, 0]]) == [0, 1])


def test_extend_time_widens_only():
  v = make_two_party_vcon()
  v.add_session(start = START_1, duration = 10)

  # dialog within the session start and duration does not change them
  v.add_dialog_inline_text("a", "2022-06-21T17:53:28.000+00:00", 2, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN, session = 0)
  assert(v.sessions[0]["start"] == START_1_UTC)
  assert(v.sessions[0]["duration"] == 10)

  # dialog starting before the session start moves the start earlier and keeps the end
  v.add_dialog_inline_text("b", START_EARLIER_UTC, 0, 1, vcon.Vcon.MEDIATYPE_TEXT_PLAIN, session = 0)
  assert(v.sessions[0]["start"] == START_EARLIER_UTC)
  assert(v.sessions[0]["duration"] == 16)

  # dialog ending after the session end extends the duration
  v.add_dialog_inline_text("c", START_LATER_UTC, 1.5, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN, session = 0)
  assert(v.sessions[0]["start"] == START_EARLIER_UTC)
  assert(v.sessions[0]["duration"] == 41.5)


def test_extend_time_false():
  v = make_two_party_vcon()
  v.add_session(start = START_1, duration = 1)
  dialog_index = v.add_dialog_inline_text("a", START_EARLIER_UTC, 60, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.add_dialog_to_session(0, dialog_index, extend_time = False)
  assert(v.sessions[0]["start"] == START_1_UTC)
  assert(v.sessions[0]["duration"] == 1)


def test_extend_time_session_without_duration():
  v = make_two_party_vcon()
  v.add_session(start = START_1)
  v.add_dialog_inline_text("a", START_LATER_UTC, 5, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN, session = 0)
  assert(v.sessions[0]["start"] == START_1_UTC)
  assert("duration" not in v.sessions[0])
  v.add_dialog_inline_text("b", START_EARLIER_UTC, 5, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN, session = 0)
  assert(v.sessions[0]["start"] == START_EARLIER_UTC)
  assert("duration" not in v.sessions[0])


def test_set_session_parameter(caplog):
  v = make_two_party_vcon()
  v.add_session()
  assert(v.set_session_parameter("duration", 5.5, 0) == 0)
  assert(v.sessions[0]["duration"] == 5.5)

  with pytest.raises(AttributeError):
    v.set_session_parameter("duration", 5.5, 1)

  with caplog.at_level(logging.WARNING):
    v.set_session_parameter("not_a_param", "x", 0)
  assert(v.sessions[0]["not_a_param"] == "x")
  assert("not_a_param" in caplog.text)


def test_add_session_reference(caplog):
  v = make_two_party_vcon()
  v.add_session()
  v.add_session()
  v.add_session_reference(0, 1, "child")
  v.add_session_reference(0, 1, "peer", "parallel call")
  assert(v.sessions[0]["sessions"] == [
    {"session": 1, "type": "child"},
    {"session": 1, "type": "peer", "description": "parallel call"}
    ])

  with pytest.raises(AttributeError):
    v.add_session_reference(0, 2, "child")
  with pytest.raises(AttributeError):
    v.add_session_reference(2, 0, "child")

  with caplog.at_level(logging.WARNING):
    v.add_session_reference(1, 0, "x-other")
  assert("x-other" in caplog.text)
  assert(v.sessions[1]["sessions"] == [{"session": 0, "type": "x-other"}])


def test_find_sessions_for_dialog():
  v = make_two_party_vcon()
  v.add_dialog_inline_text("a", START_1, 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.add_dialog_inline_text("b", START_1, 0, 1, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.add_session(dialog = [0, 1])
  assert(v.find_sessions_for_dialog(0) == [0, 2])
  assert(v.find_sessions_for_dialog(1) == [1, 2])
  assert(v.find_sessions_for_dialog(2) == [])


def test_originator_rule_no_session_parties():
  # Rule 2: session has no parties, originator becomes the first party
  v = make_two_party_vcon()
  v.add_dialog_inline_recording(b"1234", START_1, 5, None, vcon.Vcon.MEDIATYPE_AUDIO_WAV, originator = 1)
  assert(v.sessions[0]["parties"] == [1])
  assert("originator" not in v.sessions[0])
  assert("originator" not in v.dialog[0])


def test_originator_rule_same_originator():
  # Rule 3: originator already the first party, nothing changes
  v = make_two_party_vcon()
  v.add_dialog_inline_recording(b"1234", START_1, 5, [0, 1], vcon.Vcon.MEDIATYPE_AUDIO_WAV, originator = 0)
  assert(v.sessions[0]["parties"] == [0, 1])
  assert("originator" not in v.sessions[0])
  assert("originator" not in v.dialog[0])


def test_originator_rule_only_dialog():
  # Rule 4: different originator, only dialog referenced by the session
  v = make_three_party_vcon()
  v.add_dialog_inline_recording(b"1234", START_1, 5, [0, 1], vcon.Vcon.MEDIATYPE_AUDIO_WAV, originator = 1)
  assert(v.sessions[0]["parties"] == [0, 1])
  assert(v.sessions[0]["originator"] == 1)
  assert(list(v.sessions[0].keys()) == ["start", "duration", "parties", "originator", "dialog"])

  # originator not in the session parties is added
  v.add_dialog_inline_recording(b"1234", START_1, 5, [0, 1], vcon.Vcon.MEDIATYPE_AUDIO_WAV, originator = 2)
  assert(v.sessions[1]["parties"] == [0, 1, 2])
  assert(v.sessions[1]["originator"] == 2)


def test_originator_rule_ambiguous_sessions():
  # Rule 1: dialog not referenced by exactly one session
  v = make_two_party_vcon()
  v.add_dialog_inline_text("a", START_1, 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.add_session(dialog = [0])
  with pytest.raises(AttributeError):
    v.set_dialog_parameter("originator", 1, 0)


def test_originator_rule_conflict_with_other_dialog():
  # Rule 5: different originator and other dialog referenced by the session
  v = make_two_party_vcon()
  v.add_dialog_inline_recording(b"1234", START_1, 5, [0, 1], vcon.Vcon.MEDIATYPE_AUDIO_WAV)
  v.add_dialog_inline_recording(b"1234", START_1, 5, [0, 1], vcon.Vcon.MEDIATYPE_AUDIO_WAV, session = 0)
  with pytest.raises(AttributeError):
    v.set_dialog_parameter("originator", 1, 1)

  # checked before the new dialog is created
  with pytest.raises(AttributeError):
    v.add_dialog_inline_recording(b"1234", START_1, 5, [0, 1], vcon.Vcon.MEDIATYPE_AUDIO_WAV,
      originator = 1, session = 0)
  assert(len(v.dialog) == 2)
  assert(v.sessions[0]["dialog"] == [0, 1])


def test_set_dialog_parameter_originator():
  v = make_two_party_vcon()
  v.add_dialog_inline_recording(b"1234", START_1, 5, [0, 1], vcon.Vcon.MEDIATYPE_AUDIO_WAV)
  assert(v.set_dialog_parameter("originator", 1, 0) == 0)
  assert("originator" not in v.dialog[0])
  assert(v.sessions[0]["originator"] == 1)

  # setting back to the first party removes the originator parameter
  v.set_dialog_parameter("originator", 0, 0)
  assert("originator" not in v.sessions[0])

  with pytest.raises(AttributeError):
    v.set_dialog_parameter("originator", 5, 0)


def test_new_vcon_version_label():
  v = vcon.Vcon()
  assert(v.vcon == vcon.Vcon.CURRENT_VCON_VERSION)
  assert(vcon.Vcon.CURRENT_VCON_VERSION == "0.5.0")


def test_load_version():
  v = make_two_party_vcon()
  v.add_dialog_inline_text("a", START_1, 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.set_uuid("example.com")
  vcon_dict = v.dumpd()

  # current version loads without warning
  with warnings.catch_warnings():
    warnings.simplefilter("error", vcon.UnconvertedVconVersionWarning)
    loaded = vcon.Vcon()
    loaded.loadd(vcon_dict)
  assert(loaded.vcon == "0.5.0")
  assert(loaded.sessions[0]["dialog"] == [0])

  # no vcon parameter loads as current and is not labeled
  del vcon_dict["vcon"]
  with warnings.catch_warnings():
    warnings.simplefilter("error", vcon.UnconvertedVconVersionWarning)
    loaded = vcon.Vcon()
    loaded.loadd(vcon_dict)
  assert(loaded.vcon is None)
  assert("vcon" not in loaded.dumpd())

  # 0.4.0 is accepted without conversion
  vcon_dict["vcon"] = "0.4.0"
  with pytest.warns(vcon.UnconvertedVconVersionWarning):
    loaded = vcon.Vcon()
    loaded.loadd(vcon_dict)
  assert(loaded.vcon == "0.4.0")


def test_load_sessions_only():
  vcon_dict = {
    "uuid": "01928e10-193e-8231-b9a2-279e0d16bc46",
    "created_at": "2022-06-21T17:53:00.000+00:00",
    "sessions": [{}]
    }
  loaded = vcon.Vcon()
  loaded.loads(json.dumps(vcon_dict))
  assert(loaded.sessions == [{}])

  loaded = vcon.Vcon()
  loaded.loadc(cbor2.dumps(vcon_dict))
  assert(loaded.sessions == [{}])


def test_session_registry():
  assert(vcon.Vcon.get_parameter_extension("", "sessions") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("", "events") == vcon.Vcon.PARAMETER_CORE)
  for name in ["start", "duration", "parties", "originator", "session_id", "sessions", "dialog"]:
    assert(vcon.Vcon.get_parameter_extension("sessions", name) == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("sessions.session_id", "local") == vcon.Vcon.PARAMETER_CORE)
  for name in ["session", "type", "description"]:
    assert(vcon.Vcon.get_parameter_extension("sessions.sessions", name) == vcon.Vcon.PARAMETER_CORE)
  for name in ["type", "time", "sessions", "party", "dialog", "button", "transferee",
    "transfer_target", "consultation", "target_session"]:
    assert(vcon.Vcon.get_parameter_extension("events", name) == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("analysis", "session") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("analysis", "analysis") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("attachments", "session") == vcon.Vcon.PARAMETER_CORE)
  # removed in 0.5.0, retained until the 0.4.0 converter exists
  assert(vcon.Vcon.get_parameter_extension("dialog", "originator") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("dialog.party_history", "event") == vcon.Vcon.PARAMETER_CORE)


def make_smtp_message(
  sender : str,
  to : str,
  message_id : str,
  cc : str = "",
  bcc : str = "",
  content_type : str = "text/plain"
  ) -> str:
  headers = "From: {}\r\nTo: {}\r\n".format(sender, to)
  if(cc != ""):
    headers += "Cc: {}\r\n".format(cc)
  if(bcc != ""):
    headers += "Bcc: {}\r\n".format(bcc)
  headers += ("Subject: Test\r\nDate: Fri, 23 Sep 2022 21:44:25 +0000\r\n"
    "Message-ID: {}\r\nContent-Type: {}\r\n".format(message_id, content_type))
  return(headers + "\r\nHello\r\n")


ALICE = "Alice <a@example.com>"
BOB = "Bob <b@example.com>"
CAROL = "Carol <c@example.com>"
DAVE = "Dave <d@example.com>"


def test_email_thread_one_session(caplog):
  v = vcon.Vcon()
  with caplog.at_level(logging.WARNING):
    v.add_dialog_inline_email_message(make_smtp_message(BOB, ALICE, "<1@example.com>"))
    v.add_dialog_inline_email_message(make_smtp_message(ALICE, BOB, "<2@example.com>"))
  assert("do not match" not in caplog.text)

  assert(v.parties[0]["name"] == "Bob")
  assert(v.parties[1]["name"] == "Alice")
  # Dialog Object parties reference the sender only
  assert(v.dialog[0]["parties"] == [0])
  assert(v.dialog[1]["parties"] == [1])
  # The Session Object references both dialogs and all of the receivers
  assert(len(v.sessions) == 1)
  assert(v.sessions[0]["parties"] == [0, 1])
  assert(v.sessions[0]["dialog"] == [0, 1])


def test_email_cc_receivers_bcc_ignored():
  v = vcon.Vcon()
  v.add_dialog_inline_email_message(make_smtp_message(ALICE, BOB, "<1@example.com>", cc = CAROL, bcc = DAVE))
  assert(len(v.parties) == 3)
  assert(v.dialog[0]["parties"] == [0])
  assert(v.sessions[0]["parties"] == [0, 1, 2])


def test_email_receivers_change_new_session(caplog):
  v = vcon.Vcon()
  v.add_dialog_inline_email_message(make_smtp_message(ALICE, BOB, "<1@example.com>"))
  with caplog.at_level(logging.WARNING):
    v.add_dialog_inline_email_message(make_smtp_message(BOB, ALICE, "<2@example.com>", cc = CAROL))
  assert("do not match" in caplog.text)
  assert(len(v.sessions) == 2)
  assert(v.sessions[0]["dialog"] == [0])
  assert(v.sessions[1]["dialog"] == [1])
  assert(v.sessions[1]["parties"] == [1, 0, 2])


def test_email_given_session():
  v = vcon.Vcon()
  v.add_dialog_inline_email_message(make_smtp_message(ALICE, BOB, "<1@example.com>"))
  v.add_dialog_inline_email_message(make_smtp_message(BOB, ALICE, "<2@example.com>", cc = CAROL), session = 0)
  assert(len(v.sessions) == 1)
  assert(v.sessions[0]["dialog"] == [0, 1])
  assert(v.sessions[0]["parties"] == [0, 1, 2])


def test_email_folded_content_type():
  v = vcon.Vcon()
  v.add_dialog_inline_email_message(make_smtp_message(ALICE, BOB, "<1@example.com>",
    content_type = "text/plain;\r\n\tcharset=UTF-8"))
  assert(v.dialog[0]["mediatype"] == "text/plain; charset=UTF-8")


def test_unfold_header():
  assert(vcon.utils.unfold_header(None) is None)
  assert(vcon.utils.unfold_header("text/plain") == "text/plain")
  assert(vcon.utils.unfold_header("multipart/mixed; \n\tboundary=\"x\"") == "multipart/mixed; boundary=\"x\"")
  assert(vcon.utils.unfold_header("a;\r\n  b;\r\n\tc") == "a; b; c")
