# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
# Copyright (C) 2026 SIP Spectrum, Inc.  All rights reserved.
""" Unit test for OpenAI filter plugins """
import os
import json
import logging
import types
import typing
import pydantic
import vcon
import vcon.filter_plugins.impl.openai
import vcon.pydantic_utils
import pytest
import pytest_asyncio


TEST_EXTERNAL_AUDIO_VCON_FILE = "tests/example_external_dialog.vcon"
TEST_DIARIZED_EXTERNAL_AUDIO_VCON_FILE = "tests/example_deepgram_external_dialog.vcon"
SHORT_RECORDING_VCON = "tests/hello.vcon"
# Cheap model for unit tests; the plugin default is a more capable (more costly) model.
TEST_CHAT_MODEL = os.getenv("OPENAI_TEST_MODEL", "gpt-6-luna")

def test_1_options():
  """ Tests for OpenAIChatCompletionInitOptions and OpenAIChatCompletionOptions """
  init_options_dict = {}
  try:
    init_options = vcon.filter_plugins.impl.openai.OpenAIChatCompletionInitOptions(**init_options_dict)
    raise Exception("Expected exception due to missing openai_api_key")

  except vcon.pydantic_utils.ValidationErrorType as e:
    # expected
    pass

  init_options_dict = {
      "openai_api_key": "foo"
    }
  init_options = vcon.filter_plugins.impl.openai.OpenAIChatCompletionInitOptions(**init_options_dict)
  assert(init_options.openai_api_key == "foo")

  options_dict = {}
  options = vcon.filter_plugins.impl.openai.OpenAIChatCompletionOptions(**options_dict)
  assert(options.input_dialogs == "")


@pytest.mark.asyncio
async def test_3_chat_completion_object_summary():
  """ Test OpenAIChatCompletion FilterPlugin with transcribe ananlysis and chat_completion_object output """

  in_vcon = vcon.Vcon()
  in_vcon.load(TEST_EXTERNAL_AUDIO_VCON_FILE)
  original_analysis_count = len(in_vcon.analysis)

  options = {
      "jq_result": ".",
      "model": TEST_CHAT_MODEL,
      "reasoning_effort": "none"
    }

  out_vcon = None

  try:
    out_vcon = await in_vcon.openai_chat_completion(options)

  except vcon.pydantic_utils.ValidationErrorType as e:
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
      "model": TEST_CHAT_MODEL,
      "reasoning_effort": "none"
    }

  out_vcon = None

  try:
    out_vcon = await in_vcon.openai_chat_completion(options)

  except vcon.pydantic_utils.ValidationErrorType as e:
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
  assert(30 <= plugin.last_stats['num_messages'] <= 170)
  assert(plugin.last_stats['num_text_dialogs'] == 0)
  assert(plugin.last_stats['num_dialog_list'] == 1)
  assert(30 <= plugin.last_stats['num_transcribe_analysis'] <= 170)

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
      "model": TEST_CHAT_MODEL,
      "reasoning_effort": "none"
    }

  out_vcon = None

  try:
    out_vcon = await in_vcon.openai_chat_completion(options)

  except vcon.pydantic_utils.ValidationErrorType as e:
    openai_key = os.getenv("OPENAI_API_KEY", None)
    if(openai_key is None or
      openai_key == ""):
        raise Exception("OPENAI_API_KEY environment variable not set this test cannot run") from e
    raise e

  after_analysis_count = len(out_vcon.analysis)
  assert(after_analysis_count == 2) # transcription and openai summary

  # Check stats on input to model:
  plugin = vcon.filter_plugins.FilterPluginRegistry.get("openai_chat_completion").plugin()
  # verify stats of extracted messages are as expected
  print("stats: {}".format(plugin.last_stats))
  assert(plugin.last_stats['num_messages'] == 2)
  assert(plugin.last_stats['num_text_dialogs'] == 0)
  assert(plugin.last_stats['num_dialog_list'] == 1)
  assert(plugin.last_stats['num_transcribe_analysis'] == 2)

  assert((after_analysis_count - original_analysis_count) == 2)
  assert(out_vcon.analysis[original_analysis_count + 1]["type"] == "summary")
  assert(out_vcon.analysis[original_analysis_count + 1]["dialog"] == 0)
  assert(out_vcon.analysis[original_analysis_count + 1]["vendor"] == "openai")
  assert(out_vcon.analysis[original_analysis_count + 1]["product"] == "ChatCompletion")
  assert(out_vcon.analysis[original_analysis_count + 1]["schema"] == "chat_completion_object")
  assert(out_vcon.analysis[original_analysis_count + 1]["prompt"] == "Summarize the transcript in these messages.")
  assert(out_vcon.analysis[original_analysis_count + 1].get("mimetype", None) is None)
  assert(out_vcon.analysis[original_analysis_count + 1]["mediatype"] == vcon.Vcon.MEDIATYPE_JSON)
  assert(out_vcon.analysis[original_analysis_count + 1]["encoding"] == "json")
  assert(isinstance(out_vcon.analysis[original_analysis_count + 1]["body"], dict))
  assert(isinstance(out_vcon.analysis[original_analysis_count + 1]["body"]["choices"][0]["message"]["content"], str))
  assert(len(out_vcon.analysis[original_analysis_count + 1]["body"]["choices"][0]["message"]["content"]) > 20)
  assert(out_vcon.analysis[original_analysis_count + 1]["model"] == TEST_CHAT_MODEL)
  print("Response: " + out_vcon.analysis[original_analysis_count + 1]["body"]["choices"][0]["message"]["content"])


