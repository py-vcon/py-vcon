# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
import asyncio
import pytest
import time
import fastapi.testclient
import pytest_asyncio
import py_vcon_server.queue
from py_vcon_server.settings import QUEUE_DB_URL

CREATED_JOBS = []

@pytest_asyncio.fixture()
async def job_queue():
    # Before test
    print("initializing job queue")
    global CREATED_JOBS
    CREATED_JOBS = []
    jq = py_vcon_server.queue.JobQueue(QUEUE_DB_URL)
    print("initialized job queue")
    yield jq

    # after test
    print("shutting down job queue")
    # Clean up junk we left in the in_progress queue
    for job_id in CREATED_JOBS:
      try:
        print("Removing job id: {}".format(job_id))
        await jq.remove_in_progress_job(job_id)
      except py_vcon_server.queue.JobDoesNotExist:
        # Its ok if it was already removed
        pass
    await jq.shutdown()
    print("shutdown job queue")

@pytest.mark.asyncio
async def test_queue_lifecycle(job_queue):
  q1 = "test_queue_1"
  q2 = "test_queue_2"
  try:
    # This is to clean up if queue reminents exist from prior test run
    await job_queue.delete_queue(q1)
  except py_vcon_server.queue.QueueDoesNotExist as e:
    # ignore if delete failed due to queue not existing
    pass
  except Exception as e:
    raise e


  queues = await job_queue.get_queue_names()
  print("queues: {}".format(queues))
  # don't assume this is the process using the queue db
  assert(isinstance(queues, set))
  assert(q1 not in queues)

  num_queues = await job_queue.create_new_queue(q1)
  assert(num_queues >= 1)

  queues = await job_queue.get_queue_names()
  print("queues: {}".format(queues))
  assert(isinstance(queues, set))
  assert(q1 in queues)

  jobs = await job_queue.delete_queue(q1)
  queues = await job_queue.get_queue_names()
  print("queues: {}".format(queues))
  assert(isinstance(queues, set))
  assert(q1 not in queues)
  assert(isinstance(jobs, list))
  assert(len(jobs) == 0)

  uuids = [ "fake_uuid" ]
  try:
    num_jobs = await job_queue.push_vcon_uuid_queue_job(q1, uuids)
    raise Exception("Q1 no longer exist, so expect exception here")
  except py_vcon_server.queue.QueueDoesNotExist as e:
    # expected
    pass
  except Exception as e:
    raise e

  num_queues = await job_queue.create_new_queue(q1)
  assert(num_queues >= 1)

  server_key = "pytest_run:-1:-1:{}".format(time.time())
  try:
    in_progress_job = await job_queue.pop_queued_job(q1, server_key)
    raise Exception("Expect exception as the queue is empty")
  except py_vcon_server.queue.EmptyJobQueue as e:
    pass

  jobs = await job_queue.get_queue_jobs(q1)
  assert(isinstance(jobs, list))
  assert(len(jobs) == 0)

  try:
    num_queues = await job_queue.create_new_queue(q1)
    raise Exception("should get an exception here as q1 queue already exists")
  except Exception as e:
    if("queue already exists" not in str(e)):
      raise e

  num_jobs = await job_queue.push_vcon_uuid_queue_job(q1, uuids)
  assert(num_jobs == 1)

  jobs = await job_queue.get_queue_jobs(q1)
  assert(isinstance(jobs, list))
  assert(len(jobs) == 1)
  assert(jobs[0]["job_type"] == "vcon_uuid")
  assert(jobs[0]["vcon_uuid"] == uuids)

  try:
    num_jobs = await job_queue.push_vcon_uuid_queue_job(q1, [])
    raise Exception("Expect exception here as UUID array should have at least one")
  except Exception as e:
    if("least one UUID" not in str(e)):
      raise e

  uuids2 = [ "fake_uuid2" ]
  num_jobs = await job_queue.push_vcon_uuid_queue_job(q1, uuids2)
  assert(num_jobs == 2)

  jobs = await job_queue.get_queue_jobs(q1)
  assert(isinstance(jobs, list))
  assert(len(jobs) == 2)
  assert(jobs[0]["job_type"] == "vcon_uuid")
  assert(jobs[0]["vcon_uuid"] == uuids)
  assert(jobs[1]["job_type"] == "vcon_uuid")
  assert(jobs[1]["vcon_uuid"] == uuids2)

  in_progress_job = await job_queue.pop_queued_job(q1, server_key)
  CREATED_JOBS.append(in_progress_job["id"])
  first_in_progress_job = in_progress_job
  assert(isinstance(in_progress_job, dict))
  assert(in_progress_job["queue"] == q1)
  assert(in_progress_job["server"] == server_key)
  assert(isinstance(in_progress_job["job"], dict))
  assert(in_progress_job["job"]["job_type"] == "vcon_uuid")
  assert(len(in_progress_job["job"]["vcon_uuid"]) == 1)
  assert(in_progress_job["job"]["vcon_uuid"] == uuids)
  # allow a reasonable slop in time (seconds) between this machine and redis machine
  assert(isinstance(in_progress_job["dequeued"], float))
  assert(abs(time.time() - in_progress_job["dequeued"]) < 1000)

  # This may need to be flexible as other jobs could be happening
  # in the DB while this test is running.
  last_job_id = await job_queue.get_last_job_id()
  assert(last_job_id >= 0)
  assert(int(in_progress_job["id"])  <= last_job_id)

  in_progress_jobs = await job_queue.get_in_progress_jobs()
  assert(isinstance(in_progress_jobs, dict))
  # Cannot assume other jobs are in progress as the DB may be shared
  assert(len(in_progress_jobs) >= 1)
  assert(in_progress_jobs.get(in_progress_job["id"], None) is not None)

  ip_job = in_progress_jobs[in_progress_job["id"]]
  assert(isinstance(ip_job, dict))
  assert(ip_job["queue"] == q1)
  assert(ip_job["server"] == server_key)
  assert(isinstance(ip_job["job"], dict))
  assert(ip_job["job"]["job_type"] == "vcon_uuid")
  assert(len(ip_job["job"]["vcon_uuid"]) == 1)
  assert(ip_job["job"]["vcon_uuid"] == uuids)
  # allow a reasonable slop in time (seconds) between this machine and redis machine
  assert(isinstance(ip_job["dequeued"], float))
  assert(abs(time.time() - ip_job["dequeued"]) < 1000)

  # This may need to be flexible as other jobs could be happening
  # in the DB while this test is running.
  assert(int(ip_job["id"])  <= last_job_id)

  jobs = await job_queue.get_queue_jobs(q1)
  assert(isinstance(jobs, list))
  assert(len(jobs) == 1)
  assert(jobs[0]["job_type"] == "vcon_uuid")
  assert(jobs[0]["vcon_uuid"] == uuids2)

  last_job_id = await job_queue.get_last_job_id()
  bad_job_id = last_job_id + 1111111111
  try:
    await job_queue.requeue_in_progress_job(bad_job_id)
    raise Exception("Expect exception as we gave an invalide job id")
  except py_vcon_server.queue.JobDoesNotExist as e:
    # expected
    pass
  except Exception as e:
    raise e

  queue_names = await job_queue.get_queue_names()
  print("queues: {}".format(queue_names))
  assert(isinstance(queue_names, set))
  assert(q1 in queue_names)

  await job_queue.requeue_in_progress_job(in_progress_job["id"])

  jobs = await job_queue.get_queue_jobs(q1)
  assert(isinstance(jobs, list))
  assert(len(jobs) == 2)
  assert(jobs[0]["job_type"] == "vcon_uuid")
  assert(jobs[0]["vcon_uuid"] == uuids)
  assert(jobs[1]["job_type"] == "vcon_uuid")
  assert(jobs[1]["vcon_uuid"] == uuids2)

  try:
    await job_queue.remove_in_progress_job(in_progress_job["id"])
    raise Exception("should have an exception here as job was pushed back into the queue")
  except py_vcon_server.queue.JobDoesNotExist as e:
    # expected
    pass
  except Exception as e:
    raise e

  try:
    await job_queue.requeue_in_progress_job(in_progress_job["id"])
    raise Exception("should have an exception here as job was pushed back into the queue")
  except py_vcon_server.queue.JobDoesNotExist as e:
    # expected
    pass
  except Exception as e:
    raise e

  in_progress_job = await job_queue.pop_queued_job(q1, server_key)
  CREATED_JOBS.append(in_progress_job["id"])
  second_in_progress_job = in_progress_job
  # Now:
  # q1 had uuids2 job
  # in progress has uuids

  # delete queue out from under job
  jobs = await job_queue.delete_queue(q1)
  # now:
  # q1 is deleted
  # in progress has uuids
  assert(len(jobs) == 1)
  assert(jobs[0]["job_type"] == "vcon_uuid")
  assert(jobs[0]["vcon_uuid"] == uuids2)


  try:
    await job_queue.requeue_in_progress_job(in_progress_job["id"])
    raise Exception("should have an exception here as queue was deleted")
  except py_vcon_server.queue.QueueDoesNotExist as e:
    # expected
    pass
  except Exception as e:
    raise e

  # complete in progress job
  before_in_progress_jobs = await job_queue.get_in_progress_jobs()
  print("num jobs before: {}".format(len(before_in_progress_jobs)))
  assert(in_progress_job["id"] in before_in_progress_jobs)
  await job_queue.remove_in_progress_job(in_progress_job["id"])
  in_progress_jobs = await job_queue.get_in_progress_jobs()
  assert(isinstance(in_progress_jobs, dict))
  # Cannot assume other jobs are in progress as the DB may be shared
  #assert(len(in_progress_jobs) >= 1)
  print("num jobs after: {}".format(len(in_progress_jobs)))
  # Make sure our job was removed
  assert(in_progress_jobs.get(in_progress_job["id"], None) is None)

  # Create the queue again.
  num_queues = await job_queue.create_new_queue(q1)
  # we add a job to the queue
  num_jobs = await job_queue.push_vcon_uuid_queue_job(q1, uuids2)
  assert(num_jobs == 1)
  # make the job in progress
  in_progress_job = await job_queue.pop_queued_job(q1, server_key)
  CREATED_JOBS.append(in_progress_job["id"])
  third_in_progress_job = in_progress_job 
  jobs_before = await job_queue.get_queue_jobs(q1)
  assert(len(jobs_before) == 0)
  # Remove it and make sure it did not get added to the queue
  assert(third_in_progress_job["queue"] == q1)
  await job_queue.remove_in_progress_job(third_in_progress_job["id"])
  jobs_after = await job_queue.get_queue_jobs(q1)
  # Queue should not have changed
  assert(len(jobs_before) == len(jobs_after))
  in_progress_jobs = await job_queue.get_in_progress_jobs()
  # make sure job was removed
  assert(third_in_progress_job["id"] not in in_progress_jobs)

  # TODO:
  # add info logging in JobQueue??

