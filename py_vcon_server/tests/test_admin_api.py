# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
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
TEST_JOB2 = { "job_type": "vcon_uuid", "vcon_uuid": [ TEST_UUID2 ], "parameters": {"a": 1, "b": "B"} }
# The current QueueJob model is strict. So to get to the type checking code, we need a vcon_uuid list
TEST_JOB_UNSUPPORTED = { "job_type": "foo", "vcon_uuid": [], "my_stuff": [ TEST_UUID1 ] }
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

    # Cause the next redis lookup to fail
    py_vcon_server.db.redis.redis_mgr.FAIL_NEXT = 1
    get_response = client.get(
      "/servers",
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 500)
    assert(py_vcon_server.db.redis.redis_mgr.FAIL_NEXT == 0)

    # Should succeed this time
    get_response = client.get(
      "/servers",
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)

    servers_dict = get_response.json()
    this_server_state = servers_dict[py_vcon_server.states.SERVER_STATE.server_key()]
    assert(this_server_state["pid"] == os.getpid())
    assert(this_server_state["state"] == "running")
    # last_heartbeat is now per-worker, not top-level
    worker_key = py_vcon_server.states.SERVER_STATE.worker_key()
    assert(worker_key in this_server_state["workers"])
    worker_state = this_server_state["workers"][worker_key]
    assert(worker_state["last_heartbeat"] > time.time() - 100)
    assert(worker_state["last_heartbeat"] < time.time())
    for setting_var in py_vcon_server.settings.STATE_SETTINGS:
      assert(this_server_state["settings"][setting_var] == getattr(py_vcon_server.settings, setting_var, None),
        "setting: {} not expected value".format(setting_var))

    # Try to delete no-existing server state
    get_response = client.delete(
      "/servers/foo",
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 404)

    # Should be not found
    get_response = client.delete(
      "/servers/fooooo",
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 404)


@pytest.mark.asyncio
async def test_delete_server_state_cleans_workers():
  """
  DELETE /servers/{key} (force-delete) should remove the server entry
  and any associated worker entries.  We simulate a stale server by
  writing directly to Redis, then verifying delete cleans it up.
  """
  import json
  import py_vcon_server.states as states

  fake_server_key = "test-host:9999:99999:1234567890.0"
  fake_worker_key = "test-host:9999:99999:1234567890.0:99998"
  workers_set_key = states.SERVER_WORKERS_SET_PREFIX + fake_server_key

  fake_server = {
    "host": "test-host", "port": 9999, "pid": 99999,
    "start_time": 1234567890.0, "state": "running",
    "num_workers": 0, "num_restapi_workers": 1,
    "settings": {}, "workers": {}
  }
  fake_worker = {
    "worker_pid": 99998, "state": "running",
    "last_heartbeat": 1234567890.0
  }

  # Write fake stale entries to Redis before starting TestClient
  redis_mgr = py_vcon_server.db.redis.redis_mgr.RedisMgr(
      py_vcon_server.settings.STATE_DB_URL, "test_delete_workers"
    )
  redis_mgr.create_pool()
  try:
    redis_con = redis_mgr.get_client()
    await redis_con.hset(
        states.SERVER_HASH_KEY, fake_server_key, json.dumps(fake_server)
      )
    await redis_con.sadd(workers_set_key, fake_worker_key)
    await redis_con.hset(
        states.SERVER_WORKER_HASH_KEY, fake_worker_key, json.dumps(fake_worker)
      )

    # Use synchronous TestClient for REST calls
    with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
      # Verify stale entry appears in /servers
      get_response = client.get("/servers")
      assert get_response.status_code == 200
      assert fake_server_key in get_response.json()

      # Force-delete via REST API
      delete_response = client.delete(
          "/servers/{}".format(fake_server_key),
          headers={"accept": "application/json"},
        )
      assert delete_response.status_code == 200
      assert delete_response.json()["workers_deleted"] == 1

      # Verify server entry is gone from /servers
      get_response = client.get("/servers")
      assert get_response.status_code == 200
      assert fake_server_key not in get_response.json()

    # Verify Redis cleanup after TestClient exits (async reads again)
    worker_json = await redis_con.hget(
        states.SERVER_WORKER_HASH_KEY, fake_worker_key
      )
    assert worker_json is None, \
        "Worker entry should have been cleaned up by delete_server_state"

    set_members = await redis_con.smembers(workers_set_key)
    assert len(set_members) == 0, \
        "Worker set should have been deleted"

  finally:
    await redis_mgr.shutdown_pool()


