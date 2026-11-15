# Copyright (C) 2026 SIPez LLC.  All rights reserved.
"""
Signed and encrypted vCon 0.4.0 examples from the draft repository, created
by py-vcon with python-jose, still verify and decrypt.
"""

import os
import pytest
import vcon
import vcon.security
import tests.common_utils

CA_CERT = "certs/fake_ca_root.crt"
GROUP_CERT = "certs/fake_grp.crt"
GROUP_PRIVATE_KEY = "certs/fake_grp.key"
SIGNED = "examples/ab_call_ext_rec_signed.vcon"
ENCRYPTED = "examples/ab_call_ext_rec_encrypted.vcon"
UUID = "01a07da8-c2bb-83e5-b9a2-279e0d16bc46"


@pytest.mark.asyncio
async def test_signed_0_4_0_example_verifies():
  signed_dict = tests.common_utils.load_draft_0_4_0_example(SIGNED)
  # the 0.4.0 signed form is also a valid -05 signed form
  tests.common_utils.assert_valid_cddl(signed_dict)
  signature = signed_dict["signatures"][0]
  protected = vcon.security.decode_jws_protected_header(signature["protected"])
  # the 0.4.0 form: typ JWT, alg and x5c in both headers
  assert(protected["typ"] == "JWT")
  assert(protected["alg"] == signature["header"]["alg"] == "RS256")
  assert(protected["x5c"] == signature["header"]["x5c"])

  signed = vcon.Vcon()
  signed.loadd(signed_dict)
  await signed.verify([CA_CERT])
  assert(signed.uuid == UUID)
  assert([party["name"] for party in signed.parties] == ["Alice", "Bob"])
  assert(signed.dialog[0]["type"] == "recording")


@pytest.mark.asyncio
async def test_encrypted_0_4_0_example_decrypts_and_verifies():
  encrypted_dict = tests.common_utils.load_draft_0_4_0_example(ENCRYPTED)
  # the 0.4.0 encrypted form is also a valid -05 encrypted form
  tests.common_utils.assert_valid_cddl(encrypted_dict)
  # the 0.4.0 form: enc in all three headers
  protected = vcon.security.decode_jws_protected_header(encrypted_dict["protected"])
  assert(protected == {"alg": "RSA-OAEP", "enc": "A256CBC-HS512"})
  assert(encrypted_dict["unprotected"]["enc"] == "A256CBC-HS512")
  assert(encrypted_dict["unprotected"]["cty"] == "application/vcon+json")
  assert(encrypted_dict["recipients"][0]["header"] == {"enc": "A256CBC-HS512"})

  encrypted = vcon.Vcon()
  encrypted.loadd(encrypted_dict)
  encrypted.decrypt(GROUP_PRIVATE_KEY, GROUP_CERT)
  await encrypted.verify([CA_CERT])
  assert(encrypted.uuid == UUID)
  assert([party["name"] for party in encrypted.parties] == ["Alice", "Bob"])


def test_draft_0_4_0_example_cached(monkeypatch, tmp_path):
  downloads = []
  real_download = tests.common_utils.download_file
  def counting_download(url):
    downloads.append(url)
    return(real_download(url))

  monkeypatch.setattr(tests.common_utils, "CACHE_DIR", str(tmp_path))
  monkeypatch.setattr(tests.common_utils, "download_file", counting_download)
  first = tests.common_utils.load_draft_0_4_0_example(SIGNED)
  assert(downloads == [tests.common_utils.DRAFT_URL.format(tests.common_utils.DRAFT_0_4_0_COMMIT, SIGNED)])
  assert(os.listdir(str(tmp_path)) ==
    ["ab_call_ext_rec_signed_{}.vcon".format(tests.common_utils.DRAFT_0_4_0_COMMIT)])

  assert(tests.common_utils.load_draft_0_4_0_example(SIGNED) == first)
  assert(len(downloads) == 1)
