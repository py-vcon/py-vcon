# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" Unit tests for finding the extensions used in a whole vCon """

import copy
import logging
import pytest
import vcon
import vcon.parameter_registry

CA_CERT = "certs/fake_ca_root.crt"
DIVISION_CERT = "certs/fake_div.crt"
GROUP_CERT = "certs/fake_grp.crt"
GROUP_PRIVATE_KEY = "certs/fake_grp.key"
START = "2022-06-21T13:53:26-04:00"

TEST_OBJECTS = ["-", "Party", "Dialog", "Session", "Session_Reference", "Event", "Attachment",
  "Analysis", "Redacted_from", "Civicaddress", "SessionId"]


def make_extension_dict(name : str, critical : bool) -> dict:
  return({
      "name": name,
      "description": "test extension",
      "change_controller": "py-vcon",
      "specification": "tests/test_extension_check.py",
      "critical": critical
    })


@pytest.fixture
def test_extensions():
  """ TEST_EXT (not critical) with a parameter in each Object and values, TEST_CRIT (critical) """
  rows = [{"parent": parent, "name": "test_ext_param", "description": "x"} for parent in TEST_OBJECTS]
  rows += [
      {"parent": "Event->type", "name": "test-ext-event", "description": "x"},
      {"parent": "Dialog->disposition", "name": "test-ext-disposition", "description": "x"},
      {"parent": "Session_Reference->type", "name": "test-ext-reference", "description": "x"}
    ]
  vcon.parameter_registry.register_extension(make_extension_dict("TEST_EXT", False), rows)
  vcon.parameter_registry.register_extension(make_extension_dict("TEST_CRIT", True),
    [{"parent": "Party", "name": "test_crit_param", "description": "x"}])
  yield
  vcon.parameter_registry.unregister_extension("TEST_EXT")
  vcon.parameter_registry.unregister_extension("TEST_CRIT")


