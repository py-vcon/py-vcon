# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" Unit test for the vCon parameter registry """

import logging
import pytest
import vcon
import vcon.parameter_registry

UUID_DOMAIN = "py-vcon.dev"


def make_vcon() -> vcon.Vcon:
  """ build an empty vCon with a UUID set """
  a_vcon = vcon.Vcon()
  a_vcon.set_uuid(UUID_DOMAIN)
  return(a_vcon)


# ============================================================
#  get_parameter_extension
# ============================================================

def test_core_parameter():
  """ core parameters resolve to Vcon.PARAMETER_CORE """
  assert(vcon.Vcon.get_parameter_extension("parties", "tel") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("dialog", "start") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("analysis", "vendor") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("attachments", "purpose") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("", "uuid") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("redacted", "type") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("amended", "content_hash") == vcon.Vcon.PARAMETER_CORE)


def test_core_parameters_from_draft_text():
  """ did and button are in the draft text, but absent from its IANA tables """
  assert(vcon.Vcon.get_parameter_extension("parties", "did") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("dialog.party_history", "button") == vcon.Vcon.PARAMETER_CORE)


def test_extension_parameter():
  """ CC parameters resolve to the CC extension name token """
  assert(vcon.Vcon.get_parameter_extension("parties", "role") == "CC")
  assert(vcon.Vcon.get_parameter_extension("parties", "contact_list") == "CC")
  assert(vcon.Vcon.get_parameter_extension("dialog", "campaign") == "CC")
  assert(vcon.Vcon.get_parameter_extension("dialog", "interaction_type") == "CC")
  assert(vcon.Vcon.get_parameter_extension("dialog", "interaction_id") == "CC")
  assert(vcon.Vcon.get_parameter_extension("dialog", "skill") == "CC")


def test_unregistered_parameter():
  """ unregistered parameter names resolve to None """
  assert(vcon.Vcon.get_parameter_extension("parties", "not_a_parameter") is None)
  assert(vcon.Vcon.get_parameter_extension("dialog", "siprec_session_id") is None)


def test_removed_parameters():
  """ timezone and extension were removed from the party parameters """
  assert(vcon.Vcon.get_parameter_extension("parties", "timezone") is None)
  assert(vcon.Vcon.get_parameter_extension("parties", "extension") is None)


def test_parameter_is_path_scoped():
  """ the same name may be core in one Object and unregistered in another """
  assert(vcon.Vcon.get_parameter_extension("dialog", "originator") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("parties", "originator") is None)
  assert(vcon.Vcon.get_parameter_extension("parties", "role") == "CC")
  assert(vcon.Vcon.get_parameter_extension("dialog", "role") is None)


# ============================================================
#  Nested Object paths
# ============================================================

def test_nested_paths():
  """ parameters of nested Objects resolve at their own path """
  assert(vcon.Vcon.get_parameter_extension("parties.civicaddress", "country") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("parties.civicaddress", "a1") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("parties.civicaddress", "pc") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("dialog.session_id", "local") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("dialog.session_id", "remote") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("dialog.party_history", "event") == vcon.Vcon.PARAMETER_CORE)


def test_nested_object_name_is_also_a_parent_parameter():
  """ a nested Object name resolves both as a path and as a parameter of its parent """
  assert(vcon.Vcon.get_parameter_extension("parties", "civicaddress") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("dialog", "session_id") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("dialog", "party_history") == vcon.Vcon.PARAMETER_CORE)


# ============================================================
#  Path validation
# ============================================================

def test_unregistered_path_raises():
  """ an unregistered Object path raises ValueError """
  with pytest.raises(ValueError):
    vcon.Vcon.get_parameter_extension("not_an_object", "tel")

  with pytest.raises(ValueError):
    vcon.Vcon.get_parameter_extension("parties.civicaddres", "country")


