""" Registration for the Deepgram transcription **VconProcessor** """
import os
import py_vcon_server.processor
import py_vcon_server.processor.builtin.deepgram

deepgram_key = os.getenv("DEEPGRAM_KEY", "")
init_options = py_vcon_server.processor.builtin.deepgram.DeepgramInitOptions(deepgram_key = deepgram_key)

py_vcon_server.processor.VconProcessorRegistry.register(
      init_options,
      "deepgram",
      "py_vcon_server.processor.builtin.deepgram",
      "Deepgram"
      )

