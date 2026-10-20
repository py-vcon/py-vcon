# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.

import asyncio
import pytest
import pytest_asyncio
import smtpdfix # provides fixture smtpd, does not need to imported, but
# makes more obvious error when the fixture is not installed.
import fastapi.testclient
import vcon
import vcon.pydantic_utils
import py_vcon_server
from py_vcon_server.settings import VCON_STORAGE_URL
from common_setup import make_inline_audio_vcon, make_2_party_tel_vcon, UUID

# invoke only once for all the unit test in this module
@pytest_asyncio.fixture(autouse=True)
async def setup():
  """ Setup Vcon storage connection before test """
  vs = py_vcon_server.db.VconStorage.instantiate(VCON_STORAGE_URL)
  global VCON_STORAGE
  VCON_STORAGE = vs


  # wait until teardown time
  yield

  # Shutdown the Vcon storage after test
  VCON_STORAGE = None
  await vs.shutdown()

@pytest.mark.asyncio
async def test_send_email(make_inline_audio_vcon, smtpd):
  in_vcon = make_inline_audio_vcon
  assert(isinstance(in_vcon, vcon.Vcon))

  # Setup inputs
  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(in_vcon, "fake_lock", False) # read/write
  assert(len(proc_input._vcons) == 1)

  email_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("send_email")


  email_proc_options = email_proc_inst.processor_options_class()(
      smtp_host = smtpd.hostname,
      smtp_port = smtpd.port,
      from_address = "unit_tests@py_vcon_server.org",
      to = ["me@example.com"],
      subject = "First email proc test",
      text_body = "hello vCon world"
    )

  print("using email proc options: {}".format(vcon.pydantic_utils.get_dict(email_proc_options, exclude_none=True)))
  proc_output = await email_proc_inst.process(proc_input, email_proc_options)

  print("faux SMTP host: {} port: {}".format(smtpd.hostname, smtpd.port))
  print("type: {}".format(type(smtpd)))
  print("dir: {}".format(dir(smtpd)))

  print("SMTP messages: {}".format(smtpd.messages))
  if(len(smtpd.messages) < 1):
    await asyncio.sleep(10)
  assert(len(smtpd.messages) == 1)
  print("SMTP message[0]: {}".format(smtpd.messages[0]))
  assert(smtpd.messages[0]["To"] == "me@example.com")
  assert(smtpd.messages[0]["From"] == "unit_tests@py_vcon_server.org")
  assert(smtpd.messages[0]["Subject"] == "First email proc test")
  assert(smtpd.messages[0].get_content_type() == "text/plain")
  assert("hello vCon world" in smtpd.messages[0].get_payload())


@pytest.mark.asyncio
async def test_send_email_html_only(make_inline_audio_vcon, smtpd):
  """ Test sending HTML-only email with empty text_body """
  in_vcon = make_inline_audio_vcon
  assert(isinstance(in_vcon, vcon.Vcon))

  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(in_vcon, "fake_lock", False)

  email_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("send_email")

  email_proc_options = email_proc_inst.processor_options_class()(
      smtp_host = smtpd.hostname,
      smtp_port = smtpd.port,
      from_address = "unit_tests@py_vcon_server.org",
      to = ["me@example.com"],
      subject = "HTML only email test",
      text_body = "",
      html_body = "<h1>Hello</h1><p>vCon world</p>"
    )

  proc_output = await email_proc_inst.process(proc_input, email_proc_options)

  print("SMTP messages: {}".format(smtpd.messages))
  if(len(smtpd.messages) < 1):
    await asyncio.sleep(10)
  assert(len(smtpd.messages) == 1)
  print("SMTP message[0]: {}".format(smtpd.messages[0]))
  assert(smtpd.messages[0]["Subject"] == "HTML only email test")
  assert(smtpd.messages[0].get_content_type() == "text/html")
  payload = smtpd.messages[0].get_payload()
  assert("<h1>Hello</h1>" in payload)
  assert("<p>vCon world</p>" in payload)


@pytest.mark.asyncio
async def test_send_email_multipart(make_inline_audio_vcon, smtpd):
  """ Test sending multipart/alternative email with both text and HTML bodies """
  in_vcon = make_inline_audio_vcon
  assert(isinstance(in_vcon, vcon.Vcon))

  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(in_vcon, "fake_lock", False)

  email_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("send_email")

  email_proc_options = email_proc_inst.processor_options_class()(
      smtp_host = smtpd.hostname,
      smtp_port = smtpd.port,
      from_address = "unit_tests@py_vcon_server.org",
      to = ["me@example.com"],
      subject = "Multipart email test",
      text_body = "hello vCon world",
      html_body = "<h1>Hello</h1><p>vCon world</p>"
    )

  proc_output = await email_proc_inst.process(proc_input, email_proc_options)

  print("SMTP messages: {}".format(smtpd.messages))
  if(len(smtpd.messages) < 1):
    await asyncio.sleep(10)
  assert(len(smtpd.messages) == 1)
  msg = smtpd.messages[0]
  print("SMTP message[0]: {}".format(msg))
  assert(msg["Subject"] == "Multipart email test")
  assert(msg.get_content_type() == "multipart/alternative")
  parts = msg.get_payload()
  assert(isinstance(parts, list))
  assert(len(parts) == 2)
  # First part should be text/plain
  assert(parts[0].get_content_type() == "text/plain")
  assert("hello vCon world" in parts[0].get_payload())
  # Second part should be text/html
  assert(parts[1].get_content_type() == "text/html")
  html_payload = parts[1].get_payload()
  assert("<h1>Hello</h1>" in html_payload)
  assert("<p>vCon world</p>" in html_payload)


