# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
import copy
import json
import time
import asyncio
import pytest
import pytest_asyncio
import fastapi.testclient
import logging
import py_vcon_server
import py_vcon_server.settings
from common_setup import UUID, make_inline_audio_vcon, make_2_party_tel_vcon

logger = logging.getLogger(__name__)

SERVER_QUEUES = {
  "test_pipeline_queue_a": {
    "weight": 1
  },
  "test_pipeline_queue_b": {
    "weight": 4
  },
  "test_pipeline_queue_c": {
    "weight": 2
  }
}

WORK_QUEUE = list(SERVER_QUEUES.keys())[1]
ERROR_QUEUE = WORK_QUEUE + "_errors"

TIMEOUT = 30.0
PIPELINE_DEFINITION = {
  "pipeline_options": {
      "timeout": TIMEOUT,
      "save_vcons": True,
      "failure_queue": ERROR_QUEUE
    },
  "processors": [
      {
        "processor_name": "deepgram",
        "processor_options": {
          }
      },
      {
        "processor_name": "openai_chat_completion",
        "processor_options":  {
          }
      }
    ]
}

NUM_JOBS_TO_RUN = 4

@pytest.mark.asyncio
#@pytest.mark.skip(reason="BUG: currently hangs")
async def test_pipeline(make_inline_audio_vcon):
  logger.debug("starting test_pipeline")
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    # delete the test job queues, to clean up any 
    # residual from prior tests
    for q in list(SERVER_QUEUES.keys()) + [ERROR_QUEUE]:
      delete_response = client.delete(
          "/queue/{}".format(q),
          headers={"accept": "application/json"},
        )
      assert(delete_response.status_code in [200, 404])

    # Add the pipeline definition
    set_response = client.put(
        "/pipeline/{}".format(
          WORK_QUEUE
        ),
        json = PIPELINE_DEFINITION,
        params = { "validate_processor_options": True}
      )
    resp_content = set_response.content
    assert(set_response.status_code == 204)

    # put the vcon(s) in Storage in a known state
    for job_count in range(NUM_JOBS_TO_RUN):
      vcon_uuid = "{}-{}".format(UUID, job_count)
      make_inline_audio_vcon._vcon_dict["uuid"] = vcon_uuid
      assert(len(make_inline_audio_vcon.dialog) == 1)
      assert(len(make_inline_audio_vcon.analysis) == 0)
      set_response = client.post("/vcon", json = make_inline_audio_vcon.dumpd())
      assert(set_response.status_code == 204)
      assert(make_inline_audio_vcon.uuid == vcon_uuid)

    # Create the queue (empty)
    post_response = client.post( 
      "/queue/{}".format(
          WORK_QUEUE
        ),
      headers={"accept": "application/json"},
      )
    assert(post_response.status_code == 204)

    # Create the error queue (empty)
    post_response = client.post( 
      "/queue/{}".format(
          ERROR_QUEUE
        ),
      headers={"accept": "application/json"},
      )
    assert(post_response.status_code == 204)

    # Add the vcon(s) as a job in the queue
    for job_count in range(NUM_JOBS_TO_RUN):
      vcon_uuid = "{}-{}".format(UUID, job_count)
      queue_job1 = { "job_type": "vcon_uuid", "vcon_uuid": [ vcon_uuid ] }
      put_response = client.put(
          "/queue/{}".format(
              WORK_QUEUE
            ),
          headers={"accept": "application/json"},
          content = json.dumps(queue_job1)
        )
      assert(put_response.status_code == 200)
      queue_position = put_response.json()
      assert(isinstance(queue_position, int))
      assert(queue_position == 1 + job_count)
      print("test {} queued job: {} vCon uuid: {}".format(
          __file__,
          queue_position,
          vcon_uuid
        ))

    # Enable the work queue on the pipeline server
    post_response = client.post(
        "/server/queue/{}".format(WORK_QUEUE),
        json = SERVER_QUEUES[WORK_QUEUE],
        headers={"accept": "application/json"},
      )
    assert(post_response.status_code == 204)
    assert(post_response.text == "") 

    trys = 0
    while(trys < 8 * NUM_JOBS_TO_RUN):
      trys += 1
      # Check job is not in job queue
      get_response = client.get(
          "/queue/{}".format(
              WORK_QUEUE
            ),
          headers={"accept": "application/json"},
          )
      assert(get_response.status_code == 200)
      job_list = get_response.json()
      assert(isinstance(job_list, list))
      if(len(job_list) == 0):
        break
      print("check #{}, {} jobs still in queue".format(trys, len(job_list)))
      await asyncio.sleep(3.0)

    print("after {} trys".format(trys))
    assert(len(job_list) == 0)

    # check that error queue is empty
    get_response = client.get(
        "/queue/{}".format(
            ERROR_QUEUE
          ),
        headers={"accept": "application/json"},
        )
    assert(get_response.status_code == 200)
    error_list = get_response.json()
    assert(isinstance(error_list, list))
    if(len(error_list) != 0):
      print("{} jobs in error queue: {} jobs: {}".format(len(job_list), ERROR_QUEUE, error_list))
    assert(len(error_list) == 0)

    # check that vCon(s) have transcript and summary
    for job_count in range(NUM_JOBS_TO_RUN):
      vcon_uuid = "{}-{}".format(UUID, job_count)
      get_response = client.get(
        "/vcon/{}".format(vcon_uuid),
        headers={"accept": "application/json"},
        )
      assert(get_response.status_code == 200)
      vcon_dict = get_response.json()
      print("checking vcon: {}".format(vcon_uuid))
      last_wait = 0
      while(job_count == NUM_JOBS_TO_RUN - 1 and len(vcon_dict["analysis"]) < 2):
        # Give the last job time to run and commit
        print("waiting for last job to commit")
        await asyncio.sleep(3.0)
        last_wait += 3.0
        get_response = client.get(
          "/vcon/{}".format(vcon_uuid),
          headers={"accept": "application/json"},
          )
        assert(get_response.status_code == 200)
        vcon_dict = get_response.json()
        if(last_wait > 30):
          break
      print("waited {} sec for last job".format(last_wait))
      assert(len(vcon_dict["analysis"]) == 2)
      assert(vcon_dict["analysis"][0]["type"] == "transcript")
      assert(vcon_dict["analysis"][1]["type"] == "summary")

    # TODO: confirm job id's are not in progress 

