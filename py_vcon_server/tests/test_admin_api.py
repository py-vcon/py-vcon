# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
import os
import time
import asyncio
import pytest
import pytest_asyncio
import json
import py_vcon_server
import vcon
import fastapi.testclient

TEST_Q1 = "test_admin_api_q1"
TEST_UUID1 = "fake_uuid1"
TEST_UUID2 = "fake_uuid2"
TEST_JOB1 = { "job_type": "vcon_uuid", "vcon_uuid": [ TEST_UUID1 ] }
TEST_JOB2 = { "job_type": "vcon_uuid", "vcon_uuid": [ TEST_UUID2 ] }
TEST_SERVER_KEY = "test_admin_api:-1:-1:1234"

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

    # Should be not found
    get_response = client.delete(
      "/servers/fooooo",
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 404)

@pytest.mark.asyncio
async def test_server_queue_config():
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    # delete the test queue just in case there is junk from prior tests
    delete_response = client.delete(
      "/server/queue/{}".format(TEST_Q1),
      headers={"accept": "application/json"},
      )
    assert(delete_response.status_code == 200 or
      delete_response.status_code == 404)

    # Add the test queue
    props = {"weight": 5}
    post_response = client.post(
      "/server/queue/{}".format(TEST_Q1),
      json = props,
      headers={"accept": "application/json"},
      )
    assert(post_response.status_code == 204)
    assert(post_response.text == "") 

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
    assert(delete_response.status_code == 204)
    assert(delete_response.text == "") 

    # get the list of queues for this server
    get_response = client.get(
      "/server/queues",
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    server_queues = get_response.json()
    assert(TEST_Q1 not in server_queues)


TEST_Q1 = "test_admin_pau_q1"

@pytest.mark.asyncio
async def test_job_queue():
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    delete_response = client.delete(
      "/queue/{}".format(TEST_Q1),
      headers={"accept": "application/json"},
      )
    # we are cleaning up junk from prior test runs.
    # So this may succeed or fail
    assert(delete_response.status_code == 200 or
      delete_response.status_code == 404)

    if(delete_response.status_code == 404):
      print("delete_response: {}".format(delete_response.json()))
      assert(delete_response.json()["detail"] == "queue: {} not found".format(TEST_Q1))
    else:
      assert(delete_response.status_code == 200)
      assert(isinstance(delete_response.json(), list))

    # get jobs in non existing queue
    get_response = client.get(
      "/queue/{}".format(TEST_Q1),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 404)
    response_json = get_response.json()
    assert(isinstance(response_json, dict))
    assert(response_json["detail"] == "queue: {} not found".format(TEST_Q1))

    # get list of queue names
    get_response = client.get(
      "/queues",
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    queue_list = get_response.json()
    assert(isinstance(queue_list, list))
    # queue does not exist and should not be in the list
    assert(TEST_Q1 not in queue_list)

    # create q1
    post_response = client.post(
      "/queue/{}".format(TEST_Q1),
      headers={"accept": "application/json"},
      )
    assert(post_response.status_code == 204)
    assert(post_response.text == "")

    # Already created
    post_response = client.post(
      "/queue/{}".format(TEST_Q1),
      headers={"accept": "application/json"},
      )
    assert(post_response.status_code == 404)

    # get list of queue names
    get_response = client.get(
      "/queues",
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    queue_list = get_response.json()
    assert(isinstance(queue_list, list))
    # queue does exist and should be in the list
    assert(TEST_Q1 in queue_list)

    # Add a job
    put_response = client.put(
      "/queue/{}".format(TEST_Q1),
      headers={"accept": "application/json"},
      content = json.dumps(TEST_JOB1)
      )
    assert(put_response.status_code == 200)
    queue_position = put_response.json()
    assert(isinstance(queue_position, int) == 1)

    # get the job list
    get_response = client.get(
      "/queue/{}".format(TEST_Q1),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    job_list = get_response.json()
    assert(isinstance(job_list, list))
    assert(len(job_list) == 1)
    assert(len(job_list[0]["vcon_uuid"]) == 1)
    assert(job_list[0]["vcon_uuid"][0] == TEST_UUID1)
    assert(job_list[0]["job_type"] == "vcon_uuid")

    # Add another job
    put_response = client.put(
      "/queue/{}".format(TEST_Q1),
      headers={"accept": "application/json"},
      content = json.dumps(TEST_JOB2)
      )
    assert(put_response.status_code == 200)
    queue_position = put_response.json()
    assert(isinstance(queue_position, int) == 1)

    # get the job list
    get_response = client.get(
      "/queue/{}".format(TEST_Q1),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    job_list = get_response.json()
    assert(isinstance(job_list, list))
    assert(len(job_list) == 2)
    assert(len(job_list[0]["vcon_uuid"]) == 1)
    assert(job_list[0]["vcon_uuid"][0] == TEST_UUID1)
    assert(job_list[0]["job_type"] == "vcon_uuid")
    assert(len(job_list[1]["vcon_uuid"]) == 1)
    assert(job_list[1]["vcon_uuid"][0] == TEST_UUID2)
    assert(job_list[1]["job_type"] == "vcon_uuid")

    # move a job into in progress
    assert(py_vcon_server.queue.JOB_QUEUE is not None)
    # TODO: get a job into in_progress
    # cannot seem to call this here as its using a different async loop
    # in_progress_job_id = await py_vcon_server.queue.JOB_QUEUE.pop_queued_job(TEST_Q1, TEST_SERVER_KEY)
    # assert(isinstance(in_progress_job_id, int))
    # assert(in_progress_job_id > 0)

    # get the job list
    get_response = client.get(
      "/queue/{}".format(TEST_Q1),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    job_list = get_response.json()
    assert(isinstance(job_list, list))
    # TODO
    # verify job2 is in the queue
    # assert(len(job_list) == 1)
    # assert(len(job_list[0]["vcon_uuid"]) == 1)
    # assert(job_list[0]["vcon_uuid"][0] == TEST_UUID2)
    # assert(job_list[0]["job_type"] == "vcon_uuid")

    # TODO
    # verify job1 is in progress

    # TODO
    # requeue the in progress job

    # TODO
    # verify job 1 is first and job 2 is second in the queueu

    # TODO
    # move a job into in progress

    # TODO
    # remove job 1 from in progress

    # delete the queue
    delete_response = client.delete(
      "/queue/{}".format(TEST_Q1),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    job_list = get_response.json()
    assert(isinstance(job_list, list))
    # verify job 1 and 2 are in the queue when the queue was deleted
    assert(len(job_list) == 2)
    assert(len(job_list[0]["vcon_uuid"]) == 1)
    assert(job_list[0]["vcon_uuid"][0] == TEST_UUID1)
    assert(job_list[0]["job_type"] == "vcon_uuid")
    assert(len(job_list[1]["vcon_uuid"]) == 1)
    assert(job_list[1]["vcon_uuid"][0] == TEST_UUID2)
    assert(job_list[1]["job_type"] == "vcon_uuid")