@pytest.mark.asyncio
async def test_old_format_entry_readable_and_deletable():
  """
  Old-format server entries (pre-migration, with last_heartbeat at
  top level and no workers key) should appear in /servers with an
  empty workers dict and be deletable via DELETE /servers/{key}.
  """
  import json
  import py_vcon_server.states as states

  old_key = "old-host:8000:11111:9876543210.0"
  old_entry = {
    "host": "old-host", "port": 8000, "pid": 11111,
    "start_time": 9876543210.0, "state": "running",
    "num_workers": 0, "last_heartbeat": 9876543210.0,
    "settings": {}
    # No "workers" key -- old format
  }

  # Write old-format entry before TestClient
  redis_mgr = py_vcon_server.db.redis.redis_mgr.RedisMgr(
      py_vcon_server.settings.STATE_DB_URL, "test_old_format"
    )
  redis_mgr.create_pool()
  try:
    redis_con = redis_mgr.get_client()
    await redis_con.hset(
        states.SERVER_HASH_KEY, old_key, json.dumps(old_entry)
      )

    with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
      # Should appear in /servers with empty workers dict
      get_response = client.get("/servers")
      assert get_response.status_code == 200
      servers = get_response.json()
      assert old_key in servers
      assert servers[old_key].get("workers", None) == {}, \
          "Old-format entry should have empty workers dict"

      # Should be deletable
      delete_response = client.delete(
          "/servers/{}".format(old_key),
          headers={"accept": "application/json"},
        )
      assert delete_response.status_code == 200
      assert delete_response.json()["workers_deleted"] == 0

      # Should be gone
      get_response = client.get("/servers")
      assert old_key not in get_response.json()

  finally:
    await redis_mgr.shutdown_pool()


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

    # Delete one more time to test not found case
    delete_response = client.delete(
      "/server/queue/{}".format(TEST_Q1),
      headers={"accept": "application/json"},
      )
    assert(delete_response.status_code == 404)

    props = {"weight": 5}

    # Add the test queue
    post_response = client.post(
      "/server/queue/{}".format(TEST_Q1),
      json = props,
      headers={"accept": "application/json"},
      )
    assert(post_response.status_code == 204)
    assert(post_response.text == "") 

    # Cause the next redis query to fail
    #py_vcon_server.db.redis.redis_mgr.FAIL_NEXT = 1
    #get_response = client.get(
    #  "/server/queues",
    #  headers={"accept": "application/json"},
    #  )
    #assert(get_response.status_code == 500)
    #assert(py_vcon_server.db.redis.redis_mgr.FAIL_NEXT == 0)

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
    # Cause the next redis query to fail
    #py_vcon_server.db.redis.redis_mgr.FAIL_NEXT = 1
    #delete_response = client.delete(
    #  "/queue/{}".format(TEST_Q1),
    #  headers={"accept": "application/json"},
    #  )
    #assert(delete_response.status_code == 500)
    #assert(py_vcon_server.db.redis.redis_mgr.FAIL_NEXT == 0)

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

    # Cause next redis query to fail
    #py_vcon_server.db.redis.redis_mgr.FAIL_NEXT = 1
    #get_response = client.get(
    #  "/queue/{}".format(TEST_Q1),
    #  headers={"accept": "application/json"},
    #  )
    #assert(get_response.status_code == 500)
    #assert(py_vcon_server.db.redis.redis_mgr.FAIL_NEXT == 0)

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

    # Try adding the queue again
    post_response = client.post(
      "/queue/{}".format(TEST_Q1),
      headers={"accept": "application/json"},
      )
    error_description = post_response.json()
    #print("add existing error: {}".format(error_description))
    assert(error_description["detail"] == 'queue: {} already exists'.format(TEST_Q1))
    assert(post_response.status_code == 422)

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

    # Try adding an unsupported job type
    put_response = client.put(
      "/queue/{}".format(TEST_Q1),
      headers={"accept": "application/json"},
      json = TEST_JOB_UNSUPPORTED
      )
    put_error = put_response.json()
    try:
      assert(put_response.status_code == 500)
      put_error = put_response.json()
      #assert("bar" in "{}".format(put_error))
      assert("type" in put_error["exception"] or "vcon_uuid" in put_error["exception"])
    except Exception:
      print(f"Unexpected error code: {put_error}")
      raise

    # Add a job
    put_response = client.put(
      "/queue/{}".format(TEST_Q1),
      headers={"accept": "application/json"},
      json = TEST_JOB1
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
      json = TEST_JOB2
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
    assert(len(job_list[1]["parameters"]) == 2)
    assert(job_list[1]["parameters"] == TEST_JOB2["parameters"])

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
    assert(job_list[1]["parameters"] == TEST_JOB2["parameters"])

