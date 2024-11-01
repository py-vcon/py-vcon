# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" VconProcessor binding for the Vcon signfilter filter_plugin """

import py_vcon_server.processor
import vcon.filter_plugins


PLUGIN_NAME = "signfilter"
CLASS_NAME = "SignFilterPlugin"
PLUGIN = vcon.filter_plugins.FilterPluginRegistry.get(PLUGIN_NAME)


SignInitOptions = py_vcon_server.processor.FilterPluginProcessor.makeInitOptions(CLASS_NAME, PLUGIN)


SignOptions = py_vcon_server.processor.FilterPluginProcessor.makeOptions(CLASS_NAME, PLUGIN)


class Sign(py_vcon_server.processor.FilterPluginProcessor):
  """ JWS signing of vCon binding for **VconProcessor** """
  plugin_version = "0.0.1"
  plugin_name = PLUGIN_NAME
  options_class =  SignOptions
  headline = "vCon signing **VconProcessor**"
  plugin_description = """
This **VconProcessor** will with sign the Vcon using JWS.
"""

