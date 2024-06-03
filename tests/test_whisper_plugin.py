""" Whisper transcription plugin unit test """

import os
import datetime
import json
import vcon
import vcon.filter_plugins
import pytest

def test_whisper_registration():
  """ Test registration of Whisper plugin """
  options = vcon.filter_plugins.TranscribeOptions(
    # Initialize tiny model to speed the unit tests up a bit.
    # Huge degradation in speed (factor of 8x) with stable-ts 2.x, whisper 1.1.X and torch 2.X
    model_size = "tiny",
    #output_types = ["vendor", "word_srt", "word_ass"]
    #whisper = { "language" : "en"}
    )

  plugin = vcon.filter_plugins.FilterPluginRegistry.get("whisper")
  assert(plugin is not None)
  assert(plugin.import_plugin(options))


def test_plugin_method_add():
  in_vcon = vcon.Vcon()
  # TODO


@pytest.mark.asyncio
async def test_whisper_transcribe_inline_dialog():
  """ Test Whisper plugin with an inline audio dialog """
  in_vcon = vcon.Vcon()

  options = vcon.filter_plugins.TranscribeOptions(
    llanguage = "en", # non existing options
    model_size = "base",
    output_types = ["vendor", "word_srt", "word_ass"]
    #whisper = { "language" : "en"}
    )
  with open("examples/test.vcon", "r") as vcon_file:
    in_vcon.load(vcon_file)

  assert(len(in_vcon.dialog) > 0)

  analysis_count = len(in_vcon.analysis)
  out_vcon = await in_vcon.whisper(options)
  assert(len(in_vcon.analysis) == analysis_count + 3) # Whisper transcript, srt file and ass file
  assert(len(out_vcon.analysis) == analysis_count + 3) # Whisper transcript, srt file and ass file
  #print(json.dumps(out_vcon.analysis[0], indent=2))

  assert(out_vcon.analysis[analysis_count]["type"] == "transcript")
  assert(out_vcon.analysis[analysis_count]["vendor"] == "openai")
  assert(out_vcon.analysis[analysis_count]["product"] == "whisper")
  assert(out_vcon.analysis[analysis_count]["schema"] == "whisper_word_timestamps")
  #print("whisper body: {}".format(out_vcon.analysis[analysis_count]["body"]))
  body_len = len(out_vcon.analysis[analysis_count]["body"])
  #body_type = type(out_vcon.analysis[analysis_count]["body"])
  assert(isinstance(out_vcon.analysis[analysis_count]["body"], dict))
  #print("transcript type: {}".format(body_type))
  print("transcript keys: {}".format(out_vcon.analysis[analysis_count]["body"].keys()))
  # Stable whisper changed and the word time stamps (time_scale key) are now part of "segments"
  # in transcription object.
  #if(body_len != 3):
  # Make body check a little more tollerent to addtions
  assert(out_vcon.analysis[analysis_count]["body"].keys() >=
    {'text', 'segments', 'language'})
  assert(out_vcon.analysis[analysis_count + 1]["type"] == "transcript")
  assert(out_vcon.analysis[analysis_count + 1]["vendor"] == "openai")
  assert(out_vcon.analysis[analysis_count + 1]["product"] == "whisper")
  assert(out_vcon.analysis[analysis_count + 1]["schema"] == "whisper_word_srt")
  body_len = len(out_vcon.analysis[analysis_count + 1]["body"])
  print("srt len: {}".format(body_len))
  expected_srt_size = 33000
  if(body_len < expected_srt_size):
    print("srt body: {}".format(out_vcon.analysis[analysis_count + 1]["body"]))
    print("srt type: {}".format(type(out_vcon.analysis[analysis_count + 1]["body"])))
  assert(body_len > expected_srt_size)
  assert(out_vcon.analysis[analysis_count + 2]["type"] == "transcript")
  assert(out_vcon.analysis[analysis_count + 2]["vendor"] == "openai")
  assert(out_vcon.analysis[analysis_count + 2]["product"] == "whisper")
  assert(out_vcon.analysis[analysis_count + 2]["schema"] == "whisper_word_ass")
  body_len = len(out_vcon.analysis[analysis_count + 2]["body"])
  print("ass len: {}".format(body_len))
  # The format of the output from stable whisper for ass files changed.
  # Someone with a better knowledge of the ass format, will have to review if this is ok or not.
  assert(body_len > 19000)

  if(out_vcon.uuid is None):
    out_vcon.set_uuid("vcon.net")

  # Test that we still have a valid serializable Vcon
  out_vcon_json = out_vcon.dumps()
  json.loads(out_vcon_json )

  # Run again, should not generate duplicate analysis
  out_vcon2 = await out_vcon.whisper(options)
  assert(len(out_vcon.analysis) == analysis_count + 3) # Whisper transcript, srt file and ass file
  assert(len(out_vcon2.analysis) == analysis_count + 3) # Whisper transcript, srt file and ass file

  # TODO: should test more than one invokation of whisper plugin to be sure its ok to reuse
  # models for more than one transcription.

