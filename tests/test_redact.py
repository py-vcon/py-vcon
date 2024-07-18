""" Unit test for filter plugin framework """

import sys
import vcon
import vcon.filter_plugins
import pytest
import asyncio

# test foo registration file
import tests.redact_reg

pytest_plugins = ('pytest_asyncio',)

@pytest.mark.asyncio
async def test_registry():
  print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
  plugin_names = vcon.filter_plugins.FilterPluginRegistry.get_names()

  print("found {} plugins: {}".format(len(plugin_names), plugin_names))

  # Test redact a test plugin, not fully implemented
  plugin_redact = vcon.filter_plugins.FilterPluginRegistry.get("redact")
  init_options = vcon.filter_plugins.FilterPluginInitOptions()
  options = vcon.filter_plugins.FilterPluginOptions()
  assert(plugin_redact is not None)
  assert(plugin_redact.import_plugin(init_options))
  
  await plugin_redact.filter(None, options)

  in_vcon = vcon.Vcon()
  out_vcon = await in_vcon.redact(options)

  vcon.filter_plugins.FilterPluginRegistry.shutdown_plugins()

