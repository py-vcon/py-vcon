# Copyright (C) 2026 SIPez LLC.  All rights reserved.
# Copyright (C) 2026 SIP Spectrum, Inc.  All rights reserved.
"""
Tests that the server's vCon models accept vCon 0.4.0 and 0.5.0 in the
unsigned, signed and encrypted forms.  A received vCon is converted after the
models validate it, so both versions must pass.
"""
import base64
import copy
import json
import typing
import pydantic
import pytest
import fastapi.testclient
import vcon
import vcon.pydantic_utils
import py_vcon_server
import py_vcon_server.processor
from common_setup import UUID


CA_CERT = "../certs/fake_ca_root.crt"
GROUP_CERT = "../certs/fake_grp.crt"
GROUP_PRIVATE_KEY = "../certs/fake_grp.key"
DIVISION_CERT = "../certs/fake_div.crt"


class VconHolder(pydantic.BaseModel):
  """ Validates a vCon dict against the same Union the REST API uses """
  vcon: typing.Union[
      py_vcon_server.processor.VconUnsignedObject,
      py_vcon_server.processor.VconSignedObject,
      py_vcon_server.processor.VconEncryptedObject
    ]


def validated_type(vcon_dict: dict) -> type:
  """ Validate the dict and return the model class it was accepted as """
  holder = VconHolder(vcon = vcon_dict)
  return(type(holder.vcon))


def unsigned_0_4_0() -> dict:
  """ vCon 0.4.0 with members which no longer exist in 0.5.0 """
  return({
      "vcon": "0.4.0",
      "uuid": UUID,
      "created_at": "2024-03-06T20:07:43.000+00:00",
      "parties": [{"tel": "+15551234567"}, {"tel": "+15557654321"}, {"tel": "+15550000000"}],
      "dialog": [
          {
            "type": "text",
            "start": "2024-03-06T20:07:43.000+00:00",
            "duration": 5,
            "parties": [0, 1],
            "originator": 0,
            "mediatype": "text/plain",
            "encoding": "none",
            "body": "hello",
            "party_history": [
                {"party": 1, "event": "join", "time": "2024-03-06T20:07:43.000+00:00"}
              ]
          },
          {
            "type": "transfer",
            "start": "2024-03-06T20:08:43.000+00:00",
            "transferee": 0,
            "transferor": 1,
            "transfer_target": 2,
            "original": 0
          }
        ],
      "group": [],
      "redacted": {"uuid": "01928e10-193e-8231-b9a2-279e0d16bc46", "type": "PII Redaction"}
    })


