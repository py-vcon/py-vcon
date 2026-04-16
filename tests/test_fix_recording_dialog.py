# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" Unit test for fix_recording_dialog plugin """
import vcon
import pytest
import pytest_httpserver


@pytest.mark.asyncio
async def test_fix_recording_dialog():
  external_vcon = vcon.Vcon()
  external_vcon.load("tests/ab_call_ext_rec_0.0.1.vcon")
  assert(len(external_vcon.dialog)  == 1)
  assert(len(external_vcon.dialog[0]["url"]) > 0)
  assert(external_vcon.dialog[0]["duration"] > 0)
  assert(len(external_vcon.dialog[0]["content_hash"]) > 0)
  original_hash = external_vcon.dialog[0]["content_hash"]
  original_duration = external_vcon.dialog[0]["duration"]

  external_vcon._vcon_dict["dialog"][0]["duration"] = 0
  del external_vcon._vcon_dict["dialog"][0]["content_hash"]
  assert(external_vcon.dialog[0]["duration"] == 0)
  assert("content_hash" not in  external_vcon.dialog[0])
  options = { "input_dialogs": [0]}
  fixed_vcon = await external_vcon.fix_recording_dialog(options)


  assert(original_hash == fixed_vcon.dialog[0]["content_hash"])

  print(f"duration: {fixed_vcon.dialog[0]['duration']}")
  assert(original_duration == fixed_vcon.dialog[0]["duration"])

@pytest.mark.asyncio
async def test_fix_recording_dialog_http_error(
  httpserver: pytest_httpserver.HTTPServer
  ):
  """ Test that a non-2xx response is logged and the dialog is skipped """
  httpserver.expect_request("/rec.wav").respond_with_data(
    "not found", status=404
    )

  test_vcon = vcon.Vcon()
  test_vcon.set_party_parameter("tel", "+1234567890")
  test_vcon.set_party_parameter("tel", "+0987654321")
  url = "http://{}:{}/rec.wav".format(httpserver.host, httpserver.port)

  import datetime
  import os
  fake_body = os.urandom(256)
  test_vcon.add_dialog_external_recording(
    fake_body,
    datetime.datetime.utcnow(),
    0,
    [0, 1],
    url,
    vcon.Vcon.MEDIATYPE_AUDIO_WAV,
    "rec.wav"
    )

  # Remove content_hash so we can verify it stays absent after the failed fetch
  del test_vcon._vcon_dict["dialog"][0]["content_hash"]
  assert("content_hash" not in test_vcon.dialog[0])

  options = {"input_dialogs": [0]}
  fixed_vcon = await test_vcon.fix_recording_dialog(options)

  # Dialog should be unchanged — http error causes continue, no hash or duration update
  assert("content_hash" not in fixed_vcon.dialog[0])

