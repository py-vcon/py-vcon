# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" Unit tests for empty Dialog Objects ({}) and clear_dialog """

import pytest
import vcon
import vcon.filter_plugins
import tests.common_utils

START = "2022-06-21T13:53:26-04:00"


def make_vcon() -> vcon.Vcon:
  """ text, empty, text Dialogs, each in its own Session """
  v = vcon.Vcon()
  v.set_uuid("example.com")
  v.set_party_parameter("tel", "+15551110000")
  v.set_party_parameter("tel", "+15552220000")
  v.add_text_dialog_inline("Hello", START, 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.add_text_dialog_inline("Lost", START, 0, 1, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.add_text_dialog_inline("Goodbye", START, 0, 1, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.clear_dialog(1)
  return(v)


@pytest.mark.asyncio
async def test_get_dialog_text_empty():
  v = make_vcon()
  assert(await v.get_dialog_text(1) == [])
  assert((await v.get_dialog_text(0))[0]["text"] == "Hello")


class StopBeforeRequest(Exception):
  """ raised in place of the OpenAI request """


@pytest.mark.asyncio
async def test_openai_skips_empty_dialog(monkeypatch):
  v = make_vcon()
  plugin = vcon.filter_plugins.FilterPluginRegistry.get("openai_chat_completion").plugin()
  messages = []

  async def no_request(sorted_messages, options):
    messages.extend(sorted_messages)
    raise StopBeforeRequest()

  # no network request: the messages built from the Dialogs are captured instead
  monkeypatch.setattr(plugin.client, "key_set", True)
  monkeypatch.setattr(plugin, "chat_completions_with_retry", no_request)
  with pytest.raises(StopBeforeRequest):
    await v.openai_chat_completion({})

  assert(plugin.last_stats["num_dialog_list"] == 3)
  assert(plugin.last_stats["num_text_dialogs"] == 2)
  user_messages = [message["content"] for message in messages if(message["role"] == "user")]
  assert(len(user_messages) == 2)
  assert("Hello" in user_messages[0] and "Goodbye" in user_messages[1])


@pytest.mark.asyncio
async def test_deepgram_skips_empty_dialog():
  v = make_vcon()
  v.add_recording_dialog_inline(b"\x00\x01", START, 10, [0, 1], "audio/x-wav", "a.wav")
  # the recording has a transcript, so nothing is sent to Deepgram
  v.add_analysis(3, "transcript", {"results": {}}, "deepgram", "deepgram_prerecorded",
    product = "transcription")
  before = v.dumpd()
  out_vcon = await v.deepgram({"deepgram_key": "not-used"})
  assert(out_vcon.dumpd() == before)


@pytest.mark.asyncio
async def test_whisper_skips_empty_dialog():
  plugin = vcon.filter_plugins.FilterPluginRegistry.get("whisper").plugin()
  if(plugin is None):
    pytest.skip("whisper (stable_whisper) is not installed")

  v = make_vcon()
  before = v.dumpd()
  out_vcon = await v.whisper({})
  assert(out_vcon.dumpd() == before)


def test_single_dialog_methods_raise():
  v = make_vcon()
  with pytest.raises(AttributeError, match = r"dialog\[1\] is an empty Dialog Object"):
    v.decode_dialog_inline_body(1)
  with pytest.raises(AttributeError, match = r"dialog\[1\] is an empty Dialog Object"):
    v.verify_dialog_external_recording(1, b"body")
  assert(v.decode_dialog_inline_body(0) == "Hello")


def test_clear_dialog_default():
  v = vcon.Vcon()
  v.set_uuid("example.com")
  v.set_party_parameter("tel", "+15551110000")
  v.add_text_dialog_inline("Hello", START, 5, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.add_text_dialog_inline("Again", START, 7, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN, session = 0)
  session_before = dict(v.sessions[0])
  second_before = dict(v.dialog[1])

  assert(v.clear_dialog(0) is None)
  assert(v.dialog[0] == {})
  assert(v.dialog[1] == second_before)
  # still listed in its Session, start and duration unchanged
  assert(v.sessions[0] == session_before)
  assert(v.sessions[0]["dialog"] == [0, 1])
  tests.common_utils.assert_valid_vcon(v.dumpd())


def test_clear_dialog_remove_from_sessions():
  v = vcon.Vcon()
  v.set_uuid("example.com")
  v.set_party_parameter("tel", "+15551110000")
  v.add_text_dialog_inline("Hello", START, 5, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.add_text_dialog_inline("Again", START, 5, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN, session = 0)
  v.add_session()
  v.add_dialog_to_session(1, 0)
  v.add_analysis(0, "summary", "a summary", "test_vendor", None, "none")
  assert(v.find_sessions_for_dialog(0) == [0, 1])

  v.clear_dialog(0, remove_from_sessions = True)
  assert(v.dialog[0] == {})
  assert(v.sessions[0]["dialog"] == [1])
  assert(v.sessions[1]["dialog"] == [])
  assert(v.find_sessions_for_dialog(0) == [])
  # Analysis references are left to the caller
  assert(v.analysis[0]["dialog"] == 0)


def test_clear_dialog_bad_index():
  v = make_vcon()
  with pytest.raises(AttributeError, match = "does not exist"):
    v.clear_dialog(3)
  with pytest.raises(AttributeError, match = "does not exist"):
    v.clear_dialog(-1)


def test_set_dialog_parameter_new_dialog():
  v = vcon.Vcon()
  v.set_uuid("example.com")
  v.set_party_parameter("tel", "+15551110000")
  dialog_index = v.set_dialog_parameter("start", START)
  assert(dialog_index == 0)
  assert(v.find_sessions_for_dialog(0) == [0])
  assert(v.sessions[0]["dialog"] == [0])

  v.set_dialog_parameter("type", "text", 0)
  v.set_dialog_parameter("parties", 0, 0)
  v.set_dialog_parameter("mediatype", vcon.Vcon.MEDIATYPE_TEXT_PLAIN, 0)
  v.set_dialog_parameter("encoding", "none", 0)
  v.set_dialog_parameter("body", "Hello", 0)
  tests.common_utils.assert_valid_vcon(v.dumpd())


def test_set_dialog_parameter_on_empty_dialog():
  v = make_vcon()
  assert(v.set_dialog_parameter("type", "incomplete", 1) == 1)
  assert(v.dialog[1] == {"type": "incomplete"})
