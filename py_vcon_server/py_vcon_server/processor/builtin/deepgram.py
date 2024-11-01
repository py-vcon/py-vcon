# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" VconProcessor binding for the Vcon deepgram filter_plugin """

import py_vcon_server.processor
import vcon.filter_plugins


PLUGIN_NAME = "deepgram"
CLASS_NAME = "Deepgram"
PLUGIN = vcon.filter_plugins.FilterPluginRegistry.get(PLUGIN_NAME)


DeepgramInitOptions = py_vcon_server.processor.FilterPluginProcessor.makeInitOptions(CLASS_NAME, PLUGIN)


DeepgramOptions = py_vcon_server.processor.FilterPluginProcessor.makeOptions(CLASS_NAME, PLUGIN)


class Deepgram(py_vcon_server.processor.FilterPluginProcessor):
  """ Deepgram transcription binding for **VconProcessor** """
  plugin_version = "0.0.1"
  plugin_name = PLUGIN_NAME
  options_class =  DeepgramOptions
  headline = "Deepgram transcription binding for **VconProcessor**"
  plugin_description = """
This **VconProcessor** will transcribe one or all of the audio dialogs in the input Vcon and add analysis object(s) containing the transcription for the dialogs.
The **Deepgram** **Vcon** **filter_plug** for transcription is used.
"""

