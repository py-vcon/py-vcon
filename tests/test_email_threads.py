# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" Unit tests for email threads, Bcc and the SMTP input check """

import logging
import sys
import pytest
import vcon
import tests.common_utils


ALICE = "Alice <a@example.com>"
BOB = "Bob <b@example.com>"
CAROL = "Carol <c@example.com>"
DAVE = "Dave <d@example.com>"


def make_message(
  sender : str,
  to : str,
  message_id : str,
  minute : int,
  cc : str = "",
  bcc : str = "",
  in_reply_to : str = "",
  references : str = ""
  ) -> str:
  headers = "From: {}\r\nTo: {}\r\n".format(sender, to)
  if(cc != ""):
    headers += "Cc: {}\r\n".format(cc)
  if(bcc != ""):
    headers += "Bcc: {}\r\n".format(bcc)
  if(in_reply_to != ""):
    headers += "In-Reply-To: {}\r\n".format(in_reply_to)
  if(references != ""):
    headers += "References: {}\r\n".format(references)
  headers += ("Subject: Test\r\nDate: Fri, 23 Sep 2022 21:{:02d}:00 +0000\r\n"
    "Message-ID: {}\r\nContent-Type: text/plain\r\n".format(minute, message_id))
  return(headers + "\r\nHello\r\n")


# A thread: M1 Alice to Bob, M2 Bob's reply, M3 Alice's reply adding Carol
M1 = make_message(ALICE, BOB, "<1@example.com>", 1)
M2 = make_message(BOB, ALICE, "<2@example.com>", 2, in_reply_to = "<1@example.com>",
  references = "<1@example.com>")
M3 = make_message(ALICE, BOB, "<3@example.com>", 3, cc = CAROL, in_reply_to = "<1@example.com>",
  references = "<1@example.com>")


def party_set(v : vcon.Vcon, session : dict) -> frozenset:
  return(frozenset(v.parties[party_index]["mailto"] for party_index in session.get("parties", [])))


def thread_shape(v : vcon.Vcon, thread : int = 0) -> list:
  """ (receivers, Message-IDs in order) of each child, or of the thread Session if it has none """
  sessions = v.sessions
  children = [reference["session"] for reference in sessions[thread].get("sessions", [])
    if(reference["type"] == "child")]
  return([(party_set(v, sessions[holder]),
    [v.dialog[dialog_index]["message_id"] for dialog_index in sessions[holder]["dialog"]])
    for holder in (children or [thread])])


def warnings_text(caplog) -> str:
  return(" ".join(record.getMessage() for record in caplog.records if(record.levelno >= logging.WARNING)))


def assert_valid(v : vcon.Vcon) -> None:
  if(v.uuid is None):
    v.set_uuid("example.com")
  tests.common_utils.assert_valid_vcon(v.dumpd())


def test_reply_same_receivers_one_session(caplog):
  v = vcon.Vcon()
  with caplog.at_level(logging.WARNING):
    v.add_email_dialog_inline(make_message(ALICE, BOB, "<1@example.com>", 1))
    v.add_email_dialog_inline(make_message(BOB, ALICE, "<2@example.com>", 2, in_reply_to = "<1@example.com>"))
  assert(warnings_text(caplog) == "")
  assert(len(v.sessions) == 1)
  assert(v.sessions[0]["dialog"] == [0, 1])
  assert(v.sessions[0]["parties"] == [0, 1])
  assert("sessions" not in v.sessions[0])
  assert_valid(v)


def test_reply_found_through_references():
  v = vcon.Vcon()
  v.add_email_dialog_inline(make_message(ALICE, BOB, "<1@example.com>", 1))
  v.add_email_dialog_inline(make_message(BOB, ALICE, "<2@example.com>", 2,
    references = "<0@example.com> <1@example.com>"))
  assert(len(v.sessions) == 1)
  assert(v.sessions[0]["dialog"] == [0, 1])


