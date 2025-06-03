# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" VconProcessor binding for the Vcon decryptfilter filter_plugin """

import py_vcon_server.processor
import vcon.filter_plugins


PLUGIN_NAME = "decryptfilter"
CLASS_NAME = "DecryptFilterPlugin"
PLUGIN = vcon.filter_plugins.FilterPluginRegistry.get(PLUGIN_NAME)


DecryptInitOptions = py_vcon_server.processor.FilterPluginProcessor.makeInitOptions(CLASS_NAME, PLUGIN)


DecryptOptions = py_vcon_server.processor.FilterPluginProcessor.makeOptions(CLASS_NAME, PLUGIN)


class Decrypt(py_vcon_server.processor.FilterPluginProcessor):
  """ JWE decryption of vCon binding for **VconProcessor** """
  plugin_version = "0.0.1"
  plugin_name = PLUGIN_NAME
  options_class =  DecryptOptions
  headline = "vCon decryption **VconProcessor**"
  plugin_description = """
This **VconProcessor** will decrypt the JWE form vCon into the signed/unverified JWS vCon form.
"""

