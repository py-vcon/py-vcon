# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" Unit test for filter plugin framework """

import sys
import vcon
import vcon.filter_plugins
import pytest

# test foo registration file
import tests.foo_reg


@pytest.mark.asyncio
async def test_registry():
  plugin_names = vcon.filter_plugins.FilterPluginRegistry.get_names()

  print("found {} plugins: {}".format(len(plugin_names), plugin_names))

  # Test foo a test plugin, not fully implemented
  plugin_foonoinit = vcon.filter_plugins.FilterPluginRegistry.get("foonoinittype")
  try:
    assert(plugin_foonoinit.plugin() is not None)
    raise Exception("Should have asied exception for missing init_options_type")

  except vcon.filter_plugins.FilterPluginNotImplemented as e:
    # expected
    pass

  plugin_foop = vcon.filter_plugins.FilterPluginRegistry.get("foop")
  init_options = vcon.filter_plugins.FilterPluginInitOptions()
  options = vcon.filter_plugins.FilterPluginOptions()
  assert(plugin_foop is not None)
  assert(plugin_foop.import_plugin(init_options))
  try:
    await plugin_foop.filter(None, options)
    # SHould not get here
    raise Exception("Should have thrown a FilterPluginNotImplemented exception")

  except vcon.filter_plugins.FilterPluginNotImplemented as not_found_error:
    # We are expecting this exception
    print("got {}".format(not_found_error), file=sys.stderr)
    #raise not_found_error

  # this time test foop using its registered name as a method
  try:
    in_vcon = vcon.Vcon()
    out_vcon = await in_vcon.foop(options)
    # SHould not get here
    raise Exception("Should have thrown a FilterPluginNotImplemented exception")

  except vcon.filter_plugins.FilterPluginNotImplemented as not_found_error:
    # We are expecting this exception
    print("got {}".format(not_found_error), file=sys.stderr)
    #raise not_found_error

  try:
    vcon.filter_plugins.FilterPluginRegistry.get("barp")
    raise Exception("Expected not to fine barp and throw exception")

  except vcon.filter_plugins.FilterPluginNotRegistered as not_reg_error:
    print(not_reg_error, file=sys.stderr)

  vcon.filter_plugins.FilterPluginRegistry.set_type_default_name("exclaim", "foop")
  assert(vcon.filter_plugins.FilterPluginRegistry.get_type_default_name("exclaim") == "foop")
  assert(vcon.filter_plugins.FilterPluginRegistry.get_type_default_name("bar") is None)
  assert(vcon.filter_plugins.FilterPluginRegistry.get_type_default_plugin("exclaim") == plugin_foop)

  # this time test foop using it set as default type exclaim name as a method
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

  in_vcon = vcon.Vcon()
  options = vcon.filter_plugins.FilterPluginOptions()
  try:
    out_vcon = await in_vcon.filter("doesnotexist", options)
    raise Exception("Expected not to find plugin and throw exception")

  except vcon.filter_plugins.FilterPluginNotRegistered as not_reg_error:
    print(not_reg_error, file=sys.stderr)

  import tests.bar_reg

  v2 = vcon.Vcon()

  try:
    await v2.barp(options)
    raise Exception("expect exception as filter plugin bar trys to import a non-existant package")

  except vcon.filter_plugins.FilterPluginModuleNotFound as fp_no_mod_error:
    # should get here
    print("got {}".format(fp_no_mod_error))

  vcon.filter_plugins.FilterPluginRegistry.shutdown_plugins()


def test_register_duplicate_raises():
  """Registering the same name twice without replace=True raises FilterPluginAlreadyRegistered"""
  vcon.filter_plugins.FilterPluginRegistry.register(
    "dup_test",
    "tests.foo",
    "Foo",
    "duplicate test plugin",
    {}
    )
  try:
    vcon.filter_plugins.FilterPluginRegistry.register(
      "dup_test",
      "tests.foo",
      "Foo",
      "duplicate test plugin",
      {}
      )
    raise Exception("Expected FilterPluginAlreadyRegistered")
  except vcon.filter_plugins.FilterPluginAlreadyRegistered:
    pass

  # replace=True should succeed
  vcon.filter_plugins.FilterPluginRegistry.register(
    "dup_test",
    "tests.foo",
    "Foo",
    "replaced plugin",
    {},
    replace=True
    )
  assert vcon.filter_plugins.FilterPluginRegistry.get("dup_test") is not None