def test_receivers_change_children():
  v = vcon.Vcon()
  for message in [M1, M2, M3]:
    v.add_email_dialog_inline(message)
  assert(len(v.sessions) == 3)
  parent = v.sessions[0]
  assert("dialog" not in parent)
  assert(parent["parties"] == [0, 1, 2])
  assert(parent["sessions"] == [{"session": 1, "type": "child"}, {"session": 2, "type": "child"}])
  assert(v.sessions[1]["dialog"] == [0, 1])
  assert(v.sessions[1]["parties"] == [0, 1])
  assert(v.sessions[2]["dialog"] == [2])
  assert(v.sessions[2]["parties"] == [0, 1, 2])
  # the parent spans all of the messages
  assert(parent["start"] == v.dialog[0]["start"])
  assert(parent["duration"] == 120)
  assert(v.sessions[1]["start"] == v.dialog[0]["start"])
  assert(v.sessions[1]["duration"] == 60)
  assert(v.sessions[2]["start"] == v.dialog[2]["start"])
  assert_valid(v)

  # same receivers as child 2: joins it
  v.add_email_dialog_inline(make_message(BOB, ALICE, "<4@example.com>", 4, cc = CAROL,
    in_reply_to = "<3@example.com>"))
  assert(len(v.sessions) == 3)
  assert(v.sessions[2]["dialog"] == [2, 3])
  assert(v.sessions[0]["parties"] == [0, 1, 2])
  assert(len(v.sessions[0]["sessions"]) == 2)

  # back to the original receivers: a third child
  v.add_email_dialog_inline(make_message(ALICE, BOB, "<5@example.com>", 5, in_reply_to = "<4@example.com>"))
  assert(len(v.sessions) == 4)
  assert(v.sessions[3]["dialog"] == [4])
  assert(v.sessions[3]["parties"] == [0, 1])
  assert(v.sessions[0]["sessions"][2] == {"session": 3, "type": "child"})
  assert(v.sessions[0]["duration"] == 240)
  assert_valid(v)


def test_no_reply_headers_new_session(caplog):
  v = vcon.Vcon()
  with caplog.at_level(logging.WARNING):
    v.add_email_dialog_inline(make_message(ALICE, BOB, "<1@example.com>", 1))
    v.add_email_dialog_inline(make_message(BOB, ALICE, "<2@example.com>", 2))
  assert(warnings_text(caplog) == "")
  assert(len(v.sessions) == 2)
  assert(v.sessions[0]["dialog"] == [0])
  assert(v.sessions[1]["dialog"] == [1])
  assert(v.sessions[1]["parties"] == [1, 0])


def test_unknown_reply_new_session():
  v = vcon.Vcon()
  v.add_email_dialog_inline(make_message(ALICE, BOB, "<1@example.com>", 1))
  v.add_email_dialog_inline(make_message(BOB, ALICE, "<2@example.com>", 2,
    in_reply_to = "<9@example.com>", references = "<9@example.com>"))
  assert(len(v.sessions) == 2)


def test_bcc():
  message = make_message(ALICE, BOB, "<1@example.com>", 1, cc = CAROL, bcc = DAVE)
  v = vcon.Vcon()
  v.add_email_dialog_inline(message)
  assert(len(v.parties) == 3)
  assert(v.sessions[0]["parties"] == [0, 1, 2])

  v = vcon.Vcon()
  v.add_email_dialog_inline(message, include_bcc = True)
  assert(len(v.parties) == 4)
  assert(v.parties[3]["mailto"] == "d@example.com")
  assert(v.sessions[0]["parties"] == [0, 1, 2, 3])
  assert(v.dialog[0]["parties"] == [0])
  # headers are not kept in the Dialog content
  assert("d@example.com" not in v.dialog[0]["body"])
  assert_valid(v)