def unsigned_0_5_0() -> dict:
  """ vCon 0.5.0 with the members new in 0.5.0 """
  a_vcon = vcon.Vcon()
  a_vcon._vcon_dict["uuid"] = UUID
  a_vcon.set_party_parameter("tel", "+15551234567")
  a_vcon.set_party_parameter("tel", "+15557654321")
  a_vcon.add_text_dialog_inline("hello", "2024-03-06T20:07:43+00:00", 5.0, 0,
    vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  vcon_dict = a_vcon.dumpd()
  vcon_dict["events"] = [
      {"type": "join", "time": "2024-03-06T20:07:43.000+00:00", "sessions": 0, "party": 1}
    ]
  vcon_dict["dialog"].append({})
  vcon_dict["redacted_strings"] = [{"ref": 1, "type": "PHONE_NUMBER"}]
  vcon_dict["redacted_from"] = {"uuid": "01928e10-193e-8231-b9a2-279e0d16bc46", "type": "PII"}
  return(vcon_dict)


def signed_vcon() -> vcon.Vcon:
  a_vcon = vcon.Vcon()
  a_vcon._vcon_dict["uuid"] = UUID
  a_vcon.set_party_parameter("tel", "+15551234567")
  a_vcon.sign(GROUP_PRIVATE_KEY, [GROUP_CERT, DIVISION_CERT, CA_CERT])
  return(a_vcon)


def signed_0_5_0() -> dict:
  """ signed as py-vcon produces it: alg only in the protected header """
  return(signed_vcon().dumpd())


def signed_0_4_0() -> dict:
  """ signed the 0.4.0 way: alg repeated in the unprotected header """
  vcon_dict = signed_0_5_0()
  vcon_dict["signatures"][0]["header"]["alg"] = "RS256"
  return(vcon_dict)


def signed_no_protected() -> dict:
  """ RFC 7515 layout with no protected member and alg in the header """
  vcon_dict = signed_0_5_0()
  del vcon_dict["signatures"][0]["protected"]
  vcon_dict["signatures"][0]["header"]["alg"] = "RS256"
  return(vcon_dict)


def encrypted_0_5_0() -> dict:
  """ encrypted as py-vcon produces it: alg and enc only in the protected header """
  a_vcon = signed_vcon()
  a_vcon.encrypt(DIVISION_CERT)
  return(a_vcon.dumpd())


def encrypted_0_4_0() -> dict:
  """ encrypted the 0.4.0 way: enc repeated in the unprotected and recipient headers """
  vcon_dict = encrypted_0_5_0()
  vcon_dict["unprotected"]["enc"] = "A256CBC-HS512"
  vcon_dict["recipients"][0]["header"] = {"enc": "A256CBC-HS512"}
  return(vcon_dict)


def encrypted_unprotected_alg_enc() -> dict:
  """ RFC 7516 layout with alg and enc unprotected and no protected member """
  vcon_dict = encrypted_0_5_0()
  encoded = vcon_dict["protected"]
  protected = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
  del vcon_dict["protected"]
  vcon_dict["unprotected"]["alg"] = protected["alg"]
  vcon_dict["unprotected"]["enc"] = protected["enc"]
  return(vcon_dict)


MODEL_CASES = [
    ("unsigned 0.4.0", unsigned_0_4_0, py_vcon_server.processor.VconUnsignedObject),
    ("unsigned 0.5.0", unsigned_0_5_0, py_vcon_server.processor.VconUnsignedObject),
    ("signed 0.4.0", signed_0_4_0, py_vcon_server.processor.VconSignedObject),
    ("signed 0.5.0", signed_0_5_0, py_vcon_server.processor.VconSignedObject),
    ("signed no protected", signed_no_protected, py_vcon_server.processor.VconSignedObject),
    ("encrypted 0.4.0", encrypted_0_4_0, py_vcon_server.processor.VconEncryptedObject),
    ("encrypted 0.5.0", encrypted_0_5_0, py_vcon_server.processor.VconEncryptedObject),
    ("encrypted alg enc unprotected", encrypted_unprotected_alg_enc,
      py_vcon_server.processor.VconEncryptedObject)
  ]


@pytest.mark.parametrize("label, make_dict, model_class", MODEL_CASES)
def test_model_accepts(label, make_dict, model_class):
  """ Each form and version validates as the expected model, keeping its content """
  vcon_dict = make_dict()
  holder = VconHolder(vcon = vcon_dict)
  assert(type(holder.vcon) == model_class), label
  assert(vcon.pydantic_utils.get_dict(holder.vcon, exclude_none = True) == vcon_dict), label


def test_encrypted_requires_unprotected():
  """ unprotected is still required in 0.5.0 """
  vcon_dict = encrypted_0_5_0()
  del vcon_dict["unprotected"]
  with pytest.raises(vcon.pydantic_utils.ValidationErrorType):
    VconHolder(vcon = vcon_dict)


@pytest.mark.parametrize("label, make_dict", [
    ("unsigned 0.4.0", unsigned_0_4_0),
    ("unsigned 0.5.0", unsigned_0_5_0)
  ])
def test_post_get_unsigned(label, make_dict):
  """ An unsigned 0.4.0 or 0.5.0 vCon is stored and returned unchanged """
  vcon_dict = make_dict()
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    post_response = client.post("/vcon", json = vcon_dict)
    assert(post_response.status_code == 204), "{}: {}".format(label, post_response.text)

    get_response = client.get("/vcon/{}".format(UUID), headers = {"accept": "application/json"})
    assert(get_response.status_code == 200), label
    assert(get_response.json() == vcon_dict), label

    assert(client.delete("/vcon/{}".format(UUID)).status_code == 204)


@pytest.mark.parametrize("label, make_dict, model_class", MODEL_CASES)
def test_processor_io_round_trip(label, make_dict, model_class):
  """ Each form and version passes through a processor's input and output unchanged """
  vcon_dict = make_dict()
  processor_input = {
      "processor_io": {
        "vcons": [copy.deepcopy(vcon_dict)],
        "parameters": {}
      },
      "processor_options": {"parameters": {"checked": True}}
    }
  api_parameters = {"commit_changes": False, "return_whole_vcon": True}
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    post_response = client.post("/processIO/set_parameters",
        params = api_parameters,
        json = processor_input
      )
    assert(post_response.status_code == 200), "{}: {}".format(label, post_response.text)
    processor_output = post_response.json()
    assert(processor_output["parameters"]["checked"] is True), label
    assert(processor_output["vcons"][0] == vcon_dict), label
