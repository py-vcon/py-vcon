# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" Unit tests for the 0.4.0 to 0.5.0 vCon converter """

import copy
import warnings
import pytest
import vcon.migrate_0_4_0
import tests.common_utils


UUID = "01a07da8-c2bb-83e5-b9a2-279e0d16bc46"


def at(seconds : float) -> str:
  return("2023-01-01T10:{:02d}:{:06.3f}+00:00".format(int(seconds // 60), seconds % 60))


def parties(count : int) -> list:
  return([{"name": "party{}".format(index)} for index in range(count)])


def recording(start, duration, dialog_parties, **extra) -> dict:
  dialog = {"type": "recording", "start": start, "duration": duration, "parties": dialog_parties,
    "mediatype": "audio/x-wav", "url": "https://example.com/r.wav", "content_hash": "sha512-abc"}
  dialog.update(extra)
  return(dialog)


def text(start, dialog_parties, **extra) -> dict:
  dialog = {"type": "text", "start": start, "duration": 0, "parties": dialog_parties,
    "mediatype": "text/plain", "encoding": "none", "body": "hi"}
  dialog.update(extra)
  return(dialog)


def make(dialogs, party_count = 3, **extra) -> dict:
  vcon_dict = {"vcon": "0.4.0", "uuid": UUID, "created_at": at(0), "parties": parties(party_count),
    "dialog": dialogs, "analysis": [], "attachments": []}
  vcon_dict.update(extra)
  return(vcon_dict)


def convert(vcon_dict : dict, expected_warnings : int = 0) -> dict:
  """ convert, checking the input is unchanged and the number of conversion warnings """
  before = copy.deepcopy(vcon_dict)
  with warnings.catch_warnings(record = True) as caught:
    warnings.simplefilter("always")
    result = vcon.migrate_0_4_0.migrate_0_4_0_vcon(vcon_dict)
  assert(vcon_dict == before)
  conversion_warnings = [str(warning.message) for warning in caught
    if(issubclass(warning.category, vcon.migrate_0_4_0.VconConversionWarning))]
  assert(len(conversion_warnings) == expected_warnings), conversion_warnings
  convert.warnings = conversion_warnings
  return(result)


# Step 19: framework, Sessions without transfers, party_history

def test_two_recordings_one_session():
  result = convert(make([recording(at(10), 30, [0, 1]), recording(at(20), 40, [1, 2])]))
  assert(result["vcon"] == "0.5.0")
  assert(result["uuid"] == UUID)
  assert("updated_at" in result)
  assert(result["sessions"] == [{"start": result["dialog"][0]["start"], "duration": 50,
    "parties": [0, 1, 2], "dialog": [0, 1]}])
  tests.common_utils.assert_valid_vcon(result)


def test_session_start_without_some_dialog_start():
  dialogs = [recording(at(10), 30, [0, 1]), recording(at(20), 40, [0, 1])]
  del dialogs[1]["start"]
  result = convert(make(dialogs))
  assert(result["sessions"][0]["start"] == result["dialog"][0]["start"])
  assert("duration" not in result["sessions"][0])

  for dialog in dialogs:
    dialog.pop("start", None)
  result = convert(make(dialogs))
  assert("start" not in result["sessions"][0])
  assert("duration" not in result["sessions"][0])


def test_originator_moves_to_session():
  result = convert(make([recording(at(10), 30, [0, 1]), recording(at(20), 40, [0, 1], originator = 1)]))
  assert(result["sessions"][0]["originator"] == 1)
  assert(all(["originator" not in dialog for dialog in result["dialog"]]))
  tests.common_utils.assert_valid_vcon(result)


def test_party_history_to_events():
  history = [{"party": 0, "event": "join", "time": at(10)}, {"party": 1, "event": "drop", "time": at(30)},
    {"party": 1, "event": "keydown", "time": at(20), "button": "5"}]
  result = convert(make([recording(at(10), 30, [0, 1], party_history = history)]))
  assert(result["events"] == [
    {"type": "join", "time": at(10), "sessions": 0, "party": 0},
    {"type": "drop", "time": at(30), "sessions": 0, "party": 1},
    {"type": "keydown", "time": at(20), "sessions": 0, "party": 1, "button": "5"}])
  assert("party_history" not in result["dialog"][0])
  tests.common_utils.assert_valid_vcon(result)


@pytest.mark.parametrize("dialog", [
  {"type": "recording-set", "start": at(0), "recordings": [1]},
  recording(at(0), 10, [0], recordings = [1]),
  recording(at(0), 10, [0], recording_set = 0)
  ])
def test_recording_set_refused(dialog):
  vcon_dict = make([dialog, recording(at(0), 10, [0, 1])])
  before = copy.deepcopy(vcon_dict)
  with pytest.raises(vcon.migrate_0_4_0.VconConversionError, match = r"dialog\[0\]"):
    vcon.migrate_0_4_0.migrate_0_4_0_vcon(vcon_dict)
  assert(vcon_dict == before)


def test_no_dialogs_no_session():
  result = convert(make([]))
  assert("sessions" not in result)
  assert(result["vcon"] == "0.5.0")
  tests.common_utils.assert_valid_vcon(result)


# Step 20: transfer Dialog Objects

def transfer(start, **references) -> dict:
  dialog = {"type": "transfer", "start": start, "transferee": 0, "transferor": 1, "transfer_target": 2}
  dialog.update(references)
  return(dialog)


def test_blind_transfer():
  result = convert(make([recording(at(0), 60, [0, 1]), recording(at(70), 60, [0, 2]),
    transfer(at(55), original = 0, target_dialog = 1)]))
  assert(result["dialog"][2] == {})
  assert(result["sessions"][0]["sessions"] == [{"session": 1, "type": "child"}, {"session": 2, "type": "child"}])
  assert("dialog" not in result["sessions"][0])
  assert(result["sessions"][1]["dialog"] == [0])
  assert(result["sessions"][2]["dialog"] == [1])
  assert(result["events"] == [{"type": "blind-transfer", "time": at(55), "sessions": 1, "party": 1,
    "transferee": 0, "transfer_target": 2, "target_session": 2}])
  tests.common_utils.assert_valid_vcon(result)


def test_consultative_transfer():
  result = convert(make([recording(at(0), 60, [0, 1]), recording(at(10), 20, [1, 2]),
    recording(at(40), 60, [0, 2]), transfer(at(5), original = 0, consultation = 1, target_dialog = 2)]))
  assert([event["type"] for event in result["events"]] == ["consultation-start", "consultative-transfer"])
  assert(result["events"][0]["time"] == at(5))
  assert(result["events"][0]["consultation"] == 2)
  assert("target_session" not in result["events"][0])
  assert(result["events"][1]["time"] == at(40))
  assert(result["events"][1]["consultation"] == 2)
  assert(result["events"][1]["target_session"] == 3)
  tests.common_utils.assert_valid_vcon(result)


def test_abandoned_after_consultation():
  result = convert(make([recording(at(0), 60, [0, 1]), recording(at(10), 20, [1, 2]),
    transfer(at(5), original = 0, consultation = 1)]))
  assert([event["type"] for event in result["events"]] == ["consultation-start", "transfer-abandoned"])
  assert(result["events"][1]["time"] == at(30))
  assert(result["events"][1]["consultation"] == 2)
  assert(result["events"][1]["transfer_target"] == 2)
  tests.common_utils.assert_valid_vcon(result)


def test_abandoned_without_consultation_or_target():
  dialogs = [recording(at(0), 60, [0, 1]), transfer(at(5), original = 0)]
  del dialogs[1]["transfer_target"]
  result = convert(make(dialogs))
  assert(result["events"] == [{"type": "transfer-abandoned", "time": at(5), "sessions": 1, "party": 1,
    "transferee": 0}])
  tests.common_utils.assert_valid_vcon(result)


def test_two_transfers_share_original_session():
  result = convert(make([recording(at(0), 60, [0, 1]), recording(at(70), 60, [0, 2]),
    transfer(at(55), original = 0, target_dialog = 1), transfer(at(65), original = 0)]))
  assert(len(result["sessions"]) == 3)
  assert([event["sessions"] for event in result["events"]] == [1, 1])


def test_no_original_placeholder_session():
  result = convert(make([recording(at(70), 60, [0, 2]), transfer(at(55), target_dialog = 0)]))
  placeholder = result["events"][0]["sessions"]
  assert(result["sessions"][placeholder] == {})
  tests.common_utils.assert_valid_vcon(result)


def test_missing_transferor_empty_party():
  dialogs = [recording(at(0), 60, [0, 1]), recording(at(70), 60, [0, 2]),
    transfer(at(55), original = 0, target_dialog = 1)]
  del dialogs[2]["transferor"]
  result = convert(make(dialogs))
  assert(result["parties"][3] == {})
  assert(result["events"][0]["party"] == 3)
  tests.common_utils.assert_valid_vcon(result)


def test_no_usable_time_warns():
  dialogs = [recording(at(0), 60, [0, 1]), recording(at(70), 60, [0, 2]),
    transfer(at(55), original = 0, target_dialog = 1)]
  del dialogs[2]["start"]
  result = convert(make(dialogs), expected_warnings = 1)
  assert("time" not in result["events"][0])
  assert("blind-transfer" in convert.warnings[0])


def test_transfer_references_removed():
  dialogs = [recording(at(0), 60, [0, 1]), recording(at(70), 60, [0, 2]),
    transfer(at(55), original = 0, target_dialog = 1)]
  analysis = [{"type": "summary", "dialog": [0, 2], "vendor": "v", "body": "s", "encoding": "none"},
    {"type": "summary", "dialog": 2, "vendor": "v", "body": "s", "encoding": "none"}]
  attachments = [{"dialog": 2, "party": 0, "start": at(0), "mediatype": "text/plain",
    "encoding": "none", "body": "a"}]
  result = convert(make(dialogs, analysis = analysis, attachments = attachments), expected_warnings = 1)
  assert(result["analysis"][0]["dialog"] == [0])
  assert("dialog" not in result["analysis"][1])
  assert("dialog" not in result["attachments"][0])
  assert("attachments[0]" in convert.warnings[0])


def test_party_history_of_original_uses_child_session():
  history = [{"party": 0, "event": "hold", "time": at(50)}]
  result = convert(make([recording(at(0), 60, [0, 1], party_history = history), recording(at(70), 60, [0, 2]),
    transfer(at(55), original = 0, target_dialog = 1)]))
  holds = [event for event in result["events"] if(event["type"] == "hold")]
  assert(holds[0]["sessions"] == 1)


def test_top_session_covers_children():
  result = convert(make([recording(at(0), 60, [0, 1]), recording(at(70), 60, [0, 2]),
    recording(at(200), 10, [0]), transfer(at(55), original = 0, target_dialog = 1)]))
  top = result["sessions"][0]
  assert(top["dialog"] == [2])
  assert(top["start"] == result["dialog"][0]["start"])
  assert(top["duration"] == 210)
  assert(top["parties"] == [0, 1, 2])


# Step 21: text and incomplete Dialog parties, email grouping, originator

def test_texts_same_receivers_one_session():
  result = convert(make([text(at(0), [0, 1, 2]), text(at(10), [1, 0, 2]), text(at(20), [2, 0, 1])]))
  assert(len(result["sessions"]) == 1)
  assert([dialog["parties"] for dialog in result["dialog"]] == [[0], [1], [2]])
  assert(result["sessions"][0]["parties"] == [0, 1, 2])
  tests.common_utils.assert_valid_vcon(result)


def test_texts_receivers_change_and_change_back():
  result = convert(make([text(at(0), [0, 1]), text(at(10), [1, 0]), text(at(20), [0, 1, 2]),
    text(at(30), [0, 1])]))
  parent = result["sessions"][0]
  assert("dialog" not in parent)
  assert(parent["sessions"] == [{"session": 1, "type": "child"}, {"session": 2, "type": "child"},
    {"session": 3, "type": "child"}])
  assert(result["sessions"][1]["dialog"] == [0, 1])
  assert(result["sessions"][1]["parties"] == [0, 1])
  assert(result["sessions"][2]["dialog"] == [2])
  assert(result["sessions"][2]["parties"] == [0, 1, 2])
  assert(result["sessions"][3]["dialog"] == [3])
  assert(parent["parties"] == [0, 1, 2])
  tests.common_utils.assert_valid_vcon(result)


def test_chat_during_recording():
  result = convert(make([recording(at(0), 100, [0, 1, 2]), text(at(10), [0, 1]), text(at(20), [0, 1, 2])]))
  parent = result["sessions"][0]
  assert(parent["dialog"] == [0])
  assert([reference["session"] for reference in parent["sessions"]] == [1, 2])
  assert(result["sessions"][1]["dialog"] == [1])
  assert(result["sessions"][2]["dialog"] == [2])
  tests.common_utils.assert_valid_vcon(result)


def test_text_originator_reduces_parties():
  result = convert(make([text(at(0), [0, 1], originator = 1)]))
  assert(result["dialog"][0]["parties"] == [1])
  assert(result["sessions"][0]["parties"] == [0, 1])
  assert(result["sessions"][0]["originator"] == 1)


def test_single_party_text_unchanged():
  result = convert(make([text(at(0), [1])]))
  assert(result["dialog"][0]["parties"] == [1])
  assert(result["sessions"][0]["parties"] == [1])


def test_incomplete_keeps_caller():
  incomplete = {"type": "incomplete", "start": at(0), "parties": [2, 0, 1], "disposition": "busy"}
  result = convert(make([incomplete]))
  assert(result["dialog"][0]["parties"] == [2])
  assert(result["sessions"][0]["parties"] == [2, 0, 1])
  tests.common_utils.assert_valid_vcon(result)


def test_originator_written_only_if_not_first_party():
  result = convert(make([recording(at(0), 10, [0, 1], originator = 0)]))
  assert("originator" not in result["sessions"][0])
  result = convert(make([recording(at(0), 10, [0, 1], originator = 1)]))
  assert(result["sessions"][0]["originator"] == 1)


def test_different_originators_warn():
  result = convert(make([recording(at(0), 10, [0, 1], originator = 1), recording(at(20), 10, [0, 1], originator = 0)]),
    expected_warnings = 1)
  assert(result["sessions"][0]["originator"] == 1)
  assert("dialog[1]: 0" in convert.warnings[0])


def test_texts_grouped_by_start_not_array_order():
  result = convert(make([text(at(20), [0, 1, 2]), text(at(0), [0, 1]), text(at(10), [1, 0])]))
  assert(result["sessions"][1]["dialog"] == [1, 2])
  assert(result["sessions"][2]["dialog"] == [0])


# Renames, extensions, version

def test_redacted_and_amended_renamed():
  redacted = {"uuid": UUID, "type": "PII"}
  result = convert(make([], redacted = redacted))
  assert(result["redacted_from"] == redacted)
  assert("redacted" not in result)
  result = convert(make([], amended = {"uuid": UUID}))
  assert(result["amended_from"] == {"uuid": UUID})
  tests.common_utils.assert_valid_vcon(result)


def test_redacted_and_amended_both_warn():
  result = convert(make([], redacted = {"uuid": "x", "type": "PII"}, amended = {"uuid": "y"}),
    expected_warnings = 1)
  assert("redacted_from" in result and "amended_from" in result)


def test_redacted_without_type_warns():
  result = convert(make([], redacted = {"uuid": "x"}), expected_warnings = 1)
  assert(result["redacted_from"] == {"uuid": "x"})


def test_unlisted_extension_added():
  vcon_dict = make([])
  vcon_dict["parties"][0]["role"] = "agent"
  result = convert(vcon_dict)
  assert(result["extensions"] == ["CC"])
  assert("critical" not in result)


def test_unusable_transfer_references_warn():
  dialogs = [recording(at(0), 60, [0, 1]), transfer(at(5), original = 0, consultation = 7, transferee = 9)]
  result = convert(make(dialogs), expected_warnings = 2)
  assert("consultation: 7" in convert.warnings[0])
  assert("transferee: 9" in convert.warnings[1])
  # treated as absent: abandoned with no consultation, an empty Party for the transferee
  assert([event["type"] for event in result["events"]] == ["transfer-abandoned"])
  assert(result["events"][0]["transferee"] == 3)
  assert(result["parties"][3] == {})


def test_abandoned_consultation_without_duration_warns():
  dialogs = [recording(at(0), 60, [0, 1]), recording(at(10), 20, [1, 2]),
    transfer(at(5), original = 0, consultation = 1)]
  del dialogs[1]["duration"]
  result = convert(make(dialogs), expected_warnings = 1)
  assert("time" not in result["events"][1])
  assert("time" in result["events"][0])


def test_other_references_kept():
  dialogs = [recording(at(0), 60, [0, 1]), recording(at(70), 60, [0, 2]),
    transfer(at(55), original = 0, target_dialog = 1)]
  analysis = [{"type": "summary", "vendor": "v", "body": "s", "encoding": "none"},
    {"type": "summary", "dialog": [2], "vendor": "v", "body": "s", "encoding": "none"},
    {"type": "summary", "dialog": [0, 1], "vendor": "v", "body": "s", "encoding": "none"}]
  result = convert(make(dialogs, analysis = analysis))
  assert("dialog" not in result["analysis"][0])
  assert("dialog" not in result["analysis"][1])
  assert(result["analysis"][2]["dialog"] == [0, 1])