@pytest_asyncio.fixture(autouse = True)
async def close_openai_clients():
  """
  Close the plugins' OpenAI clients at the end of every test in this module,
  while the test's event loop is still running.

  Each test gets its own event loop, and a client's connections belong to the
  loop that opened them.  A client left over from a finished test is closed by
  the OpenAI SDK's __del__ on whatever loop is running when it is collected,
  which fails with "Event loop is closed" and is reported by asyncio.  Closing
  here leaves nothing for the SDK to finalize.
  """
  yield
  for registration in vcon.filter_plugins.FilterPluginRegistry._registry.values():
    plugin = registration._plugin
    client = getattr(plugin, "client", None) if(plugin is not None) else None
    if(isinstance(client, vcon.filter_plugins.impl.openai.OpenAIClient)):
      await client.aclose()


def test_client_per_event_loop():
  """
  The AsyncOpenAI client is bound to the event loop it is first used on, so the
  plugin must not reuse it on a later loop (RuntimeError: Event loop is closed).
  """
  import asyncio
  init_options = vcon.filter_plugins.impl.openai.OpenAIChatCompletionInitOptions(
      openai_api_key = "sk-test-not-used"
    )
  client = vcon.filter_plugins.impl.openai.OpenAIClient(init_options, "test")

  async def same_loop_twice():
    return(client._async_client(), client._async_client())

  first, again = asyncio.run(same_loop_twice())
  # reused within a loop, keeping its connection pool
  assert(first is again)

  async def once():
    return(client._async_client())

  # a new loop gets a new client
  second = asyncio.run(once())
  assert(second is not first)

  client.close()
  assert(client.client is None)


def test_init_no_key():
  """ Construction with an empty openai_api_key must not raise.
      The OpenAIClient should mark key_set False and skip creating
      the inner AsyncOpenAI client.
  """
  init_options_dict = { "openai_api_key": "" }

  chat_init = vcon.filter_plugins.impl.openai.OpenAIChatCompletionInitOptions(
      **init_options_dict
    )
  chat_plugin = vcon.filter_plugins.impl.openai.OpenAIChatCompletion(chat_init)
  assert(chat_plugin.client.key_set == False)
  assert(hasattr(chat_plugin.client, "client") == False)


@pytest.mark.asyncio
async def test_filter_no_key_raises_openai_chat_completion():
  """ OpenAIChatCompletion.filter must raise OpenAIKeyNotSet when constructed
      with no api key.
  """
  init_options = vcon.filter_plugins.impl.openai.OpenAIChatCompletionInitOptions(
      openai_api_key = ""
    )
  plugin = vcon.filter_plugins.impl.openai.OpenAIChatCompletion(init_options)

  in_vcon = vcon.Vcon()
  in_vcon.add_dialog_inline_text(
      "Hello, this is a test.",
      "2024-03-06T20:07:43+00:00",
      5.0,
      0,
      vcon.Vcon.MEDIATYPE_TEXT_PLAIN
    )

  options = vcon.filter_plugins.impl.openai.OpenAIChatCompletionOptions()

  try:
    await plugin.filter(in_vcon, options)
    raise Exception("filter should have raised OpenAIKeyNotSet")
  except vcon.filter_plugins.impl.openai.OpenAIKeyNotSet:
    pass



def make_chat_response(
    content: typing.Union[str, None],
    finish_reason: str,
    usage: typing.Union[typing.Dict[str, typing.Any], None] = None,
    refusal: typing.Union[str, None] = None
  ) -> typing.Dict[str, typing.Any]:
  """ Build a canned chat completion response dict, as returned by OpenAIClient.chat_completions """
  return({
      "id": "chatcmpl-test",
      "object": "chat.completion",
      "model": TEST_CHAT_MODEL,
      "choices": [
          {
            "index": 0,
            "finish_reason": finish_reason,
            "message": {
                "role": "assistant",
                "content": content,
                "refusal": refusal
              }
          }
        ],
      "usage": usage
    })


