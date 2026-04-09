# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
import asyncio
import pytest
import pytest_asyncio
import py_vcon_server
import vcon
import fastapi.testclient
from common_setup import UUID, make_2_party_tel_vcon

@pytest.mark.asyncio
async def test_set_get_delete(make_2_party_tel_vcon: vcon.Vcon):
  vCon = make_2_party_tel_vcon

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    set_response = client.post("/vcon", json=vCon.dumpd())
    assert(set_response.status_code == 204)

    get_response = client.get(
      "/vcon/{}".format(UUID),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    vcon_dict = get_response.json()
    assert(vcon_dict["parties"][0]["tel"] == "1234")
    assert(vcon_dict["parties"][1]["tel"] == "5678")
    got_vcon = vcon.Vcon()
    got_vcon.loads(get_response.text)
    assert(got_vcon.parties[0]["tel"] == "1234")
    assert(got_vcon.parties[1]["tel"] == "5678")

    delete_response = client.delete("/vcon/{}".format(UUID))
    assert(delete_response.status_code == 204)
    assert(delete_response.text == "")

    get2_response = client.get(
      "/vcon/{}".format(UUID),
      headers={"accept": "application/json"},
      )
    assert(get2_response.status_code == 404)

@pytest.mark.asyncio
async def test_jq(make_2_party_tel_vcon: vcon.Vcon):
  vCon = make_2_party_tel_vcon

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    set_response = client.post("/vcon", json=vCon.dumpd())
    assert(set_response.status_code == 204)

    query = {}
    query["jq_transform"] = ".parties[]"

    jq_response = client.get(
      "/vcon/{}/jq".format(UUID),
      params=query,
      headers={"accept": "application/json"},
      )

    assert(jq_response.status_code == 200)
    query_list = jq_response.json()
    assert(len(query_list) == 2)
    assert(query_list[0]["tel"] == "1234")
    assert(query_list[1]["tel"] == "5678")

@pytest.mark.asyncio
async def test_jsonpath(make_2_party_tel_vcon: vcon.Vcon):
  vCon = make_2_party_tel_vcon

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    set_response = client.post("/vcon", json=vCon.dumpd())
    assert(set_response.status_code == 204)

    query = {}
    query["path_string"] = "$.parties"

    jsonpath_response = client.get(
      "/vcon/{}/jsonpath".format(UUID),
      params=query,
      headers={"accept": "application/json"},
      )

    assert(jsonpath_response.status_code == 200)
    query_list = jsonpath_response.json()[0]
    assert(len(query_list) == 2)
    assert(query_list[0]["tel"] == "1234")
    assert(query_list[1]["tel"] == "5678")

@pytest.mark.asyncio
async def test_post_vcon_missing_uuid():
  """POST /vcon with no UUID set should return validation error"""
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    # Build a minimal vCon dict with the uuid removed
    vcon_dict = {
      "vcon": "0.0.2",
      "uuid": "",
      "created_at": "2024-03-06T20:07:43.000+00:00",
      "parties": [],
      "dialog": [],
      "analysis": [],
      "attachments": []
    }

    post_response = client.post("/vcon", json=vcon_dict)
    assert(post_response.status_code == 422)


@pytest.mark.asyncio
async def test_get_vcon_not_found():
  """GET /vcon/{uuid} for a non-existent UUID should return 404"""
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    get_response = client.get(
      "/vcon/00000000-0000-0000-0000-000000000000",
      headers={"accept": "application/json"},
    )
    assert(get_response.status_code == 404)


@pytest.mark.asyncio
async def test_jq_not_found(make_2_party_tel_vcon: vcon.Vcon):
  """GET /vcon/{uuid}/jq for a non-existent UUID should return 500"""
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    query = {"jq_transform": ".uuid"}
    jq_response = client.get(
      "/vcon/00000000-0000-0000-0000-000000000000/jq",
      params=query,
      headers={"accept": "application/json"},
    )
    assert(jq_response.status_code == 404)


@pytest.mark.asyncio
async def test_jsonpath_not_found():
  """GET /vcon/{uuid}/jsonpath for a non-existent UUID should return 500"""
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    query = {"path_string": "$.uuid"}
    jsonpath_response = client.get(
      "/vcon/00000000-0000-0000-0000-000000000000/jsonpath",
      params=query,
      headers={"accept": "application/json"},
    )
    assert(jsonpath_response.status_code == 404)


@pytest.mark.asyncio
async def test_delete_vcon_not_found():
  """DELETE /vcon/{uuid} for a non-existent UUID should return 204 (idempotent)"""
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    delete_response = client.delete("/vcon/00000000-0000-0000-0000-000000000000")
    # Redis delete of non-existent key is not an error
    assert(delete_response.status_code == 204)