@pytest.mark.asyncio
async def test_in_progress_api(job_queue):

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    q1 = "test_queue_1"

    try:
      # This is to clean up if queue reminents exist from prior test run
      await job_queue.delete_queue(q1)
    except py_vcon_server.queue.QueueDoesNotExist as e:
      # ignore if delete failed due to queue not existing
      pass
    except Exception as e:
      raise e

    # Create new empty queue
    num_queues = await job_queue.create_new_queue(q1)
    assert(num_queues >= 1)

    # Push a job into the queue
    uuids = [ "fake_uuid" ]
    num_jobs = await job_queue.push_vcon_uuid_queue_job(q1, uuids)
    assert(num_jobs == 1)

    server_key = "pytest_run:-1:-1:{}".format(time.time())

    # Move the job from the queue to in_progress
    in_progress_job = await job_queue.pop_queued_job(q1, server_key)
    CREATED_JOBS.append(in_progress_job["id"])
    # Cause the next redis query to fail
    py_vcon_server.db.redis.redis_mgr.FAIL_NEXT = 1
    get_response = client.get(
      "/in_progress",
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 500)

    # Get list of in_progress_jobs
    get_response = client.get(
      "/in_progress",
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    in_progress_dict = get_response.json()
    assert(in_progress_job["id"] in list(in_progress_dict.keys()))
    assert(in_progress_dict[in_progress_job["id"]]["job"]["vcon_uuid"] == uuids)

    # check that the queue is now empty
    get_response = client.get(
      "/queue/{}".format(q1),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    queue_list = get_response.json()
    assert(len(queue_list) == 0)

    # Delete the in_progress job
    get_response = client.delete(
      "/in_progress/{}".format(in_progress_job["id"]),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 204)

    # should fail as its already deleted
    get_response = client.delete(
      "/in_progress/{}".format(in_progress_job["id"]),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 404)


    # check that the queue is now empty
    get_response = client.get(
      "/queue/{}".format(q1),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    queue_list = get_response.json()
    assert(len(queue_list) == 0)

    # Get list of in_progress_jobs
    get_response = client.get(
      "/in_progress",
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    in_progress_dict = get_response.json()
    # Job should no longer be in dict
    assert(in_progress_job["id"] not in list(in_progress_dict.keys()))

    # invalid job id type, should be int
    get_response = client.delete(
      "/in_progress/foo",
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 422)

    # Push a new job into the queue
    uuids = [ "fake_uuid" ]
    num_jobs = await job_queue.push_vcon_uuid_queue_job(q1, uuids)
    assert(num_jobs == 1)

    # Move the job from the queue to in_progress
    in_progress_job = await job_queue.pop_queued_job(q1, server_key)
    CREATED_JOBS.append(in_progress_job["id"])

    # Get list of in_progress_jobs
    get_response = client.get(
      "/in_progress",
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    in_progress_dict = get_response.json()
    assert(in_progress_job["id"] in list(in_progress_dict.keys()))
    assert(in_progress_dict[in_progress_job["id"]]["job"]["vcon_uuid"] == uuids)

    # check that the queue is now empty
    get_response = client.get(
      "/queue/{}".format(q1),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    queue_list = get_response.json()
    assert(len(queue_list) == 0)

    # move the job from in_progress back into the queue
    get_response = client.put(
      "/in_progress/{}".format(in_progress_job["id"]),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 204)

    # Should fail a second time as the job is no longer in_progress
    get_response = client.put(
      "/in_progress/{}".format(in_progress_job["id"]),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 404)


    # check that the job is back in the queue now
    get_response = client.get(
      "/queue/{}".format(q1),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    queue_list = get_response.json()
    assert(len(queue_list) == 1)
    assert(queue_list[0]["vcon_uuid"] == uuids)

    # Get list of in_progress_jobs
    get_response = client.get(
      "/in_progress",
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    in_progress_dict = get_response.json()
    # Job should not be in dict
    assert(in_progress_job["id"] not in list(in_progress_dict.keys()))

    # Move the job from the queue to in_progress
    in_progress_job = await job_queue.pop_queued_job(q1, server_key)
    CREATED_JOBS.append(in_progress_job["id"])

    # Delete the queue
    get_response = client.delete(
      "/queue/{}".format(q1),
      headers={"accept": "application/json"},
      )
    # Should have been empty
    assert(get_response.status_code == 200)
    queue_list = get_response.json()
    assert(len(queue_list) == 0)

    # Get list of in_progress_jobs
    get_response = client.get(
      "/in_progress",
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    in_progress_dict = get_response.json()
    # Job should be in dict
    assert(in_progress_job["id"] in list(in_progress_dict.keys()))

    # Try to move the job from non0existing queue to in_progress
    try:
      in_progress_job = await job_queue.pop_queued_job(q1, server_key)
      raise Exception("Should not get here, queue does not exist")
    except py_vcon_server.queue.QueueDoesNotExist:
      # expected
      pass

    # try to move the job from in_progress back into the not existing queue
    get_response = client.put(
      "/in_progress/{}".format(in_progress_job["id"]),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 404)
    not_found_details = get_response.json()
    print("queue not found details: {}".format(not_found_details))

    # try to move non-existing job from in_progress
    get_response = client.put(
      "/in_progress/{}".format(0),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 404)
    not_found_details = get_response.json()
    print("queue not found details: {}".format(not_found_details))

