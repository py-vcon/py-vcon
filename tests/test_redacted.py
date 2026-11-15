# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" Unit tests for redacted_from and amended_from """

import logging
import cbor2
import pytest
import vcon
import tests.common_utils

UUID = "01928e10-193e-8231-b9a2-279e0d16bc46"
OTHER_UUID = "01928e10-193e-8231-b9a2-279e0d16bc47"
HASH = "sha512-GLy6IPaIUM1GqzZqfIPZlWjaDsNgtvZM0iM2v7XuGNPMpqbd9qZu0f6v8V3P9QIdD5aqWl1KpqBeA_sjaycDcQ"


def make_vcon() -> vcon.Vcon:
  v = vcon.Vcon()
  v.set_uuid("example.com")
  v.set_party_parameter("tel", "+15551110000")
  v.add_text_dialog_inline("Hello", "2022-06-21T13:53:26-04:00", 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  return(v)


def test_set_redacted_from(caplog):
  v = make_vcon()
  with caplog.at_level(logging.WARNING):
    v.set_redacted_from(UUID, "PII Redaction")
  # free text type, no warning
  assert([record for record in caplog.records if(record.levelno >= logging.WARNING)] == [])
  assert(v.redacted_from == {"uuid": UUID, "type": "PII Redaction"})
  assert(v.dumpd()["redacted_from"] == {"uuid": UUID, "type": "PII Redaction"})
  tests.common_utils.assert_valid_vcon(v.dumpd())

  # replaced, not added to
  v.set_redacted_from(OTHER_UUID, "PHONE_NUMBER")
  assert(v.redacted_from == {"uuid": OTHER_UUID, "type": "PHONE_NUMBER"})


def test_set_redacted_from_without_uuid():
  v = make_vcon()
  v.set_redacted_from(None, "UNSPECIFIED")
  assert(v.redacted_from == {"type": "UNSPECIFIED"})
  tests.common_utils.assert_valid_vcon(v.dumpd())


def test_url_and_content_hash():
  v = make_vcon()
  v.set_redacted_from(UUID, "PII", url = "https://example.com/less.vcon", content_hash = HASH)
  assert(v.redacted_from == {"uuid": UUID, "type": "PII", "url": "https://example.com/less.vcon",
    "content_hash": HASH})
  tests.common_utils.assert_valid_vcon(v.dumpd())

  v = make_vcon()
  v.set_amended_from(None, url = "https://example.com/prior.vcon", content_hash = [HASH, "sha256-abc"])
  assert(v.amended_from == {"url": "https://example.com/prior.vcon", "content_hash": [HASH, "sha256-abc"]})
  tests.common_utils.assert_valid_vcon(v.dumpd())


def test_url_without_content_hash_raises():
  v = make_vcon()
  with pytest.raises(AttributeError, match = "needs a content_hash"):
    v.set_redacted_from(UUID, "PII", url = "https://example.com/less.vcon")
  with pytest.raises(AttributeError, match = "needs a content_hash"):
    v.set_amended_from(UUID, url = "https://example.com/prior.vcon", content_hash = [])
  assert("redacted_from" not in v._vcon_dict)
  assert("amended_from" not in v._vcon_dict)


def test_set_amended_from():
  v = make_vcon()
  v.set_amended_from(UUID)
  assert(v.amended_from == {"uuid": UUID})
  tests.common_utils.assert_valid_vcon(v.dumpd())

  with pytest.raises(AttributeError, match = "needs a uuid or a url"):
    make_vcon().set_amended_from(None)


@pytest.mark.parametrize("existing, setter", [
    ("amended_from", lambda v: v.set_redacted_from(UUID, "PII")),
    ("amended", lambda v: v.set_redacted_from(UUID, "PII")),
    ("redacted_from", lambda v: v.set_amended_from(UUID)),
    ("redacted", lambda v: v.set_amended_from(UUID))
  ])
def test_mutually_exclusive(existing, setter):
  v = make_vcon()
  v._vcon_dict[existing] = {"uuid": OTHER_UUID}
  with pytest.raises(AttributeError, match = "has {}, which is mutually exclusive".format(existing)):
    setter(v)
  assert(set(v._vcon_dict.keys()) & {"redacted_from", "amended_from", "redacted", "amended"} == {existing})


def test_new_name_replaces_0_4_0_name():
  v = make_vcon()
  v._vcon_dict["redacted"] = {"uuid": OTHER_UUID, "type": "PII"}
  v.set_redacted_from(UUID, "PII")
  assert("redacted" not in v._vcon_dict)
  assert(v.redacted_from["uuid"] == UUID)


def test_deprecated_setters():
  v = make_vcon()
  with pytest.warns(DeprecationWarning, match = "set_redacted_from"):
    v.set_redacted("1234", "PII")
  assert(v._vcon_dict["redacted_from"] == {"uuid": "1234", "type": "PII"})
  assert("redacted" not in v._vcon_dict)

  v = make_vcon()
  with pytest.warns(DeprecationWarning, match = "set_amended_from"):
    v.set_amended("1234")
  assert(v._vcon_dict["amended_from"] == {"uuid": "1234"})
  assert("amended" not in v._vcon_dict)


def test_deprecated_properties_return_new_members():
  vcon_dict = make_vcon().dumpd()
  vcon_dict["vcon"] = "0.4.0"
  vcon_dict.pop("sessions", None)
  vcon_dict["redacted"] = {"uuid": UUID, "type": "PII Redaction"}
  v = vcon.Vcon()
  v.loadd(vcon_dict)
  # converted on load
  assert(v.redacted_from == {"uuid": UUID, "type": "PII Redaction"})
  assert("redacted" not in v._vcon_dict)
  with pytest.warns(DeprecationWarning, match = "redacted attribute is deprecated, use redacted_from"):
    assert(v.redacted == {"uuid": UUID, "type": "PII Redaction"})
  with pytest.warns(DeprecationWarning, match = "amended attribute is deprecated, use amended_from"):
    assert(v.amended is None)
  # the descriptor itself, from the class
  assert(isinstance(vcon.Vcon.redacted, vcon.VconDeprecatedDict))


def test_load_redacted_from():
  v = make_vcon()
  v.set_redacted_from(UUID, "PII")
  loaded = vcon.Vcon()
  loaded.loads(v.dumps())
  assert(loaded.redacted_from == {"uuid": UUID, "type": "PII"})

  # CBOR round trip
  loaded = vcon.Vcon()
  loaded.loadc(v.dumpc())
  assert(loaded.redacted_from == {"uuid": UUID, "type": "PII"})


@pytest.mark.asyncio
async def test_redact_an_amended_vcon():
  """ the redacted vCon references only the vCon it was redacted from """
  v = make_vcon()
  v.set_amended_from(OTHER_UUID)
  redacted = await v.jq_redaction({"jq_redaction_query": ".", "redaction_type_label": "everything",
    "uuid_domain": "example.com"})
  assert(redacted.redacted_from == {"uuid": v.uuid, "type": "everything"})
  assert(redacted.amended_from is None)
  # the input vCon is unchanged
  assert(v.amended_from == {"uuid": OTHER_UUID})


@pytest.mark.asyncio
async def test_amend_a_redacted_vcon():
  """ the amended vCon references only its prior version """
  v = make_vcon()
  v.set_redacted_from(OTHER_UUID, "PII")
  amended = await v.create_amended({})
  assert(amended.amended_from == {"uuid": v.uuid})
  assert(amended.redacted_from is None)
  # the input vCon is unchanged
  assert(v.redacted_from == {"uuid": OTHER_UUID, "type": "PII"})


def test_dumpc_inline_reference_body():
  """ an inline base64url body in a referenced vCon member is tagged in CBOR, for each member name """
  for name in ["redacted_from", "amended_from", "redacted", "amended"]:
    v = make_vcon()
    v._vcon_dict[name] = {"uuid": UUID, "encoding": "base64url", "body": "AAEC"}
    cbor_dict = cbor2.loads(v.dumpc())
    assert(cbor_dict[name]["encoding"] == "binary"), name
    assert(isinstance(cbor_dict[name]["body"], cbor2.CBORTag)), name
    # the vCon itself is unchanged
    assert(v._vcon_dict[name]["encoding"] == "base64url"), name
