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
      "save_vcons": True
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

    # put the vcon in Storage in a known state
    assert(len(make_inline_audio_vcon.dialog) == 1)
    assert(len(make_inline_audio_vcon.analysis) == 0)
    set_response = client.post("/vcon", json = make_inline_audio_vcon.dumpd())
    assert(set_response.status_code == 204)
    assert(make_inline_audio_vcon.uuid == UUID)

    # Create the queue (empty)
    post_response = client.post( 
      "/queue/{}".format(
          WORK_QUEUE
        ),
      headers={"accept": "application/json"},
      )
    assert(post_response.status_code == 204)

    # Create the queue (empty)
    post_response = client.post( 
      "/queue/{}".format(
          ERROR_QUEUE
        ),
      headers={"accept": "application/json"},
      )
    assert(post_response.status_code == 204)

    # Add this vcon as a job in the queue
    queue_job1 = { "job_type": "vcon_uuid", "vcon_uuid": [ UUID ] }
    put_response = client.put(
        "/queue/{}".format(
            WORK_QUEUE
          ),
        headers={"accept": "application/json"},
        content = json.dumps(queue_job1)
      )
    assert(put_response.status_code == 200)
    queue_position = put_response.json()
    assert(queue_position == 1)
    assert(isinstance(queue_position, int) == 1)
    print("test {} queued job: {}".format(
        __file__,
        queue_position
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
    while(trys < 10):
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
      await asyncio.sleep(3.0)

    print("after {} trys".format(trys))
    assert(len(job_list) == 0)