@pytest.mark.asyncio
async def test_whisper_transcribe_external_dialog():
  """ Test Whisper plugin with an externally referenced audio dialog """
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
    llanguage = "en",
    model_size = "base",
    output_types = ["vendor", "word_srt", "word_ass"],
    whisper = { "language" : "en"}
    )

  assert(len(in_vcon.dialog) > 0)

  analysis_count = len(in_vcon.analysis)
  out_vcon = await in_vcon.transcribe(options)
  assert(len(out_vcon.analysis) == analysis_count + 3) # Whisper transcript, srt file and ass file
  #print(json.dumps(out_vcon.analysis[0], indent=2))

  assert(out_vcon.analysis[analysis_count]["type"] == "transcript")
  assert(out_vcon.analysis[analysis_count]["vendor"] == "openai")
  assert(out_vcon.analysis[analysis_count]["product"] == "whisper")
  assert(out_vcon.analysis[analysis_count]["schema"] == "whisper_word_timestamps")
  #print("whisper body: {}".format(out_vcon.analysis[analysis_count]["body"]))
  body_len = len(out_vcon.analysis[analysis_count]["body"])
  #body_type = type(out_vcon.analysis[analysis_count]["body"])
  assert(isinstance(out_vcon.analysis[analysis_count]["body"], dict))
  #print("transcript type: {}".format(body_type))
  print("transcript keys: {}".format(out_vcon.analysis[analysis_count]["body"].keys()))
  # Stable whisper changed and the word time stamps (time_scale key) are now part of "segments"
  # in transcription object.
  #if(body_len != 3):
  # Make body check a little more tollerent to addtions
  assert(out_vcon.analysis[analysis_count]["body"].keys() >=
    {'text', 'segments', 'language'})
  assert(out_vcon.analysis[analysis_count + 1]["type"] == "transcript")
  assert(out_vcon.analysis[analysis_count + 1]["vendor"] == "openai")
  assert(out_vcon.analysis[analysis_count + 1]["product"] == "whisper")
  assert(out_vcon.analysis[analysis_count + 1]["schema"] == "whisper_word_srt")
  body_len = len(out_vcon.analysis[analysis_count + 1]["body"])
  print("srt len: {}".format(body_len))
  expected_srt_size = 33000
  if(body_len < expected_srt_size):
    print("srt body: {}".format(out_vcon.analysis[analysis_count + 1]["body"]))
    print("srt type: {}".format(type(out_vcon.analysis[analysis_count + 1]["body"])))
  assert(body_len > expected_srt_size)
  assert(out_vcon.analysis[analysis_count + 2]["type"] == "transcript")
  assert(out_vcon.analysis[analysis_count + 2]["vendor"] == "openai")
  assert(out_vcon.analysis[analysis_count + 2]["product"] == "whisper")
  assert(out_vcon.analysis[analysis_count + 2]["schema"] == "whisper_word_ass")
  body_len = len(out_vcon.analysis[analysis_count + 2]["body"])
  print("ass len: {}".format(body_len))
  # The format of the output from stable whisper for ass files changed.
  # Someone with a better knowledge of the ass format, will have to review if this is ok or not.
  assert(body_len > 21000)

  # hack the UUID so that the output Vcon does not change
  in_vcon._vcon_dict[vcon.Vcon.UUID] = "018a4cd9-b326-811b-9a21-90977a450c19"
  # set the date so that output does not change
  in_vcon.set_created_at(constant_date)

  # Test that we still have a valid serializable Vcon
  out_vcon_json = out_vcon.dumps()
  out_vcon_dict = json.loads(out_vcon_json)

  # Save a copy for reference
  with open("tests/example_external_dialog.vcon", "w") as vcon_file:
    vcon_file.write(json.dumps(out_vcon_dict, indent = 2))


@pytest.mark.asyncio
async def test_whisper_no_dialog():
  """ Test Whisper plugin on Vcon with no dialogs """
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
    llanguage = "en",
    model_size = "base",
    output_types = ["vendor", "word_srt", "word_ass"],
    whisper = { "language" : "en"}
    )

  assert(in_vcon.dialog is None)
  out_vcon = await in_vcon.transcribe(options)
  assert(out_vcon.analysis is None)
