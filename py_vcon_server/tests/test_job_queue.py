import asyncio
import pytest
import time
import pytest_asyncio
import py_vcon_server.queue
from py_vcon_server.settings import QUEUE_DB_URL

@pytest_asyncio.fixture()
async def job_queue():
    # Before test
    print("initializing job queue")
    jq = py_vcon_server.queue.JobQueue(QUEUE_DB_URL)
    print("initialized job queue")
    yield jq

    # after test
    print("shutting down job queue")
    await jq.shutdown()
    print("shutdown job queue")

@pytest.mark.asyncio
async def test_queue_lifecycle(job_queue):
  q1 = "test_queue_1"
  q2 = "test_queue_2"
  try:
    # This is to clean up if queue reminents exist from prior test run
    await job_queue.delete_queue(q1)
  except Exception as e:
    # ignore if delete failed
    if("queue does not exist" not in str(e)):
      raise e


  queues = await job_queue.get_queue_names()
  print("queues: {}".format(queues))
  # don't assume this is the process using the queue db
  assert(q1 not in queues)

  num_queues = await job_queue.create_new_queue(q1)
  assert(num_queues >= 1)

  queues = await job_queue.get_queue_names()
  print("queues: {}".format(queues))
  assert(q1 in queues)

  jobs = await job_queue.delete_queue(q1)
  queues = await job_queue.get_queue_names()
  print("queues: {}".format(queues))
  assert(q1 not in queues)
  assert(isinstance(jobs, list))
  assert(len(jobs) == 0)

  uuids = [ "fake_uuid" ]
  try:
    num_jobs = await job_queue.push_vcon_uuid_queue_job(q1, uuids)
    raise Exception("Q1 no longer exist, so expect exception here")
  except Exception as e:
    if("queue does not exist" not in str(e)):
      raise e

  num_queues = await job_queue.create_new_queue(q1)
  assert(num_queues >= 1)

  server_key = "pytest_run:-1:-1"
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
  assert(isinstance(in_progress_job, dict))
  assert(in_progress_job["queue"] == q1)
  assert(in_progress_job["server"] == server_key)
  assert(isinstance(in_progress_job["job"], dict))
  assert(in_progress_job["job"]["job_type"] == "vcon_uuid")
  assert(len(in_progress_job["job"]["vcon_uuid"]) == 1)
  assert(in_progress_job["job"]["vcon_uuid"] == uuids)
  # allow a reasonable slop in time (seconds) between this machine and redis machine
  assert(isinstance(in_progress_job["start"], float))
  assert(abs(time.time() - in_progress_job["start"]) < 1000)

  # This may need to be flexible as other jobs could be happening
  # in the DB while this test is running.
  last_job_id = await job_queue.get_last_job_id()
  assert(last_job_id >= 0)
  assert(in_progress_job["jobid"]  <= last_job_id)

  in_progress_jobs = await job_queue.get_in_progress_jobs()
  assert(isinstance(in_progress_jobs, dict))
  # Cannot assume other jobs are in progress as the DB may be shared
  assert(len(in_progress_jobs) >= 1)
  assert(in_progress_jobs.get(in_progress_job["jobid"], None) is not None)

  ip_job = in_progress_jobs[in_progress_job["jobid"]]
  assert(isinstance(ip_job, dict))
  assert(ip_job["queue"] == q1)
  assert(ip_job["server"] == server_key)
  assert(isinstance(ip_job["job"], dict))
  assert(ip_job["job"]["job_type"] == "vcon_uuid")
  assert(len(ip_job["job"]["vcon_uuid"]) == 1)
  assert(ip_job["job"]["vcon_uuid"] == uuids)
  # allow a reasonable slop in time (seconds) between this machine and redis machine
  assert(isinstance(ip_job["start"], float))
  assert(abs(time.time() - ip_job["start"]) < 1000)

  # This may need to be flexible as other jobs could be happening
  # in the DB while this test is running.
  assert(ip_job["jobid"]  <= last_job_id)

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
  except Exception as e:
    if("job does not exist" not in str(e)):
      raise e

  queue_names = await job_queue.get_queue_names()
  print("queues: {}".format(queue_names))
  assert(q1 in queue_names)

  await job_queue.requeue_in_progress_job(in_progress_job["jobid"])

  jobs = await job_queue.get_queue_jobs(q1)
  assert(isinstance(jobs, list))
  assert(len(jobs) == 2)
  assert(jobs[0]["job_type"] == "vcon_uuid")
  assert(jobs[0]["vcon_uuid"] == uuids)
  assert(jobs[1]["job_type"] == "vcon_uuid")
  assert(jobs[1]["vcon_uuid"] == uuids2)

  try:
    await job_queue.remove_in_progress_job(in_progress_job["jobid"])
    raise Exception("should have an exception here as job was pushed back into the queue")
  except Exception as e:
    if("job does not exist" not in str(e)):
      raise e

  try:
    await job_queue.requeue_in_progress_job(in_progress_job["jobid"])
    raise Exception("should have an exception here as job was pushed back into the queue")
  except Exception as e:
    if("job does not exist" not in str(e)):
      raise e

  in_progress_job = await job_queue.pop_queued_job(q1, server_key)
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
    await job_queue.requeue_in_progress_job(in_progress_job["jobid"])
    raise Exception("should have an exception here as queue was deleted")
  except Exception as e:
    if("queue: {} does not exist".format(q1) not in str(e)):
      raise e

  # complete in progress job
  await job_queue.remove_in_progress_job(in_progress_job["jobid"])
  in_progress_jobs = await job_queue.get_in_progress_jobs()
  assert(isinstance(in_progress_jobs, dict))
  # Cannot assume other jobs are in progress as the DB may be shared
  assert(len(in_progress_jobs) >= 1)
  # Make sure our job was removed
  assert(in_progress_jobs.get(in_progress_job["jobid"], None) is None)

  # TODO:
  # add info logging in JobQueue??

