import asyncio
import pytest
import pytest_asyncio
import py_vcon_server
import vcon
import fastapi.testclient
from common_setup import UUID, make_2_party_tel_vcon

@pytest.mark.asyncio
async def test_set_get_delete(make_2_party_tel_vcon: vcon.Vcon):
  vCon = await make_2_party_tel_vcon

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    set_response = client.post("/vcon", json=vCon.dumpd())
    assert(set_response.status_code == 200)

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
    assert(delete_response.status_code == 200)

    get2_response = client.get(
      "/vcon/{}".format(UUID),
      headers={"accept": "application/json"},
      )
    assert(get2_response.status_code == 404)

@pytest.mark.asyncio
async def test_jq(make_2_party_tel_vcon: vcon.Vcon):
  vCon = await make_2_party_tel_vcon

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    set_response = client.post("/vcon", json=vCon.dumpd())
    assert(set_response.status_code == 200)

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
  vCon = await make_2_party_tel_vcon

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    set_response = client.post("/vcon", json=vCon.dumpd())
    assert(set_response.status_code == 200)

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

