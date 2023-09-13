""" OpenAi filter plugin registrations """
import os
import vcon.filter_plugins

openai_api_key = os.getenv("OPENAI_API_KEY", None)
init_options = {"openai_api_key": openai_api_key}

vcon.filter_plugins.FilterPluginRegistry.register(
  "openai_completion",
  "vcon.filter_plugins.impl.openai",
  "OpenAICompletion",
  "OpenAI completion generative AI",
  init_options
  )

vcon.filter_plugins.FilterPluginRegistry.register(
  "openai_chat_completion",
  "vcon.filter_plugins.impl.openai",
  "OpenAIChatCompletion",
  "OpenAI chat completion generative AI",
  init_options
  )

