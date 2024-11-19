# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" Unit tests for queue job processor """
import pytest
import pytest_asyncio
from common_setup import make_inline_audio_vcon, make_2_party_tel_vcon, UUID
import vcon
import py_vcon_server
from py_vcon_server.settings import VCON_STORAGE_URL


VCON_STORAGE = None
JOB_QUEUE = None

TO_QUEUE_NAME = "proc_test_queue"
FROM_QUEUE_NAME = "pipe_test_queue"

# invoke only once for all the unit test in this module
@pytest_asyncio.fixture(autouse=True)
async def setup():
  """ Setup Vcon storage connection before test """
  vs = py_vcon_server.db.VconStorage.instantiate(VCON_STORAGE_URL)
  global VCON_STORAGE
  VCON_STORAGE = vs

  jq = py_vcon_server.queue.JobQueue(py_vcon_server.settings.QUEUE_DB_URL)
  print("initialized JobQueue connection")
  global JOB_QUEUE
  JOB_QUEUE = jq

  # wait until teardown time
  yield

  # Shutdown the Job Queue and Vcon storage connections after test
  JOB_QUEUE = None
  await jq.shutdown()

  VCON_STORAGE = None
  await vs.shutdown()


@pytest.mark.asyncio
async def test_queue_job_processor(make_2_party_tel_vcon : vcon.Vcon) -> None:
  # Clear the target queue
  try:
    await JOB_QUEUE.delete_queue(TO_QUEUE_NAME)
  except py_vcon_server.queue.QueueDoesNotExist:
    # ok if queue does not exist
    pass

  # Create empty queue
  await JOB_QUEUE.create_new_queue(TO_QUEUE_NAME)

  # Setup inputs
  in_vcon = make_2_party_tel_vcon
  assert(isinstance(in_vcon, vcon.Vcon))

  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(in_vcon, "fake_lock", False) # read/write
  assert(len(proc_input._vcons) == 1)

  queue_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("queue_job")

  queue_options = {
      "queue_name": TO_QUEUE_NAME,
      "from_queue": FROM_QUEUE_NAME
    }
  options = queue_proc_inst.processor_options_class()(**queue_options)

  assert(proc_input.get_queue_job_count() == 0)
  proc_output = await queue_proc_inst.process(proc_input, options)
  assert(proc_output.get_queue_job_count() == 1)

  jobs_queued = await proc_output.commit_queue_jobs(JOB_QUEUE)
  assert(jobs_queued == 1)

  # Verify job got queued
  job_list = await JOB_QUEUE.get_queue_jobs(TO_QUEUE_NAME)
  assert(len(job_list) == 1)
  assert(len(job_list[0]["vcon_uuid"]) == 1)
  assert(job_list[0]["vcon_uuid"][0] == in_vcon.uuid)
  assert(job_list[0]["queue"] == FROM_QUEUE_NAME)

