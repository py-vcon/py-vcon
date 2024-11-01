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

  verify_options = {"allowed_ca_cert_pems": [ca_cert_string]}

  bad_verify_options = {"allowed_ca_cert_pems": [ca2_cert_string]}

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

  # Create a new clean io object 
  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(encrypted_vcon_dict, "fake_lock", False) # read/write
  assert(len(proc_input._vcons) == 1)

  decrypt_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("decrypt")
  decrypt_output = await decrypt_proc_inst.process(proc_input, decrypt_options)
  out_vcon = await decrypt_output.get_vcon(0)
  assert(out_vcon._state == vcon.VconStates.UNVERIFIED)

  verify_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("verify")
  verify_output = await verify_proc_inst.process(decrypt_output, verify_options)
  out_vcon = await verify_output.get_vcon(0)
  assert(out_vcon._state == vcon.VconStates.VERIFIED)
  assert(out_vcon.uuid == UUID)
  assert(len(out_vcon.parties) == 2)
  assert({"tel"} <= out_vcon.parties[0].keys())
  assert({"tel"} <= out_vcon.parties[1].keys())
  assert(out_vcon.parties[0]["tel"] == "1234")
  assert(out_vcon.parties[1]["tel"] == "5678")
  assert(len(out_vcon.dialog) == 0)
  assert(len(out_vcon.analysis) == 0)


SIGN_PIPE_DEF_DICT = {
  "pipeline_options": {
      "timeout": 33
    },
  "processors": [
      {
        "processor_name": "sign",
        "processor_options": {
          "private_pem_key": vcon.security.load_string_from_file(GROUP_PRIVATE_KEY), 
          "cert_chain_pems": [
              vcon.security.load_string_from_file(GROUP_CERT),
              vcon.security.load_string_from_file(DIVISION_CERT),
              vcon.security.load_string_from_file(CA_CERT)
            ]
          }
      }
    ]
}


ENCRYPT_PIPE_DEF_DICT = {
  "pipeline_options": {
      "timeout": 33
    },
  "processors": [
      {
        "processor_name": "encrypt",
        "processor_options": {
          "public_pem_key": vcon.security.load_string_from_file(GROUP_CERT)
          }
      }
    ]
}


SIGN_ENCRYPT_PIPE_DEF_DICT = {
  "pipeline_options": {
      "timeout": 33
    },
  "processors": [
      {
        "processor_name": "sign",
        "processor_options": {
          "private_pem_key": vcon.security.load_string_from_file(GROUP_PRIVATE_KEY), 
          "cert_chain_pems": [
              vcon.security.load_string_from_file(GROUP_CERT),
              vcon.security.load_string_from_file(DIVISION_CERT),
              vcon.security.load_string_from_file(CA_CERT)
            ]
          }
      },
      {
        "processor_name": "encrypt",
        "processor_options": {
          "public_pem_key": vcon.security.load_string_from_file(GROUP_CERT)
          }
      }
    ]
}


DECRYPT_VERIFY_PIPE_DEF_DICT = {
  "pipeline_options": {
      "timeout": 33
    },
  "processors": [
      {
        "processor_name": "decrypt",
        "processor_options": {
          "private_pem_key": vcon.security.load_string_from_file(GROUP_PRIVATE_KEY), 
          "public_pem_key": vcon.security.load_string_from_file(GROUP_CERT)
          }
      },
      {
        "processor_name": "verify",
        "processor_options":  {
          "allowed_ca_cert_pems": [vcon.security.load_string_from_file(CA_CERT)]
          }
      },
      {
        "processor_name": "jq",
        "processor_options": {
            "jq_queries": {
                "num_vcons": ".vcons | length",
                "num_dialogs": ".vcons[0].dialog | length",
                "num_analysis": ".vcons[0].analysis | length",
                "num_parties": ".vcons[0].parties | length",
                "num_signatures": ".vcons[0].signatures | length",
                "is_three": ".parameters.three == \"three\"",
                "is_four": ".parameters.four == \"four\""
              }
          }
      }
    ]
}


