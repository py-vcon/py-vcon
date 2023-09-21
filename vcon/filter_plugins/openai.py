""" OpenAi filter plugin registrations """
import os
import vcon.filter_plugins

logger = vcon.build_logger(__name__)

openai_api_key = os.getenv("OPENAI_API_KEY", "")
logger.warning("OPENAI_API_KEY env variable not set.  OpenAI pluggins will be no-op.")
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