REASONING_USAGE = {
    "completion_tokens": 200,
    "prompt_tokens": 1634,
    "total_tokens": 1834,
    "completion_tokens_details": {
        "reasoning_tokens": 190
      }
  }


def make_stubbed_plugin(
    response: typing.Dict[str, typing.Any]
  ) -> vcon.filter_plugins.impl.openai.OpenAIChatCompletion:
  """ OpenAIChatCompletion plugin whose API call returns the given canned response """
  init_options = vcon.filter_plugins.impl.openai.OpenAIChatCompletionInitOptions(
      openai_api_key = "sk-test-not-used"
    )
  plugin = vcon.filter_plugins.impl.openai.OpenAIChatCompletion(init_options)

  async def chat_completions(options, messages):
    return(response)

  plugin.client.chat_completions = chat_completions
  return(plugin)


def make_text_vcon() -> vcon.Vcon:
  """ Vcon with one text dialog """
  in_vcon = vcon.Vcon()
  in_vcon.set_party_parameter("tel", "+15551234567")
  in_vcon.add_dialog_inline_text(
      "Hello, this is a test.",
      "2024-03-06T20:07:43+00:00",
      5.0,
      0,
      vcon.Vcon.MEDIATYPE_TEXT_PLAIN
    )
  return(in_vcon)


@pytest.mark.asyncio
async def test_token_limit_empty_output_raises():
  """ All of max_tokens used for reasoning and no text output raises OpenAITokenLimitExceeded """
  plugin = make_stubbed_plugin(make_chat_response("", "length", REASONING_USAGE))
  options = vcon.filter_plugins.impl.openai.OpenAIChatCompletionOptions(model = TEST_CHAT_MODEL)

  try:
    await plugin.filter(make_text_vcon(), options)
    raise Exception("filter should have raised OpenAITokenLimitExceeded")
  except vcon.filter_plugins.impl.openai.OpenAITokenLimitExceeded as limit_error:
    message = str(limit_error)
    print(message)
    assert("max_tokens (1000; 200 used, 190 for reasoning)" in message)
    assert("returned no text" in message)
    assert("Increase max_tokens" in message)


@pytest.mark.asyncio
async def test_token_limit_empty_output_raises_no_reasoning_count():
  """ Empty output with null content and no usage reported still raises with a clear message """
  plugin = make_stubbed_plugin(make_chat_response(None, "length"))
  options = vcon.filter_plugins.impl.openai.OpenAIChatCompletionOptions(model = TEST_CHAT_MODEL)

  try:
    await plugin.filter(make_text_vcon(), options)
    raise Exception("filter should have raised OpenAITokenLimitExceeded")
  except vcon.filter_plugins.impl.openai.OpenAITokenLimitExceeded as limit_error:
    message = str(limit_error)
    print(message)
    assert("max_tokens (1000)" in message)
    assert("reasoning)" not in message)
    assert("returned no text" in message)


@pytest.mark.asyncio
async def test_token_limit_truncated_json_raises():
  """ JSON output cut off at max_tokens raises OpenAITokenLimitExceeded """
  plugin = make_stubbed_plugin(make_chat_response('{"score": 7, "criteria": ["po', "length", REASONING_USAGE))
  options = vcon.filter_plugins.impl.openai.OpenAIChatCompletionOptions(
      model = TEST_CHAT_MODEL,
      json_response = True
    )

  try:
    await plugin.filter(make_text_vcon(), options)
    raise Exception("filter should have raised OpenAITokenLimitExceeded")
  except vcon.filter_plugins.impl.openai.OpenAITokenLimitExceeded as limit_error:
    message = str(limit_error)
    print(message)
    assert("the JSON is incomplete" in message)


@pytest.mark.asyncio
async def test_token_limit_truncated_valid_json_kept(caplog):
  """ JSON output that is still valid despite finish_reason length is kept and flagged """
  plugin = make_stubbed_plugin(make_chat_response('{"score": 7}', "length", REASONING_USAGE))
  options = vcon.filter_plugins.impl.openai.OpenAIChatCompletionOptions(
      model = TEST_CHAT_MODEL,
      json_response = True
    )
  in_vcon = make_text_vcon()

  with caplog.at_level(logging.WARNING, logger = "vcon.filter_plugins.impl.openai"):
    out_vcon = await plugin.filter(in_vcon, options)

  assert(len(out_vcon.analysis) == 1)
  assert(out_vcon.analysis[0]["truncated"] == True)
  assert(out_vcon.analysis[0]["body"] == '{"score": 7}')
  assert("Keeping the truncated output" in caplog.text)


