""" Unit test for OpenAI filter plugins """
import os
import json
import pydantic
import vcon
import vcon.filter_plugins.impl.openai


TEST_EXTERNAL_AUDIO_VCON_FILE = "tests/example_external_dialog.vcon"

def test_1_options():
  """ Tests for OpenAICompletionInitOptions and OpenAICompletionOptions """
  init_options_dict = {}
  try:
    init_options = vcon.filter_plugins.impl.openai.OpenAICompletionInitOptions(**init_options_dict)
    raise Exception("Expected exception due to missing openai_api_key")

  except pydantic.error_wrappers.ValidationError as e:
    # expected
    pass

  init_options_dict = {"openai_api_key": "foo"}
  init_options = vcon.filter_plugins.impl.openai.OpenAICompletionInitOptions(**init_options_dict)
  assert(init_options.openai_api_key == "foo")

  options_dict = {}
  options = vcon.filter_plugins.impl.openai.OpenAICompletionOptions(**options_dict)
  assert(options.input_dialogs == "")
  assert(options.input_transcripts == "")

def test_2_completion_text_summary():
  """ Test OpenAICompletion FilterPlugin with transcribe ananlysis and text output """
  in_vcon = vcon.Vcon()
  in_vcon.load(TEST_EXTERNAL_AUDIO_VCON_FILE)
  original_analysis_count = len(in_vcon.analysis)

  options = {}

  out_vcon = None

  try:
    out_vcon = in_vcon.openai_completion(options)

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
  assert(out_vcon.analysis[original_analysis_count]["vendor_product"] == "completion")
  assert(out_vcon.analysis[original_analysis_count]["vendor_schema"] == "text")
  assert(out_vcon.analysis[original_analysis_count]["prompt"] == "Summarize this conversation: ")
  assert(out_vcon.analysis[original_analysis_count]["mimetype"] == vcon.Vcon.MIMETYPE_TEXT_PLAIN)
  assert(out_vcon.analysis[original_analysis_count]["encoding"] == "none")
  assert(isinstance(out_vcon.analysis[original_analysis_count]["body"], str))
  assert(len(out_vcon.analysis[original_analysis_count]["body"]) > 250)
  assert(out_vcon.analysis[original_analysis_count]["model"] == "text-davinci-003")


def test_2_completion_object_summary():
  """ Test OpenAICompletion FilterPlugin with transcribe ananlysis and completion_object output """

  in_vcon = vcon.Vcon()
  in_vcon.load(TEST_EXTERNAL_AUDIO_VCON_FILE)
  original_analysis_count = len(in_vcon.analysis)

  options = {"jq_result": "."}

  out_vcon = None

  try:
    out_vcon = in_vcon.openai_completion(options)

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
  assert(out_vcon.analysis[original_analysis_count]["vendor_product"] == "completion")
  assert(out_vcon.analysis[original_analysis_count]["vendor_schema"] == "completion_object")
  assert(out_vcon.analysis[original_analysis_count]["prompt"] == "Summarize this conversation: ")
  assert(out_vcon.analysis[original_analysis_count]["mimetype"] == vcon.Vcon.MIMETYPE_JSON)
  assert(out_vcon.analysis[original_analysis_count]["encoding"] == "json")
  assert(isinstance(out_vcon.analysis[original_analysis_count]["body"], dict))
  assert(isinstance(out_vcon.analysis[original_analysis_count]["body"]["choices"][0]["text"], str))
  assert(len(out_vcon.analysis[original_analysis_count]["body"]["choices"][0]["text"]) > 250)
  assert(out_vcon.analysis[original_analysis_count]["model"] == "text-davinci-003")

