import os
import vcon
import pytest


SMTP_MESSAGE_W_IMAGE_FILE_NAME = "tests/email_acct_prob_bob_image.txt"


@pytest.mark.asyncio
async def test_add_email_multipart():
  """ Test import of a SMTP message with multipart body """

  out_vcon = vcon.Vcon()

  # get a SMTP message from a file
  with open(SMTP_MESSAGE_W_IMAGE_FILE_NAME, "r") as smtp_message_file:
    smtp_message_string = smtp_message_file.read()

  # add the email message as a dialog along with its paties if not 
  # already in the vcon
  out_vcon.add_dialog_inline_email_message(
    smtp_message_string,
    os.path.basename(SMTP_MESSAGE_W_IMAGE_FILE_NAME)
    )

  out_vcon.set_uuid("py-vcon.com")

  assert(len(out_vcon.parties) == 2)
  assert(len(out_vcon.parties[0].keys()) == 2)
  assert(len(out_vcon.parties[1].keys()) == 2)
  assert(out_vcon.subject == "Account problem")
  assert(out_vcon.parties[0]["name"] == "Bob")
  assert(out_vcon.parties[1]["name"] == "Alice")
  assert(out_vcon.parties[0]["mailto"] == "b@example.com")
  assert(out_vcon.parties[1]["mailto"] == "a@example.com")
  assert(len(out_vcon.dialog) == 1)
  assert(out_vcon.dialog[0]["type"] == "text")
  assert(out_vcon.dialog[0]["parties"] == [0, 1])
  assert(out_vcon.dialog[0]["mimetype"][:len(vcon.Vcon.MIMETYPE_MULTIPART)] == vcon.Vcon.MIMETYPE_MULTIPART)
  assert(out_vcon.dialog[0]["start"] == "2022-09-23T21:44:25.000+00:00")
  assert(out_vcon.dialog[0]["duration"] == 0)
  assert(len(out_vcon.dialog[0]["body"]) == 2048)
  assert(out_vcon.dialog[0]["encoding"] is None or
    out_vcon.dialog[0]["encoding"].lower() == "none")
  # TODO: fix:
  #assert(len(out_vcon.attachments) == 1)
  #assert(out_vcon.attachments[0]["mimetype"] == vcon.Vcon.MIMETYPE_IMAGE_PNG)
  # TODO: fix:
  # fix:
  #assert(out_vcon.attachments[0]["encoding"] is "base64")
  #assert(len(out_vcon.attachments[0]["body"]) == 402)

  texts = await out_vcon.get_dialog_text(0)
  assert(len(texts) == 1)
  assert(texts[0]["text"] == 'Alice:Please find the image attached.\r\n\r\nRegards,Bob\r\n')

