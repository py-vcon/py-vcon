""" Unit test for filter plugin framework """

import sys
import vcon
import vcon.filter_plugins
import pytest

# test foo registration file
import redact_reg


@pytest.mark.asyncio
async def test_registry():
  plugin_names = vcon.filter_plugins.FilterPluginRegistry.get_names()

  print("found {} plugins: {}".format(len(plugin_names), plugin_names))

  # Test redact a test plugin, not fully implemented
  plugin_redact = vcon.filter_plugins.FilterPluginRegistry.get("redact")
  init_options = vcon.filter_plugins.FilterPluginInitOptions()
  options = vcon.filter_plugins.FilterPluginOptions()
  assert(plugin_redact is not None)
  assert(plugin_redact.import_plugin(init_options))
  try:
    await plugin_redact.filter(None, options)
    # SHould not get here
    raise Exception("Should have thrown a FilterPluginNotImplemented exception")

  except vcon.filter_plugins.FilterPluginNotImplemented as not_found_error:
    # We are expecting this exception
    print("got {}".format(not_found_error), file=sys.stderr)
    #raise not_found_error

  # this time test foop using its registered name as a method
  try:
    in_vcon = vcon.Vcon()
    out_vcon = await in_vcon.redact(options)
    # SHould not get here
    raise Exception("Should have thrown a FilterPluginNotImplemented exception")

  except vcon.filter_plugins.FilterPluginNotImplemented as not_found_error:
    # We are expecting this exception
    print("got {}".format(not_found_error), file=sys.stderr)
    #raise not_found_error

  vcon.filter_plugins.FilterPluginRegistry.set_type_default_name("exclaim", "redact")
  assert(vcon.filter_plugins.FilterPluginRegistry.get_type_default_name("exclaim") == "redact")
  assert(vcon.filter_plugins.FilterPluginRegistry.get_type_default_plugin("exclaim") == plugin_redact)

  # this time test redact using it set as default type exclaim name as a method
  in_vcon = vcon.Vcon()
  try:
    out_vcon = await in_vcon.exclaim()
    # Should not get here
    raise Exception("Should have thrown a AttributErro for missing options arguement")

  except AttributeError as missing_options:
    # expected
    pass

  try:
    out_vcon = await in_vcon.exclaim(options)
    # SHould not get here
    raise Exception("Should have thrown a FilterPluginNotImplemented exception")

  except vcon.filter_plugins.FilterPluginNotImplemented as not_found_error:
    # We are expecting this exception
    print("got {}".format(not_found_error), file=sys.stderr)
    #raise not_found_error


  # Test that real plugin was registered
  plugin_whisper = vcon.filter_plugins.FilterPluginRegistry.get("whisper")
  assert(plugin_whisper is not None)
  init_options = vcon.filter_plugins.FilterPluginInitOptions(model_size = "base")
  assert(plugin_whisper.import_plugin(init_options))
  # force open AI chat plugin to be instantiated so that we can test delete/close of the client
  plugin_openai_chat = vcon.filter_plugins.FilterPluginRegistry.get("openai_chat_completion")
  assert(plugin_openai_chat is not None)
  assert(plugin_openai_chat.import_plugin({"openai_api_key": "abc"}))

  # Verify whisper is the default transcribe type filter plugin
  assert(vcon.filter_plugins.FilterPluginRegistry.get_type_default_name("transcribe") == "whisper")

  vcon.filter_plugins.FilterPluginRegistry.shutdown_plugins()

