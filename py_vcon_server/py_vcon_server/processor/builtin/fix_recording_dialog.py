# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" VconProcessor binding for the Vcon fix recording dialog filter_plugin """

import py_vcon_server.processor
import vcon.filter_plugins


PLUGIN_NAME = "fix_recording_dialog"
CLASS_NAME = "FixRecordingDialog"
PLUGIN = vcon.filter_plugins.FilterPluginRegistry.get(PLUGIN_NAME)


FixRecordingDialogInitOptions = py_vcon_server.processor.FilterPluginProcessor.makeInitOptions(CLASS_NAME, PLUGIN)


FixRecordingDialogOptions = py_vcon_server.processor.FilterPluginProcessor.makeOptions(CLASS_NAME, PLUGIN)


class FixRecordingDialog(py_vcon_server.processor.FilterPluginProcessor):
  """ fix recording dialog vCon filterPlugin binding for **VconProcessor** """
  plugin_version = "0.0.1"
  plugin_name = PLUGIN_NAME
  options_class =  FixRecordingDialogOptions
  headline = "vCon fix recording dialog **VconProcessor**"
  plugin_description = """
This **VconProcessor** will fix dialog parameters that need updating post recording
"""