@pytest.mark.asyncio
async def test_token_limit_truncated_text_warns_and_flags(caplog):
  """ Text output cut off at max_tokens is kept, warned about and flagged on the analysis """
  plugin = make_stubbed_plugin(make_chat_response("The caller asked to cancel the", "length", REASONING_USAGE))
  options = vcon.filter_plugins.impl.openai.OpenAIChatCompletionOptions(model = TEST_CHAT_MODEL)
  in_vcon = make_text_vcon()

  with caplog.at_level(logging.WARNING, logger = "vcon.filter_plugins.impl.openai"):
    out_vcon = await plugin.filter(in_vcon, options)

  assert(len(out_vcon.analysis) == 1)
  assert(out_vcon.analysis[0]["truncated"] == True)
  assert(out_vcon.analysis[0]["body"] == "The caller asked to cancel the")
  assert("cut off at max_tokens (1000; 200 used, 190 for reasoning)" in caplog.text)
  assert("Keeping the truncated output" in caplog.text)


@pytest.mark.asyncio
async def test_token_limit_truncated_text_fail_on_truncation_raises():
  """ Text output cut off at max_tokens raises when fail_on_truncation is True """
  plugin = make_stubbed_plugin(make_chat_response("The caller asked to cancel the", "length", REASONING_USAGE))
  options = vcon.filter_plugins.impl.openai.OpenAIChatCompletionOptions(
      model = TEST_CHAT_MODEL,
      fail_on_truncation = True
    )

  try:
    await plugin.filter(make_text_vcon(), options)
    raise Exception("filter should have raised OpenAITokenLimitExceeded")
  except vcon.filter_plugins.impl.openai.OpenAITokenLimitExceeded as limit_error:
    message = str(limit_error)
    print(message)
    assert("cut off at max_tokens (1000; 200 used, 190 for reasoning)" in message)


@pytest.mark.asyncio
async def test_complete_response_not_flagged(caplog):
  """ A response that finished normally is added with no truncated flag and no warning """
  plugin = make_stubbed_plugin(make_chat_response("The caller asked to cancel.", "stop", REASONING_USAGE))
  options = vcon.filter_plugins.impl.openai.OpenAIChatCompletionOptions(model = TEST_CHAT_MODEL)
  in_vcon = make_text_vcon()

  with caplog.at_level(logging.WARNING, logger = "vcon.filter_plugins.impl.openai"):
    out_vcon = await plugin.filter(in_vcon, options)

  assert(len(out_vcon.analysis) == 1)
  assert("truncated" not in out_vcon.analysis[0])
  assert(out_vcon.analysis[0]["body"] == "The caller asked to cancel.")
  assert("cut off at max_tokens" not in caplog.text)


@pytest.mark.asyncio
async def test_refusal_raises():
  """ A refusal from the model raises OpenAIRefusal with the refusal text """
  plugin = make_stubbed_plugin(make_chat_response(None, "stop", refusal = "I can not help with that."))
  options = vcon.filter_plugins.impl.openai.OpenAIChatCompletionOptions(model = TEST_CHAT_MODEL)

  try:
    await plugin.filter(make_text_vcon(), options)
    raise Exception("filter should have raised OpenAIRefusal")
  except vcon.filter_plugins.impl.openai.OpenAIRefusal as refusal_error:
    message = str(refusal_error)
    print(message)
    assert("refused the request: I can not help with that." in message)


@pytest.mark.asyncio
async def test_optional_api_args_sent_only_when_set():
  """ temperature and reasoning_effort are only sent to OpenAI when set to non default values """
  init_options = vcon.filter_plugins.impl.openai.OpenAIChatCompletionInitOptions(
      openai_api_key = "sk-test-not-used"
    )
  client = vcon.filter_plugins.impl.openai.OpenAIClient(init_options, "test")
  calls = []

  async def create(**kwargs):
    calls.append(kwargs)
    return(types.SimpleNamespace(dict = lambda: make_chat_response("ok", "stop")))

  stub_async_client = types.SimpleNamespace(
      chat = types.SimpleNamespace(completions = types.SimpleNamespace(create = create))
    )
  client._async_client = lambda: stub_async_client
  messages = [{"role": "user", "content": "hello"}]

  default_options = vcon.filter_plugins.impl.openai.OpenAIChatCompletionOptions()
  await client.chat_completions(default_options, messages)
  assert(calls[0]["model"] == default_options.model)
  assert(calls[0]["max_completion_tokens"] == 1000)
  assert("temperature" not in calls[0])
  assert("reasoning_effort" not in calls[0])
  assert("max_tokens" not in calls[0])

  set_options = vcon.filter_plugins.impl.openai.OpenAIChatCompletionOptions(
      temperature = 0.5,
      reasoning_effort = "low"
    )
  await client.chat_completions(set_options, messages)
  assert(calls[1]["temperature"] == 0.5)
  assert(calls[1]["reasoning_effort"] == "low")

