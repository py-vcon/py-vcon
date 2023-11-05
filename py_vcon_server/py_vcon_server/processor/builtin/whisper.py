""" VconProcessor binding for the Vcon Whisper filter_plugin """

import typing
import pydantic
import py_vcon_server.processor
import py_vcon_server.logging_utils
import vcon.filter_plugins

logger = py_vcon_server.logging_utils.init_logger(__name__)


PLUGIN_NAME = "whisper"
CLASS_NAME = "Whisper"
PLUGIN = vcon.filter_plugins.FilterPluginRegistry.get(PLUGIN_NAME)


WhisperInitOptions = py_vcon_server.processor.FilterPluginProcessor.makeInitOptions(CLASS_NAME, PLUGIN)


WhisperOptions = py_vcon_server.processor.FilterPluginProcessor.makeOptions(CLASS_NAME, PLUGIN)


class Whisper(py_vcon_server.processor.FilterPluginProcessor):
  """ Whisper OpenAI transcription binding for **VconProcessor** """
  plugin_version = "0.0.1"
  plugin_name = PLUGIN_NAME
  options_class =  WhisperOptions
  headline = "Whisper OpenAI transcription binding for **VconProcessor**  with model size: {}".format(
    PLUGIN.plugin().init_options().model_size)
  plugin_description = """

This **VconProcessor** will transcribe one or all of the audio dialogs in the input Vcon and add analysis object(s) containing the transcription for the dialogs.
The **Whisper** **Vcon** **filter_plug** for transcription is used which is built upon the OpenAI Whisper package.
      """


    #TODO: register different Vcon filter_plugin for each model size

