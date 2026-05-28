# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" Deepgram transcription plugin unit test """

import os
import datetime
import json
import vcon
import vcon.filter_plugins
import vcon.filter_plugins.impl.deepgram
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
  assert(30 <= len(text_list) <= 170)

  # Run again, should not generate duplicate analysis
  out_vcon2 = await out_vcon.deepgram({})
  assert(len(out_vcon.analysis) == analysis_count + 1)
  assert(len(out_vcon2.analysis) == analysis_count + 1)


@pytest.mark.asyncio
async def test_deepgram_2_channel_inline_dialog():
  """ Test Deepgram plugin with an 2 channel inline audio dialog """
  in_vcon = vcon.Vcon()
  in_vcon.set_uuid("tests.python-vcon.org")

  assert(in_vcon.set_party_parameter("name", "Agent") == 0)
  assert(in_vcon.set_party_parameter("name", "Customer") == 1)

  file_path = "tests/agent_2_channel.wav"
  with open(file_path, "rb") as file_handle:
    body_bytes = file_handle.read()
  assert(len(body_bytes) > 1000000)

  start_time = "2023-08-31T18:26:36.987+00:00"
  duration = 0
  parties = [0,1]

  in_vcon.add_dialog_inline_recording(
      body_bytes,
      start_time,
      duration,
      parties,
      vcon.Vcon.MEDIATYPE_AUDIO_WAV
    )

  options = vcon.filter_plugins.TranscribeOptions()
  out_vcon = await in_vcon.deepgram(options)
  assert(len(out_vcon.dialog) == 1)
  assert(len(out_vcon.analysis) == 1)
  out_vcon.dump("agent_2_channel_out.vcon")

  dialog_texts = await in_vcon.get_dialog_text(
    0, #dialog_index
    True, # find text from transcript analysis if dialog is a recording and transcript exists
    False  # transcribe this recording dialog if transcript does not exist
    )

  sorted_texts = sorted(dialog_texts.copy(), key = lambda msg: msg["start"])

  # Should have 25-32 sentences
  assert(len(sorted_texts) >= 25)
  assert(len(sorted_texts) < 32)
  agent_sentence_count = sum(phrase.get("parties") == 0 for phrase in sorted_texts)
  customer_sentence_count = sum(phrase.get("parties") == 1 for phrase in sorted_texts)
  assert(agent_sentence_count + customer_sentence_count == len(sorted_texts))
  assert(agent_sentence_count > 10)
  assert(customer_sentence_count > 8)
  print("\n".join(map(str, sorted_texts)))


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
    vcon.Vcon.MEDIATYPE_AUDIO_WAV,
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

  assert(len(in_vcon.dialog) == 0)
  out_vcon = await in_vcon.deepgram(options)
  assert(len(out_vcon.analysis)  == 0)

def test_deepgram_init_no_key():
  """ Test Deepgram plugin instantiation with no key logs warning """
  import vcon.filter_plugins.impl.deepgram
  plugin = vcon.filter_plugins.impl.deepgram.Deepgram(
    vcon.filter_plugins.impl.deepgram.DeepgramInitOptions(deepgram_key="")
    )
  assert(plugin.deepgram_client is None)


@pytest.mark.asyncio
async def test_deepgram_malformed_wav_header():
  """ Test Deepgram plugin logs warning for malformed WAV header and raises on bad response """
  in_vcon = vcon.Vcon()
  in_vcon.set_uuid("tests.python-vcon.org")
  in_vcon.set_party_parameter("tel", "+1234567890")

  # 24 bytes of junk — enough to parse header fields but not a valid WAV
  bad_wav = b'\x00' * 24

  in_vcon.add_dialog_inline_recording(
    bad_wav,
    "2023-08-31T18:26:36.987+00:00",
    0,
    [0],
    vcon.Vcon.MEDIATYPE_AUDIO_WAV
    )

  options = vcon.filter_plugins.TranscribeOptions()
  with pytest.raises(Exception, match="failed: 400"):
    await in_vcon.deepgram(options)


