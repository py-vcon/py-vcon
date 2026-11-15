# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" Unit tests for add_transfer_dialog, which adds transfer Event Objects """
import pytest
import vcon
import tests.common_utils

TRANSFEREE = 0
TRANSFEROR = 1
TRANSFER_TARGET = 2


def make_vcon() -> vcon.Vcon:
  """
  three parties; Dialogs, each in its own Session: 0 original call, 1
  consultation, 2 target call, each 60 s, a minute apart
  """
  v = vcon.Vcon()
  v.set_uuid("example.com")
  for tel in ["+15551110000", "+15552220000", "+15553330000"]:
    v.set_party_parameter("tel", tel)
  v.add_text_dialog_inline("original", "2022-06-21T13:00:00-04:00", 60, [TRANSFEREE, TRANSFEROR],
    vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.add_text_dialog_inline("consult", "2022-06-21T13:01:00-04:00", 60, [TRANSFEROR, TRANSFER_TARGET],
    vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.add_text_dialog_inline("target", "2022-06-21T13:02:00-04:00", 60, [TRANSFEREE, TRANSFER_TARGET],
    vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  return(v)


def add_transfer(v : vcon.Vcon, target, consultation) -> list:
  with pytest.warns(DeprecationWarning, match = "transfer Event Objects are added instead"):
    return(v.add_transfer_dialog(TRANSFEREE, TRANSFEROR, TRANSFER_TARGET, 0, target, consultation))


def test_blind():
  v = make_vcon()
  assert(add_transfer(v, 2, None) == [0])
  assert(v.events == [{"type": "blind-transfer", "time": "2022-06-21T17:02:00.000+00:00", "sessions": 0,
    "party": TRANSFEROR, "transferee": TRANSFEREE, "transfer_target": TRANSFER_TARGET, "target_session": 2}])
  # no transfer Dialog
  assert(len(v.dialog) == 3)
  tests.common_utils.assert_valid_vcon(v.dumpd())


def test_consultative():
  v = make_vcon()
  assert(add_transfer(v, 2, 1) == [0, 1])
  assert(v.events[0] == {"type": "consultation-start", "time": "2022-06-21T17:01:00.000+00:00", "sessions": 0,
    "party": TRANSFEROR, "transferee": TRANSFEREE, "transfer_target": TRANSFER_TARGET, "consultation": 1})
  assert(v.events[1] == {"type": "consultative-transfer", "time": "2022-06-21T17:02:00.000+00:00", "sessions": 0,
    "party": TRANSFEROR, "transferee": TRANSFEREE, "transfer_target": TRANSFER_TARGET, "consultation": 1,
    "target_session": 2})
  tests.common_utils.assert_valid_vcon(v.dumpd())


def test_abandoned_after_consultation():
  v = make_vcon()
  assert(add_transfer(v, None, 1) == [0, 1])
  assert(v.events[0]["type"] == "consultation-start")
  # at the end of the consultation
  assert(v.events[1] == {"type": "transfer-abandoned", "time": "2022-06-21T17:02:00.000+00:00", "sessions": 0,
    "party": TRANSFEROR, "transferee": TRANSFEREE, "transfer_target": TRANSFER_TARGET, "consultation": 1})
  tests.common_utils.assert_valid_vcon(v.dumpd())


def test_abandoned_without_consultation():
  v = make_vcon()
  assert(add_transfer(v, None, None) == [0])
  # at the end of the original call
  assert(v.events == [{"type": "transfer-abandoned", "time": "2022-06-21T17:01:00.000+00:00", "sessions": 0,
    "party": TRANSFEROR, "transferee": TRANSFEREE, "transfer_target": TRANSFER_TARGET}])
  tests.common_utils.assert_valid_vcon(v.dumpd())


def no_duration(v : vcon.Vcon) -> None:
  del v._vcon_dict["dialog"][1]["duration"]


def no_start(v : vcon.Vcon) -> None:
  del v._vcon_dict["dialog"][2]["start"]


def shared_session(v : vcon.Vcon) -> None:
  v._vcon_dict["sessions"][0]["dialog"].append(2)
  v._vcon_dict["sessions"][2]["dialog"] = []


def two_sessions(v : vcon.Vcon) -> None:
  v._vcon_dict["sessions"][1]["dialog"].append(2)


def no_session(v : vcon.Vcon) -> None:
  v._vcon_dict["sessions"][2]["dialog"] = []


@pytest.mark.parametrize("label, prepare, arguments, message", [
    ("missing dialog", None, (0, 1, 2, 0, 3, None), "target dialog: 3 does not exist"),
    ("dialog in no Session", no_session, (0, 1, 2, 0, 2, None), "referenced by 0 Session Objects"),
    ("dialog in two Sessions", two_sessions, (0, 1, 2, 0, 2, 1), "referenced by 2 Session Objects"),
    ("shared Session", shared_session, (0, 1, 2, 0, 2, None), "another of the transfer dialogs"),
    ("party out of range", None, (0, 3, 2, 0, 2, None), "transferor party: 3 does not exist"),
    ("missing start", no_start, (0, 1, 2, 0, 2, None), "needs a start"),
    ("missing duration", no_duration, (0, 1, 2, 0, None, 1), "needs a start and duration")
  ])
def test_errors(label, prepare, arguments, message):
  v = make_vcon()
  if(prepare is not None):
    prepare(v)
  with pytest.warns(DeprecationWarning):
    with pytest.raises(AttributeError, match = message):
      v.add_transfer_dialog(*arguments)
  assert(len(v.events) == 0), label
  assert(len(v.dialog) == 3), label
