# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" Unit tests for the JWS header parameters of signed vCons """

import json
import jose.jws
import jose.utils
import pytest
import vcon
import vcon.security

CA_CERT = "certs/fake_ca_root.crt"
DIVISION_CERT = "certs/fake_div.crt"
GROUP_CERT = "certs/fake_grp.crt"
GROUP_PRIVATE_KEY = "certs/fake_grp.key"
CERT_CHAIN = [GROUP_CERT, DIVISION_CERT, CA_CERT]


def make_vcon() -> vcon.Vcon:
  v = vcon.Vcon()
  v.set_party_parameter("tel", "+15551110000")
  v.set_party_parameter("tel", "+15552220000")
  v.add_dialog_inline_text("Hello", "2022-06-21T13:53:26-04:00", 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.set_uuid("example.com")
  return(v)


def make_0_4_0_signed_dict(v : vcon.Vcon) -> dict:
  """
  Sign the vCon the way that py-vcon did for vCon 0.4.0: alg and x5c in
  both the protected and unprotected headers and typ JWT in the protected
  header.
  """
  header, signing_jwk = vcon.security.build_signing_jwk_from_pem_files(GROUP_PRIVATE_KEY, CERT_CHAIN)
  jws_token = jose.jws.sign(v.dumpd(), signing_jwk, headers = header, algorithm = signing_jwk["alg"])
  protected_header, payload, signature = jws_token.split(".")
  header["uuid"] = v.uuid
  return({
    "payload": payload,
    "signatures": [{"header": header, "signature": signature, "protected": protected_header}]
    })


def test_signed_headers():
  v = make_vcon()
  v.sign(GROUP_PRIVATE_KEY, CERT_CHAIN)
  signed_dict = v.dumpd()

  signature = signed_dict["signatures"][0]
  protected = vcon.security.decode_jws_protected_header(signature["protected"])
  assert(protected == {"alg": "RS256"})
  assert(set(signature["header"].keys()) == {"x5c", "uuid"})
  assert(len(signature["header"]["x5c"]) == 3)
  assert(signature["header"]["uuid"] == v.uuid)
  assert(set(protected) & set(signature["header"]) == set())

  # payload is the unsigned vCon
  payload = json.loads(jose.utils.base64url_decode(bytes(signed_dict["payload"] + "==", "utf-8")))
  assert(payload["uuid"] == v.uuid)
  assert(payload["sessions"][0]["dialog"] == [0])


def test_sign_verify():
  v = make_vcon()
  v.sign(GROUP_PRIVATE_KEY, CERT_CHAIN)

  signed = vcon.Vcon()
  signed.loads(v.dumps())
  signed.verify([CA_CERT])
  assert(signed.parties[0]["tel"] == "+15551110000")
  assert(signed.sessions[0]["dialog"] == [0])


def test_verify_0_4_0_identical_repeats():
  signed_dict = make_0_4_0_signed_dict(make_vcon())
  signature = signed_dict["signatures"][0]
  protected = vcon.security.decode_jws_protected_header(signature["protected"])
  # confirm this is the 0.4.0 form with repeated header parameters
  assert(protected["typ"] == "JWT")
  assert(protected["alg"] == signature["header"]["alg"])
  assert(protected["x5c"] == signature["header"]["x5c"])

  signed = vcon.Vcon()
  signed.loadd(signed_dict)
  signed.verify([CA_CERT])
  assert(signed.parties[1]["tel"] == "+15552220000")


def test_verify_differing_repeats_rejected():
  signed_dict = make_0_4_0_signed_dict(make_vcon())
  signed_dict["signatures"][0]["header"]["alg"] = "RS512"

  signed = vcon.Vcon()
  signed.loadd(signed_dict)
  with pytest.raises(vcon.InvalidVconSignature, match = "alg"):
    signed.verify([CA_CERT])


def test_jws_sign():
  header, signing_jwk = vcon.security.build_signing_jwk_from_pem_files(GROUP_PRIVATE_KEY, CERT_CHAIN)
  protected, payload, signature = vcon.security.jws_sign({"a": 1}, signing_jwk, {"alg": "RS256"})
  assert(vcon.security.decode_jws_protected_header(protected) == {"alg": "RS256"})

  verification_jwk = {name: signing_jwk[name] for name in ("kty", "use", "alg", "n", "e")}
  verified = jose.jws.verify(protected + "." + payload + "." + signature, verification_jwk, "RS256")
  assert(json.loads(verified) == {"a": 1})


def test_decode_jws_protected_header():
  assert(vcon.security.decode_jws_protected_header("") == {})
  encoded = jose.utils.base64url_encode(b'{"alg":"RS256"}').decode("utf-8")
  assert(vcon.security.decode_jws_protected_header(encoded) == {"alg": "RS256"})


def test_merge_jose_headers():
  merged = vcon.security.merge_jose_headers({"alg": "RS256"}, {"x5c": ["a"], "uuid": "u"}, "test")
  assert(merged == {"alg": "RS256", "x5c": ["a"], "uuid": "u"})

  merged = vcon.security.merge_jose_headers({"alg": "RS256"}, {"alg": "RS256", "uuid": "u"}, "test")
  assert(merged == {"alg": "RS256", "uuid": "u"})

  with pytest.raises(ValueError, match = "alg"):
    vcon.security.merge_jose_headers({"alg": "RS256"}, {"alg": "RS512"}, "test")