def test_get_with_load_plugin():
  """get(load_plugin=True) imports the plugin immediately"""
  plugin_reg = vcon.filter_plugins.FilterPluginRegistry.get("foop", load_plugin=True)
  assert plugin_reg is not None
  assert plugin_reg.plugin() is not None


def test_get_check_type_default_no_match():
  """get with check_type_default=True raises when name is not registered and not a type default"""
  try:
    vcon.filter_plugins.FilterPluginRegistry.get("no_such_plugin_xyz", check_type_default=True)
    raise Exception("Expected FilterPluginNotRegistered")
  except vcon.filter_plugins.FilterPluginNotRegistered as e:
    assert "not register and is not a type default" in str(e)


def test_get_type_default_plugin_errors():
  """get_type_default_plugin raises AttributeError for non-string and FilterPluginNotRegistered when no default"""
  try:
    vcon.filter_plugins.FilterPluginRegistry.get_type_default_plugin(42)
    raise Exception("Expected AttributeError")
  except AttributeError as e:
    assert "should be a string" in str(e)

  try:
    vcon.filter_plugins.FilterPluginRegistry.get_type_default_plugin("no_default_type_xyz")
    raise Exception("Expected FilterPluginNotRegistered")
  except vcon.filter_plugins.FilterPluginNotRegistered as e:
    assert "not set" in str(e)


@pytest.mark.asyncio
async def test_class_not_found_errors():
  """options_type() and filter() raise FilterPluginClassNotFound when class is missing"""
  plugin_reg = vcon.filter_plugins.FilterPluginRegistry.get("badclass")

  # Trigger the load attempt (will set _class_not_found = True)
  plugin_reg.import_plugin({})

  try:
    plugin_reg.options_type()
    raise Exception("Expected FilterPluginClassNotFound")
  except vcon.filter_plugins.FilterPluginClassNotFound:
    pass

  in_vcon = vcon.Vcon()
  options = vcon.filter_plugins.FilterPluginOptions()
  try:
    await plugin_reg.filter(in_vcon, options)
    raise Exception("Expected FilterPluginClassNotFound")
  except vcon.filter_plugins.FilterPluginClassNotFound:
    pass


def test_options_type_module_not_found():
  """options_type() raises FilterPluginModuleNotFound when the module failed to load"""
  plugin_reg = vcon.filter_plugins.FilterPluginRegistry.get("barp")
  # barp points at tests.bar which doesn't exist — force the load
  plugin_reg.import_plugin({})
  try:
    plugin_reg.options_type()
    raise Exception("Expected FilterPluginModuleNotFound")
  except vcon.filter_plugins.FilterPluginModuleNotFound:
    pass


@pytest.mark.asyncio
async def test_filter_with_dict_options():
  """filter() accepts a dict for options and converts it"""
  plugin_reg = vcon.filter_plugins.FilterPluginRegistry.get("foop")
  in_vcon = vcon.Vcon()
  # foop.filter raises FilterPluginNotImplemented but dict conversion happens first
  try:
    await plugin_reg.filter(in_vcon, {})
  except vcon.filter_plugins.FilterPluginNotImplemented:
    pass  # expected — filter not implemented on Foo, but dict path was exercised


@pytest.mark.asyncio
async def test_filter_with_wrong_options_type():
  """filter() raises FilterPluginNotImplemented when options is not a FilterPluginOptions"""
  plugin_reg = vcon.filter_plugins.FilterPluginRegistry.get("foop")
  in_vcon = vcon.Vcon()
  try:
    await plugin_reg.filter(in_vcon, "not_options")
    raise Exception("Expected FilterPluginNotImplemented")
  except vcon.filter_plugins.FilterPluginNotImplemented as e:
    assert "should take an instance of class derived from FilterPluginOptions" in str(e)


