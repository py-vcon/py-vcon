# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" Unit tests for the JWE header parameters of encrypted vCons """

import jose.utils
import pytest
import vcon
import vcon.security

CA_CERT = "certs/fake_ca_root.crt"
DIVISION_CERT = "certs/fake_div.crt"
DIVISION_PRIVATE_KEY = "certs/fake_div.key"
GROUP_CERT = "certs/fake_grp.crt"
GROUP_PRIVATE_KEY = "certs/fake_grp.key"
CERT_CHAIN = [GROUP_CERT, DIVISION_CERT, CA_CERT]


def make_encrypted_dict() -> dict:
  v = vcon.Vcon()
  v.set_party_parameter("tel", "+15551110000")
  v.set_party_parameter("tel", "+15552220000")
  v.add_dialog_inline_text("Hello", "2022-06-21T13:53:26-04:00", 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.set_uuid("example.com")
  v.sign(GROUP_PRIVATE_KEY, CERT_CHAIN)
  v.encrypt(DIVISION_CERT)
  return(v.dumpd())


def decrypt_verify(encrypted_dict : dict) -> vcon.Vcon:
  v = vcon.Vcon()
  v.loadd(encrypted_dict)
  v.decrypt(DIVISION_PRIVATE_KEY, DIVISION_CERT)
  v.verify([CA_CERT])
  return(v)


def test_encrypted_headers():
  encrypted_dict = make_encrypted_dict()

  protected = vcon.security.decode_jws_protected_header(encrypted_dict["protected"])
  assert(protected == {"alg": "RSA-OAEP", "enc": "A256CBC-HS512"})
  assert(encrypted_dict["unprotected"] == {"uuid": encrypted_dict["unprotected"]["uuid"], "cty": "application/vcon"})
  assert(len(encrypted_dict["unprotected"]["uuid"]) == 36)
  assert(len(encrypted_dict["recipients"]) == 1)
  assert("header" not in encrypted_dict["recipients"][0])
  assert(set(protected) & set(encrypted_dict["unprotected"]) == set())


def test_encrypt_decrypt_verify():
  v = decrypt_verify(make_encrypted_dict())
  assert(v.parties[0]["tel"] == "+15551110000")
  assert(v.sessions[0]["dialog"] == [0])


def test_decrypt_0_4_0_identical_repeats():
  # vCon 0.4.0 form: enc repeated in the unprotected and recipient headers
  encrypted_dict = make_encrypted_dict()
  encrypted_dict["unprotected"]["enc"] = "A256CBC-HS512"
  encrypted_dict["unprotected"]["cty"] = "application/vcon+json"
  encrypted_dict["recipients"][0]["header"] = {"enc": "A256CBC-HS512"}

  v = decrypt_verify(encrypted_dict)
  assert(v.parties[1]["tel"] == "+15552220000")


def test_decrypt_differing_unprotected_rejected():
  encrypted_dict = make_encrypted_dict()
  encrypted_dict["unprotected"]["enc"] = "A128GCM"

  v = vcon.Vcon()
  v.loadd(encrypted_dict)
  with pytest.raises(vcon.InvalidVconJson, match = "enc"):
    v.decrypt(DIVISION_PRIVATE_KEY, DIVISION_CERT)


def test_decrypt_differing_recipient_rejected():
  encrypted_dict = make_encrypted_dict()
  encrypted_dict["recipients"][0]["header"] = {"alg": "RSA1_5"}

  v = vcon.Vcon()
  v.loadd(encrypted_dict)
  with pytest.raises(vcon.InvalidVconJson, match = "recipient"):
    v.decrypt(DIVISION_PRIVATE_KEY, DIVISION_CERT)


def test_check_jwe_headers():
  protected = jose.utils.base64url_encode(b'{"alg":"RSA-OAEP","enc":"A256GCM"}').decode("utf-8")
  vcon.security.check_jwe_headers({"protected": protected, "unprotected": {"cty": "application/vcon"},
    "recipients": [{"encrypted_key": "x"}]})
  vcon.security.check_jwe_headers({"protected": protected, "unprotected": {"enc": "A256GCM"},
    "recipients": [{"header": {"enc": "A256GCM"}}]})

  with pytest.raises(ValueError, match = "unprotected and recipient"):
    vcon.security.check_jwe_headers({"unprotected": {"kid": "a"},
      "recipients": [{"header": {"kid": "b"}}]})


def test_merge_jose_headers_names():
  with pytest.raises(ValueError, match = "both the protected and recipient headers"):
    vcon.security.merge_jose_headers({"alg": "A"}, {"alg": "B"}, "test", "protected", "recipient")
