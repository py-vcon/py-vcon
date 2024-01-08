import copy
import json
import pytest
import pytest_asyncio
import fastapi.testclient
import py_vcon_server
from py_vcon_server.settings import PIPELINE_DB_URL, QUEUE_DB_URL, VCON_STORAGE_TYPE, VCON_STORAGE_URL
from common_setup import UUID, make_inline_audio_vcon, make_2_party_tel_vcon


class ItemIterator():
  def __init__(self):
    self.items = {
        "a": 1,
        "b": 4,
        "c": 2
      }
    self.next_items = []

  def item_itr(self):
      for item_index, item_name in enumerate(self.items.keys()):
        for count in range(self.items[item_name]):
          yield(item_name)

  def get_item(self):
    if(len(self.next_items) == 0):
      self.next_items.extend(list(self.item_itr()))

    return(self.next_items.pop(0))


@pytest.mark.asyncio
async def test_item_iterations():
  itr = ItemIterator()

  for test_iteration in range(30):
    item_name = itr.get_item()
    print("item[{}]: {}".format(test_iteration, item_name))

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

PIPELINE_DEFINITION = {
  "pipeline_options": {
      "timeout": 2.0
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

PIPELINE_DB = None
JOB_QUEUE = None
@pytest_asyncio.fixture(autouse=True)
async def set_queue_config():
  await py_vcon_server.db.VconStorage.setup(VCON_STORAGE_TYPE,
    VCON_STORAGE_URL)

  print("caching queue settings")
  saved_config = copy.deepcopy(py_vcon_server.settings.WORK_QUEUES)
  py_vcon_server.settings.WORK_QUEUES = copy.deepcopy(SERVER_QUEUES)
  print("set queue settings")
  """ Setup Pipeline DB connection before test """
  print("initializing PipelineDB connection")
  pdb = py_vcon_server.pipeline.PipelineDb(PIPELINE_DB_URL)
  print("initialized PipelineDB connection")
  global PIPELINE_DB
  PIPELINE_DB = pdb

  print("initializing JobQueue connection")
  jq = py_vcon_server.queue.JobQueue(QUEUE_DB_URL)
  print("initialized JobQueue connection")
  global JOB_QUEUE
  JOB_QUEUE = jq

  await py_vcon_server.db.VconStorage.teardown()
  yield

  py_vcon_server.settings.WORK_QUEUES = saved_config
  print("reset queue settings")

  print("shutting down PipelineDB connection")
  PIPELINE_DB = None
  await pdb.shutdown()
  print("shutdown PipelineDB connection")

  print("shutting down JobQueue connection")
  JOB_QUEUE = None
  await jq.shutdown()
  print("shutdown JobQueue connection")


@pytest.mark.asyncio
async def test_server_queue_iterator():
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    # Add the queues and weights
    # for q in SERVER_QUEUES.keys():
    #   # set each queue weight 
    #   post_response = client.post(
    #       "/server/queue/{}".format(q),
    #       json = SERVER_QUEUES[q],
    #       headers={"accept": "application/json"},
    #     )
    #   assert(post_response.status_code == 204)
    #   assert(post_response.text == "") 

    # initialize the queue iterator
    q_itr = py_vcon_server.queue.QueueIterator()
    assert(len(SERVER_QUEUES.keys()) == 3)

    # get cycle count
    queue_cycles = q_itr.get_cycle_count()
    assert(queue_cycles == 7)

    # iterate a full cycle
    for i in range(20):
      q = q_itr.get_next_queue()
      if(i % queue_cycles == 0):
        assert(q == "test_pipeline_queue_a")
      elif(i % queue_cycles == 1 or
        i % queue_cycles == 2 or
        i % queue_cycles == 3 or
        i % queue_cycles == 4):
        assert(q == "test_pipeline_queue_b")
      elif(i % queue_cycles == 5 or
        i % queue_cycles == 6):
        assert(q == "test_pipeline_queue_c")
      else:
        # Should not get here
        assert(0)

    assert(q_itr.check_update() == False)
    # make a change to server queues
    py_vcon_server.settings.WORK_QUEUES["fff"] = None
    assert(q_itr.check_update() == True)
    queue_cycles = q_itr.get_cycle_count()
    assert(queue_cycles == 8)

    # test if updated
    for i in range(20, 30):
      q = q_itr.get_next_queue()
      if(i % queue_cycles == 0):
        assert(q == "test_pipeline_queue_a")
      elif(i % queue_cycles == 1 or
        i % queue_cycles == 2 or
        i % queue_cycles == 3 or
        i % queue_cycles == 4):
        assert(q == "test_pipeline_queue_b")
      elif(i % queue_cycles == 5 or
        i % queue_cycles == 6):
        assert(q == "test_pipeline_queue_c")
      elif(i % queue_cycles == 7):
        assert(q == "fff")
      else:
        # Should not get here
        assert(0)

    # delete the test server queues
    # for q in SERVER_QUEUES.keys():
    #   delete_response = client.delete(
    #       "/server/queue/{}".format(q),
    #       headers={"accept": "application/json"},
    #     )
    #   assert(delete_response.status_code == 204)


@pytest.mark.asyncio
async def test_pipeline_jobber(make_inline_audio_vcon):
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    # delete the test job queues, to clean up any 
    # residual from prior tests
    for q in SERVER_QUEUES.keys():
      delete_response = client.delete(
          "/queue/{}".format(q),
          headers={"accept": "application/json"},
        )
      assert(delete_response.status_code in [200, 404])

    assert(JOB_QUEUE is not None)
    assert(PIPELINE_DB is not None)

    jobber = py_vcon_server.pipeline.PipelineJobHandler(
        JOB_QUEUE,
        PIPELINE_DB,
        "unit_test_server"
      )

    job = await jobber.get_job()
    # Expect no job as the pipeline is not defined
    assert(job is None)

    # Add the pipeline definition
    set_response = client.put(
        "/pipeline/{}".format(
          list(SERVER_QUEUES.keys())[1]
        ),
        json = PIPELINE_DEFINITION,
        params = { "validate_processor_options": True}
      )
    resp_content = set_response.content
    assert(set_response.status_code == 204)

    job = await jobber.get_job()
    # Still expect no job as the queue does not exist yet
    assert(job is None)

    # Create the queue (empty)
    post_response = client.post( 
      "/queue/{}".format(
          list(SERVER_QUEUES.keys())[1]
        ),
      headers={"accept": "application/json"},
      )
    assert(post_response.status_code == 204)

    job = await jobber.get_job()
    # Still expect no job as the queue is empty
    assert(job is None)

    # put the vcon in Storage in a known state
    assert(len(make_inline_audio_vcon.dialog) == 1)
    assert(len(make_inline_audio_vcon.analysis) == 0)
    set_response = client.post("/vcon", json = make_inline_audio_vcon.dumpd())
    assert(set_response.status_code == 204)
    assert(make_inline_audio_vcon.uuid == UUID)

    # Add this vcon as a job in the queue
    queue_job1 = { "job_type": "vcon_uuid", "vcon_uuid": [ UUID ] }
    put_response = client.put(
        "/queue/{}".format(
            list(SERVER_QUEUES.keys())[1]
          ),
        headers={"accept": "application/json"},
        content = json.dumps(queue_job1)
      )
    assert(put_response.status_code == 200)
    queue_position = put_response.json()
    assert(isinstance(queue_position, int) == 1)


    job = await jobber.get_job()
    # expect to get a job this time
    print("got job: {}".format(job))
    assert(job)

    # TODO:
    # Check that queue job is attached
    assert(isinstance(job["job"], dict))
    assert(job["job"]["job_type"] == "vcon_uuid")
    assert(len(job["job"]["vcon_uuid"]) == 1)
    assert(job["job"]["vcon_uuid"][0] == UUID)
    job_id = job["id"]
    assert(job is not None)
    assert(isinstance(job_id, str))

    # Check that pipeline def is attached
    assert(isinstance(job["pipeline"], dict))
    assert(job["pipeline"]["pipeline_options"]["timeout"] == 2.0)
    assert(len(job["pipeline"]["processors"]) == 2)

    # check that queue is labeled in job
    assert(job["queue"] == list(SERVER_QUEUES.keys())[1])

    # Check job is not in job queue
    get_response = client.get(
        "/queue/{}".format(
            list(SERVER_QUEUES.keys())[1]
          ),
        headers={"accept": "application/json"},
        )
    assert(get_response.status_code == 200)
    job_list = get_response.json()
    assert(isinstance(job_list, list))
    assert(len(job_list) == 0)

    # Check item is in inprogress queue
    get_response = client.get(
        "/in_progress",
        headers={"accept": "application/json"},
        )
    assert(get_response.status_code == 200)
    in_progress_jobs = get_response.json()
    assert(isinstance(in_progress_jobs, dict))
    assert(len(in_progress_jobs) > 0)
    in_progress = in_progress_jobs[job_id]
    assert(in_progress["job"]["job_type"] == "vcon_uuid")
    assert(in_progress["job"]["vcon_uuid"][0] == UUID)

    # confirm no residual analysis
    get_response = client.get(
      "/vcon/{}".format(UUID),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    vcon_dict = get_response.json()
    assert(len(vcon_dict["analysis"]) == 0)

    #TODO:
    # Run a job 
    #job_result = await jobber.do_job(job)

    # Confirm transcript and summary were created
    # get_response = client.get(
    #   "/vcon/{}".format(UUID),
    #   headers={"accept": "application/json"},
    #   )
    # assert(get_response.status_code == 200)
    # vcon_dict = get_response.json()
    # assert(len(vcon_dict["analysis"]) == 2)

    # run finished job

    # confirm job not in queue

    # confirm job not in in_progress list

