# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" Unit test for the vCon parameter registry """

import logging
import pytest
import vcon
import vcon.parameter_registry
import tests.common_utils

UUID_DOMAIN = "py-vcon.dev"


def make_vcon() -> vcon.Vcon:
  """ build an empty vCon with a UUID set """
  a_vcon = vcon.Vcon()
  a_vcon.set_uuid(UUID_DOMAIN)
  return(a_vcon)


TEST_EXTENSION = {
    "name": "TEST_CRIT",
    "description": "test critical extension",
    "change_controller": "py-vcon",
    "specification": "tests/test_parameter_registry.py",
    "critical": True
  }

TEST_ROWS = [
    {"parent": "Party", "name": "test_crit_param", "description": "test parameter"},
    {"parent": "Event->type", "name": "test-crit-event", "description": "test Event type"}
  ]


@pytest.fixture
def test_extension():
  """ register TEST_CRIT for one test """
  vcon.parameter_registry.register_extension(TEST_EXTENSION, TEST_ROWS)
  yield TEST_EXTENSION["name"]
  vcon.parameter_registry.unregister_extension(TEST_EXTENSION["name"])


# ============================================================
#  core data set against the -05 IANA tables
# ============================================================

def test_core_rows_match_draft_iana_tables():
  """ each -05 IANA table has exactly the draft's names in the core data set (legacy rows excluded) """
  tables = tests.common_utils.load_iana_tables()
  assert(set(tables.keys()) == {"-", "Party", "Dialog", "Dialog->type", "Session", "Session_Reference",
    "Session_Reference->type", "Event", "Event->type", "Attachment", "Analysis", "Redacted_from",
    "Amended_from"})

  for parent, draft_names in tables.items():
    core_names = [row["name"] for row in vcon.parameter_registry.CORE_ROWS
      if(row["parent"] == parent and not row["legacy"])]
    assert(core_names == draft_names), parent
    assert(all([row["iana"] for row in vcon.parameter_registry.CORE_ROWS
      if(row["parent"] == parent and not row["legacy"])])), parent


def test_value_lists():
  """ the value registries of -05 """
  assert(len([row for row in vcon.parameter_registry.get_rows("Dialog->type") if(not row["legacy"])]) == 3)
  assert(len(vcon.parameter_registry.get_rows("Event->type")) == 13)
  assert(len(vcon.parameter_registry.get_rows("Session_Reference->type")) == 4)


def test_rows_without_iana_registry():
  """ Objects and values defined in the -05 text with no IANA registry are core with iana False """
  expected = {
      "Civicaddress": ["country", "a1", "a2", "a3", "a4", "a5", "a6", "prd", "pod", "sts", "hno",
        "hns", "lmk", "loc", "flr", "nam", "pc"],
      "SessionId": ["local", "remote"],
      # marker is proposed for the draft (see tests/test_redacted_strings.py)
      "Redacted_string": ["ref", "type", "orig", "marker"],
      # channel is proposed for the draft (see tests/test_redacted_segments.py)
      "Redacted_segments": ["start", "end", "parties", "channel"],
      "Dialog->disposition": ["no-answer", "congestion", "failed", "busy", "hung-up", "voicemail-no-message"],
      "Dialog->encoding": ["base64url", "json", "none"],
      "Attachment->encoding": ["base64url", "json", "none"],
      "Analysis->encoding": ["base64url", "json", "none"]
    }
  for parent, names in expected.items():
    rows = vcon.parameter_registry.get_rows(parent)
    assert([row["name"] for row in rows] == names), parent
    assert(all([row["iana"] is False and row["legacy"] is False for row in rows])), parent
    for row in rows:
      if(vcon.parameter_registry.VALUE_SEPARATOR in parent):
        object_name, parameter_name = parent.split(vcon.parameter_registry.VALUE_SEPARATOR)
        assert(vcon.parameter_registry.get_value_extension(object_name, parameter_name, row["name"]) ==
          vcon.Vcon.PARAMETER_CORE)
      else:
        assert(vcon.Vcon.get_parameter_extension(parent, row["name"]) == vcon.Vcon.PARAMETER_CORE)


def test_analysis_sessions():
  """ Analysis references Sessions by sessions, not session """
  assert(vcon.Vcon.get_parameter_extension("Analysis", "sessions") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("Analysis", "session") is None)


def test_event_channel_contributors():
  assert(vcon.Vcon.get_parameter_extension("Event", "channel") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("Event", "contributors") == vcon.Vcon.PARAMETER_CORE)


# ============================================================
#  lookups
# ============================================================

