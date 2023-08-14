import os
import time
import asyncio
import pytest
import pytest_asyncio
import py_vcon_server
import vcon
import fastapi.testclient

TEST_Q1 = "test_admin_api_q1"

@pytest.mark.asyncio
async def test_get_server_info():
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    get_response = client.get(
      "/server/info",
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)

    version_dict = get_response.json()

    assert(version_dict["py_vcon_server"] == py_vcon_server.__version__)
    assert(version_dict["vcon"] == vcon.__version__)
    assert(version_dict["pid"] == os.getpid())
    assert(version_dict["start_time"] <= time.time())
    assert(version_dict["start_time"] > time.time() - 1000)

    get_response = client.get(
      "/servers",
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)

    servers_dict = get_response.json()
    this_server_state = servers_dict[py_vcon_server.states.SERVER_STATE.server_key()]
    assert(this_server_state["pid"] == os.getpid())
    assert(this_server_state["state"] == "running")
    assert(this_server_state["last_heartbeat"] > time.time() - 100)
    assert(this_server_state["last_heartbeat"] < time.time())


@pytest.mark.asyncio
async def test_server_queue_config():
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    # delete the test queue just in case there is junk from prior tests
    delete_response = client.delete(
      "/server/queue/{}".format(TEST_Q1),
      headers={"accept": "application/json"},
      )
    assert(delete_response.status_code == 200)

    # Add the test queue
    props = {"weight": 5}
    post_response = client.post(
      "/server/queue/{}".format(TEST_Q1),
      json = props,
      headers={"accept": "application/json"},
      )
    assert(post_response.status_code == 200)


    # get the list of queues for this server
    get_response = client.get(
      "/server/queues",
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    server_queues = get_response.json()
    assert(isinstance(server_queues, dict))
    assert(TEST_Q1 in server_queues)
    assert(server_queues[TEST_Q1]["weight"] == 5)

    # delete the queue
    delete_response = client.delete(
      "/server/queue/{}".format(TEST_Q1),
      headers={"accept": "application/json"},
      )
    assert(delete_response.status_code == 200)

    # get the list of queues for this server
    get_response = client.get(
      "/server/queues",
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    server_queues = get_response.json()
    assert(TEST_Q1 not in server_queues)


@pytest.mark.asyncio
async def test_job_queue():
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    pass
