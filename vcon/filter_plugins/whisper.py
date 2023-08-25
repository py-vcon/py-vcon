""" Whisper audio transcription filter plugin registration """
import vcon.filter_plugins

# Register the whisper filter plugin
init_options = {"model_size": "base"}

vcon.filter_plugins.FilterPluginRegistry.register(
  "whisper",
  "vcon.filter_plugins.impl.whisper",
  "Whisper",
  "OpenAI Whisper implemented transcription of audio dialog recordings using model size: \"base\"",
  init_options
  )

# Make this the default transcribe type filter plugin
vcon.filter_plugins.FilterPluginRegistry.set_type_default_name("transcribe", "whisper")