@pytest.mark.asyncio
async def test_send_email_both_empty(make_inline_audio_vcon, smtpd):
  """ Test sending email with both text_body and html_body empty (permissive) """
  in_vcon = make_inline_audio_vcon
  assert(isinstance(in_vcon, vcon.Vcon))

  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(in_vcon, "fake_lock", False)

  email_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("send_email")

  email_proc_options = email_proc_inst.processor_options_class()(
      smtp_host = smtpd.hostname,
      smtp_port = smtpd.port,
      from_address = "unit_tests@py_vcon_server.org",
      to = ["me@example.com"],
      subject = "Empty body email test",
      text_body = "",
      html_body = ""
    )

  proc_output = await email_proc_inst.process(proc_input, email_proc_options)

  print("SMTP messages: {}".format(smtpd.messages))
  if(len(smtpd.messages) < 1):
    await asyncio.sleep(10)
  assert(len(smtpd.messages) == 1)
  msg = smtpd.messages[0]
  print("SMTP message[0]: {}".format(msg))
  assert(msg["Subject"] == "Empty body email test")
  # Both empty falls through to text/plain with empty body
  assert(msg.get_content_type() == "text/plain")


@pytest.mark.asyncio
async def test_send_email_cc_bcc(make_inline_audio_vcon, smtpd):
  """ Test that cc and bcc headers are set correctly """
  in_vcon = make_inline_audio_vcon
  assert(isinstance(in_vcon, vcon.Vcon))

  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(in_vcon, "fake_lock", False)

  email_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("send_email")

  email_proc_options = email_proc_inst.processor_options_class()(
      smtp_host = smtpd.hostname,
      smtp_port = smtpd.port,
      from_address = "unit_tests@py_vcon_server.org",
      to = ["me@example.com"],
      cc = ["cc1@example.com", "cc2@example.com"],
      bcc = ["bcc1@example.com"],
      subject = "CC and BCC test",
      text_body = "testing cc and bcc"
    )

  proc_output = await email_proc_inst.process(proc_input, email_proc_options)

  print("SMTP messages: {}".format(smtpd.messages))
  if(len(smtpd.messages) < 1):
    await asyncio.sleep(10)
  assert(len(smtpd.messages) == 1)
  msg = smtpd.messages[0]
  print("SMTP message[0]: {}".format(msg))
  assert(msg["To"] == "me@example.com")
  assert(msg["Cc"] == "cc1@example.com,cc2@example.com")
  # Note: BCC headers are stripped from delivered messages per SMTP spec.
  # We verify bcc was accepted without error but cannot assert on the header.
  #assert(msg["Bcc"] == "bcc1@example.com")
  assert(msg["Subject"] == "CC and BCC test")
  assert(msg.get_content_type() == "text/plain")
  assert("testing cc and bcc" in msg.get_payload())


@pytest.mark.asyncio
async def test_send_email_version(make_inline_audio_vcon, smtpd):
  """ Test that the send_email processor version has been bumped """
  email_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("send_email")
  assert(email_proc_inst.version() == "0.1.0")


@pytest.mark.asyncio
async def test_send_email_api(make_inline_audio_vcon, smtpd):
  in_vcon = make_inline_audio_vcon
  assert(isinstance(in_vcon, vcon.Vcon))

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    # Put the vCon in the DB, don't really care what is looks like as
    # its not used.
    set_response = client.post("/vcon", json = in_vcon.dumpd())
    assert(set_response.status_code == 204)

    parameters = {
        "commit_changes": False,
        "return_whole_vcon": False
      }
    email_proc_options = {
        "smtp_host": smtpd.hostname,
        "smtp_port": smtpd.port,
        "from_address": "unit_tests@py_vcon_server.org",
        "to": ["me@example.com"],
        "subject": "First email proc test",
        "text_body": "hello vCon world"
      }

    post_response = client.post("/process/{}/send_email".format(UUID),
        params = parameters,
        json = email_proc_options
      )
    assert(post_response.status_code == 200)

    print("SMTP messages: {}".format(smtpd.messages))
    if(len(smtpd.messages) < 1):
      await asyncio.sleep(10)
    assert(len(smtpd.messages) == 1)
    print("SMTP message[0]: {}".format(smtpd.messages[0]))
    assert(smtpd.messages[0]["To"] == "me@example.com")
    assert(smtpd.messages[0]["From"] == "unit_tests@py_vcon_server.org")
    assert(smtpd.messages[0]["Subject"] == "First email proc test")
    assert(smtpd.messages[0].get_content_type() == "text/plain")
    assert("hello vCon world" in smtpd.messages[0].get_payload())

    # Clean up
    client.delete("/vcon/{}".format(UUID))
