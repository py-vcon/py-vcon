# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" VconProcessor binding for the Vcon create amended filter_plugin """

import py_vcon_server.processor
import vcon.filter_plugins


PLUGIN_NAME = "create_amended"
CLASS_NAME = "AmendedFilterPlugin"
PLUGIN = vcon.filter_plugins.FilterPluginRegistry.get(PLUGIN_NAME)


AmendedInitOptions = py_vcon_server.processor.FilterPluginProcessor.makeInitOptions(CLASS_NAME, PLUGIN)


AmendedOptions = py_vcon_server.processor.FilterPluginProcessor.makeOptions(CLASS_NAME, PLUGIN)


class Amended(py_vcon_server.processor.FilterPluginProcessor):
  """ Create amended vCon binding for **VconProcessor** """
  plugin_version = "0.0.1"
  plugin_name = PLUGIN_NAME
  options_class =  AmendedOptions
  headline = "vCon create amended **VconProcessor**"
  plugin_description = """
This **VconProcessor** will create a new amendable vCon copy from the
given vCon and add it to the VconProcessorIO.  Typically the input vCon
is signed, but that is not necessary.
"""

