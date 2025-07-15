# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" Unit tests for queue job processor """
import pytest
import pytest_asyncio
from common_setup import make_inline_audio_vcon, make_2_party_tel_vcon, UUID
import vcon
import py_vcon_server
from py_vcon_server.settings import VCON_STORAGE_URL
import fastapi.testclient


VCON_STORAGE = None
JOB_QUEUE = None

TO_QUEUE_NAME = "proc_test_queue"
FROM_QUEUE_NAME = "py_vcon_unit_test_queue"

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


@pytest.mark.asyncio
async def test_sign_processor_api(make_2_party_tel_vcon : vcon.Vcon) -> None:
  in_vcon = make_2_party_tel_vcon
  assert(isinstance(in_vcon, vcon.Vcon))

  queue_options = {
      "queue_name": TO_QUEUE_NAME,
      "from_queue": FROM_QUEUE_NAME
    }

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    # clear the queue of residual jobs if it exists.
    delete_response = client.delete(
        "/queue/{}".format(TO_QUEUE_NAME),
        headers={"accept": "application/json"},
      )
    assert(delete_response.status_code in [200, 404])

    # Create the queue (empty)
    post_response = client.post(
      "/queue/{}".format(TO_QUEUE_NAME),
      headers={"accept": "application/json"},
      )
    assert(post_response.status_code == 204)

    # Put the vCon in the DB
    set_response = client.post("/vcon", json = in_vcon.dumpd())
    assert(set_response.status_code == 204)

    parameters = {
        "commit_changes": False,
        "return_whole_vcon": True
      }

    post_response = client.post("/process/{}/queue_job".format(UUID),
        params = parameters,
        json = queue_options
      )
    print("UUID: {}".format(UUID))
    assert(post_response.status_code == 200)
    processor_out_dict = post_response.json()
    assert(len(processor_out_dict["vcons"]) == 1)
    assert(not processor_out_dict["vcons_modified"][0])
    assert(len(processor_out_dict["queue_jobs"]) == 1)
    assert(processor_out_dict["queue_jobs"][0]["vcon_uuids"][0] == in_vcon.uuid)

    # Get the jobs in the queue and verify the new job is in it.
    get_response = client.get(
      "/queue/{}".format(TO_QUEUE_NAME),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    job_list = get_response.json()
    assert(isinstance(job_list, list))
    assert(len(job_list) == 1)
    assert(len(job_list[0]["vcon_uuid"]) == 1)
    assert(job_list[0]["vcon_uuid"][0] == in_vcon.uuid)
    assert(job_list[0]["queue"] == FROM_QUEUE_NAME)


PIPE_QUEUE_JOBS_DICT = {
  "pipeline_options": {
      "timeout": 10.0
    },
  "processors": [
      {
        "processor_name": "jq",
        "processor_options": {
          "jq_queries": {
              "has_dialogs": ".vcons[0].dialog[0].body | length > 0",
              "party0_has_tel": ".vcons[0].parties[0].tel | length > 0"
            }
          }
        },
      {
        "processor_name": "queue_job",
        "processor_options": {
            "format_options": {
                "should_process": "{has_dialogs}"
              },
            "queue_name": TO_QUEUE_NAME + "1",
            "from_queue": FROM_QUEUE_NAME
          }
        },
      {
        "processor_name": "queue_job",
        "processor_options": {
            "format_options": {
                "should_process": "{party0_has_tel}"
              },
            "queue_name": TO_QUEUE_NAME + "2",
            "from_queue": FROM_QUEUE_NAME
          }
        },
      {
        "processor_name": "set_parameters",
        "processor_options": {
            "parameters": {
                "party0_has_email_address": "nobody@example.com"
              }
          }
        }
    ]
}


@pytest.mark.asyncio
async def test_pipeline_queue_job(make_inline_audio_vcon: vcon.Vcon):
  in_vcon = make_inline_audio_vcon
  pipe_name = "unit_test_pipe1"

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    set_response = client.put(
        "/pipeline/{}".format(
          pipe_name
        ),
        json = PIPE_QUEUE_JOBS_DICT,
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

    # delete the queues so that we know they are empty
    delete_response = client.delete(
        "/queue/{}".format(TO_QUEUE_NAME + "1"),
        headers={"accept": "application/json"},
      )
    assert(delete_response.status_code in [200, 404])

    delete_response = client.delete(
        "/queue/{}".format(TO_QUEUE_NAME + "2"),
        headers={"accept": "application/json"},
      )
    assert(delete_response.status_code in [200, 404])

    # Create the queues (empty)
    post_response = client.post(
      "/queue/{}".format(TO_QUEUE_NAME + "1"),
      headers={"accept": "application/json"},
      )
    assert(post_response.status_code == 204)
    post_response = client.post(
      "/queue/{}".format(TO_QUEUE_NAME + "2"),
      headers={"accept": "application/json"},
      )
    assert(post_response.status_code == 204)

    # Put the vCon in the DB
    set_response = client.post("/vcon", json = in_vcon.dumpd())
    assert(set_response.status_code == 204)

    # Run the pipeline on the vCon
    post_response = client.post(
      "/pipeline/{}/run/{}".format(
          pipe_name,
          in_vcon.uuid
        ),
        json = make_inline_audio_vcon.dumpd(),
        params = {
            "save_vcons": False,
            "return_results": True
          },
        headers={"accept": "application/json"},
      )
    pipeline_out_dict = post_response.json()
    print("pipe out: {}".format(pipeline_out_dict))
    assert(post_response.status_code == 200)
    assert(len(pipeline_out_dict["vcons"]) == 1)
    assert(len(pipeline_out_dict["vcons_modified"]) == 1)
    assert(not pipeline_out_dict["vcons_modified"][0])

    # Check the contents of the queues
    get_response = client.get(
      "/queue/{}".format(TO_QUEUE_NAME + "1"),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    job_list = get_response.json()
    assert(isinstance(job_list, list))
    assert(len(job_list) == 1)
    assert(len(job_list[0]["vcon_uuid"]) == 1)
    assert(job_list[0]["vcon_uuid"][0] == in_vcon.uuid)
    assert(job_list[0]["queue"] == FROM_QUEUE_NAME)
    get_response = client.get(
      "/queue/{}".format(TO_QUEUE_NAME + "2"),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    job_list = get_response.json()
    assert(isinstance(job_list, list))
    assert(len(job_list) == 1)
    assert(len(job_list[0]["vcon_uuid"]) == 1)
    assert(job_list[0]["vcon_uuid"][0] == in_vcon.uuid)
    assert(job_list[0]["queue"] == FROM_QUEUE_NAME)