@pytest.mark.asyncio
async def test_encrypt_processor_api(make_2_party_tel_vcon : vcon.Vcon) -> None:
  in_vcon = make_2_party_tel_vcon
  assert(isinstance(in_vcon, vcon.Vcon))
  group_private_key_string = vcon.security.load_string_from_file(GROUP_PRIVATE_KEY)
  group_cert_string = vcon.security.load_string_from_file(GROUP_CERT)
  division_cert_string = vcon.security.load_string_from_file(DIVISION_CERT)
  ca_cert_string = vcon.security.load_string_from_file(CA_CERT)
  ca2_cert_string = vcon.security.load_string_from_file(CA2_CERT)

  sign_options = {
      "private_pem_key": group_private_key_string, 
      "cert_chain_pems": [group_cert_string, division_cert_string, ca_cert_string]
    }

  verify_options = {"allowed_ca_cert_pems": [ca_cert_string]}

  encrypt_options = {
      "public_pem_key": group_cert_string
    }

  decrypt_options = {
      "private_pem_key": group_private_key_string,
      "public_pem_key": group_cert_string
    }

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    # Put the vCon in the DB
    set_response = client.post("/vcon", json = in_vcon.dumpd())
    assert(set_response.status_code == 204)

    parameters = {
        "commit_changes": True,
        "return_whole_vcon": True
      }

    # attempt to encrypt, will fail as it is not signed
    post_response = client.post("/process/{}/encrypt".format(UUID),
        params = parameters,
        json = encrypt_options
      )
    assert(post_response.status_code == 500)
    processor_out_dict = post_response.json()
    print("processor out: {}".format(processor_out_dict))
    assert(processor_out_dict["exception_class"] == "InvalidVconState")

    # sign it and save to DB
    post_response = client.post("/process/{}/sign".format(UUID),
        params = parameters,
        json = sign_options
      )
    assert(post_response.status_code == 200)
    processor_out_dict = post_response.json()
    assert(len(processor_out_dict["vcons"]) == 1)
    assert(processor_out_dict["vcons_modified"][0])
    print("signed vcon: {}".format(processor_out_dict["vcons"][0]))

    # encrypt the signed vCon and save to DB
    post_response = client.post("/process/{}/encrypt".format(UUID),
        params = parameters,
        json = encrypt_options
      )
    assert(post_response.status_code == 200)
    processor_out_dict = post_response.json()
    print("processor out: {}".format(processor_out_dict))
    assert(len(processor_out_dict["vcons"]) == 1)
    assert(processor_out_dict["vcons_modified"][0])
    print("encrypted vcon: {}".format(processor_out_dict["vcons"][0]))
    assert({"unprotected", "recipients", "iv", "ciphertext", "tag"} <= processor_out_dict["vcons"][0].keys())
    encrypted_vcon = vcon.Vcon()
    encrypted_vcon.loadd(processor_out_dict["vcons"][0])
    assert(encrypted_vcon._state == vcon.VconStates.ENCRYPTED)
    assert(encrypted_vcon.uuid == UUID)

    # decrypt the signed vCon and save to DB
    post_response = client.post("/process/{}/decrypt".format(UUID),
        params = parameters,
        json = decrypt_options
      )
    assert(post_response.status_code == 200)
    processor_out_dict = post_response.json()
    print("processor out: {}".format(processor_out_dict))
    assert(len(processor_out_dict["vcons"]) == 1)
    assert(processor_out_dict["vcons_modified"][0])
    print("decrypted vcon: {}".format(processor_out_dict["vcons"][0]))
    assert({"payload", "signatures"} <= processor_out_dict["vcons"][0].keys())
    decrypted_vcon = vcon.Vcon()
    decrypted_vcon.loadd(processor_out_dict["vcons"][0])
    assert(decrypted_vcon._state == vcon.VconStates.UNVERIFIED)
    assert(decrypted_vcon.uuid == UUID)

    # verify the decrypted vCon
    post_response = client.post("/process/{}/verify".format(UUID),
        params = parameters,
        json = verify_options
      )
    assert(post_response.status_code == 200)
    processor_out_dict = post_response.json()
    print("processor out: {}".format(processor_out_dict))
    assert(len(processor_out_dict["vcons"]) == 1)
    assert(processor_out_dict["vcons_modified"][0])
    print("verified vcon: {}".format(processor_out_dict["vcons"][0]))
    # Note: verified vCon gets streamed as a unverified or we lose the signature
    assert({"payload", "signatures"} <= processor_out_dict["vcons"][0].keys())
    verified_vcon = vcon.Vcon()
    verified_vcon.loadd(processor_out_dict["vcons"][0])
    assert(verified_vcon._state == vcon.VconStates.UNVERIFIED)
    assert(verified_vcon.uuid == UUID)