def test_group_path_raises():
  """
  group is a registered vCon Object parameter name, but no Group Object
  registry is defined, so "group" is not a registered path.
  """
  assert(vcon.Vcon.get_parameter_extension("", "group") == vcon.Vcon.PARAMETER_CORE)

  with pytest.raises(ValueError):
    vcon.Vcon.get_parameter_extension("group", "uuid")


def test_malformed_path_raises():
  """ leading and trailing path separators raise ValueError """
  with pytest.raises(ValueError):
    vcon.Vcon.get_parameter_extension(".parties", "tel")

  with pytest.raises(ValueError):
    vcon.Vcon.get_parameter_extension("parties.", "tel")


def test_path_whitespace_stripped():
  """ surrounding whitespace on the path is ignored """
  assert(vcon.Vcon.get_parameter_extension("  parties  ", "tel") == vcon.Vcon.PARAMETER_CORE)


# ============================================================
#  Index build and collision detection
# ============================================================

def test_duplicate_core_name_raises():
  """ a duplicated name within one core path is a registry error """
  vcon.parameter_registry.CORE_PARAMETERS["parties"].append("tel")
  try:
    with pytest.raises(ValueError):
      vcon.parameter_registry.build_index()

  finally:
    vcon.parameter_registry.CORE_PARAMETERS["parties"].remove("tel")
    vcon.parameter_registry.build_index()

  assert(vcon.Vcon.get_parameter_extension("parties", "tel") == vcon.Vcon.PARAMETER_CORE)


def test_extension_colliding_with_core_raises():
  """ an extension may not redefine a core parameter name at the same path """
  vcon.parameter_registry.EXTENSION_PARAMETERS["TEST"] = {"parties": ["tel"]}
  try:
    with pytest.raises(ValueError):
      vcon.parameter_registry.build_index()

  finally:
    del vcon.parameter_registry.EXTENSION_PARAMETERS["TEST"]
    vcon.parameter_registry.build_index()

  assert(vcon.Vcon.get_parameter_extension("parties", "tel") == vcon.Vcon.PARAMETER_CORE)


def test_two_extensions_colliding_raises():
  """ two extensions may not define the same name at the same path """
  vcon.parameter_registry.EXTENSION_PARAMETERS["TEST"] = {"parties": ["role"]}
  try:
    with pytest.raises(ValueError):
      vcon.parameter_registry.build_index()

  finally:
    del vcon.parameter_registry.EXTENSION_PARAMETERS["TEST"]
    vcon.parameter_registry.build_index()

  assert(vcon.Vcon.get_parameter_extension("parties", "role") == "CC")


def test_extension_only_path_is_registered():
  """ an extension may introduce a path that core does not define """
  vcon.parameter_registry.EXTENSION_PARAMETERS["TEST"] = {"parties.testobject": ["thing"]}
  try:
    vcon.parameter_registry.build_index()
    assert(vcon.Vcon.get_parameter_extension("parties.testobject", "thing") == "TEST")

  finally:
    del vcon.parameter_registry.EXTENSION_PARAMETERS["TEST"]
    vcon.parameter_registry.build_index()

  with pytest.raises(ValueError):
    vcon.Vcon.get_parameter_extension("parties.testobject", "thing")


# ============================================================
#  PARTIES_OBJECT_STRING_PARAMETERS derived from the registry
# ============================================================

def test_parties_object_string_parameters_derived():
  """ the party parameter list is derived from the registry """
  party_parameters = vcon.Vcon.PARTIES_OBJECT_STRING_PARAMETERS

  for expected in ["tel", "sip", "stir", "mailto", "name", "did", "validation",
      "gmlpos", "civicaddress", "uuid", "type", "org", "dept",
      "role", "contact_list"]:
    assert(expected in party_parameters)

  assert("timezone" not in party_parameters)
  assert("extension" not in party_parameters)


# ============================================================
#  add_parameter_extension
# ============================================================

def test_core_parameter_adds_no_extension():
  """ a core parameter does not add an extensions parameter to the vCon """
  a_vcon = make_vcon()
  definer = a_vcon.add_parameter_extension("parties", "tel")

  assert(definer == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.EXTENSIONS not in a_vcon._vcon_dict)
  assert(a_vcon.extensions == [])


