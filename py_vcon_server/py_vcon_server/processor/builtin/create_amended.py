# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" VconProcessor binding for the Vcon create appended filter_plugin """

import py_vcon_server.processor
import vcon.filter_plugins


PLUGIN_NAME = "create_appended"
CLASS_NAME = "AppendedFilterPlugin"
PLUGIN = vcon.filter_plugins.FilterPluginRegistry.get(PLUGIN_NAME)


AppendedInitOptions = py_vcon_server.processor.FilterPluginProcessor.makeInitOptions(CLASS_NAME, PLUGIN)


AppendedOptions = py_vcon_server.processor.FilterPluginProcessor.makeOptions(CLASS_NAME, PLUGIN)


class Appended(py_vcon_server.processor.FilterPluginProcessor):
  """ Create appended vCon binding for **VconProcessor** """
  plugin_version = "0.0.1"
  plugin_name = PLUGIN_NAME
  options_class =  AppendedOptions
  headline = "vCon create appended **VconProcessor**"
  plugin_description = """
This **VconProcessor** will create a new appendable vCon copy from the
given vCon and add it to the VconProcessorIO.  Typically the input vCon
is signed, but that is not necessary.
"""

