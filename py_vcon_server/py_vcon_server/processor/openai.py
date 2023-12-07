""" Registration for the OpenAI chat_completions generative AI **VconProcessor** """
import os
import py_vcon_server.processor
import py_vcon_server.processor.builtin.openai

logger = py_vcon_server.logging_utils.init_logger(__name__)

openai_api_key = os.getenv("OPENAI_API_KEY", "")
if(openai_api_key == ""):
  logger.warning("OPENAI_API_KEY env variable not set.  OpenAI pluggins will be no-op.")
init_options = py_vcon_server.processor.builtin.openai.OpenAiChatCompletionInitOptions(openai_api_key = openai_api_key)

py_vcon_server.processor.VconProcessorRegistry.register(
      init_options,
      "openai_chat_completion",
      "py_vcon_server.processor.builtin.openai",
      "OpenAiChatCompletion"
      )