def test_extension_parameter_adds_extension():
  """ an extension parameter adds the extension name to the vCon """
  a_vcon = make_vcon()
  definer = a_vcon.add_parameter_extension("parties", "role")

  assert(definer == "CC")
  assert(a_vcon.extensions == ["CC"])
  assert(a_vcon._vcon_dict[vcon.Vcon.EXTENSIONS] == ["CC"])


def test_add_parameter_extension_is_idempotent():
  """ the extension name is added at most once """
  a_vcon = make_vcon()
  a_vcon.add_parameter_extension("parties", "role")
  a_vcon.add_parameter_extension("parties", "contact_list")
  a_vcon.add_parameter_extension("dialog", "campaign")

  assert(a_vcon.extensions == ["CC"])


def test_unregistered_parameter_warns(caplog):
  """ an unregistered parameter logs a warning and changes nothing """
  a_vcon = make_vcon()

  with caplog.at_level(logging.WARNING):
    definer = a_vcon.add_parameter_extension("parties", "not_a_parameter")

  assert(definer is None)
  assert("not_a_parameter" in caplog.text)
  assert(vcon.Vcon.EXTENSIONS not in a_vcon._vcon_dict)


def test_add_parameter_extension_bad_path_raises():
  """ an unregistered path raises rather than warning """
  a_vcon = make_vcon()

  with pytest.raises(ValueError):
    a_vcon.add_parameter_extension("not_an_object", "tel")


# ============================================================
#  extensions and critical attributes
# ============================================================

def test_extensions_absent_by_default():
  """ a new vCon has no extensions or critical parameter """
  a_vcon = make_vcon()

  assert(vcon.Vcon.EXTENSIONS not in a_vcon._vcon_dict)
  assert(vcon.Vcon.CRITICAL not in a_vcon._vcon_dict)


def test_reading_extensions_does_not_add_it():
  """ reading the attribute must not add an empty list to the vCon """
  a_vcon = make_vcon()

  assert(a_vcon.extensions == [])
  assert(len(a_vcon.extensions) == 0)
  assert(not a_vcon.extensions)
  for name in a_vcon.extensions:
    raise Exception("empty list should not iterate")

  assert(vcon.Vcon.EXTENSIONS not in a_vcon._vcon_dict)
  assert(vcon.Vcon.EXTENSIONS not in a_vcon.dumpd())


def test_appending_to_extensions_adds_it():
  """ modifying the returned list adds it to the vCon """
  a_vcon = make_vcon()
  a_vcon.extensions.append("CC")

  assert(a_vcon.extensions == ["CC"])
  assert(a_vcon._vcon_dict[vcon.Vcon.EXTENSIONS] == ["CC"])
  assert(a_vcon.dumpd()[vcon.Vcon.EXTENSIONS] == ["CC"])


def test_vcon_dict_holds_a_plain_list():
  """ the vCon dict must never hold the write back list type """
  a_vcon = make_vcon()
  a_vcon.extensions.append("CC")

  assert(type(a_vcon._vcon_dict[vcon.Vcon.EXTENSIONS]) is list)


def test_extensions_mutators_write_back():
  """ mutators other than append also add the list to the vCon """
  a_vcon = make_vcon()
  a_vcon.extensions.extend(["CC", "XX"])
  assert(a_vcon._vcon_dict[vcon.Vcon.EXTENSIONS] == ["CC", "XX"])

  another_vcon = make_vcon()
  another_vcon.extensions.insert(0, "CC")
  assert(another_vcon._vcon_dict[vcon.Vcon.EXTENSIONS] == ["CC"])


def test_extensions_may_not_be_replaced():
  """ the attribute is read only """
  a_vcon = make_vcon()

  with pytest.raises(AttributeError):
    a_vcon.extensions = ["CC"]


