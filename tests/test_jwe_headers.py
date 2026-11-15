# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" Unit tests for the JWE header parameters of encrypted vCons """

import pytest
import jwcrypto.jwe
import vcon
import vcon.security
import vcon.utils
import tests.common_utils

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
  v.add_text_dialog_inline("Hello", "2022-06-21T13:53:26-04:00", 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.set_uuid("example.com")
  v.sign(GROUP_PRIVATE_KEY, CERT_CHAIN)
  v.encrypt(DIVISION_CERT)
  return(v.dumpd())


async def decrypt_verify(encrypted_dict : dict) -> vcon.Vcon:
  v = vcon.Vcon()
  v.loadd(encrypted_dict)
  v.decrypt(DIVISION_PRIVATE_KEY, DIVISION_CERT)
  await v.verify([CA_CERT])
  return(v)


def test_encrypted_headers():
  encrypted_dict = make_encrypted_dict()
  tests.common_utils.assert_valid_cddl(encrypted_dict)

  assert(list(encrypted_dict.keys()) == ["protected", "iv", "ciphertext", "tag", "recipients", "unprotected"])
  protected = vcon.security.decode_jws_protected_header(encrypted_dict["protected"])
  assert(protected == {"alg": "RSA-OAEP", "enc": "A256CBC-HS512"})
  assert(list(encrypted_dict["recipients"][0].keys()) == ["encrypted_key"])
  assert(encrypted_dict["unprotected"] == {"uuid": encrypted_dict["unprotected"]["uuid"], "cty": "application/vcon"})
  assert(len(encrypted_dict["unprotected"]["uuid"]) == 36)
  assert(len(encrypted_dict["recipients"]) == 1)
  assert("header" not in encrypted_dict["recipients"][0])
  assert(set(protected) & set(encrypted_dict["unprotected"]) == set())


@pytest.mark.asyncio
async def test_encrypt_decrypt_verify():
  v = await decrypt_verify(make_encrypted_dict())
  assert(v.parties[0]["tel"] == "+15551110000")
  assert(v.sessions[0]["dialog"] == [0])


@pytest.mark.asyncio
async def test_decrypt_0_4_0_identical_repeats():
  # vCon 0.4.0 form: enc repeated in the unprotected and recipient headers
  encrypted_dict = make_encrypted_dict()
  encrypted_dict["unprotected"]["enc"] = "A256CBC-HS512"
  encrypted_dict["unprotected"]["cty"] = "application/vcon+json"
  encrypted_dict["recipients"][0]["header"] = {"enc": "A256CBC-HS512"}

  v = await decrypt_verify(encrypted_dict)
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
  protected = vcon.utils.base64url_encode(b'{"alg":"RSA-OAEP","enc":"A256GCM"}')
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


def test_decrypt_tampered_ciphertext_rejected():
  encrypted_dict = make_encrypted_dict()
  ciphertext = bytearray(vcon.utils.base64url_decode(encrypted_dict["ciphertext"]))
  ciphertext[0] ^= 0x01
  encrypted_dict["ciphertext"] = vcon.utils.base64url_encode(bytes(ciphertext))

  v = vcon.Vcon()
  v.loadd(encrypted_dict)
  with pytest.raises(jwcrypto.jwe.InvalidJWEData):
    v.decrypt(DIVISION_PRIVATE_KEY, DIVISION_CERT)


def test_decrypt_wrong_key_rejected():
  v = vcon.Vcon()
  v.loadd(make_encrypted_dict())
  with pytest.raises(jwcrypto.jwe.InvalidJWEData):
    v.decrypt(GROUP_PRIVATE_KEY, GROUP_CERT)


@pytest.mark.asyncio
async def test_large_inline_recording():
  """ no size limit on the JWS payload or JWE plaintext (python-jose limited JWE to 250 KB) """
  body = bytes(range(256)) * 4096
  v = vcon.Vcon()
  v.set_party_parameter("tel", "+15551110000")
  v.add_recording_dialog_inline(body, "2022-06-21T13:53:26-04:00", 0, 0, "audio/x-wav", "large.wav")
  v.set_uuid("example.com")
  v.sign(GROUP_PRIVATE_KEY, CERT_CHAIN)
  v.encrypt(DIVISION_CERT)

  decrypted = await decrypt_verify(v.dumpd())
  assert(decrypted.decode_dialog_inline_body(0) == body)


def test_remove_jwe_repeated_headers():
  protected = vcon.utils.base64url_encode(b'{"alg":"RSA-OAEP","enc":"A256CBC-HS512"}')
  jwe = {
    "protected": protected,
    "unprotected": {"enc": "A256CBC-HS512", "uuid": "u"},
    "recipients": [{"header": {"enc": "A256CBC-HS512", "uuid": "u"}, "encrypted_key": "k1"},
      {"header": {"kid": "2"}, "encrypted_key": "k2"}],
    "ciphertext": "c"
    }
  assert(vcon.security.remove_jwe_repeated_headers(jwe) == {
    "protected": protected,
    "unprotected": {"uuid": "u"},
    "recipients": [{"encrypted_key": "k1"}, {"header": {"kid": "2"}, "encrypted_key": "k2"}],
    "ciphertext": "c"
    })
  # the JWE passed in is not changed
  assert(jwe["unprotected"] == {"enc": "A256CBC-HS512", "uuid": "u"})
  assert(jwe["recipients"][0]["header"] == {"enc": "A256CBC-HS512", "uuid": "u"})

  jwe = {"protected": protected, "unprotected": {"enc": "A256CBC-HS512"}, "ciphertext": "c"}
  assert(vcon.security.remove_jwe_repeated_headers(jwe) == {"protected": protected, "ciphertext": "c"})