def test_parameter_lookup():
  """ core, extension and unregistered parameter names """
  assert(vcon.Vcon.get_parameter_extension("Party", "tel") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("-", "uuid") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.get_parameter_extension("Party", "role") == "CC")
  assert(vcon.Vcon.get_parameter_extension("Party", "contact_list") == "CC")
  for name in ["campaign", "interaction_type", "interaction_id", "skill"]:
    assert(vcon.Vcon.get_parameter_extension("Dialog", name) == "CC")
  assert(vcon.Vcon.get_parameter_extension("Party", "not_a_parameter") is None)
  # parameter names are scoped to their Object
  assert(vcon.Vcon.get_parameter_extension("Dialog", "role") is None)
  assert(vcon.Vcon.get_parameter_extension("Party", "originator") is None)
  # removed party parameters
  assert(vcon.Vcon.get_parameter_extension("Party", "timezone") is None)


def test_value_lookup(test_extension):
  assert(vcon.parameter_registry.get_value_extension("Event", "type", "join") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.parameter_registry.get_value_extension("Event", "type", "test-crit-event") == test_extension)
  assert(vcon.parameter_registry.get_value_extension("Event", "type", "not-an-event") is None)

  with pytest.raises(ValueError, match = "not a registered value set"):
    vcon.parameter_registry.get_value_extension("Party", "tel", "x")


def test_unregistered_object_name_raises():
  with pytest.raises(ValueError, match = "not a registered vCon Object name"):
    vcon.Vcon.get_parameter_extension("parties", "tel")
  with pytest.raises(ValueError):
    vcon.Vcon.get_parameter_extension("Group", "uuid")
  with pytest.raises(ValueError):
    vcon.parameter_registry.get_object_parameter_names("Dialog->type")


def test_get_object_parameter_names():
  names = vcon.parameter_registry.get_object_parameter_names("Session")
  assert(names == ["start", "duration", "parties", "originator", "session_id", "sessions", "dialog"])


# ============================================================
#  writing extension parameters
# ============================================================

def test_cc_parameter_adds_extension_not_critical():
  a_vcon = make_vcon()
  a_vcon.set_party_parameter("role", "agent")
  assert(a_vcon.extensions == ["CC"])
  assert(vcon.Vcon.CRITICAL not in a_vcon._vcon_dict)
  assert(vcon.parameter_registry.is_critical("CC") is False)


def test_critical_parameter_adds_extension_and_critical(test_extension):
  a_vcon = make_vcon()
  a_vcon.set_party_parameter("test_crit_param", "x")
  assert(a_vcon.extensions == [test_extension])
  assert(a_vcon.critical == [test_extension])

  # added at most once
  a_vcon.add_parameter_extension("Party", "test_crit_param")
  assert(a_vcon.extensions == [test_extension])
  assert(a_vcon.critical == [test_extension])


# ============================================================
#  registration
# ============================================================

def test_register_extension(test_extension):
  assert(test_extension in vcon.parameter_registry.EXTENSIONS)
  assert(vcon.Vcon.get_parameter_extension("Party", "test_crit_param") == test_extension)
  assert(vcon.parameter_registry.is_critical(test_extension) is True)
  rows = [row for row in vcon.parameter_registry.get_rows("Party") if(row.get("extension", None) == test_extension)]
  assert(rows == [{
      "parent": "Party",
      "name": "test_crit_param",
      "description": "test parameter",
      "change_controller": "py-vcon",
      "specification": "tests/test_parameter_registry.py",
      "iana": True,
      "legacy": False,
      "extension": test_extension
    }])

  # identical re-registration is accepted
  vcon.parameter_registry.register_extension(TEST_EXTENSION, TEST_ROWS)

  # different re-registration raises
  with pytest.raises(ValueError, match = "different content"):
    vcon.parameter_registry.register_extension(dict(TEST_EXTENSION, critical = False), TEST_ROWS)

  # extension name differing only in case raises
  with pytest.raises(ValueError, match = "differs only in case"):
    vcon.parameter_registry.register_extension(dict(TEST_EXTENSION, name = "test_crit"), [])

  # an extension Object of its own
  vcon.parameter_registry.register_extension(dict(TEST_EXTENSION, name = "TEST_OBJECT"),
    [{"parent": "Test_object", "name": "thing", "description": "a thing"}])
  try:
    assert(vcon.Vcon.get_parameter_extension("Test_object", "thing") == "TEST_OBJECT")
  finally:
    vcon.parameter_registry.unregister_extension("TEST_OBJECT")
  with pytest.raises(ValueError):
    vcon.Vcon.get_parameter_extension("Test_object", "thing")


@pytest.mark.parametrize("label, rows, message", [
    ("core collision", [{"parent": "Party", "name": "tel", "description": "x"}], "collides with: \"tel\" defined by: \"core\""),
    ("core collision differing in case", [{"parent": "Party", "name": "Tel", "description": "x"}], "defined by: \"core\""),
    ("core value collision", [{"parent": "Event->type", "name": "join", "description": "x"}], "defined by: \"core\""),
    ("other extension collision", [{"parent": "Party", "name": "role", "description": "x"}], "defined by: \"CC\""),
    ("collision within the extension", [{"parent": "Party", "name": "a", "description": "x"},
      {"parent": "Party", "name": "A", "description": "y"}], "defined by: \"TEST_BAD\""),
    ("missing field", [{"parent": "Party", "name": "a"}], "missing")
  ])
