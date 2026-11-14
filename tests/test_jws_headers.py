# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" Unit tests for the JWS header parameters of signed vCons """

import json
import subprocess
import sys
import cryptography.exceptions
import jwcrypto.jws
import pytest
import vcon
import vcon.security
import vcon.utils

CA_CERT = "certs/fake_ca_root.crt"
CA2_CERT = "certs/fake_ca2_root.crt"
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
  protected_header = dict(header)
  protected_header["typ"] = "JWT"
  jws = jwcrypto.jws.JWS(json.dumps(v.dumpd(), separators = (",", ":")).encode("utf-8"))
  jws.add_signature(signing_jwk, None, json.dumps(protected_header, separators = (",", ":"), sort_keys = True))
  flattened = json.loads(jws.serialize())
  header["uuid"] = v.uuid
  return({
    "payload": flattened["payload"],
    "signatures": [{"header": header, "signature": flattened["signature"], "protected": flattened["protected"]}]
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
  payload = json.loads(vcon.utils.base64url_decode(signed_dict["payload"]))
  assert(payload["uuid"] == v.uuid)
  assert(payload["sessions"][0]["dialog"] == [0])


@pytest.mark.asyncio
async def test_sign_verify():
  v = make_vcon()
  v.sign(GROUP_PRIVATE_KEY, CERT_CHAIN)

  signed = vcon.Vcon()
  signed.loads(v.dumps())
  await signed.verify([CA_CERT])
  assert(signed.parties[0]["tel"] == "+15551110000")
  assert(signed.sessions[0]["dialog"] == [0])


@pytest.mark.asyncio
async def test_verify_0_4_0_identical_repeats():
  signed_dict = make_0_4_0_signed_dict(make_vcon())
  signature = signed_dict["signatures"][0]
  protected = vcon.security.decode_jws_protected_header(signature["protected"])
  # confirm this is the 0.4.0 form with repeated header parameters
  assert(protected["typ"] == "JWT")
  assert(protected["alg"] == signature["header"]["alg"])
  assert(protected["x5c"] == signature["header"]["x5c"])

  signed = vcon.Vcon()
  signed.loadd(signed_dict)
  await signed.verify([CA_CERT])
  assert(signed.parties[1]["tel"] == "+15552220000")


@pytest.mark.asyncio
async def test_verify_differing_repeats_rejected():
  signed_dict = make_0_4_0_signed_dict(make_vcon())
  signed_dict["signatures"][0]["header"]["alg"] = "RS512"

  signed = vcon.Vcon()
  signed.loadd(signed_dict)
  with pytest.raises(vcon.InvalidVconSignature, match = "alg"):
    await signed.verify([CA_CERT])


def test_signed_payload_bytes():
  """ protected header and payload are encoded exactly as before the switch to jwcrypto """
  v = make_vcon()
  unsigned_dict = v.dumpd()
  v.sign(GROUP_PRIVATE_KEY, CERT_CHAIN)
  signed_dict = v.dumpd()

  assert(set(signed_dict.keys()) == {"payload", "signatures"})
  assert(len(signed_dict["signatures"]) == 1)
  assert(list(signed_dict["signatures"][0].keys()) == ["header", "signature", "protected"])
  assert(signed_dict["signatures"][0]["protected"] == vcon.utils.base64url_encode(b'{"alg":"RS256"}'))
  assert(vcon.utils.base64url_decode(signed_dict["payload"]) ==
    json.dumps(unsigned_dict, separators = (",", ":")).encode("utf-8"))


@pytest.mark.asyncio
async def test_verify_tampered_payload_rejected():
  v = make_vcon()
  v.sign(GROUP_PRIVATE_KEY, CERT_CHAIN)
  signed_dict = v.dumpd()
  payload = json.loads(vcon.utils.base64url_decode(signed_dict["payload"]))
  payload["parties"][0]["tel"] = "+15559990000"
  signed_dict["payload"] = vcon.utils.base64url_encode(json.dumps(payload).encode("utf-8"))

  signed = vcon.Vcon()
  signed.loadd(signed_dict)
  with pytest.raises(jwcrypto.jws.InvalidJWSSignature):
    await signed.verify([CA_CERT])
  assert(signed._state == vcon.VconStates.UNVERIFIED)


@pytest.mark.asyncio
async def test_verify_wrong_ca_rejected():
  v = make_vcon()
  v.sign(GROUP_PRIVATE_KEY, CERT_CHAIN)

  signed = vcon.Vcon()
  signed.loadd(v.dumpd())
  with pytest.raises(cryptography.exceptions.InvalidSignature):
    await signed.verify([CA2_CERT])
  assert(signed._state == vcon.VconStates.UNVERIFIED)


def test_decode_jws_protected_header():
  assert(vcon.security.decode_jws_protected_header("") == {})
  encoded = vcon.utils.base64url_encode(b'{"alg":"RS256"}')
  assert(vcon.security.decode_jws_protected_header(encoded) == {"alg": "RS256"})


def test_merge_jose_headers():
  merged = vcon.security.merge_jose_headers({"alg": "RS256"}, {"x5c": ["a"], "uuid": "u"}, "test")
  assert(merged == {"alg": "RS256", "x5c": ["a"], "uuid": "u"})

  merged = vcon.security.merge_jose_headers({"alg": "RS256"}, {"alg": "RS256", "uuid": "u"}, "test")
  assert(merged == {"alg": "RS256", "uuid": "u"})

  with pytest.raises(ValueError, match = "alg"):
    vcon.security.merge_jose_headers({"alg": "RS256"}, {"alg": "RS512"}, "test")


def test_remove_jws_repeated_headers():
  protected = vcon.utils.base64url_encode(b'{"alg":"RS256","x5c":["a"]}')
  signature = {"protected": protected, "header": {"alg": "RS256", "x5c": ["a"], "uuid": "u"}, "signature": "s"}
  assert(vcon.security.remove_jws_repeated_headers(signature) ==
    {"protected": protected, "header": {"uuid": "u"}, "signature": "s"})
  # the signature passed in is not changed
  assert(signature["header"] == {"alg": "RS256", "x5c": ["a"], "uuid": "u"})

  signature = {"protected": protected, "header": {"alg": "RS256"}, "signature": "s"}
  assert(vcon.security.remove_jws_repeated_headers(signature) == {"protected": protected, "signature": "s"})

  signature = {"header": {"alg": "RS256"}, "signature": "s"}
  assert(vcon.security.remove_jws_repeated_headers(signature) == signature)


def test_import_vcon_does_not_load_jose():
  """ python-jose is no longer used by the vcon package """
  completed = subprocess.run(
    [sys.executable, "-c", "import sys, vcon; print(sorted(m for m in sys.modules if m == 'jose' or m.startswith('jose.')))"],
    capture_output = True,
    text = True,
    check = True
    )
  assert(completed.stdout.strip().splitlines()[-1] == "[]")
