# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" Unit test for OpenAI filter plugins """
import os
import json
import pydantic
import vcon
import vcon.filter_plugins.impl.openai
import vcon.pydantic_utils
import pytest


TEST_EXTERNAL_AUDIO_VCON_FILE = "tests/example_external_dialog.vcon"
TEST_DIARIZED_EXTERNAL_AUDIO_VCON_FILE = "tests/example_deepgram_external_dialog.vcon"
SHORT_RECORDING_VCON = "tests/hello.vcon"
TEST_MODEL = "gpt-3.5-turbo-instruct" # cheaper to run in tests than davinci-003 ???
TEST_CHAT_MODEL = "gpt-3.5-turbo-16k" # should be a little cheaper to run instead of GPT-4 for testing 

def test_1_options():
  """ Tests for OpenAICompletionInitOptions and OpenAICompletionOptions """
  init_options_dict = {}
  try:
    init_options = vcon.filter_plugins.impl.openai.OpenAICompletionInitOptions(**init_options_dict)
    raise Exception("Expected exception due to missing openai_api_key")

  except vcon.pydantic_utils.ValidationErrorType as e:
    # expected
    pass

  init_options_dict = {
      "openai_api_key": "foo"
    }
  init_options = vcon.filter_plugins.impl.openai.OpenAICompletionInitOptions(**init_options_dict)
  assert(init_options.openai_api_key == "foo")

  options_dict = {}
  options = vcon.filter_plugins.impl.openai.OpenAICompletionOptions(**options_dict)
  assert(options.input_dialogs == "")