def test_critical_attribute():
  """ critical behaves the same as extensions """
  a_vcon = make_vcon()

  assert(a_vcon.critical == [])
  assert(vcon.Vcon.CRITICAL not in a_vcon._vcon_dict)

  a_vcon.critical.append("XX")
  assert(a_vcon.critical == ["XX"])
  assert(type(a_vcon._vcon_dict[vcon.Vcon.CRITICAL]) is list)


def test_extensions_survives_serialization_round_trip():
  """ extensions and critical round trip through JSON """
  a_vcon = make_vcon()
  a_vcon.set_party_parameter("role", "agent")
  a_vcon.critical.append("XX")

  loaded_vcon = vcon.Vcon()
  loaded_vcon.loads(a_vcon.dumps())

  assert(loaded_vcon.extensions == ["CC"])
  assert(loaded_vcon.critical == ["XX"])


# ============================================================
#  Setter call sites
# ============================================================

def test_set_party_parameter_permissive():
  """ unregistered party parameters are set rather than raising """
  a_vcon = make_vcon()
  party_index = a_vcon.set_party_parameter("not_a_parameter", "a value")

  assert(party_index == 0)
  assert(a_vcon.parties[0]["not_a_parameter"] == "a value")
  assert(vcon.Vcon.EXTENSIONS not in a_vcon._vcon_dict)


def test_set_party_parameter_previously_rejected_names():
  """ core names which the old hardcoded list omitted are now accepted """
  a_vcon = make_vcon()
  a_vcon.set_party_parameter("contact_list", "list-1", -1)
  a_vcon.set_party_parameter("org", "Acme", 0)
  a_vcon.set_party_parameter("dept", "Support", 0)

  assert(a_vcon.parties[0]["contact_list"] == "list-1")
  assert(a_vcon.parties[0]["org"] == "Acme")
  assert(a_vcon.parties[0]["dept"] == "Support")
  assert(a_vcon.extensions == ["CC"])


def test_add_party_adds_extension():
  """ add_party registers extensions for its keys """
  a_vcon = make_vcon()
  party_index = a_vcon.add_party({"tel": "+12345678901", "role": "agent"})

  assert(party_index == 0)
  assert(a_vcon.extensions == ["CC"])


def test_set_dialog_parameter_adds_extension():
  """ set_dialog_parameter registers the extension """
  a_vcon = make_vcon()
  a_vcon.add_dialog_inline_text(
    "hello",
    "2024-03-06T20:07:43+00:00",
    5.0,
    0,
    vcon.Vcon.MEDIATYPE_TEXT_PLAIN
    )
  a_vcon.set_dialog_parameter("skill", "billing", 0)

  assert(a_vcon.dialog[0]["skill"] == "billing")
  assert(a_vcon.extensions == ["CC"])


def test_add_analysis_optional_parameters():
  """ add_analysis registers extensions for its optional parameters """
  a_vcon = make_vcon()
  a_vcon.add_analysis(
    0,
    "summary",
    "a summary",
    "test_vendor",
    None,
    "none",
    mediatype = vcon.Vcon.MEDIATYPE_TEXT_PLAIN
    )

  assert(a_vcon.analysis[0]["mediatype"] == vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  assert(vcon.Vcon.EXTENSIONS not in a_vcon._vcon_dict)


# ============================================================
#  redacted no longer eagerly created
# ============================================================

def test_redacted_absent_by_default():
  """ a new vCon has no redacted parameter """
  a_vcon = make_vcon()

  assert(a_vcon.redacted is None)
  assert(vcon.Vcon.REDACTED not in a_vcon._vcon_dict)
  assert(vcon.Vcon.REDACTED not in a_vcon.dumpd())


def test_set_redacted_still_works():
  """ set_redacted assigns a fresh dict """
  a_vcon = make_vcon()
  a_vcon.set_redacted("1234", "PII")

  assert(a_vcon.redacted["uuid"] == "1234")
  assert(a_vcon.redacted["type"] == "PII")

