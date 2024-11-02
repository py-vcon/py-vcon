# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" Unit tests for Whisper VconProcessor """

import pytest
import pytest_asyncio
from common_setup import make_inline_audio_vcon, make_2_party_tel_vcon
import py_vcon_server.processor
from py_vcon_server.settings import VCON_STORAGE_URL
#import py_vcon_server.processor.whisper_base
import vcon


VCON_STORAGE = None

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
async def test_whisper_base_model(make_inline_audio_vcon):
  # Build a Vcon with inline audio dialog
  in_vcon = make_inline_audio_vcon
  assert(isinstance(in_vcon, vcon.Vcon))

  # Make sure Whisper VconProcessor is registered for base model
  names = py_vcon_server.processor.VconProcessorRegistry.get_processor_names()

  proc_name = "whisper_base"
  assert(proc_name in names)

  proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance(proc_name)

  # TODO setup transcription options
  proc_options = proc_inst.processor_options_class()()
  assert(proc_options.input_vcon_index == 0)


  # Setup inputs
  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(in_vcon, "fake_lock", False) # read/write
  assert(len(proc_input._vcons) == 1)
  in_vcon = await proc_input.get_vcon(proc_options.input_vcon_index)
  assert(in_vcon is not None)
  assert(isinstance(in_vcon, vcon.Vcon))

  proc_output = await proc_inst.process(proc_input, proc_options)
  out_vcon = await proc_output.get_vcon(proc_options.input_vcon_index)
  assert(out_vcon is not None)
  assert(isinstance(out_vcon, vcon.Vcon))
  assert(len(out_vcon.analysis) == 3) # Whisper transcript, srt file and ass file


  assert(out_vcon.analysis[0]["body"]["text"] ==" Hello, can you hear me?")