@pytest.mark.asyncio
async def test_2_completion_text_summary():
  """ Test OpenAICompletion FilterPlugin with transcribe ananlysis and text output """
  in_vcon = vcon.Vcon()
  in_vcon.load(TEST_EXTERNAL_AUDIO_VCON_FILE)
  original_analysis_count = len(in_vcon.analysis)

  options = {
      "model": TEST_MODEL
    }

  out_vcon = None

  try:
    out_vcon = await in_vcon.openai_completion(options)

  except pydantic.error_wrappers.ValidationError as e:
    openai_key = os.getenv("OPENAI_API_KEY", None)
    if(openai_key is None or
      openai_key == ""):
        raise Exception("OPENAI_API_KEY environment variable not set this test cannot run") from e
    raise e

  #print(json.dumps(out_vcon.dumpd(), indent = 2))

  after_analysis_count = len(out_vcon.analysis)
  assert((after_analysis_count - original_analysis_count) == 1)
  assert(out_vcon.analysis[original_analysis_count]["type"] == "summary")
  assert(out_vcon.analysis[original_analysis_count]["dialog"] == 0)
  assert(out_vcon.analysis[original_analysis_count]["vendor"] == "openai")
  assert(out_vcon.analysis[original_analysis_count]["product"] == "Completion")
  assert(out_vcon.analysis[original_analysis_count]["schema"] == "text")
  assert(out_vcon.analysis[original_analysis_count]["prompt"] == "Summarize this conversation: ")
  assert(out_vcon.analysis[original_analysis_count].get("mimetype", None) is None)
  assert(out_vcon.analysis[original_analysis_count]["mediatype"] == vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  assert(out_vcon.analysis[original_analysis_count]["encoding"] == "none")
  assert(isinstance(out_vcon.analysis[original_analysis_count]["body"], str))
  assert(len(out_vcon.analysis[original_analysis_count]["body"]) > 250)
  assert(out_vcon.analysis[original_analysis_count]["model"] == TEST_MODEL)


@pytest.mark.asyncio
async def test_2a_completion_object_summary():
  """ Test OpenAICompletion FilterPlugin with transcribe ananlysis and completion_object output """

  in_vcon = vcon.Vcon()
  in_vcon.load(TEST_EXTERNAL_AUDIO_VCON_FILE)
  original_analysis_count = len(in_vcon.analysis)

  options = {
      "jq_result": ".",
      "model": TEST_MODEL
    }

  out_vcon = None

  try:
    out_vcon = await in_vcon.openai_completion(options)

  except pydantic.error_wrappers.ValidationError as e:
    openai_key = os.getenv("OPENAI_API_KEY", None)
    if(openai_key is None or
      openai_key == ""):
        raise Exception("OPENAI_API_KEY environment variable not set this test cannot run") from e
    raise e

  #print(json.dumps(out_vcon.dumpd(), indent = 2))

  after_analysis_count = len(out_vcon.analysis)
  assert((after_analysis_count - original_analysis_count) == 1)
  assert(out_vcon.analysis[original_analysis_count]["type"] == "summary")
  assert(out_vcon.analysis[original_analysis_count]["dialog"] == 0)
  assert(out_vcon.analysis[original_analysis_count]["vendor"] == "openai")
  assert(out_vcon.analysis[original_analysis_count]["product"] == "Completion")
  assert(out_vcon.analysis[original_analysis_count]["schema"] == "completion_object")
  assert(out_vcon.analysis[original_analysis_count]["prompt"] == "Summarize this conversation: ")
  assert(out_vcon.analysis[original_analysis_count].get("mimetype", None) is None)
  assert(out_vcon.analysis[original_analysis_count]["mediatype"] == vcon.Vcon.MEDIATYPE_JSON)
  assert(out_vcon.analysis[original_analysis_count]["encoding"] == "json")
  assert(isinstance(out_vcon.analysis[original_analysis_count]["body"], dict))
  assert(isinstance(out_vcon.analysis[original_analysis_count]["body"]["choices"][0]["text"], str))
  assert(len(out_vcon.analysis[original_analysis_count]["body"]["choices"][0]["text"]) > 250)
  assert(out_vcon.analysis[original_analysis_count]["model"] == TEST_MODEL)


@pytest.mark.asyncio
async def test_2b_completion_object_summary():
  """ Test OpenAICompletion FilterPlugin with transcribe ananlysis and completion_object output """

  in_vcon = vcon.Vcon()
  in_vcon.load(TEST_DIARIZED_EXTERNAL_AUDIO_VCON_FILE)
  original_analysis_count = len(in_vcon.analysis)

  options = {
      "jq_result": ".",
      "model": TEST_MODEL
    }

  out_vcon = None

  try:
    out_vcon = await in_vcon.openai_completion(options)

  except pydantic.error_wrappers.ValidationError as e:
    openai_key = os.getenv("OPENAI_API_KEY", None)
    if(openai_key is None or
      openai_key == ""):
        raise Exception("OPENAI_API_KEY environment variable not set this test cannot run") from e
    raise e

  #print(json.dumps(out_vcon.dumpd(), indent = 2))

  # Check stats on input to model:
  plugin = vcon.filter_plugins.FilterPluginRegistry.get("openai_completion").plugin()
  assert(40 < plugin.last_stats["num_text_segments"] < 70)

  after_analysis_count = len(out_vcon.analysis)
  assert((after_analysis_count - original_analysis_count) == 1)
  assert(out_vcon.analysis[original_analysis_count]["type"] == "summary")
  assert(out_vcon.analysis[original_analysis_count]["dialog"] == 0)
  assert(out_vcon.analysis[original_analysis_count]["vendor"] == "openai")
  assert(out_vcon.analysis[original_analysis_count]["product"] == "Completion")
  assert(out_vcon.analysis[original_analysis_count]["schema"] == "completion_object")
  assert(out_vcon.analysis[original_analysis_count]["prompt"] == "Summarize this conversation: ")
  assert(out_vcon.analysis[original_analysis_count].get("mimetype", None) is None)
  assert(out_vcon.analysis[original_analysis_count]["mediatype"] == vcon.Vcon.MEDIATYPE_JSON)
  assert(out_vcon.analysis[original_analysis_count]["encoding"] == "json")
  assert(isinstance(out_vcon.analysis[original_analysis_count]["body"], dict))
  assert(isinstance(out_vcon.analysis[original_analysis_count]["body"]["choices"][0]["text"], str))
  assert(len(out_vcon.analysis[original_analysis_count]["body"]["choices"][0]["text"]) > 250)
  assert(out_vcon.analysis[original_analysis_count]["model"] == TEST_MODEL)


@pytest.mark.asyncio
async def test_3_chat_completion_object_summary():
  """ Test OpenAIChatCompletion FilterPlugin with transcribe ananlysis and chat_completion_object output """

  in_vcon = vcon.Vcon()
  in_vcon.load(TEST_EXTERNAL_AUDIO_VCON_FILE)
  original_analysis_count = len(in_vcon.analysis)

  options = {
      "jq_result": ".",
      "model": TEST_CHAT_MODEL
    }

  out_vcon = None

  try:
    out_vcon = await in_vcon.openai_chat_completion(options)

  except pydantic.error_wrappers.ValidationError as e:
    openai_key = os.getenv("OPENAI_API_KEY", None)
    if(openai_key is None or
      openai_key == ""):
        raise Exception("OPENAI_API_KEY environment variable not set this test cannot run") from e
    raise e

  after_analysis_count = len(out_vcon.analysis)

  # Check stats on input to model:
  plugin = vcon.filter_plugins.FilterPluginRegistry.get("openai_chat_completion").plugin()
  # verify stats of extracted messages are as expected
  print("stats: {}".format(plugin.last_stats))
  assert(plugin.last_stats['num_messages'] == 1)
  assert(plugin.last_stats['num_text_dialogs'] == 0)
  assert(plugin.last_stats['num_dialog_list'] == 1)
  assert(plugin.last_stats['num_transcribe_analysis'] == 1)

  assert((after_analysis_count - original_analysis_count) == 1)
  assert(out_vcon.analysis[original_analysis_count]["type"] == "summary")
  assert(out_vcon.analysis[original_analysis_count]["dialog"] == 0)
  assert(out_vcon.analysis[original_analysis_count]["vendor"] == "openai")
  assert(out_vcon.analysis[original_analysis_count]["product"] == "ChatCompletion")
  assert(out_vcon.analysis[original_analysis_count]["schema"] == "chat_completion_object")
  assert(out_vcon.analysis[original_analysis_count]["prompt"] == "Summarize the transcript in these messages.")
  assert(out_vcon.analysis[original_analysis_count].get("mimetype", None) is None)
  assert(out_vcon.analysis[original_analysis_count]["mediatype"] == vcon.Vcon.MEDIATYPE_JSON)
  assert(out_vcon.analysis[original_analysis_count]["encoding"] == "json")
  assert(isinstance(out_vcon.analysis[original_analysis_count]["body"], dict))
  assert(isinstance(out_vcon.analysis[original_analysis_count]["body"]["choices"][0]["message"]["content"], str))
  assert(len(out_vcon.analysis[original_analysis_count]["body"]["choices"][0]["message"]["content"]) > 250)
  assert(out_vcon.analysis[original_analysis_count]["model"] == TEST_CHAT_MODEL)
  print("Response: " + out_vcon.analysis[original_analysis_count]["body"]["choices"][0]["message"]["content"])


@pytest.mark.asyncio
async def test_4_diarized_chat_completion_object_summary():
  """ Test OpenAIChatCompletion FilterPlugin with transcribe ananlysis and chat_completion_object output """

  in_vcon = vcon.Vcon()
  in_vcon.load(TEST_DIARIZED_EXTERNAL_AUDIO_VCON_FILE)
  original_analysis_count = len(in_vcon.analysis)

  options = {
      "jq_result": ".",
      "model": TEST_CHAT_MODEL
    }

  out_vcon = None

  try:
    out_vcon = await in_vcon.openai_chat_completion(options)

  except pydantic.error_wrappers.ValidationError as e:
    openai_key = os.getenv("OPENAI_API_KEY", None)
    if(openai_key is None or
      openai_key == ""):
        raise Exception("OPENAI_API_KEY environment variable not set this test cannot run") from e
    raise e

  after_analysis_count = len(out_vcon.analysis)

  # Check stats on input to model:
  plugin = vcon.filter_plugins.FilterPluginRegistry.get("openai_chat_completion").plugin()
  # verify stats of extracted messages are as expected
  print("stats: {}".format(plugin.last_stats))
  assert(40 <= plugin.last_stats['num_messages'] <= 70)
  assert(plugin.last_stats['num_text_dialogs'] == 0)
  assert(plugin.last_stats['num_dialog_list'] == 1)
  assert(50 <= plugin.last_stats['num_transcribe_analysis'] <= 70)

  print("New analysis object: {}".format(out_vcon.analysis[original_analysis_count]))
  assert((after_analysis_count - original_analysis_count) == 1)
  assert(out_vcon.analysis[original_analysis_count]["type"] == "summary")
  assert(out_vcon.analysis[original_analysis_count]["dialog"] == 0)
  assert(out_vcon.analysis[original_analysis_count]["vendor"] == "openai")
  assert(out_vcon.analysis[original_analysis_count]["product"] == "ChatCompletion")
  assert(out_vcon.analysis[original_analysis_count]["schema"] == "chat_completion_object")
  assert(out_vcon.analysis[original_analysis_count]["prompt"] == "Summarize the transcript in these messages.")
  assert(out_vcon.analysis[original_analysis_count].get("mimetype", None) is None)
  assert(out_vcon.analysis[original_analysis_count]["mediatype"] == vcon.Vcon.MEDIATYPE_JSON)
  assert(out_vcon.analysis[original_analysis_count]["encoding"] == "json")
  assert(isinstance(out_vcon.analysis[original_analysis_count]["body"], dict))
  assert(isinstance(out_vcon.analysis[original_analysis_count]["body"]["choices"][0]["message"]["content"], str))
  assert(len(out_vcon.analysis[original_analysis_count]["body"]["choices"][0]["message"]["content"]) > 250)
  assert(out_vcon.analysis[original_analysis_count]["model"] == TEST_CHAT_MODEL)
  print("Response: " + out_vcon.analysis[original_analysis_count]["body"]["choices"][0]["message"]["content"])


@pytest.mark.asyncio
async def test_5_openai_triggers_transcribe():
  """ Test OpenAIChatCompletion FilterPlugin with missing transcribe ananlysis, should transcribe"""

  in_vcon = vcon.Vcon()
  in_vcon.load(SHORT_RECORDING_VCON)
  # Remove transcription or any other analysis
  in_vcon.analysis.clear()
  assert(len(in_vcon.analysis) == 0)
  original_analysis_count = 0

  options = {
      "jq_result": ".",
      "model": TEST_CHAT_MODEL
    }

  out_vcon = None

  try:
    out_vcon = await in_vcon.openai_chat_completion(options)

  except pydantic.error_wrappers.ValidationError as e:
    openai_key = os.getenv("OPENAI_API_KEY", None)
    if(openai_key is None or
      openai_key == ""):
        raise Exception("OPENAI_API_KEY environment variable not set this test cannot run") from e
    raise e

  after_analysis_count = len(out_vcon.analysis)
  assert(after_analysis_count == 4) # transcription and openai summary

  # Check stats on input to model:
  plugin = vcon.filter_plugins.FilterPluginRegistry.get("openai_chat_completion").plugin()
  # verify stats of extracted messages are as expected
  print("stats: {}".format(plugin.last_stats))
  assert(plugin.last_stats['num_messages'] == 1)
  assert(plugin.last_stats['num_text_dialogs'] == 0)
  assert(plugin.last_stats['num_dialog_list'] == 1)
  assert(plugin.last_stats['num_transcribe_analysis'] == 1)

  assert((after_analysis_count - original_analysis_count) == 4)
  assert(out_vcon.analysis[original_analysis_count + 3]["type"] == "summary")
  assert(out_vcon.analysis[original_analysis_count + 3]["dialog"] == 0)
  assert(out_vcon.analysis[original_analysis_count + 3]["vendor"] == "openai")
  assert(out_vcon.analysis[original_analysis_count + 3]["product"] == "ChatCompletion")
  assert(out_vcon.analysis[original_analysis_count + 3]["schema"] == "chat_completion_object")
  assert(out_vcon.analysis[original_analysis_count + 3]["prompt"] == "Summarize the transcript in these messages.")
  assert(out_vcon.analysis[original_analysis_count + 3].get("mimetype", None) is None)
  assert(out_vcon.analysis[original_analysis_count + 3]["mediatype"] == vcon.Vcon.MEDIATYPE_JSON)
  assert(out_vcon.analysis[original_analysis_count + 3]["encoding"] == "json")
  assert(isinstance(out_vcon.analysis[original_analysis_count + 3]["body"], dict))
  assert(isinstance(out_vcon.analysis[original_analysis_count + 3]["body"]["choices"][0]["message"]["content"], str))
  assert(len(out_vcon.analysis[original_analysis_count + 3]["body"]["choices"][0]["message"]["content"]) > 80)
  assert(out_vcon.analysis[original_analysis_count + 3]["model"] == TEST_CHAT_MODEL)
  print("Response: " + out_vcon.analysis[original_analysis_count + 3]["body"]["choices"][0]["message"]["content"])