def test_register_extension_rejected(label, rows, message):
  with pytest.raises(ValueError, match = message):
    vcon.parameter_registry.register_extension(dict(TEST_EXTENSION, name = "TEST_BAD"), rows)
  # nothing is registered
  assert("TEST_BAD" not in vcon.parameter_registry.EXTENSIONS), label
  assert(vcon.Vcon.get_parameter_extension("Party", "role") == "CC"), label


def test_register_extension_missing_field():
  with pytest.raises(ValueError, match = "critical"):
    vcon.parameter_registry.register_extension({"name": "X", "description": "x",
      "change_controller": "x", "specification": "x"}, [])
  with pytest.raises(ValueError, match = "not registered"):
    vcon.parameter_registry.unregister_extension("X")


# ============================================================
#  legacy 0.4.0 names
# ============================================================

def test_legacy_names(caplog):
  """ 0.4.0 names are recognized as core without a warning and marked legacy """
  legacy = [("-", "redacted"), ("-", "amended"), ("Dialog", "originator"), ("Dialog", "party_history"),
    ("Dialog", "transferee"), ("Dialog", "transferor"), ("Dialog", "transfer_target"), ("Dialog", "original"),
    ("Dialog", "consultation"), ("Dialog", "target_dialog"), ("Party_history", "event"),
    ("Redacted", "type"), ("Amended", "uuid")]
  a_vcon = make_vcon()
  with caplog.at_level(logging.WARNING):
    for object_name, name in legacy:
      assert(a_vcon.add_parameter_extension(object_name, name) == vcon.Vcon.PARAMETER_CORE)
      assert(vcon.parameter_registry.is_legacy(object_name, name)), name
  assert([record for record in caplog.records if(record.levelno >= logging.WARNING)] == [])
  assert(vcon.parameter_registry.get_value_extension("Dialog", "type", "transfer") == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.parameter_registry.is_legacy("Dialog->type", "transfer"))
  assert(not vcon.parameter_registry.is_legacy("Dialog", "type"))


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
  definer = a_vcon.add_parameter_extension("Party", "tel")

  assert(definer == vcon.Vcon.PARAMETER_CORE)
  assert(vcon.Vcon.EXTENSIONS not in a_vcon._vcon_dict)
  assert(a_vcon.extensions == [])


def test_add_parameter_extension_is_idempotent():
  """ the extension name is added at most once """
  a_vcon = make_vcon()
  a_vcon.add_parameter_extension("Party", "role")
  a_vcon.add_parameter_extension("Party", "contact_list")
  a_vcon.add_parameter_extension("Dialog", "campaign")

  assert(a_vcon.extensions == ["CC"])


def test_unregistered_parameter_warns(caplog):
  """ an unregistered parameter logs a warning and changes nothing """
  a_vcon = make_vcon()

  with caplog.at_level(logging.WARNING):
    definer = a_vcon.add_parameter_extension("Party", "not_a_parameter")

  assert(definer is None)
  assert("not_a_parameter" in caplog.text)
  assert(vcon.Vcon.EXTENSIONS not in a_vcon._vcon_dict)


def test_add_parameter_extension_bad_object_raises():
  """ an unregistered Object name raises rather than warning """
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

def test_set_party_parameter_warnings(caplog):
  """ a core party parameter gives no warning, an unregistered one the unregistered warning """
  a_vcon = make_vcon()
  with caplog.at_level(logging.WARNING):
    a_vcon.set_party_parameter("tel", "+15551110000")
  assert([record for record in caplog.records if(record.levelno >= logging.WARNING)] == [])

  with caplog.at_level(logging.WARNING):
    a_vcon.set_party_parameter("not_a_parameter", "a value", 0)
  assert("parameter name: \"not_a_parameter\" in Object: \"Party\" is not defined" in caplog.text)


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
    None,
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
#  redacted_from not eagerly created
# ============================================================

def test_redacted_from_absent_by_default():
  """ a new vCon has no redacted_from parameter """
  a_vcon = make_vcon()

  assert(a_vcon.redacted_from is None)
  assert(vcon.Vcon.REDACTED_FROM not in a_vcon._vcon_dict)
  assert(vcon.Vcon.REDACTED_FROM not in a_vcon.dumpd())


def test_set_redacted_from_assigns_a_dict():
  """ set_redacted_from assigns a fresh dict """
  a_vcon = make_vcon()
  a_vcon.set_redacted_from("1234", "PII")

  assert(a_vcon.redacted_from["uuid"] == "1234")
  assert(a_vcon.redacted_from["type"] == "PII")