@pytest.mark.asyncio
async def test_encrypt_pipeline(make_inline_audio_vcon: vcon.Vcon):
  pipe_name = "unit_test_pipe1"

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    # Put unsigned vCon in DB
    set_response = client.post("/vcon", json = make_inline_audio_vcon.dumpd())
    assert(set_response.status_code == 204)
    assert(make_inline_audio_vcon.uuid == UUID)

    set_response = client.put(
        "/pipeline/{}".format(
          pipe_name
        ),
        json = ENCRYPT_PIPE_DEF_DICT,
        params = { "validate_processor_options": True}
      )
    resp_content = set_response.content
    if(set_response.status_code != 204):
      print("put: /pipeline/{} returned: {} {}".format(
          pipe_name,
          set_response.status_code,
          resp_content 
        ))
    assert(set_response.status_code == 204)
    assert(len(resp_content) == 0)

    # Attempt to encrypt unsigned vCon, should fail
    post_response = client.post(
      "/pipeline/{}/run/{}".format(
          pipe_name,
          UUID
        ),
        params = {
            "save_vcons": False,
            "return_results": True
          },
        headers={"accept": "application/json"},
      )
    assert(post_response.status_code == 500)
    pipeline_out_dict = post_response.json()
    print("pipe out: {}".format(pipeline_out_dict))
    assert(pipeline_out_dict["exception_class"] == "InvalidVconState")

    set_response = client.put(
        "/pipeline/{}".format(
          pipe_name
        ),
        json = SIGN_ENCRYPT_PIPE_DEF_DICT,
        params = { "validate_processor_options": True}
      )
    resp_content = set_response.content
    if(set_response.status_code != 204):
      print("put: /pipeline/{} returned: {} {}".format(
          pipe_name,
          set_response.status_code,
          resp_content 
        ))
    assert(set_response.status_code == 204)
    assert(len(resp_content) == 0)

    # sign, encrypt and save to the DB
    post_response = client.post(
      "/pipeline/{}/run/{}".format(
          pipe_name,
          UUID
        ),
        params = {
            "save_vcons": True,
            "return_results": True
          },
        headers={"accept": "application/json"},
      )
    assert(post_response.status_code == 200)
    pipeline_out_dict = post_response.json()
    print("pipe out: {}".format(pipeline_out_dict))
    assert(len(pipeline_out_dict["vcons"]) == 1)
    assert(pipeline_out_dict["vcons_modified"][0])
    assert({"unprotected", "ciphertext"} <= pipeline_out_dict["vcons"][0].keys())
    encrypted_vcon = vcon.Vcon()
    encrypted_vcon.loadd(pipeline_out_dict["vcons"][0])
    assert(encrypted_vcon._state == vcon.VconStates.ENCRYPTED)
    assert(encrypted_vcon.uuid == UUID)

    set_response = client.put(
        "/pipeline/{}".format(
          pipe_name
        ),
        json = DECRYPT_VERIFY_PIPE_DEF_DICT,
        params = { "validate_processor_options": True}
      )
    resp_content = set_response.content
    if(set_response.status_code != 204):
      print("put: /pipeline/{} returned: {} {}".format(
          pipe_name,
          set_response.status_code,
          resp_content 
        ))
    assert(set_response.status_code == 204)
    assert(len(resp_content) == 0)

    # decrypt, verify, don't save to the DB
    post_response = client.post(
      "/pipeline/{}/run/{}".format(
          pipe_name,
          UUID
        ),
        params = {
            "save_vcons": False,
            "return_results": True
          },
        headers={"accept": "application/json"},
      )
    assert(post_response.status_code == 200)
    pipeline_out_dict = post_response.json()
    print("pipe out: {}".format(pipeline_out_dict))
    assert(len(pipeline_out_dict["vcons"]) == 1)
    assert(pipeline_out_dict["vcons_modified"][0])
    # Note: we get back a signed/unverified vCon
    assert({"payload", "signatures"} <= pipeline_out_dict["vcons"][0].keys())
    unverified_vcon = vcon.Vcon()
    unverified_vcon.loadd(pipeline_out_dict["vcons"][0])
    assert(unverified_vcon._state == vcon.VconStates.UNVERIFIED)
    assert(unverified_vcon.uuid == UUID)

    assert(pipeline_out_dict["parameters"]["num_vcons"] == 1)
    assert(pipeline_out_dict["parameters"]["num_dialogs"] == 1)
    assert(pipeline_out_dict["parameters"]["num_analysis"] == 0)
    assert(pipeline_out_dict["parameters"]["num_parties"] == 2)
    assert(pipeline_out_dict["parameters"]["is_three"] == False)