def test_deepgram_transcript_accessor_non_diarized():
  """ Test DeepgramTranscriptAccessor with non-diarized (no paragraphs) transcript """
  import vcon.filter_plugins.deepgram

  dialog_dict = {
    "type": "recording",
    "start": "2023-08-31T18:26:36.987+00:00",
    "parties": [0, 1]
  }

  analysis_dict = {
    "type": "transcript",
    "vendor": "deepgram",
    "product": "transcription",
    "schema": "deepgram_prerecorded",
    "encoding": "json",
    "dialog": 0,
    "body": {
      "results": {
        "channels": [
          {
            "alternatives": [
              {
                "transcript": "Hello how are you",
                "words": [
                  {"word": "Hello", "start": 0.1, "end": 0.5},
                  {"word": "you", "start": 1.0, "end": 1.3}
                ]
              }
            ]
          }
        ]
      }
    }
  }

  accessor = vcon.filter_plugins.deepgram.DeepgramTranscriptAccessor(
    dialog_dict,
    analysis_dict
    )
  text_list = accessor.get_text()
  assert(len(text_list) == 1)
  assert(text_list[0]["text"] == "Hello how are you")
  assert(text_list[0]["parties"] == [0, 1])


def test_deepgram_transcript_accessor_no_match():
  """ Test DeepgramTranscriptAccessor returns empty list when analysis does not match """
  import vcon.filter_plugins.deepgram

  dialog_dict = {
    "type": "recording",
    "start": "2023-08-31T18:26:36.987+00:00",
    "parties": [0, 1]
  }

  analysis_dict = {
    "type": "transcript",
    "vendor": "other_vendor",
    "product": "transcription",
    "schema": "deepgram_prerecorded",
    "encoding": "json",
    "dialog": 0,
    "body": {}
  }

  accessor = vcon.filter_plugins.deepgram.DeepgramTranscriptAccessor(
    dialog_dict,
    analysis_dict
    )
  text_list = accessor.get_text()
  assert(text_list == [])


@pytest.mark.asyncio
async def test_deepgram_options_override():
  """ Test that model, language and deepgram_key option overrides are passed through """
  in_vcon = vcon.Vcon()
  in_vcon.set_uuid("tests.python-vcon.org")
  in_vcon.set_party_parameter("tel", "+1234567890")

  with open("examples/test.vcon", "r") as vcon_file:
    in_vcon.load(vcon_file)

  deepgram_key = os.getenv("DEEPGRAM_KEY", None)
  options = vcon.filter_plugins.impl.deepgram.DeepgramOptions(
    model = "nova-2",
    language = "en",
    deepgram_key = deepgram_key
    )

  analysis_count = len(in_vcon.analysis)
  out_vcon = await in_vcon.deepgram(options)
  assert(len(out_vcon.analysis) == analysis_count + 1)
  assert(out_vcon.analysis[analysis_count]["vendor"] == "deepgram")
  assert(out_vcon.analysis[analysis_count]["product"] == "transcription")


@pytest.mark.asyncio
async def test_deepgram_no_key_in_options():
  """ Test that filter returns early when key is not set in init or options """
  import vcon.filter_plugins.impl.deepgram
  plugin = vcon.filter_plugins.impl.deepgram.Deepgram(
    vcon.filter_plugins.impl.deepgram.DeepgramInitOptions(deepgram_key="")
    )
  in_vcon = vcon.Vcon()
  in_vcon.set_party_parameter("tel", "+1234567890")
  in_vcon.add_dialog_inline_text("hello", "2023-08-31T18:26:36.987+00:00", 0, [0], "text/plain")
  options = vcon.filter_plugins.impl.deepgram.DeepgramOptions(deepgram_key="")
  out_vcon = await plugin.filter(in_vcon, options)
  assert(len(out_vcon.analysis) == 0)


@pytest.mark.asyncio
async def test_deepgram_dialog_is_none():
  """ Test that filter returns early when dialog is None """
  import vcon.filter_plugins.impl.deepgram
  plugin = vcon.filter_plugins.impl.deepgram.Deepgram(
    vcon.filter_plugins.impl.deepgram.DeepgramInitOptions(deepgram_key="test_key")
    )
  in_vcon = vcon.Vcon()
  in_vcon._vcon_dict[vcon.Vcon.DIALOG] = None
  options = vcon.filter_plugins.impl.deepgram.DeepgramOptions()
  out_vcon = await plugin.filter(in_vcon, options)
  assert(out_vcon is in_vcon)

