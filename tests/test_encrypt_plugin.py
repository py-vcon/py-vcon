# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" Unit tests for encrypting filter plugin """
import pytest
import json
import vcon


CA_CERT = "certs/fake_ca_root.crt"
CA2_CERT = "certs/fake_ca2_root.crt"
EXPIRED_CERT = "certs/expired_div.crt"
DIVISION_CERT = "certs/fake_div.crt"
DIVISION_PRIVATE_KEY = "certs/fake_div.key"
GROUP_CERT = "certs/fake_grp.crt"
GROUP_PRIVATE_KEY = "certs/fake_grp.key"

call_data = {
      "epoch" : "1652552179",
      "destination" : "2117",
      "source" : "+19144345359",
      "rfc2822" : "Sat, 14 May 2022 18:16:19 -0000",
      "file_extension" : "WAV",
      "duration" : 94.84,
      "channels" : 1
}


@pytest.fixture(scope="function")
def two_party_tel_vcon() -> vcon.Vcon:
  """ construct vCon with two tel URL """
  vCon = vcon.Vcon()
  first_party = vCon.set_party_parameter("tel", call_data['source'])
  assert(first_party == 0)
  second_party = vCon.set_party_parameter("tel", call_data['destination'])
  assert(second_party == 1)
  return(vCon)



@pytest.mark.asyncio
async def test_encrypt_2party(two_party_tel_vcon : vcon.Vcon) -> None:
  two_party_tel_vcon.set_uuid("vcon.dev")
  uuid = two_party_tel_vcon.uuid
  group_private_key_string = vcon.security.load_string_from_file(GROUP_PRIVATE_KEY)
  group_cert_string = vcon.security.load_string_from_file(GROUP_CERT)
  division_cert_string = vcon.security.load_string_from_file(DIVISION_CERT)
  ca_cert_string = vcon.security.load_string_from_file(CA_CERT)

  sign_options = {
      "private_pem_key": group_private_key_string,
      "cert_chain_pems": [group_cert_string, division_cert_string, ca_cert_string]
    }

  encrypt_options = {
      "private_pem_key": group_cert_string
    }

  assert(two_party_tel_vcon._state == vcon.VconStates.UNSIGNED)
  try:
    await two_party_tel_vcon.encryptfilter(encrypt_options)
    raise Exception("Should have failed for not being signed first")

  except vcon.InvalidVconState as invalid_state:
    # expected
    pass

  two_party_tel_vcon = await two_party_tel_vcon.signfilter(sign_options)
  assert(two_party_tel_vcon._state == vcon.VconStates.SIGNED)
  assert(two_party_tel_vcon.uuid == uuid)

  print("JWS keys: {}".format(two_party_tel_vcon._jws_dict.keys()))
  two_party_tel_vcon = await two_party_tel_vcon.encryptfilter(encrypt_options)
  print(two_party_tel_vcon.dumps())
  assert(two_party_tel_vcon._state == vcon.VconStates.ENCRYPTED)
  print("JWE keys: {}".format(two_party_tel_vcon._jwe_dict.keys()))
  print("JWE unprotected uuid: {}".format(two_party_tel_vcon._jwe_dict["unprotected"]["uuid"]))
  assert(two_party_tel_vcon.uuid == uuid)

  jwe_json_string = two_party_tel_vcon.dumps()
  deserialized_vcon = vcon.Vcon()
  deserialized_vcon.loads(jwe_json_string)
  assert(deserialized_vcon._state == vcon.VconStates.ENCRYPTED)
  assert(deserialized_vcon.uuid == uuid)


 
