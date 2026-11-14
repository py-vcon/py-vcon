# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" The deprecated add Dialog method names call the new names """

import pytest
import vcon

START = "2022-06-21T13:53:26-04:00"
SMTP_MESSAGE_FILE_NAME = "tests/email_acct_prob_bob_image.txt"


def make_vcon() -> vcon.Vcon:
  v = vcon.Vcon()
  v.set_party_parameter("tel", "+15551110000")
  v.set_party_parameter("tel", "+15552220000")
  return(v)


def smtp_message() -> str:
  with open(SMTP_MESSAGE_FILE_NAME, "r") as smtp_file:
    return(smtp_file.read())


CASES = [
    ("add_dialog_inline_text", "add_text_dialog_inline",
      ("Hello", START, 5, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN), {"file_name": "hello.txt"}),
    ("add_dialog_inline_recording", "add_recording_dialog_inline",
      (b"\x00\x01\x02", START, 10, [0, 1], "audio/x-wav"), {"file_name": "a.wav", "originator": 1}),
    ("add_dialog_external_recording", "add_recording_dialog_external",
      (b"\x00\x01\x02", START, 10, [0, 1], "https://example.com/a.wav"), {"media_type": "audio/x-wav"}),
    ("add_dialog_inline_email_message", "add_email_dialog_inline",
      (smtp_message(),), {"file_name": "message.eml"})
  ]


@pytest.mark.parametrize("old_name, new_name, args, kwargs", CASES)
def test_deprecated_name(old_name, new_name, args, kwargs):
  old_vcon = make_vcon()
  with pytest.warns(DeprecationWarning, match = "{}.*use {}".format(old_name, new_name)):
    old_index = getattr(old_vcon, old_name)(*args, **kwargs)

  new_vcon = make_vcon()
  new_index = getattr(new_vcon, new_name)(*args, **kwargs)

  assert(old_index == new_index == 0)
  for name in ["parties", "dialog", "sessions", "attachments"]:
    assert(old_vcon._vcon_dict.get(name, None) == new_vcon._vcon_dict.get(name, None)), name
