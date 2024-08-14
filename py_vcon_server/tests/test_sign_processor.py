# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" Unit tests for signing processor """
import json
import pytest
import pytest_asyncio
from common_setup import make_inline_audio_vcon, make_2_party_tel_vcon, UUID
import vcon
import py_vcon_server
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
async def test_sign_processor(make_2_party_tel_vcon : vcon.Vcon) -> None:
  # Setup inputs
  in_vcon = make_2_party_tel_vcon
  assert(isinstance(in_vcon, vcon.Vcon))
  group_private_key_string = vcon.security.load_string_from_file(GROUP_PRIVATE_KEY)
  group_cert_string = vcon.security.load_string_from_file(GROUP_CERT)
  division_cert_string = vcon.security.load_string_from_file(DIVISION_CERT)
  ca_cert_string = vcon.security.load_string_from_file(CA_CERT)

  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(in_vcon, "fake_lock", False) # read/write
  assert(len(proc_input._vcons) == 1)

  sign_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("sign")

  sign_options = {
      "private_pem_key": group_private_key_string, 
      "cert_chain_pems": [group_cert_string, division_cert_string, ca_cert_string]
    }

  proc_output = await sign_proc_inst.process(proc_input, sign_options)

  out_vcon = await proc_output.get_vcon(0)
  assert(out_vcon._state == vcon.VconStates.SIGNED)

  try:
    no_output = await sign_proc_inst.process(proc_output, sign_options)
    raise Exception("Should have thrown an exception as this vcon was already signed")

  except vcon.InvalidVconState as already_signed_error:
    if(already_signed_error.args[0].find("should") != -1):
      raise already_signed_error

  #verify
  #assert(len(out_vcon.parties) == 2)


@pytest.mark.asyncio
async def test_sign_processor_api(make_2_party_tel_vcon : vcon.Vcon) -> None:
  in_vcon = make_2_party_tel_vcon
  assert(isinstance(in_vcon, vcon.Vcon))
  group_private_key_string = vcon.security.load_string_from_file(GROUP_PRIVATE_KEY)
  group_cert_string = vcon.security.load_string_from_file(GROUP_CERT)
  division_cert_string = vcon.security.load_string_from_file(DIVISION_CERT)
  ca_cert_string = vcon.security.load_string_from_file(CA_CERT)

  sign_options = {
      "private_pem_key": group_private_key_string, 
      "cert_chain_pems": [group_cert_string, division_cert_string, ca_cert_string]
    }

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    # Put the vCon in the DB
    set_response = client.post("/vcon", json = in_vcon.dumpd())
    assert(set_response.status_code == 204)

    parameters = {
        "commit_changes": True,
        "return_whole_vcon": True
      }

    post_response = client.post("/process/{}/sign".format(UUID),
        params = parameters,
        json = sign_options
      )
    print("UUID: {}".format(UUID))
    assert(post_response.status_code == 200)
    processor_out_dict = post_response.json()
    assert(len(processor_out_dict["vcons"]) == 1)
    assert(processor_out_dict["vcons_modified"][0])
    print("signed vcon: {}".format(processor_out_dict["vcons"][0]))


    get_response = client.get(
        "/vcon/{}".format(UUID),
        headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    signed_vcon_dict_from_db = get_response.json()
    print("vcon dict from db: keys:{}".format(signed_vcon_dict_from_db.keys()))
    db_signed_vcon = vcon.Vcon()
    db_signed_vcon.loadd(signed_vcon_dict_from_db)
    assert(db_signed_vcon._state == vcon.VconStates.UNVERIFIED)