def test_slice_indices_single_int():
  """slice_indices with a single integer string (no colon) returns one index"""
  result = vcon.filter_plugins.FilterPlugin.slice_indices("2", 5, "test_option")
  assert result == [2]


def test_slice_indices_invalid_type():
  """slice_indices raises AttributeError when spec is neither str nor list"""
  try:
    vcon.filter_plugins.FilterPlugin.slice_indices(42, 5, "test_option")
    raise Exception("Expected AttributeError")
  except AttributeError as e:
    assert "should be string or list of integers" in str(e)


def test_filter_plugin_init_wrong_init_options_type():
  """FilterPlugin.__init__ raises when init_options_type is not a subclass of FilterPluginInitOptions"""
  import vcon.filter_plugins

  class BadInitOptions:  # not derived from FilterPluginInitOptions
    pass

  class BadPlugin(vcon.filter_plugins.FilterPlugin):
    init_options_type = BadInitOptions

  try:
    BadPlugin(vcon.filter_plugins.FilterPluginInitOptions(), vcon.filter_plugins.FilterPluginOptions)
    raise Exception("Expected FilterPluginNotImplemented")
  except vcon.filter_plugins.FilterPluginNotImplemented as e:
    assert "init_options_type value must be derived from FilterPluginInitOptions" in str(e)


def test_filter_plugin_init_wrong_options_type():
  """FilterPlugin.__init__ raises when options_type is not a subclass of FilterPluginOptions"""
  import vcon.filter_plugins

  class GoodInitOptions(vcon.filter_plugins.FilterPluginInitOptions):
    pass

  class BadOptionsType:  # not derived from FilterPluginOptions
    pass

  class BadPlugin2(vcon.filter_plugins.FilterPlugin):
    init_options_type = GoodInitOptions

  try:
    BadPlugin2(GoodInitOptions(), BadOptionsType)
    raise Exception("Expected FilterPluginNotImplemented")
  except vcon.filter_plugins.FilterPluginNotImplemented as e:
    assert "options_type value must be derived from FilterPluginOptions" in str(e)


def test_filter_plugin_options_field_defaults():
  """
  FilterPluginOptions.__init_subclass__ applies field_defaults to the subclass.
  Covers the field_defaults for loop body in FilterPluginOptions.__init_subclass__.
  """
  class MyOptions(vcon.filter_plugins.TranscribeOptions,
    field_defaults = {"language": "fr"}
    ):
    pass

  opts = MyOptions()
  assert opts.language == "fr"


def test_import_plugin_already_loaded_returns_true():
  """
  Calling import_plugin a second time on an already-loaded plugin
  returns True via the elif self._plugin is not None branch (line 201).
  """
  plugin_reg = vcon.filter_plugins.FilterPluginRegistry.get("foop")
  plugin_reg.import_plugin(vcon.filter_plugins.FilterPluginInitOptions())
  # Second call — plugin already loaded
  result = plugin_reg.import_plugin(vcon.filter_plugins.FilterPluginInitOptions())
  assert result is True


def test_slice_indices_explicit_start_open_end():
  """
  slice_indices with "2:" — explicit start, open end.
  Covers the non-empty start operand branch (line 265-266) and
  empty end operand -> end=None branch (line 268).
  """
  result = vcon.filter_plugins.FilterPlugin.slice_indices("2:", 5, "test")
  assert result == [2, 3, 4]


def test_slice_indices_with_explicit_increment():
  """
  slice_indices with "0:6:2" — explicit start, end, and increment.
  Covers the non-empty increment branch (line 280).
  """
  result = vcon.filter_plugins.FilterPlugin.slice_indices("0:6:2", 6, "test")
  assert result == [0, 2, 4]


def test_get_party_label_none_index():
  """get_party_label returns 'unknown' for None party_index (line 326-327)"""
  in_vcon = vcon.Vcon()
  label = vcon.filter_plugins.FilterPlugin.get_party_label(in_vcon, None)
  assert label == "unknown"


def test_get_party_label_negative_index():
  """get_party_label returns 'unknown' for negative party_index (line 326-327)"""
  in_vcon = vcon.Vcon()
  label = vcon.filter_plugins.FilterPlugin.get_party_label(in_vcon, -1)
  assert label == "unknown"