@pytest.mark.asyncio
async def test_deepgram_bogus_model(caplog):
  """
  Probe Deepgram's response to a misconfigured model name.

  Purpose: confirm Deepgram returns a non-404 status code for user
  misconfiguration (model name).  Our retry policy treats 404 as
  transient (Deepgram's internal failures are emitted as 404 per
  observed CI logs); if Deepgram ever starts returning 404 for bad
  model names this test will fail and force us to revisit.

  Skipped when DEEPGRAM_KEY is not set; a real key is required to
  exercise Deepgram's request validation path.
  """
  import logging

  deepgram_key = os.getenv("DEEPGRAM_KEY", None)
  if(deepgram_key is None or deepgram_key == ""):
    pytest.skip("DEEPGRAM_KEY not set; cannot probe Deepgram response")

  in_vcon = vcon.Vcon()
  in_vcon.set_uuid("tests.python-vcon.org")
  in_vcon.set_party_parameter("tel", "+1234567890")

  file_path = "py_vcon_server/tests/hello.wav"
  with open(file_path, "rb") as file_handle:
    body_bytes = file_handle.read()

  in_vcon.add_dialog_inline_recording(
    body_bytes,
    "2023-08-31T18:26:36.987+00:00",
    0,
    [0],
    vcon.Vcon.MEDIATYPE_AUDIO_WAV
    )

  options = vcon.filter_plugins.TranscribeOptions()
  # bogus model name; Deepgram should reject as a config error
  options.model = "nova-bogus-99"

  caplog.set_level(logging.WARNING, logger="vcon.filter_plugins.impl.deepgram")

  with pytest.raises(Exception, match="failed: 403") as exc_info:
    await in_vcon.deepgram(options)

  # Log the captured warning body for visibility in CI output
  print("bogus model exception: {}".format(str(exc_info.value)))
  for record in caplog.records:
    if(record.name == "vcon.filter_plugins.impl.deepgram"):
      print("bogus model warning: {}".format(record.getMessage()))

  # Hard contract: Deepgram returns 403 for an unrecognized/unauthorized
  # model name (observed err_code INSUFFICIENT_PERMISSIONS).  Critically,
  # this is NOT 404 -- the Deepgram filter's retry policy treats 404 as
  # a transient server-side failure.  If Deepgram ever starts emitting
  # 404 for bad model names, this assertion fails and forces a review
  # of the retry policy in vcon/filter_plugins/impl/deepgram.py.
  assert("failed: 403" in str(exc_info.value))

@pytest.mark.asyncio
async def test_deepgram_bogus_language(caplog):
  """
  Probe Deepgram's response to a misconfigured language code.

  Purpose: confirm Deepgram returns a non-404 status code for user
  misconfiguration (language code).  Companion to
  test_deepgram_bogus_model; see that test's docstring for rationale.

  Skipped when DEEPGRAM_KEY is not set.
  """
  import logging

  deepgram_key = os.getenv("DEEPGRAM_KEY", None)
  if(deepgram_key is None or deepgram_key == ""):
    pytest.skip("DEEPGRAM_KEY not set; cannot probe Deepgram response")

  in_vcon = vcon.Vcon()
  in_vcon.set_uuid("tests.python-vcon.org")
  in_vcon.set_party_parameter("tel", "+1234567890")

  file_path = "py_vcon_server/tests/hello.wav"
  with open(file_path, "rb") as file_handle:
    body_bytes = file_handle.read()

  in_vcon.add_dialog_inline_recording(
    body_bytes,
    "2023-08-31T18:26:36.987+00:00",
    0,
    [0],
    vcon.Vcon.MEDIATYPE_AUDIO_WAV
    )

  options = vcon.filter_plugins.TranscribeOptions()
  # bogus language code; "zz" is not an assigned ISO 639-1 code
  options.language = "zz"

  caplog.set_level(logging.WARNING, logger="vcon.filter_plugins.impl.deepgram")

  with pytest.raises(Exception, match="failed: 400") as exc_info:
    await in_vcon.deepgram(options)

  print("bogus language exception: {}".format(str(exc_info.value)))
  for record in caplog.records:
    if(record.name == "vcon.filter_plugins.impl.deepgram"):
      print("bogus language warning: {}".format(record.getMessage()))

  # Hard contract: Deepgram returns 400 Bad Request for an unrecognized
  # language code (observed err_msg "No such model/language/tier
  # combination found.").  Critically, this is NOT 404 -- see retry
  # policy in vcon/filter_plugins/impl/deepgram.py.
  assert("failed: 400" in str(exc_info.value))