@pytest.mark.asyncio
async def test_bcc_cli(capsys, tmp_path):
  import vcon.cli
  email_file = tmp_path / "bcc.txt"
  email_file.write_text(make_message(ALICE, BOB, "<1@example.com>", 1, bcc = DAVE))

  for arguments, party_count in [([], 2), (["--include-bcc"], 3)]:
    await vcon.cli.main(["-n", "add", "in-email", str(email_file)] + arguments)
    out_vcon_json, error = capsys.readouterr()
    print("stderr: {}".format(error), file = sys.stderr)
    out_vcon = vcon.Vcon()
    out_vcon.loads(out_vcon_json)
    assert(len(out_vcon.parties) == party_count)
    assert(out_vcon.sessions[0]["parties"] == list(range(party_count)))


def test_given_session_no_thread_logic():
  v = vcon.Vcon()
  v.add_email_dialog_inline(M1)
  v.add_email_dialog_inline(make_message(BOB, ALICE, "<2@example.com>", 2, cc = CAROL), session = 0)
  assert(len(v.sessions) == 1)
  assert(v.sessions[0]["dialog"] == [0, 1])
  assert(v.sessions[0]["parties"] == [0, 1, 2])
  # a reply given another session does not regroup the thread
  session = v.add_session()
  v.add_email_dialog_inline(make_message(ALICE, BOB, "<3@example.com>", 3, in_reply_to = "<1@example.com>"),
    session = session)
  assert(len(v.sessions) == 2)
  assert(v.sessions[1]["dialog"] == [2])
  assert("sessions" not in v.sessions[0])


@pytest.mark.parametrize("message", [
  "Hello there",
  "To: Bob <b@example.com>\r\nDate: Fri, 23 Sep 2022 21:01:00 +0000\r\n\r\nHello\r\n",
  "From: Alice\r\nTo: Bob <b@example.com>\r\nDate: Fri, 23 Sep 2022 21:01:00 +0000\r\n\r\nHello\r\n",
  "From: Alice <a@example.com>\r\nTo: Bob <b@example.com>\r\n\r\nHello\r\n",
  "From: Alice <a@example.com>\r\nTo: Bob <b@example.com>\r\nDate: someday\r\n\r\nHello\r\n"
  ])
def test_smtp_input_check(message):
  v = vcon.Vcon()
  v.set_uuid("example.com")
  v.add_email_dialog_inline(M1)
  before = v.dumps()
  with pytest.raises(ValueError):
    v.add_email_dialog_inline(message)
  with pytest.raises(ValueError):
    v.add_email_dialogs_inline([M2, message])
  assert(v.dumps() == before)


def test_draft_examples_one_session_per_thread():
  for file_names, dialog_count in [
    (["tests/email_acct_prob_bob_image.txt", "tests/email_acct_prob_alice_reply.txt"], 2),
    (["tests/email_prob_followup_bob_reply.txt", "tests/email_prob_followup_alice.txt",
      "tests/email_prob_followup_alice_ack.txt"], 3)
    ]:
    v = vcon.Vcon()
    for file_name in file_names:
      with open(file_name, "r") as email_file:
        v.add_email_dialog_inline(email_file.read(), file_name)
    assert(len(v.sessions) == 1)
    assert(v.sessions[0]["dialog"] == list(range(dialog_count)))
    assert(v.sessions[0]["parties"] == [0, 1])
    assert_valid(v)


def test_reply_headers_written():
  v = vcon.Vcon()
  v.add_email_dialog_inline(M1)
  v.add_email_dialog_inline(make_message(BOB, ALICE, "<2@example.com>", 2, in_reply_to = " <1@example.com> ",
    references = "<0@example.com>\r\n <1@example.com>"))
  assert("in_reply_to" not in v.dialog[0])
  assert("references" not in v.dialog[0])
  assert(v.dialog[0]["message_id"] == "<1@example.com>")
  assert(v.dialog[1]["in_reply_to"] == ["<1@example.com>"])
  assert(v.dialog[1]["references"] == ["<0@example.com>", "<1@example.com>"])
  assert_valid(v)