def make_vcon() -> vcon.Vcon:
  """ a vCon using every core Object, with only core parameters and values """
  v = vcon.Vcon()
  v.set_uuid("example.com")
  v.set_party_parameter("tel", "+15551110000")
  v.set_party_parameter("tel", "+15552220000")
  v.add_text_dialog_inline("Hello", START, 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.add_session()
  v.add_session_reference(0, 1, "child")
  v.add_join_event(START, 0, 1)
  v.add_attachment_inline(b"notes", START, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN, dialog = 0)
  v.add_analysis(0, "summary", "a summary", "test_vendor", None, "none")
  vcon_dict = v.dumpd()
  vcon_dict["parties"][0]["civicaddress"] = {"country": "US", "a1": "MA"}
  vcon_dict["dialog"][0]["session_id"] = {"local": "a", "remote": "b"}
  vcon_dict["redacted_from"] = {"uuid": "01928e10-193e-8231-b9a2-279e0d16bc46", "type": "PII"}
  v.loadd(vcon_dict)
  return(v)


# where to write a parameter of each Object in the vCon made by make_vcon
def object_in(vcon_dict : dict, object_name : str) -> dict:
  return({
      "-": lambda: vcon_dict,
      "Party": lambda: vcon_dict["parties"][1],
      "Dialog": lambda: vcon_dict["dialog"][0],
      "Session": lambda: vcon_dict["sessions"][1],
      "Session_Reference": lambda: vcon_dict["sessions"][0]["sessions"][0],
      "Event": lambda: vcon_dict["events"][0],
      "Attachment": lambda: vcon_dict["attachments"][0],
      "Analysis": lambda: vcon_dict["analysis"][0],
      "Redacted_from": lambda: vcon_dict["redacted_from"],
      "Civicaddress": lambda: vcon_dict["parties"][0]["civicaddress"],
      "SessionId": lambda: vcon_dict["dialog"][0]["session_id"]
    }[object_name]())


def test_core_only_nothing_reported():
  v = make_vcon()
  report = v.check_extensions()
  assert(report == {"used": [], "unlisted": [], "critical_unlisted": [], "unregistered": []})


def test_cc_written_directly():
  v = make_vcon()
  v._vcon_dict["parties"][0]["role"] = "agent"
  report = v.check_extensions()
  assert(report["used"] == ["CC"])
  assert(report["unlisted"] == ["CC"])
  assert(report["critical_unlisted"] == [])
  assert(vcon.parameter_registry.find_extensions(v._vcon_dict) == report)

  # once listed, nothing is reported as unlisted
  v._vcon_dict["extensions"] = ["CC"]
  assert(v.check_extensions()["unlisted"] == [])


@pytest.mark.parametrize("object_name", TEST_OBJECTS)
def test_extension_parameter_in_each_object(test_extensions, object_name):
  v = make_vcon()
  object_in(v._vcon_dict, object_name)["test_ext_param"] = "x"
  report = v.check_extensions()
  assert(report["used"] == ["TEST_EXT"]), object_name
  assert(report["unlisted"] == ["TEST_EXT"]), object_name
  assert(report["unregistered"] == []), object_name


@pytest.mark.parametrize("label, place", [
    ("Dialog single", lambda d, s: d["dialog"][0].__setitem__("session_id", s)),
    ("Dialog array", lambda d, s: d["dialog"][0].__setitem__("session_id", [{}, s])),
    ("Dialog nested arrays", lambda d, s: d["dialog"][0].__setitem__("session_id", [[{}, s], {}])),
    ("Session single", lambda d, s: d["sessions"][1].__setitem__("session_id", s)),
    ("Session nested arrays", lambda d, s: d["sessions"][1].__setitem__("session_id", [[s]]))
  ])
def test_session_id_forms(test_extensions, label, place):
  v = make_vcon()
  place(v._vcon_dict, {"local": "a", "test_ext_param": "x"})
  report = v.check_extensions()
  assert(report["used"] == ["TEST_EXT"]), label
  assert(report["unregistered"] == []), label


@pytest.mark.parametrize("label, place", [
    ("Event type", lambda d: d["events"][0].__setitem__("type", "test-ext-event")),
    ("Dialog disposition", lambda d: d["dialog"][0].__setitem__("disposition", "test-ext-disposition")),
    ("Session_Reference type", lambda d: d["sessions"][0]["sessions"][0].__setitem__("type", "test-ext-reference"))
  ])
def test_extension_values(test_extensions, label, place):
  v = make_vcon()
  place(v._vcon_dict)
  report = v.check_extensions()
  assert(report["used"] == ["TEST_EXT"]), label
  assert(report["unregistered"] == []), label


def test_unregistered_reported_with_location():
  v = make_vcon()
  v._vcon_dict["parties"][1]["my_param"] = "x"
  v._vcon_dict["dialog"][0]["session_id"] = [{}, {"local": "a", "my_id": "x"}]
  v._vcon_dict["events"][0]["type"] = "my-event"
  v._vcon_dict["my_top"] = 1
  report = v.check_extensions()
  assert(report["used"] == [])
  assert(report["unlisted"] == [])
  assert(report["unregistered"] == [
      '$: "my_top"',
      '$.parties[1]: "my_param"',
      '$.dialog[0].session_id[1]: "my_id"',
      '$.events[0].type: "my-event"'
    ])


def test_update_extensions(test_extensions):
  v = make_vcon()
  v._vcon_dict["parties"][0]["role"] = "agent"
  v._vcon_dict["parties"][0]["test_crit_param"] = "x"
  v._vcon_dict["parties"][1]["my_param"] = "x"

  report = v.update_extensions()
  assert(report["unlisted"] == ["CC", "TEST_CRIT"])
  assert(report["critical_unlisted"] == ["TEST_CRIT"])
  assert(v.extensions == ["CC", "TEST_CRIT"])
  assert(v.critical == ["TEST_CRIT"])
  # unregistered names are not assigned to an extension
  assert(report["unregistered"] == ['$.parties[1]: "my_param"'])

  # a second run changes nothing
  second = v.update_extensions()
  assert(second["unlisted"] == [] and second["critical_unlisted"] == [])
  assert(v.extensions == ["CC", "TEST_CRIT"])
  assert(v.critical == ["TEST_CRIT"])


def test_sign_encrypt_warn_unlisted(caplog):
  v = make_vcon()
  v._vcon_dict["parties"][0]["role"] = "agent"
  unsigned = copy.deepcopy(v.dumpd())

  with caplog.at_level(logging.WARNING):
    v.sign(GROUP_PRIVATE_KEY, [GROUP_CERT, DIVISION_CERT, CA_CERT])
  assert("sign vCon UUID: {} uses extensions not listed in extensions: ['CC']".format(v.uuid) in caplog.text)
  assert(v._vcon_dict == unsigned)
  assert("extensions" not in v._vcon_dict)

  caplog.clear()
  with caplog.at_level(logging.WARNING):
    v.encrypt(DIVISION_CERT)
  assert("encrypt vCon UUID: {} uses extensions not listed".format(v.uuid) in caplog.text)


def test_sign_listed_no_warning(caplog):
  v = make_vcon()
  v.set_party_parameter("role", "agent", 0)
  with caplog.at_level(logging.WARNING):
    v.sign(GROUP_PRIVATE_KEY, [GROUP_CERT, DIVISION_CERT, CA_CERT])
  assert("not listed" not in caplog.text)


def test_dict_never_loaded():
  vcon_dict = {
      "vcon": "0.5.0",
      "uuid": "01928e10-193e-8231-b9a2-279e0d16bc46",
      "parties": [{"tel": "+15551110000", "role": "agent", "civicaddress": {"pc": "02134", "my_line": "x"}}],
      "dialog": [{}, {"type": "text", "campaign": "spring"}],
      "events": [{"type": "join", "time": START, "sessions": 0, "party": 0}]
    }
  original = copy.deepcopy(vcon_dict)
  report = vcon.parameter_registry.find_extensions(vcon_dict)
  assert(report == {
      "used": ["CC"],
      "unlisted": ["CC"],
      "critical_unlisted": [],
      "unregistered": ['$.parties[0].civicaddress: "my_line"']
    })
  assert(vcon_dict == original)

  v = vcon.Vcon()
  v.loadd(copy.deepcopy(vcon_dict))
  assert(v.check_extensions() == report)


def test_malformed_objects_skipped():
  """ a value which is not an Object where one is expected is not looked into """
  report = vcon.parameter_registry.find_extensions({"parties": [None, "x"], "redacted_from": "x"})
  assert(report == {"used": [], "unlisted": [], "critical_unlisted": [], "unregistered": []})
