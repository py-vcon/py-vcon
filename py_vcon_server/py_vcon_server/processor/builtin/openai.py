# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" VconProcessor binding for the Vcon OpenAI chat_completion filter_plugin """

import typing
import pydantic
import py_vcon_server.processor
import vcon.filter_plugins


PLUGIN_NAME = "openai_chat_completion"
CLASS_NAME = "OpenAiChatCompletion"
PLUGIN = vcon.filter_plugins.FilterPluginRegistry.get(PLUGIN_NAME)


OpenAiChatCompletionInitOptions = py_vcon_server.processor.FilterPluginProcessor.makeInitOptions(CLASS_NAME, PLUGIN)


OpenAiChatCompletionOptions = py_vcon_server.processor.FilterPluginProcessor.makeOptions(CLASS_NAME, PLUGIN)


class OpenAiChatCompletion(py_vcon_server.processor.FilterPluginProcessor):
  """ OpenAi Chat Completion generative AI binding for **VconProcessor** """
  plugin_version = "0.0.1"
  plugin_name = PLUGIN_NAME
  options_class =  OpenAiChatCompletionOptions
  headline = "OpenAi Chat Completion binding for **VconProcessor**"
  plugin_description = """

This **VconProcessor** will input the text dialog and transcribed dialog(s) for one or all of the audio dialogs in the input Vcon and add an analysis object containing the generative AI output for the prompt provided in the option.
The **openai_chat_completions** **Vcon** **filter_plug** is used.
      """

