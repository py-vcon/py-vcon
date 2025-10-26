# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" Unit test for fix_recording_dialog plugin """
import vcon
import pytest


@pytest.mark.asyncio
async def test_jq_redaction():
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

  # TODO:
  # assert(original_duration == fixed_vcon.dialog[0]["duration"])

