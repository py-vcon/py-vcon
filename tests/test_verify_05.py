# Copyright (C) 2026 SIPez LLC.  All rights reserved.
"""
Unit tests for verifying signed vCons in the JWS layouts allowed by vCon 0.5.0
(RFC7515): protected header present or absent, alg in either header, and the
certificate chain in x5c, x5u or supplied by the caller.
"""

import io
import json
import sys
import cryptography.exceptions
import jwcrypto.jws
import pytest
import pytest_httpserver
import vcon
import vcon.security
import vcon.utils
import tests.common_utils

CA_CERT = "certs/fake_ca_root.crt"
CA2_CERT = "certs/fake_ca2_root.crt"
DIVISION_CERT = "certs/fake_div.crt"
GROUP_CERT = "certs/fake_grp.crt"
GROUP_PRIVATE_KEY = "certs/fake_grp.key"
CERT_CHAIN = [GROUP_CERT, DIVISION_CERT, CA_CERT]
CHAIN_PATH = "/certs/chain.pem"


def make_vcon() -> vcon.Vcon:
  v = vcon.Vcon()
  v.set_party_parameter("tel", "+15551110000")
  v.set_party_parameter("tel", "+15552220000")
  v.add_text_dialog_inline("Hello", "2022-06-21T13:53:26-04:00", 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.set_uuid("example.com")
  return(v)


def pem_chain() -> bytes:
  """ the PEM certificate chain as served from an x5u URL """
  chain = b""
  for cert_file in CERT_CHAIN:
    with open(cert_file, "rb") as pem_file:
      chain += pem_file.read()
  return(chain)


def sign_layout(protected, header) -> dict:
  """
  Sign a vCon with the given protected (dict or None) and unprotected header
  parameters, as another -05 producer might, in the general JSON serialization.
  """
  v = make_vcon()
  x5c_header, signing_jwk = vcon.security.build_signing_jwk_from_pem_files(GROUP_PRIVATE_KEY, CERT_CHAIN)
  header = {name: (x5c_header["x5c"] if value == "X5C" else value) for name, value in header.items()}
  if(protected is not None):
    protected = {name: (x5c_header["x5c"] if value == "X5C" else value) for name, value in protected.items()}
    protected = json.dumps(protected, separators = (",", ":"))
  jws = jwcrypto.jws.JWS(json.dumps(v.dumpd(), separators = (",", ":")).encode("utf-8"))
  jws.add_signature(signing_jwk, None, protected, header)
  flattened = json.loads(jws.serialize())
  signature = {"signature": flattened["signature"]}
  if("header" in flattened):
    signature["header"] = flattened["header"]
  if("protected" in flattened):
    signature["protected"] = flattened["protected"]
  return({"payload": flattened["payload"], "signatures": [signature]})


def signed_today() -> dict:
  v = make_vcon()
  v.sign(GROUP_PRIVATE_KEY, CERT_CHAIN)
  return(v.dumpd())


def signed_no_protected() -> dict:
  return(sign_layout(None, {"alg": "RS256", "x5c": "X5C"}))


def signed_alg_unprotected() -> dict:
  return(sign_layout({"x5c": "X5C"}, {"alg": "RS256"}))


# x5c must be in the unprotected header in -05, though RFC7515 allows it in
# either; verify accepts both
NOT_05_LAYOUTS = ["alg unprotected, x5c protected"]

LAYOUTS = [
    ("today: alg protected, x5c unprotected", signed_today),
    ("no protected member", signed_no_protected),
    ("alg unprotected, x5c protected", signed_alg_unprotected)
  ]


def load(signed_dict : dict) -> vcon.Vcon:
  signed = vcon.Vcon()
  signed.loadd(signed_dict)
  return(signed)


@pytest.mark.asyncio
@pytest.mark.parametrize("label, make_signed", LAYOUTS)
async def test_layout_verifies(label, make_signed):
  signed_dict = make_signed()
  if(label in NOT_05_LAYOUTS):
    with pytest.raises(AssertionError, match = "not valid against the vCon CDDL"):
      tests.common_utils.assert_valid_cddl(signed_dict)
  else:
    tests.common_utils.assert_valid_cddl(signed_dict)
  signed = load(signed_dict)
  await signed.verify([CA_CERT])
  assert(signed.state == vcon.VconStates.VERIFIED), label
  assert(signed.parties[1]["tel"] == "+15552220000"), label


@pytest.mark.asyncio
@pytest.mark.parametrize("label, make_signed", LAYOUTS)
async def test_layout_wrong_signature_rejected(label, make_signed):
  signed_dict = make_signed()
  signature = bytearray(vcon.utils.base64url_decode(signed_dict["signatures"][0]["signature"]))
  signature[0] ^= 0x01
  signed_dict["signatures"][0]["signature"] = vcon.utils.base64url_encode(bytes(signature))

  signed = load(signed_dict)
  with pytest.raises(jwcrypto.jws.InvalidJWSSignature):
    await signed.verify([CA_CERT])
  assert(signed.state == vcon.VconStates.UNVERIFIED), label


@pytest.mark.asyncio
async def test_no_alg_rejected():
  signed_dict = signed_today()
  del signed_dict["signatures"][0]["protected"]

  with pytest.raises(vcon.InvalidVconSignature, match = r"signature\[0\] has no alg"):
    await load(signed_dict).verify([CA_CERT])


def set_alg_none(signed_dict : dict, where : str) -> dict:
  """ put alg "none" in the given header of the first signature, removing it from the other """
  signature = signed_dict["signatures"][0]
  protected = vcon.security.decode_jws_protected_header(signature.get("protected", None) or "")
  header = signature.get("header", None) or {}
  protected.pop("alg", None)
  header.pop("alg", None)
  if(where == "protected"):
    protected["alg"] = "none"
  else:
    header["alg"] = "none"
  signature["protected"] = vcon.utils.base64url_encode(json.dumps(protected).encode("utf-8")) if(len(protected) > 0) else ""
  signature["header"] = header
  return(signed_dict)


@pytest.mark.asyncio
@pytest.mark.parametrize("where", ["protected", "header"])
async def test_alg_none_rejected(where):
  signed = load(set_alg_none(signed_today(), where))
  with pytest.raises(vcon.InvalidVconSignature, match = r'signature\[0\] has alg "none"'):
    await signed.verify([CA_CERT])
  assert(signed.state == vcon.VconStates.UNVERIFIED)


@pytest.mark.asyncio
async def test_alg_none_rejected_before_x5u_fetch():
  """ an alg "none" signature is refused without fetching its x5u chain """
  signed_dict = signed_today()
  header = signed_dict["signatures"][0]["header"]
  del header["x5c"]
  header["x5u"] = "http://localhost:1/never_fetched.pem"
  signed = load(set_alg_none(signed_dict, "header"))
  with pytest.raises(vcon.InvalidVconSignature, match = 'alg "none"'):
    await signed.verify([CA_CERT], fetch_x5u = True)


@pytest.mark.asyncio
async def test_no_chain_rejected():
  signed_dict = signed_today()
  del signed_dict["signatures"][0]["header"]["x5c"]

  with pytest.raises(vcon.InvalidVconSignature, match = "no x5c or x5u"):
    await load(signed_dict).verify([CA_CERT])


def test_sign_x5u_options():
  v = make_vcon()
  v.sign(GROUP_PRIVATE_KEY, CERT_CHAIN, x5u = "https://example.com/chain.pem")
  header = v.dumpd()["signatures"][0]["header"]
  assert(list(header.keys()) == ["x5c", "x5u", "uuid"])
  assert(header["x5u"] == "https://example.com/chain.pem")

  v = make_vcon()
  v.sign(GROUP_PRIVATE_KEY, CERT_CHAIN, x5u = "https://example.com/chain.pem", include_x5c = False)
  header = v.dumpd()["signatures"][0]["header"]
  assert(list(header.keys()) == ["x5u", "uuid"])

  v = make_vcon()
  with pytest.raises(ValueError, match = "x5c or x5u"):
    v.sign(GROUP_PRIVATE_KEY, CERT_CHAIN, include_x5c = False)
  assert(v.state == vcon.VconStates.UNSIGNED)


def signed_x5u_only(httpserver : pytest_httpserver.HTTPServer) -> dict:
  httpserver.expect_request(CHAIN_PATH).respond_with_data(pem_chain(), content_type = "application/pem-certificate-chain")
  v = make_vcon()
  v.sign(GROUP_PRIVATE_KEY, CERT_CHAIN, x5u = httpserver.url_for(CHAIN_PATH), include_x5c = False)
  return(v.dumpd())


@pytest.mark.asyncio
async def test_x5u_fetch_off_rejected(httpserver : pytest_httpserver.HTTPServer):
  signed = load(signed_x5u_only(httpserver))
  with pytest.raises(vcon.InvalidVconSignature, match = "only available by x5u"):
    await signed.verify([CA_CERT])
  assert(len(httpserver.log) == 0)


@pytest.mark.asyncio
async def test_x5u_fetched(httpserver : pytest_httpserver.HTTPServer):
  signed = load(signed_x5u_only(httpserver))
  await signed.verify([CA_CERT], fetch_x5u = True)
  assert(signed.state == vcon.VconStates.VERIFIED)
  assert(len(httpserver.log) == 1)


@pytest.mark.asyncio
async def test_x5u_supplied_chain(httpserver : pytest_httpserver.HTTPServer):
  signed = load(signed_x5u_only(httpserver))
  await signed.verify([CA_CERT], cert_chain_pem_files = CERT_CHAIN)
  assert(signed.state == vcon.VconStates.VERIFIED)
  # a supplied chain is used in place of fetching
  assert(len(httpserver.log) == 0)


@pytest.mark.asyncio
async def test_x5u_other_ca_rejected(httpserver : pytest_httpserver.HTTPServer):
  signed = load(signed_x5u_only(httpserver))
  with pytest.raises(cryptography.exceptions.InvalidSignature):
    await signed.verify([CA2_CERT], fetch_x5u = True)
  assert(signed.state == vcon.VconStates.UNVERIFIED)


@pytest.mark.asyncio
async def test_x5u_not_a_chain_rejected(httpserver : pytest_httpserver.HTTPServer):
  signed = load(signed_x5u_only(httpserver))
  httpserver.clear()
  httpserver.expect_request(CHAIN_PATH).respond_with_data("not a certificate")
  with pytest.raises(vcon.InvalidVconSignature, match = "could not be fetched from x5u"):
    await signed.verify([CA_CERT], fetch_x5u = True)


@pytest.mark.asyncio
async def test_x5u_unreachable_rejected():
  v = make_vcon()
  # nothing listens on port 1
  v.sign(GROUP_PRIVATE_KEY, CERT_CHAIN, x5u = "http://localhost:1/chain.pem", include_x5c = False)
  with pytest.raises(vcon.InvalidVconSignature, match = "could not be fetched from x5u: http://localhost:1/chain.pem"):
    await load(v.dumpd()).verify([CA_CERT], fetch_x5u = True)


@pytest.mark.asyncio
async def test_verify_filter_fetch_x5u(httpserver : pytest_httpserver.HTTPServer):
  signed_dict = signed_x5u_only(httpserver)

  with pytest.raises(vcon.InvalidVconSignature, match = "only available by x5u"):
    await load(signed_dict).verifyfilter({"allowed_ca_cert_pems": [CA_CERT]})

  verified = await load(signed_dict).verifyfilter({"allowed_ca_cert_pems": [CA_CERT], "fetch_x5u": True})
  assert(verified.state == vcon.VconStates.VERIFIED)


@pytest.mark.asyncio
async def test_cli_verify_fetch_x5u(httpserver : pytest_httpserver.HTTPServer, capsys):
  # Importing vcon.cli here so that we catch any junk stdout which will break the CLI
  import vcon.cli
  signed_json = json.dumps(signed_x5u_only(httpserver))

  sys.stdin = io.StringIO(signed_json)
  with pytest.raises(vcon.InvalidVconSignature, match = "only available by x5u"):
    await vcon.cli.main(["verify", CA_CERT])
  capsys.readouterr()

  sys.stdin = io.StringIO(signed_json)
  await vcon.cli.main(["verify", "--fetch-x5u", CA_CERT])
  out_json, error = capsys.readouterr()
  out_vcon = vcon.Vcon()
  out_vcon.loads(out_json)
  assert(out_vcon.parties[1]["tel"] == "+15552220000")


def test_pem_chain_to_certs():
  chain = pem_chain()
  certs = vcon.security.pem_chain_to_certs(chain)
  assert(len(certs) == 3)
  assert(certs[0] == vcon.security.load_pem_cert(GROUP_CERT)[0])
  assert(certs[2] == vcon.security.load_pem_cert(CA_CERT)[0])
  assert(len(vcon.security.pem_chain_to_certs(chain.decode("utf-8"))) == 3)

  with pytest.raises(ValueError):
    vcon.security.pem_chain_to_certs("not a certificate")
