# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" Unit tests for signing filter plugin """
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
async def test_sign_2party(two_party_tel_vcon : vcon.Vcon) -> None:
  two_party_tel_vcon.set_uuid("vcon.dev")
  group_private_key_string = vcon.security.load_string_from_file(GROUP_PRIVATE_KEY)
  group_cert_string = vcon.security.load_string_from_file(GROUP_CERT)
  division_cert_string = vcon.security.load_string_from_file(DIVISION_CERT)
  ca_cert_string = vcon.security.load_string_from_file(CA_CERT)

  init_options = {
      "private_pem_key": group_private_key_string, 
      "cert_chain_pems": [group_cert_string, division_cert_string, ca_cert_string]
    }

  await two_party_tel_vcon.signfilter(init_options)
  print(two_party_tel_vcon.dumps())
  assert(two_party_tel_vcon._state == vcon.VconStates.SIGNED)

  try:
    await two_party_tel_vcon.signfilter(init_options)
    raise Exception("Should have thrown an exception as this vcon was already signed")

  except vcon.InvalidVconState as already_signed_error:
    if(already_signed_error.args[0].find("should") != -1):
      raise already_signed_error

  try:
    two_party_tel_vcon.verify([ca_cert_string])
    raise Exception("Should have thrown an exception as this vcon was signed locally")

  except vcon.InvalidVconState as locally_signed_error:
    # Expected to get here because vCon was signed locally
    # Its already verified
    if(locally_signed_error.args[0].find("should") != -1):
      raise locally_signed_error

  vcon_json_string = two_party_tel_vcon.dumps()
  #print("Signed vcon: {}".format(vcon_json_string))

  deserialized_signed_vcon = vcon.Vcon()
  deserialized_signed_vcon.loads(vcon_json_string)
  assert(deserialized_signed_vcon._state == vcon.VconStates.UNVERIFIED)
  signed_dict = json.loads(vcon_json_string)
  print("JSW keys: {}".format(signed_dict.keys()))
  assert("payload" in signed_dict)
  assert("signatures" in signed_dict)
  print("sigs keys: {}".format(signed_dict["signatures"][0].keys()))
  assert("header" in signed_dict["signatures"][0])
  assert("signature" in signed_dict["signatures"][0])
  assert("protected" in signed_dict["signatures"][0])
  print("sig keys: {}".format(signed_dict["signatures"][0]["header"].keys()))
  assert(len(signed_dict["signatures"][0]["header"]["x5c"]) == 3)

  deserialized_signed_vcon.verify([ca_cert_string])
  assert(deserialized_signed_vcon._state == vcon.VconStates.VERIFIED)
  assert(len(deserialized_signed_vcon.parties) == 2)
  assert(deserialized_signed_vcon.parties[0]['tel'] == call_data['source'])
  assert(deserialized_signed_vcon.parties[1]['tel'] == call_data['destination'])

