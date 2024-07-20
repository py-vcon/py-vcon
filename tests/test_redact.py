""" Unit test for filter plugin framework """

import sys
import vcon
import vcon.filter_plugins
import pytest
import asyncio

# test foo registration file
import tests.redact_reg
import tests.redact
 
pytest_plugins = ('pytest_asyncio',)
TEST_DIARIZED_EXTERNAL_AUDIO_VCON_FILE = "tests/example_deepgram_external_dialog.vcon"

@pytest.mark.asyncio
async def test_redaction():
  plugin_names = vcon.filter_plugins.FilterPluginRegistry.get_names()

  print("found {} plugins: {}".format(len(plugin_names), plugin_names))

  # Test redact a test plugin, not fully implemented
  plugin_redact = vcon.filter_plugins.FilterPluginRegistry.get("redact")
  init_options = tests.redact.RedactInitOptions()
  options = tests.redact.RedactOptions()
  assert(plugin_redact is not None)
  assert(plugin_redact.import_plugin(init_options))
  
  in_vcon = vcon.Vcon()
  in_vcon.load(TEST_DIARIZED_EXTERNAL_AUDIO_VCON_FILE)
  out_vcon = await in_vcon.redact(options)

  vcon.filter_plugins.FilterPluginRegistry.shutdown_plugins()

