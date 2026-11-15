# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" 0.4.0 vCons, labeled or detected, are converted to vCon 0.5.0 on load """

import json
import logging
import warnings
import cbor2
import pytest
import vcon
import vcon.migrate_0_4_0
import tests.common_utils

CA_CERT = "certs/fake_ca_root.crt"
GROUP_CERT = "certs/fake_grp.crt"
GROUP_PRIVATE_KEY = "certs/fake_grp.key"
UUID = "01a07da8-c2bb-83e5-b9a2-279e0d16bc46"
START = "2023-01-01T10:00:00.000+00:00"


def make_0_4_0(label : bool = True) -> dict:
  """ a 0.4.0 vCon with a recording Dialog and party_history """
  vcon_dict = {"uuid": UUID, "created_at": START, "parties": [{"name": "Alice"}, {"name": "Bob"}],
    "dialog": [{"type": "recording", "start": START, "duration": 30, "parties": [0, 1],
      "mediatype": "audio/x-wav", "url": "https://example.com/a.wav", "content_hash": "sha512-abc",
      "party_history": [{"party": 1, "event": "join", "time": START}]}],
    "analysis": [], "attachments": []}
  if(label):
    vcon_dict["vcon"] = "0.4.0"
  return(vcon_dict)


def load_no_unconverted_warning(vcon_dict : dict) -> vcon.Vcon:
  loaded = vcon.Vcon()
  with warnings.catch_warnings():
    warnings.simplefilter("error", vcon.UnconvertedVconVersionWarning)
    loaded.loads(json.dumps(vcon_dict))
  return(loaded)


def check_converted(loaded : vcon.Vcon) -> None:
  assert(loaded.vcon == "0.5.0")
  assert(loaded.uuid == UUID)
  assert(loaded._vcon_dict["updated_at"] is not None)
  assert(loaded.sessions[0]["dialog"] == [0])
  assert(loaded.events == [{"type": "join", "time": START, "sessions": 0, "party": 1}])
  assert("party_history" not in loaded.dialog[0])
  tests.common_utils.assert_valid_vcon(loaded.dumpd())


def test_labeled_0_4_0_converted():
  check_converted(load_no_unconverted_warning(make_0_4_0()))


def test_unlabeled_0_4_0_detected(caplog):
  with caplog.at_level(logging.WARNING):
    loaded = load_no_unconverted_warning(make_0_4_0(label = False))
  check_converted(loaded)
  assert("detected as a 0.4.0 vCon" in caplog.text)


def test_unlabeled_0_5_0_not_converted(caplog):
  vcon_dict = load_no_unconverted_warning(make_0_4_0()).dumpd()
  del vcon_dict["vcon"]
  with caplog.at_level(logging.WARNING):
    loaded = load_no_unconverted_warning(vcon_dict)
  assert(loaded.dumpd() == vcon_dict)
  assert("detected as a 0.4.0 vCon" not in caplog.text)


def test_cbor_0_4_0_converted():
  loaded = vcon.Vcon()
  with warnings.catch_warnings():
    warnings.simplefilter("ignore", vcon.ExperimentalWarning)
    loaded.loadc(cbor2.dumps(make_0_4_0()))
  check_converted(loaded)


@pytest.mark.parametrize("change, expected", [
  ({}, True),                                            # Dialog Objects and no sessions
  ({"dialog": []}, False),
  ({"dialog": [{}]}, False),                             # only empty Dialog Objects
  ({"sessions": [{"dialog": [0]}]}, True),               # still has party_history
  ({"sessions": [{"dialog": [0]}], "party_history": None}, False),
  ({"dialog": [], "redacted": {"type": "PII"}}, True),
  ({"dialog": [], "amended": {"uuid": UUID}}, True),
  ({"sessions": [{}], "dialog": [{"type": "transfer"}]}, True),
  ({"sessions": [{}], "dialog": [{"type": "text", "originator": 0}]}, True)
  ])
def test_is_0_4_0_vcon(change, expected):
  vcon_dict = make_0_4_0(label = False)
  if(change.pop("party_history", 0) is None):
    del vcon_dict["dialog"][0]["party_history"]
  vcon_dict.update(change)
  assert(vcon.migrate_0_4_0.is_0_4_0_vcon(vcon_dict) == expected)


def test_recording_set_refused_on_load():
  vcon_dict = make_0_4_0()
  vcon_dict["dialog"].append({"type": "recording-set", "recordings": [0]})
  with pytest.raises(vcon.VconConversionError):
    vcon.Vcon().loads(json.dumps(vcon_dict))


def test_conversion_warning_on_load():
  vcon_dict = make_0_4_0()
  vcon_dict["redacted"] = {"uuid": UUID}
  with pytest.warns(vcon.VconConversionWarning, match = "redacted has no type"):
    loaded = vcon.Vcon()
    loaded.loads(json.dumps(vcon_dict))
  assert(loaded.redacted_from == {"uuid": UUID})


@pytest.mark.parametrize("path", tests.common_utils.DRAFT_0_4_0_UNSIGNED_EXAMPLES)
def test_draft_example_converts(path):
  example = tests.common_utils.load_draft_0_4_0_example(path)
  assert("vcon" not in example)
  loaded = load_no_unconverted_warning(example)
  assert(loaded.vcon == "0.5.0")
  assert(loaded.uuid == example["uuid"])
  assert(len(loaded.sessions) > 0)
  tests.common_utils.assert_valid_vcon(loaded.dumpd())


@pytest.mark.asyncio
async def test_signed_example_converted_after_verify():
  signed_dict = tests.common_utils.load_draft_0_4_0_example("examples/ab_call_ext_rec_signed.vcon")
  signed = vcon.Vcon()
  signed.loadd(signed_dict)
  await signed.verify([CA_CERT])
  assert(signed.vcon == "0.5.0")
  assert(signed.sessions[0]["dialog"] == [0])
  # the original JWS is kept
  assert(signed.dumpd() == signed_dict)


@pytest.mark.asyncio
async def test_encrypted_example_converted_after_decrypt():
  encrypted = vcon.Vcon()
  encrypted.loadd(tests.common_utils.load_draft_0_4_0_example("examples/ab_call_ext_rec_encrypted.vcon"))
  encrypted.decrypt(GROUP_PRIVATE_KEY, GROUP_CERT)
  await encrypted.verify([CA_CERT])
  assert(encrypted.vcon == "0.5.0")
  assert(encrypted.sessions[0]["dialog"] == [0])


def test_empty_redacted_and_amended_removed():
  """ early py-vcon versions wrote empty redacted and amended Objects """
  vcon_dict = make_0_4_0()
  vcon_dict["redacted"] = {}
  vcon_dict["amended"] = {}
  with warnings.catch_warnings():
    warnings.simplefilter("error", vcon.VconConversionWarning)
    loaded = load_no_unconverted_warning(vcon_dict)
  for name in ["redacted", "amended", "redacted_from", "amended_from"]:
    assert(name not in loaded._vcon_dict), name
  tests.common_utils.assert_valid_vcon(loaded.dumpd())
