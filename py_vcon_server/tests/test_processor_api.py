# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
import asyncio
import pytest
import pytest_asyncio
import py_vcon_server
import vcon
import fastapi.testclient

@pytest.mark.asyncio
async def test_deepgram_processor_api():

  vCon = vcon.Vcon()
  vCon.load("tests/hello.vcon")
  assert(len(vCon.dialog) == 1)
  assert(len(vCon.analysis) == 0)

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    set_response = client.post("/vcon", json=vCon.dumpd())
    assert(set_response.status_code == 204)

    get_response = client.get(
      "/vcon/{}".format(vCon.uuid),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    vcon_dict = get_response.json()
    assert(len(vcon_dict.get("dialog", [])) == 1)
    assert(len(vcon_dict.get("analysis", [])) == 0)

    parameters = {
        "commit_changes": False,
        "return_whole_vcon": True
      }
    options = {
        "language": "en",
        "input_dialogs": "",
        "input_vcon_index": 0
      }
    post_response = client.post("/process/{}/deepgram".format(vCon.uuid),
        params = parameters,
        json = options
      )
    assert(post_response.status_code == 200)
    processor_out_dict = post_response.json()

    # Verify analysis for deepgram
    assert(len(processor_out_dict["vcons"]) == 1)
    assert(len(processor_out_dict["vcons"][0]["analysis"]) == 1)

    # Verify not saved to VconStorage
    get_response = client.get(
      "/vcon/{}".format(vCon.uuid),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    vcon_dict = get_response.json()
    assert(len(vcon_dict.get("dialog", [])) == 1)
    assert(len(vcon_dict.get("analysis", [])) == 0)


    # Test again with commit to VconStorage
    parameters["commit_changes"] = True
    post_response = client.post("/process/{}/deepgram".format(vCon.uuid),
        params = parameters,
        json = options
      )
    assert(post_response.status_code == 200)
    processor_out_dict = post_response.json()



    # Verify saved to VconStorage
    get_response = client.get(
      "/vcon/{}".format(vCon.uuid),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    vcon_dict = get_response.json()
    assert(len(vcon_dict.get("dialog", [])) == 1)
    assert(len(vcon_dict.get("analysis", [])) == 1)

    # Test OpenAI  /process entry point
    post_response = client.post("/process/{}/openai_chat_completion".format(vCon.uuid),
        params = parameters,
        json = options
      )
    assert(post_response.status_code == 200)
    processor_out_dict = post_response.json()

    # Confirm summary analysis exists
    assert(len(processor_out_dict["vcons"]) == 1)
    assert(len(processor_out_dict["vcons"][0]["analysis"]) == 2)
    get_response = client.get(
      "/vcon/{}".format(vCon.uuid),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    vcon_dict = get_response.json()
    assert(len(vcon_dict.get("dialog", [])) == 1)
    assert(len(vcon_dict.get("analysis", [])) == 2)


@pytest.mark.asyncio
async def test_set_parameters_processor_api():

  vCon = vcon.Vcon()
  vCon.load("tests/hello.vcon")
  assert(len(vCon.dialog) == 1)
  assert(len(vCon.analysis) == 0)

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    set_response = client.post("/vcon", json=vCon.dumpd())
    assert(set_response.status_code == 204)

    get_response = client.get(
      "/vcon/{}".format(vCon.uuid),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    vcon_dict = get_response.json()
    assert(len(vcon_dict.get("dialog", [])) == 1)
    assert(len(vcon_dict.get("analysis", [])) == 0)

    api_parameters = {
        "commit_changes": False,
        "return_whole_vcon": True
      }
    options = {
        "language": "en",
        "input_dialogs": "",
        "input_vcon_index": 0,
        "parameters": {
           "fu": "bar",
           "x": 7
          }
      }
    post_response = client.post("/process/{}/set_parameters".format(vCon.uuid),
        params = api_parameters,
        json = options
      )
    assert(post_response.status_code == 200)
    processor_out_dict = post_response.json()

    assert(len(processor_out_dict["vcons"]) == 1)
    assert(len(processor_out_dict["vcons"][0]["dialog"]) == 1)
    assert(len(processor_out_dict["vcons"][0]["analysis"]) == 0)
    assert(processor_out_dict["parameters"]["fu"] == "bar")
    assert(processor_out_dict["parameters"]["x"] == 7)

    # Verify not saved to VconStorage
    get_response = client.get(
      "/vcon/{}".format(vCon.uuid),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    vcon_dict = get_response.json()
    assert(len(vcon_dict.get("dialog", [])) == 1)
    assert(len(vcon_dict.get("analysis", [])) == 0)


@pytest.mark.asyncio
async def test_set_parameters_processor_io_api():

  vCon = vcon.Vcon()
  vCon.load("tests/hello.vcon")
  assert(len(vCon.dialog) == 1)
  assert(len(vCon.analysis) == 0)

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    set_response = client.delete("/vcon/{}".format(vCon.uuid))
    assert(set_response.status_code == 204)

    get_response = client.get(
      "/vcon/{}".format(vCon.uuid),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 404)

    api_parameters = {
        "commit_changes": False,
        "return_whole_vcon": True
      }
    options = {
        "input_dialogs": "",
        "input_vcon_index": 0,
        "parameters": {
           "fu": "bar",
           "x": 7
          }
      }
    processor_input = {
        "processor_io": {
          "vcons": [ vCon.dumpd() ],
          "parameters": {
            "who": "two",
            "fu": "no"
            }
        },
        "processor_options": options
      }
    post_response = client.post("/processIO/set_parameters",
        params = api_parameters,
        json = processor_input
      )
    assert(post_response.status_code == 200)
    processor_out_dict = post_response.json()

    assert(len(processor_out_dict["vcons"]) == 1)
    assert(len(processor_out_dict["vcons"][0]["dialog"]) == 1)
    assert(len(processor_out_dict["vcons"][0]["analysis"]) == 0)
    assert(processor_out_dict["parameters"]["fu"] == "bar")
    assert(processor_out_dict["parameters"]["x"] == 7)
    assert(processor_out_dict["parameters"]["who"] == "two")

    # Verify not saved to VconStorage
    get_response = client.get(
      "/vcon/{}".format(vCon.uuid),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 404)

