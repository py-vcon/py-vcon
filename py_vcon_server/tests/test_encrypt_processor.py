# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" Unit tests for encrypting processor """
import json
import pytest
import pytest_asyncio
from common_setup import make_inline_audio_vcon, make_2_party_tel_vcon, UUID
import vcon
import py_vcon_server
import cryptography.x509
from py_vcon_server.settings import VCON_STORAGE_URL
import fastapi.testclient


CA_CERT = "../certs/fake_ca_root.crt"
CA2_CERT = "../certs/fake_ca2_root.crt"
EXPIRED_CERT = "../certs/expired_div.crt"
DIVISION_CERT = "../certs/fake_div.crt"
DIVISION_PRIVATE_KEY = "../certs/fake_div.key"
GROUP_CERT = "../certs/fake_grp.crt"
GROUP_PRIVATE_KEY = "../certs/fake_grp.key"

call_data = {
      "epoch" : "1652552179",
      "destination" : "2117",
      "source" : "+19144345359",
      "rfc2822" : "Sat, 14 May 2022 18:16:19 -0000",
      "file_extension" : "WAV",
      "duration" : 94.84,
      "channels" : 1
}


# invoke only once for all the unit test in this module
@pytest_asyncio.fixture(autouse=True)
async def setup():
  """ Setup Vcon storage connection before test """
  vs = py_vcon_server.db.VconStorage.instantiate(VCON_STORAGE_URL)
  global VCON_STORAGE
  VCON_STORAGE = vs


  # wait until teardown time
  yield

  # Shutdown the Vcon storage after test
  VCON_STORAGE = None
  await vs.shutdown()


@pytest.mark.asyncio
async def test_encrypt_processor(make_2_party_tel_vcon : vcon.Vcon) -> None:
  # Setup inputs
  in_vcon = make_2_party_tel_vcon
  assert(isinstance(in_vcon, vcon.Vcon))
  group_private_key_string = vcon.security.load_string_from_file(GROUP_PRIVATE_KEY)
  group_cert_string = vcon.security.load_string_from_file(GROUP_CERT)
  division_cert_string = vcon.security.load_string_from_file(DIVISION_CERT)
  ca_cert_string = vcon.security.load_string_from_file(CA_CERT)
  ca2_cert_string = vcon.security.load_string_from_file(CA2_CERT)

  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(in_vcon, "fake_lock", False) # read/write
  assert(len(proc_input._vcons) == 1)

  encrypt_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("encrypt")

  sign_options = {
      "private_pem_key": group_private_key_string, 
      "cert_chain_pems": [group_cert_string, division_cert_string, ca_cert_string]
    }

  encrypt_options = {
      "public_pem_key": group_cert_string
    }

  decrypt_options = {
      "private_pem_key": group_private_key_string,
      "public_pem_key": group_cert_string
    }

  assert(in_vcon._state == vcon.VconStates.UNSIGNED)
  try:
    proc_output = await encrypt_proc_inst.process(proc_input, encrypt_options)
    raise Exception("Should have failed for not being signed first")

  except vcon.InvalidVconState as invalid_state:
    # expected
    pass

  sign_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("sign")

  signed_output = await sign_proc_inst.process(proc_input, sign_options)
  out_vcon = await signed_output.get_vcon(0)
  assert(out_vcon._state == vcon.VconStates.SIGNED)

  encrypt_output = await encrypt_proc_inst.process(signed_output, encrypt_options)
  out_vcon = await encrypt_output.get_vcon(0)
  assert(out_vcon._state == vcon.VconStates.ENCRYPTED)
  encrypted_vcon_dict = out_vcon.dumpd()
  assert({"unprotected", "ciphertext"} <= encrypted_vcon_dict.keys())

