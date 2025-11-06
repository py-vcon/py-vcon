# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.

import asyncio
import pytest
import pytest_asyncio
import fastapi.testclient
import vcon
import py_vcon_server


@pytest.mark.asyncio
async def test_fix_recording_dialog_processor():
  in_vcon = vcon.Vcon()
  in_vcon.load("../tests/ab_call_ext_rec_0.0.1.vcon")
  assert(len(in_vcon.dialog)  == 1)
  assert(len(in_vcon.dialog[0]["url"]) > 0)
  assert(in_vcon.dialog[0]["duration"] > 0)
  assert(len(in_vcon.dialog[0]["content_hash"]) > 0)
  original_hash = in_vcon.dialog[0]["content_hash"]
  original_duration = in_vcon.dialog[0]["duration"]

  in_vcon._vcon_dict["dialog"][0]["duration"] = 0
  del in_vcon._vcon_dict["dialog"][0]["content_hash"]
  assert(in_vcon.dialog[0]["duration"] == 0)
  assert("content_hash" not in  in_vcon.dialog[0])

  # Setup inputs
  proc_input = py_vcon_server.processor.VconProcessorIO(None)
  await proc_input.add_vcon(in_vcon, "fake_lock", False) # read/write
  assert(len(proc_input._vcons) == 1)

  fix_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("fix_recording_dialog")

  input_dialogs = [0]

  fix_proc_options = fix_proc_inst.processor_options_class()(
      input_dialogs = input_dialogs
    )

  proc_output = await fix_proc_inst.process(proc_input, fix_proc_options)

  fixed_vcon = await proc_output.get_vcon(0)

  assert(original_hash == fixed_vcon.dialog[0]["content_hash"])

  # TODO:
  # assert(original_duration == fixed_vcon.dialog[0]["duration"])