def test_get_party_label_out_of_bounds_allow_missing():
  """get_party_label returns 'party[N]' when index is out of bounds and allow_missing_parties=True (lines 329-331)"""
  in_vcon = vcon.Vcon()
  label = vcon.filter_plugins.FilterPlugin.get_party_label(in_vcon, 5, allow_missing_parties=True)
  assert label == "party[5]"


def test_get_party_label_out_of_bounds_raises():
  """get_party_label raises AttributeError when index out of bounds and allow_missing_parties=False (line 333)"""
  in_vcon = vcon.Vcon()
  try:
    vcon.filter_plugins.FilterPlugin.get_party_label(in_vcon, 5, allow_missing_parties=False)
    raise Exception("Expected AttributeError")
  except AttributeError as e:
    assert "greater than number of parties" in str(e)


def test_get_party_label_with_name():
  """get_party_label returns name field when present (lines 335-337, 343-345)"""
  in_vcon = vcon.Vcon()
  in_vcon.set_party_parameter("name", "Alice")
  label = vcon.filter_plugins.FilterPlugin.get_party_label(in_vcon, 0)
  assert label == "Alice"


def test_get_party_label_no_name_or_tel():
  """get_party_label returns 'party[N]' fallback when no name or tel (lines 339-341)"""
  in_vcon = vcon.Vcon()
  in_vcon.set_party_parameter("mailto", "alice@example.com")
  label = vcon.filter_plugins.FilterPlugin.get_party_label(in_vcon, 0)
  assert label == "party[0]"


def test_get_party_label_list_of_indices():
  """get_party_label with a list of indices joins labels (lines 319-321)"""
  in_vcon = vcon.Vcon()
  in_vcon.set_party_parameter("name", "Alice")
  in_vcon.set_party_parameter("name", "Bob")
  label = vcon.filter_plugins.FilterPlugin.get_party_label(in_vcon, [0, 1])
  assert label == "Alice, Bob"


def test_filter_plugin_base_filter_raises():
  """
  Calling filter() directly on the base FilterPlugin raises FilterPluginNotImplemented.
  Covers the abstract raise on line 177.
  """
  import asyncio

  class ConcreteInitOptions(vcon.filter_plugins.FilterPluginInitOptions):
    pass

  class ConcretePlugin(vcon.filter_plugins.FilterPlugin):
    init_options_type = ConcreteInitOptions
    # deliberately does NOT override filter()

  plugin = ConcretePlugin(ConcreteInitOptions(), vcon.filter_plugins.FilterPluginOptions)
  in_vcon = vcon.Vcon()
  options = vcon.filter_plugins.FilterPluginOptions()

  async def run():
    await plugin.filter(in_vcon, options)

  try:
    asyncio.get_event_loop().run_until_complete(run())
    raise Exception("Expected FilterPluginNotImplemented")
  except vcon.filter_plugins.FilterPluginNotImplemented:
    pass


def test_check_valid_state_raises_on_signed_vcon():
  """
  check_valid_state raises InvalidVconState when the vCon is not unsigned.
  Covers line 401 (filter_vcon._attempting_modify() on a non-UNSIGNED vcon).
  """
  import vcon

  class ConcreteInitOptions(vcon.filter_plugins.FilterPluginInitOptions):
    pass

  class ConcretePlugin(vcon.filter_plugins.FilterPlugin):
    init_options_type = ConcreteInitOptions

  plugin = ConcretePlugin(ConcreteInitOptions(), vcon.filter_plugins.FilterPluginOptions)

  in_vcon = vcon.Vcon()
  # Force vcon into a non-unsigned state by loading a signed vcon JSON
  signed_vcon_json = '{"payload": "e30", "signatures": [{"header": {"uuid": "test-uuid"}, "protected": "e30", "signature": "abc"}]}'
  in_vcon.loads(signed_vcon_json)

  try:
    plugin.check_valid_state(in_vcon)
    raise Exception("Expected InvalidVconState")
  except Exception as e:
    assert "UNSIGNED" in str(e) or "Cannot modify" in str(e)

