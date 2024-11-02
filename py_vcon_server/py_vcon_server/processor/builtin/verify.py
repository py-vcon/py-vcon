# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" VconProcessor binding for the Vcon verifyfilter filter_plugin """

import py_vcon_server.processor
import vcon.filter_plugins


PLUGIN_NAME = "verifyfilter"
CLASS_NAME = "VerifyFilterPlugin"
PLUGIN = vcon.filter_plugins.FilterPluginRegistry.get(PLUGIN_NAME)


VerifyInitOptions = py_vcon_server.processor.FilterPluginProcessor.makeInitOptions(CLASS_NAME, PLUGIN)


VerifyOptions = py_vcon_server.processor.FilterPluginProcessor.makeOptions(CLASS_NAME, PLUGIN)


class Verify(py_vcon_server.processor.FilterPluginProcessor):
  """ JWS verification of vCon binding for **VconProcessor** """
  plugin_version = "0.0.1"
  plugin_name = PLUGIN_NAME
  options_class =  VerifyOptions
  headline = "vCon verification **VconProcessor**"
  plugin_description = """
This **VconProcessor** will verify the JWS signed Vcon.
"""

