""" Deepgram transcription plugin unit test """

import os
import datetime
import json
import vcon
import vcon.filter_plugins
import pytest


def test_deepgram_options():
  import vcon.filter_plugins.impl.deepgram
  init_options = vcon.filter_plugins.impl.deepgram.DeepgramInitOptions()
  assert(init_options.deepgram_key == "")

  init_options = vcon.filter_plugins.impl.deepgram.DeepgramInitOptions(**{})
  assert(init_options.deepgram_key == "")


@pytest.mark.asyncio
async def test_deepgram_transcribe_inline_dialog():
  """ Test Deepgram plugin with an inline audio dialog """
  in_vcon = vcon.Vcon()


  deepgram_key = os.getenv("DEEPGRAM_KEY", None)
  # Register the Deepgram filter plugin
  init_options = {"deepgram_key": deepgram_key}

  with open("examples/test.vcon", "r") as vcon_file:
    in_vcon.load(vcon_file)

  assert(len(in_vcon.dialog) > 0)

  analysis_count = len(in_vcon.analysis)
  out_vcon = await in_vcon.deepgram({})
  assert(len(in_vcon.analysis) == analysis_count + 1)
  assert(len(out_vcon.analysis) == analysis_count + 1)
  #print(json.dumps(out_vcon.analysis[0], indent=2))

  assert(out_vcon.analysis[analysis_count]["type"] == "transcript")
  assert(out_vcon.analysis[analysis_count]["vendor"] == "deepgram")
  assert(out_vcon.analysis[analysis_count]["product"] == "transcription")
  assert(out_vcon.analysis[analysis_count]["schema"] == "deepgram_prerecorded")
  assert(out_vcon.analysis[analysis_count]["encoding"] == "json")
  body_len = len(out_vcon.analysis[analysis_count]["body"])
  assert(isinstance(out_vcon.analysis[analysis_count]["body"], dict))
  print("transcript keys: {}".format(out_vcon.analysis[analysis_count]["body"].keys()))
  # Make body check a little more tollerent to addtions
  assert(out_vcon.analysis[analysis_count]["body"].keys() >=
    {'metadata', 'results'})
  #print(json.dumps(out_vcon.analysis[analysis_count]["body"], indent = 2))

  if(out_vcon.uuid is None):
    out_vcon.set_uuid("vcon.net")

  # Test that we still have a valid serializable Vcon
  out_vcon_json = out_vcon.dumps()
  json.loads(out_vcon_json )

  text_list = await out_vcon.get_dialog_text(0)
  print("text: {}".format(json.dumps(text_list, indent = 2)))
  assert(56 <= len(text_list) <= 62)

  # Run again, should not generate duplicate analysis
  out_vcon2 = await out_vcon.deepgram({})
  assert(len(out_vcon.analysis) == analysis_count + 1)
  assert(len(out_vcon2.analysis) == analysis_count + 1)


@pytest.mark.asyncio
async def test_deepgram_transcribe_external_dialog():
  """ Test deepgram plugin with an externally referenced audio dialog """
  constant_date = "2023-08-31T18:26:36.987+00:00"
  in_vcon = vcon.Vcon()

  assert(in_vcon.set_party_parameter("name", "Dana") == 0)
  assert(in_vcon.set_party_parameter("name", "Carolyn Lake") == 1)

  # Add external ref
  file_path = "examples/agent_sample.wav"
  url = "https://github.com/py-vcon/py-vcon/blob/main/examples/agent_sample.wav?raw=true"
  file_content = b""
  with open(file_path, "rb") as file_handle:
    file_content = file_handle.read()
    print("body length: {}".format(len(file_content)))
    assert(len(file_content) > 10000)

  dialog_index = in_vcon.add_dialog_external_recording(file_content,
    constant_date,
    0, # duration TODO
    [0,1],
    url,
    vcon.Vcon.MIMETYPE_AUDIO_WAV,
    os.path.basename(file_path))

  assert(dialog_index == 0)

  options = vcon.filter_plugins.TranscribeOptions(
    )

  assert(len(in_vcon.dialog) > 0)

  analysis_count = len(in_vcon.analysis)
  out_vcon = await in_vcon.deepgram(options)
  assert(len(out_vcon.analysis) == analysis_count + 1)
  #print(json.dumps(out_vcon.analysis[0], indent=2))

  assert(out_vcon.analysis[analysis_count]["type"] == "transcript")
  assert(out_vcon.analysis[analysis_count]["vendor"] == "deepgram")
  assert(out_vcon.analysis[analysis_count]["product"] == "transcription")
  assert(out_vcon.analysis[analysis_count]["schema"] == "deepgram_prerecorded")
  #print("whisper body: {}".format(out_vcon.analysis[analysis_count]["body"]))
  body_len = len(out_vcon.analysis[analysis_count]["body"])
  #body_type = type(out_vcon.analysis[analysis_count]["body"])
  assert(isinstance(out_vcon.analysis[analysis_count]["body"], dict))
  #print("transcript type: {}".format(body_type))
  print("transcript keys: {}".format(out_vcon.analysis[analysis_count]["body"].keys()))

  # Make body check a little more tollerent to addtions
  assert(out_vcon.analysis[analysis_count]["body"].keys() >=
    {'metadata', 'results'})

  # hack the UUID so that the output Vcon does not change
  in_vcon._vcon_dict[vcon.Vcon.UUID] = "018a4cd9-b326-811b-9a21-90977a450c19"
  # set the date so that output does not change
  in_vcon.set_created_at(constant_date)

  # Test that we still have a valid serializable Vcon
  out_vcon_json = out_vcon.dumps()
  out_vcon_dict = json.loads(out_vcon_json)

  # Save a copy for reference
  out_vcon.dump("tests/example_deepgram_external_dialog.vcon", indent = 2)


@pytest.mark.asyncio
async def test_deepgram_no_dialog():
  """ Test Deepgram plugin on Vcon with no dialogs """
  in_vcon = vcon.Vcon()
  vcon_json = """
  {
    "vcon": "0.0.1",
    "uuid": "my_fake_uuid",
    "created_at": "2023-08-18T07:14:45.894+00:00",
    "parties": [
      {
        "tel": "+1 123 456 7890"
      }
    ]
  }
  """
  in_vcon.loads(vcon_json)

  options = vcon.filter_plugins.TranscribeOptions(
    )

  assert(in_vcon.dialog is None)
  out_vcon = await in_vcon.deepgram(options)
  assert(out_vcon.analysis is None)
