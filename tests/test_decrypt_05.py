# Copyright (C) 2026 SIPez LLC.  All rights reserved.
"""
Unit tests for decrypting encrypted vCons in the JWE layouts allowed by
vCon 0.5.0 (RFC7516): alg and enc in the protected, unprotected or recipient
headers, and more than one recipient.
"""

import json
import jwcrypto.jwe
import pytest
import vcon
import vcon.security
import tests.common_utils

CA_CERT = "certs/fake_ca_root.crt"
DIVISION_CERT = "certs/fake_div.crt"
DIVISION_PRIVATE_KEY = "certs/fake_div.key"
GROUP_CERT = "certs/fake_grp.crt"
GROUP_PRIVATE_KEY = "certs/fake_grp.key"
CERT_CHAIN = [GROUP_CERT, DIVISION_CERT, CA_CERT]
ALG = "RSA-OAEP"
ENC = "A256CBC-HS512"


def signed_vcon() -> vcon.Vcon:
  v = vcon.Vcon()
  v.set_party_parameter("tel", "+15551110000")
  v.set_party_parameter("tel", "+15552220000")
  v.add_text_dialog_inline("Hello", "2022-06-21T13:53:26-04:00", 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.set_uuid("example.com")
  v.sign(GROUP_PRIVATE_KEY, CERT_CHAIN)
  return(v)


def encrypt_layout(protected, unprotected, recipients) -> dict:
  """
  Encrypt a signed vCon with the given protected and unprotected headers
  (dict or None) for the given recipients, a list of (certificate file,
  recipient header dict or None), as another -05 producer might, in the
  general JSON serialization.
  """
  v = signed_vcon()
  jwe = jwcrypto.jwe.JWE(
    json.dumps(v.dumpd()).encode("utf-8"),
    protected = None if protected is None else json.dumps(protected),
    unprotected = None if unprotected is None else json.dumps(dict(unprotected, uuid = v.uuid))
    )
  for cert_file, header in recipients:
    jwe.add_recipient(vcon.security.build_encryption_jwk_from_pem_file(cert_file), header)
  jwe_dict = json.loads(jwe.serialize())
  # a single recipient is serialized flattened, vCon uses the general form
  if("recipients" not in jwe_dict):
    recipient = {"encrypted_key": jwe_dict.pop("encrypted_key")}
    if("header" in jwe_dict):
      recipient["header"] = jwe_dict.pop("header")
    jwe_dict["recipients"] = [recipient]
  return(jwe_dict)


# cty is mandatory in the -05 Unprotected Object, though RFC7516 does not
# require it; decrypt accepts its absence
NOT_05_LAYOUTS = ["enc unprotected, alg in the recipient header"]

LAYOUTS = [
    ("alg and enc protected", {"alg": ALG, "enc": ENC}, {"cty": "application/vcon"}, None),
    ("alg and enc unprotected, no protected", None, {"alg": ALG, "enc": ENC, "cty": "application/vcon"}, None),
    ("enc protected, alg in the recipient header", {"enc": ENC}, {"cty": "application/vcon"}, {"alg": ALG}),
    ("enc unprotected, alg in the recipient header", None, {"enc": ENC}, {"alg": ALG})
  ]


@pytest.mark.asyncio
@pytest.mark.parametrize("label, protected, unprotected, recipient_header", LAYOUTS)
async def test_layout_decrypts(label, protected, unprotected, recipient_header):
  jwe_dict = encrypt_layout(protected, unprotected, [(DIVISION_CERT, recipient_header)])
  assert(("protected" in jwe_dict) == (protected is not None)), label
  if(label in NOT_05_LAYOUTS):
    with pytest.raises(AssertionError, match = "not valid against the vCon CDDL"):
      tests.common_utils.assert_valid_cddl(jwe_dict)
  else:
    tests.common_utils.assert_valid_cddl(jwe_dict)

  encrypted = vcon.Vcon()
  encrypted.loadd(jwe_dict)
  assert(encrypted.state == vcon.VconStates.ENCRYPTED), label
  assert(encrypted.uuid == jwe_dict["unprotected"]["uuid"]), label

  encrypted.decrypt(DIVISION_PRIVATE_KEY, DIVISION_CERT)
  await encrypted.verify([CA_CERT])
  assert(encrypted.parties[1]["tel"] == "+15552220000"), label


@pytest.mark.parametrize("label, protected, unprotected, recipient_header", LAYOUTS)
def test_layout_wrong_key_rejected(label, protected, unprotected, recipient_header):
  encrypted = vcon.Vcon()
  encrypted.loadd(encrypt_layout(protected, unprotected, [(DIVISION_CERT, recipient_header)]))
  with pytest.raises(jwcrypto.jwe.InvalidJWEData):
    encrypted.decrypt(GROUP_PRIVATE_KEY, GROUP_CERT)
  assert(encrypted.state == vcon.VconStates.ENCRYPTED), label


@pytest.mark.asyncio
@pytest.mark.parametrize("private_key, cert", [
    (DIVISION_PRIVATE_KEY, DIVISION_CERT),
    (GROUP_PRIVATE_KEY, GROUP_CERT)
  ])
async def test_two_recipients(private_key, cert):
  jwe_dict = encrypt_layout({"alg": ALG, "enc": ENC}, {"cty": "application/vcon"},
    [(DIVISION_CERT, None), (GROUP_CERT, None)])
  assert(len(jwe_dict["recipients"]) == 2)

  encrypted = vcon.Vcon()
  encrypted.loadd(jwe_dict)
  encrypted.decrypt(private_key, cert)
  await encrypted.verify([CA_CERT])
  assert(encrypted.parties[0]["tel"] == "+15551110000")


def test_differing_alg_in_recipient_header_rejected():
  jwe_dict = encrypt_layout(None, {"alg": ALG, "enc": ENC}, [(DIVISION_CERT, None)])
  jwe_dict["recipients"][0]["header"] = {"alg": "RSA1_5"}

  encrypted = vcon.Vcon()
  encrypted.loadd(jwe_dict)
  with pytest.raises(vcon.InvalidVconJson, match = "unprotected and recipient"):
    encrypted.decrypt(DIVISION_PRIVATE_KEY, DIVISION_CERT)


def test_get_dict_uuid_optional_headers():
  v = signed_vcon()
  uuid = v.uuid

  # JWE with no protected member
  jwe_dict = encrypt_layout(None, {"alg": ALG, "enc": ENC}, [(DIVISION_CERT, None)])
  assert(vcon.Vcon.get_dict_uuid(jwe_dict) == jwe_dict["unprotected"]["uuid"])
  # JWE with no unprotected member
  del jwe_dict["unprotected"]
  assert(vcon.Vcon.get_dict_uuid(jwe_dict) is None)

  # JWS signature with no unprotected header: the uuid is read from the payload
  jws_dict = v.dumpd()
  del jws_dict["signatures"][0]["header"]
  assert(vcon.Vcon.get_dict_uuid(jws_dict) == uuid)
