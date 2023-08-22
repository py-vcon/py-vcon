""" Unit tests for Whisper VconProcessor """

import asyncio
import pytest
import pytest_asyncio
import py_vcon_server.processor
#import py_vcon_server.processor.whisper_base
import vcon
from common_setup import make_inline_audio_vcon, make_2_party_tel_vcon


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
  proc_input = py_vcon_server.processor.VconProcessorIO()
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
