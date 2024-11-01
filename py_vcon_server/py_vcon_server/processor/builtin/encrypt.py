# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" VconProcessor binding for the Vcon encryptfilter filter_plugin """

import py_vcon_server.processor
import vcon.filter_plugins


PLUGIN_NAME = "encryptfilter"
CLASS_NAME = "EncryptFilterPlugin"
PLUGIN = vcon.filter_plugins.FilterPluginRegistry.get(PLUGIN_NAME)


EncryptInitOptions = py_vcon_server.processor.FilterPluginProcessor.makeInitOptions(CLASS_NAME, PLUGIN)


EncryptOptions = py_vcon_server.processor.FilterPluginProcessor.makeOptions(CLASS_NAME, PLUGIN)


class Encrypt(py_vcon_server.processor.FilterPluginProcessor):
  """ JWE encryption of vCon binding for **VconProcessor** """
  plugin_version = "0.0.1"
  plugin_name = PLUGIN_NAME
  options_class =  EncryptOptions
  headline = "vCon encryption **VconProcessor**"
  plugin_description = """
This **VconProcessor** will encrypt the Vcon into its JWE form.
"""