@pytest.mark.parametrize("order", [[1, 2, 0], [2, 0, 1], [2, 1, 0]])
def test_arrival_order(order):
  in_order = vcon.Vcon()
  for message in [M1, M2, M3]:
    in_order.add_email_dialog_inline(message)

  v = vcon.Vcon()
  for message_index in order:
    v.add_email_dialog_inline([M1, M2, M3][message_index])
  assert(len(v.sessions) == 3)
  assert(thread_shape(v) == thread_shape(in_order))
  assert(v.sessions[0]["start"] == in_order.sessions[0]["start"])
  assert(v.sessions[0]["duration"] == in_order.sessions[0]["duration"])
  assert_valid(v)


def test_earlier_message_regroups():
  v = vcon.Vcon()
  for message in [M1, M2, M3]:
    v.add_email_dialog_inline(message)
  # an earlier message, to Dave as well, which M1 is a reply to
  v.add_email_dialog_inline(make_message(BOB, ALICE, "<0@example.com>", 0, cc = DAVE))
  # not linked yet: M1 has no reply headers
  assert(len(v.sessions) == 4)

  v = vcon.Vcon()
  for message in [M1, M2, M3]:
    v.add_email_dialog_inline(message)
  v.add_email_dialog_inline(make_message(BOB, ALICE, "<0@example.com>", 0, cc = DAVE,
    references = "<1@example.com>"))
  assert(len(v.sessions) == 4)
  # existing children keep their indices, the new run is first in the parent
  assert(v.sessions[0]["sessions"] == [{"session": 3, "type": "child"},
    {"session": 1, "type": "child"}, {"session": 2, "type": "child"}])
  assert(v.sessions[3]["dialog"] == [3])
  assert(v.sessions[1]["dialog"] == [0, 1])
  assert(v.sessions[2]["dialog"] == [2])
  assert(v.sessions[0]["start"] == v.dialog[3]["start"])
  assert(v.sessions[0]["duration"] == 180)
  assert(v.sessions[0]["parties"] == [0, 1, 2, 3])
  assert_valid(v)

  # a message splitting a run: the later part of the run gets a new child
  v.add_email_dialog_inline(make_message(CAROL, ALICE, "<9@example.com>", 1, in_reply_to = "<1@example.com>"))
  assert([message_ids for receivers, message_ids in thread_shape(v)] ==
    [["<0@example.com>"], ["<1@example.com>"], ["<9@example.com>"], ["<2@example.com>"], ["<3@example.com>"]])
  assert(v.sessions[0]["sessions"] == [{"session": 3, "type": "child"}, {"session": 1, "type": "child"},
    {"session": 4, "type": "child"}, {"session": 5, "type": "child"}, {"session": 2, "type": "child"}])
  assert(v.sessions[1]["dialog"] == [0])
  assert(v.sessions[1]["duration"] == 0)
  assert(v.sessions[5]["dialog"] == [1])
  assert_valid(v)


def test_bridging_message_joins_earliest(caplog):
  v = vcon.Vcon()
  v.add_email_dialog_inline(make_message(ALICE, BOB, "<1@example.com>", 1))
  v.add_email_dialog_inline(make_message(CAROL, DAVE, "<2@example.com>", 2))
  assert(len(v.sessions) == 2)
  with caplog.at_level(logging.WARNING):
    v.add_email_dialog_inline(make_message(ALICE, BOB, "<3@example.com>", 3,
      references = "<1@example.com> <2@example.com>"))
  assert("[0, 1]" in warnings_text(caplog))
  assert(len(v.sessions) == 2)
  assert(v.sessions[0]["dialog"] == [0, 2])
  assert(v.sessions[1]["dialog"] == [1])


def test_batch_out_of_order():
  in_order = vcon.Vcon()
  in_order.set_uuid("example.com")
  in_order.add_email_dialogs_inline([M1, M2, M3])

  v = vcon.Vcon()
  v.set_uuid("example.com")
  dialog_indices = v.add_email_dialogs_inline([M3, M1, M2])
  # indices are returned in the order given; the messages are added in Date order
  assert(dialog_indices == [2, 0, 1])
  assert(v.dumpd()["dialog"] == in_order.dumpd()["dialog"])
  assert(v.dumpd()["sessions"] == in_order.dumpd()["sessions"])
  assert(len(v.sessions) == 3)
