""" Unit tests for Pipeline and related data objects """
import pydantic
import pytest
import pytest_asyncio
import copy
import fastapi.testclient
import vcon
import py_vcon_server.pipeline
from py_vcon_server.settings import PIPELINE_DB_URL
from common_setup import UUID, make_inline_audio_vcon, make_2_party_tel_vcon

PIPELINE_DB = None

@pytest_asyncio.fixture(autouse=True)
async def pipeline_db():
  """ Setup Pipeline DB connection before test """
  print("initializing PipelineDB connection")
  pdb = py_vcon_server.pipeline.PipelineDb(PIPELINE_DB_URL)
  print("initialized PipelineDB connection")
  global PIPELINE_DB
  PIPELINE_DB = pdb

  # wait until teardown time
  yield pdb

  # Shutdown the Vcon storage after test
  print("shutting down PipelineDB connection")
  PIPELINE_DB = None
  await pdb.shutdown()
  print("shutdown PipelineDB connection")

def test_pipeline_objects():

  proc1 = py_vcon_server.pipeline.PipelineProcessor(processor_name = "foo", processor_options = {"a": 3, "b": "abc"})
  print("options: {}".format(proc1.processor_options))
  assert(proc1.processor_name == "foo")
  assert(proc1.processor_options.input_vcon_index == 0)
  assert(proc1.processor_options.a == 3)
  assert(proc1.processor_options.b == "abc")
  assert("b" in proc1.processor_options.__fields_set__)
  assert("c" not in proc1.processor_options.__fields_set__)

  processor_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance(
      "whisper_base"
    )
  whisp_opts = processor_inst.processor_options_class()(**{"output_types": ["vendor"]})
  proc2  = py_vcon_server.pipeline.PipelineProcessor(processor_name = "whisper_base", processor_options = whisp_opts)
  assert(proc2.processor_options.output_types == ["vendor"])

  pipe1_opts = py_vcon_server.pipeline.PipelineOptions(
      save_vcons = False,
      timeout = 30,
      failure_queue = "bad_jobs"
    )

  try:
    py_vcon_server.pipeline.PipelineOptions(
        timeout = "ddd"
      )
    raise Exception("Should raise validation error for timeout not an int")
  except pydantic.error_wrappers.ValidationError as ve:
    # Expected
    #print("ve dir: {}".format(dir(ve)))
    errors_dict = ve.errors()
    #print("error: {}".format(errors_dict[0]))
    assert(errors_dict[0]["loc"][0] == "timeout")
    assert(errors_dict[0]["type"] == "type_error.integer"
      or errors_dict[0]["type"] == "type_error.float")
    assert(errors_dict[1]["loc"][0] == "timeout")
    assert(errors_dict[1]["type"] == "type_error.integer"
      or errors_dict[1]["type"] == "type_error.float")
    print("validation error: {}".format(errors_dict[0]["msg"]))

  pipe1_def = py_vcon_server.pipeline.PipelineDefinition(
      pipeline_options = pipe1_opts,
      processors = [ proc1, proc2 ]
    )

  print("pipe1: {}".format(pipe1_def))

  try:
    py_vcon_server.pipeline.PipelineDefinition(
        pipeline_options = {
            "timeout": "ddd"
          },
        processors = [ proc1, proc2 ]
      )
    raise Exception("Should raise validation error for timeout not an int")
  except pydantic.error_wrappers.ValidationError as ve:
    # Expected
    #print("ve dir: {}".format(dir(ve)))
    errors_dict = ve.errors()
    #print("error: {}".format(errors_dict[0]))
    assert(errors_dict[0]["loc"][0] == "pipeline_options")
    assert(errors_dict[0]["loc"][1] == "timeout")
    assert(errors_dict[0]["type"] == "type_error.integer"
      or errors_dict[0]["type"] == "type_error.float")
    assert(errors_dict[1]["loc"][1] == "timeout")
    assert(errors_dict[1]["type"] == "type_error.integer"
      or errors_dict[1]["type"] == "type_error.float")
    print("validation error: {}".format(errors_dict[0]["msg"]))

  pipe_def_dict = {
    "pipeline_options": {
        "timeout": 33
      },
    "processors": [
        {
          "processor_name": "foo",
          "processor_options": {
              "a": 3,
              "b": "abc"
            }
        },
        {
          "processor_name": "whisper_base",
          "processor_options":  {
              "output_types": ["vendor"]
            }
        }
      ]
  }

  pipe3_def = py_vcon_server.pipeline.PipelineDefinition(**pipe_def_dict)

  assert(pipe3_def.pipeline_options.timeout == 33)
  assert(len(pipe3_def.processors) == 2)
  assert(pipe3_def.processors[0].processor_name == "foo")
  assert(pipe3_def.processors[0].processor_options.a == 3)
  assert(pipe3_def.processors[0].processor_options.b == "abc")
  assert(pipe3_def.processors[1].processor_name == "whisper_base")
  assert(pipe3_def.processors[1].processor_options.output_types == ["vendor"])

PIPE_DEF1_DICT = {
  "pipeline_options": {
      "timeout": 33
    },
  "processors": [
      {
        "processor_name": "foo",
        "processor_options": {
            "a": 3,
            "b": "abc"
          }
      },
      {
        "processor_name": "whisper_base",
        "processor_options":  {
            "output_types": ["vendor"]
          }
      }
    ]
}

test_timeout = 0.1
PIPE_DEF2_DICT = {
  "pipeline_options": {
      "timeout": test_timeout
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
async def test_pipeline_db():

  assert(PIPELINE_DB is not None)

  # Clean up reminents from prior runs
  try:
    await PIPELINE_DB.delete_pipeline("first_pipe")
  except py_vcon_server.pipeline.PipelineNotFound:
    # Ignore as this may have been cleaned up in prior test run
    pass

  await PIPELINE_DB.set_pipeline("first_pipe", PIPE_DEF1_DICT)

  pipe_got = await PIPELINE_DB.get_pipeline("first_pipe")
  assert(pipe_got.pipeline_options.timeout == 33)
  assert(len(pipe_got.processors) == 2)
  assert(pipe_got.processors[0].processor_name == "foo")
  assert(pipe_got.processors[0].processor_options.a == 3)
  assert(pipe_got.processors[0].processor_options.b == "abc")
  assert(pipe_got.processors[1].processor_name == "whisper_base")
  assert(pipe_got.processors[1].processor_options.output_types == ["vendor"])

  pipeline_names = await PIPELINE_DB.get_pipeline_names()
  print("name type: {}".format(type(pipeline_names)))
  # The test DB may be used for other things, so cannot assume only 1 pipeline
  assert("first_pipe" in pipeline_names)

  await PIPELINE_DB.delete_pipeline("first_pipe")

  pipeline_names = await PIPELINE_DB.get_pipeline_names()
  print("name type: {}".format(type(pipeline_names)))
  # The test DB may be used for other things, so cannot assume only 1 pipeline
  assert("first_pipe" not in pipeline_names)

  try:
    await PIPELINE_DB.delete_pipeline("first_pipe")
    raise Exception("Expected delete to fail with not found")
  except py_vcon_server.pipeline.PipelineNotFound:
    # expected as it was already deleted
    pass

  try:
    pipe_got = await PIPELINE_DB.get_pipeline("first_pipe")
    raise Exception("Expected get to fail with not found")
  except py_vcon_server.pipeline.PipelineNotFound:
    # expected as it was already deleted
    pass


@pytest.mark.asyncio
async def test_pipeline_restapi(make_inline_audio_vcon: vcon.Vcon):

  pipe_name = "unit_test_pipe1"
  pipe2_name = "unit_test_pipe2"
  bad_pipe_name = pipe_name + "_bad"
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    # Clean up junk left over from prior tests
    delete_response = client.delete(
        "/pipeline/{}".format(
          pipe_name
        )
      )
    assert(delete_response.status_code == 404 or
      delete_response.status_code == 204)
    delete_response = client.delete(
        "/pipeline/{}".format(
          pipe2_name
        )
      )
    assert(delete_response.status_code == 404 or
      delete_response.status_code == 204)

    get_response = client.get(
        "/pipelines"
      )
    assert(get_response.status_code == 200)
    pipe_list = get_response.json()
    print("pipe list: {}".format(pipe_list))
    assert(isinstance(pipe_list, list))
    assert(not pipe_name in pipe_list)
    assert(not pipe2_name in pipe_list)
    assert(not bad_pipe_name in pipe_list)

    set_response = client.put(
        "/pipeline/{}".format(
          pipe_name
        ),
        json = PIPE_DEF1_DICT, 
        params = { "validate_processor_options": True}
      )
    resp_json = set_response.json()
    print("response content: {}".format(resp_json))
    assert(set_response.status_code == 422)
    assert(resp_json["detail"] == "processor: foo not registered")

    set_response = client.put(
        "/pipeline/{}".format(
          pipe_name
        ),
        json = PIPE_DEF1_DICT,
        params = { "validate_processor_options": False}
      )
    print("response dir: {}".format(dir(set_response)))
    resp_content = set_response.content
    print("response content: {}".format(resp_content))
    assert(set_response.status_code == 204)
    assert(len(resp_content) == 0)
    #assert(resp_json["detail"] == "processor: foo not registered")

    print("PIPE_DEF2: {}".format(PIPE_DEF2_DICT))
    assert(PIPE_DEF2_DICT["pipeline_options"]["timeout"] == test_timeout)
    set_response = client.put(
        "/pipeline/{}".format(
          pipe2_name
        ),
        json = PIPE_DEF2_DICT, 
        params = { "validate_processor_options": True}
      )
    resp_content = set_response.content
    if(set_response.status_code != 204):
      print("put: /pipeline/{} returned: {} {}".format(
          pipe2_name,
          set_response.status_code,
          resp_content 
        ))
    assert(set_response.status_code == 204)
    assert(len(resp_content) == 0)

    get_response = client.get(
        "/pipelines"
      )
    assert(get_response.status_code == 200)
    pipe_list = get_response.json()
    print("pipe list: {}".format(pipe_list))
    assert(isinstance(pipe_list, list))
    assert(pipe_name in pipe_list)
    assert(pipe2_name in pipe_list)
    assert(not bad_pipe_name in pipe_list)

    get_response = client.get(
        "/pipeline/{}".format(
          pipe2_name
      ))
    assert(get_response.status_code == 200)
    pipe2_def_dict = get_response.json()
    assert(pipe2_def_dict["pipeline_options"]["timeout"] == test_timeout)

    get_response = client.get(
        "/pipeline/{}".format(
          bad_pipe_name
        )
      )

    assert(get_response.status_code == 404)

    get_response = client.get(
        "/pipeline/{}".format(
          pipe_name
        )
      )

    assert(get_response.status_code == 200)
    pipe_json = get_response.json()
    pipe_def = py_vcon_server.pipeline.PipelineDefinition(**pipe_json)
    print("got pipeline: {}".format(pipe_json))
    assert(pipe_def.pipeline_options.timeout == 33)
    assert(len(pipe_def.processors) == 2)
    assert(pipe_def.processors[0].processor_name == "foo")
    assert(pipe_def.processors[0].processor_options.a == 3)
    assert(pipe_def.processors[0].processor_options.b == "abc")
    assert(pipe_def.processors[1].processor_name == "whisper_base")
    assert(pipe_def.processors[1].processor_options.output_types == ["vendor"])

    # put the vcon in Storage in a known state
    assert(len(make_inline_audio_vcon.dialog) == 1)
    assert(len(make_inline_audio_vcon.analysis) == 0)
    set_response = client.post("/vcon", json = make_inline_audio_vcon.dumpd())
    assert(set_response.status_code == 204)
    assert(make_inline_audio_vcon.uuid == UUID)

    # Run the pipeline on a simple/small vCon, should timeout
    post_response = client.post(
      "/pipeline/{}/run/{}".format(
          pipe2_name,
          UUID
        ),
        params = {
            "save_vcons": False,
            "return_results": True
          },
        headers={"accept": "application/json"},
      )
    pipeline_out_dict = post_response.json()
    print("pipe out: {}".format(pipeline_out_dict))
    if(post_response.status_code == 200):
      # TODO: this should fail with timeout of 0.1
      assert(len(pipeline_out_dict["vcons"]) == 1)
      assert(len(pipeline_out_dict["vcons_modified"]) == 1)
      assert(pipeline_out_dict["vcons_modified"][0])
      modified_vcon = vcon.Vcon()
      modified_vcon.loadd(pipeline_out_dict["vcons"][0])
      assert(len(modified_vcon.dialog) == 1)
      assert(modified_vcon.dialog[0]["type"] == "recording")
      assert(len(modified_vcon.analysis) == 2)
      assert(modified_vcon.analysis[0]["type"] == "transcript")
      assert(modified_vcon.analysis[0]["vendor"] == "deepgram")
      assert(modified_vcon.analysis[0]["product"] == "transcription")
      assert(modified_vcon.analysis[1]["type"] == "summary")
      assert(modified_vcon.analysis[1]["vendor"] == "openai")
      assert(modified_vcon.analysis[1]["product"] == "ChatCompletion")
    elif(post_response.status_code == 430):
      # pipe_out_dict
      # TODO confirm timeout in error message
      pass
    else:
      assert(post_response.status_code != 200)


    # Give more time so that pipeline does not timeout
    more_time_pipe_dict = copy.deepcopy(PIPE_DEF2_DICT)
    more_time_pipe_dict["pipeline_options"]["timeout"] = 10.0
    assert(more_time_pipe_dict["pipeline_options"]["timeout"] == 10.0)
    set_response = client.put(
        "/pipeline/{}".format(
          pipe2_name
        ),
        json = more_time_pipe_dict, 
        params = { "validate_processor_options": True}
      )
    resp_content = set_response.content
    assert(set_response.status_code == 204)
    assert(len(resp_content) == 0)

    # get and check pipe timeout from DB
    get_response = client.get(
        "/pipeline/{}".format(
          pipe2_name
        )
      )

    assert(get_response.status_code == 200)
    pipe_json = get_response.json()
    pipe_def = py_vcon_server.pipeline.PipelineDefinition(**pipe_json)
    print("got pipeline: {}".format(pipe_json))
    assert(pipe_def.pipeline_options.timeout == 10.0)
    assert(len(pipe_def.processors) == 2)
    assert(pipe_def.processors[0].processor_name == "deepgram")
    assert(len(pipe_def.processors[0].processor_options.dict()) == 1)
    assert(pipe_def.processors[0].processor_options.input_vcon_index == 0)
    assert(pipe_def.processors[1].processor_name == "openai_chat_completion")
    assert(len(pipe_def.processors[1].processor_options.dict()) == 1)
    assert(pipe_def.processors[1].processor_options.input_vcon_index == 0)


    # run again with longer timeout, should succeed this time
    post_response = client.post(
      "/pipeline/{}/run/{}".format(
          pipe2_name,
          UUID
        ),
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
    assert(pipeline_out_dict["vcons_modified"][0])
    modified_vcon = vcon.Vcon()
    modified_vcon.loadd(pipeline_out_dict["vcons"][0])
    assert(len(modified_vcon.dialog) == 1)
    assert(modified_vcon.dialog[0]["type"] == "recording")
    assert(len(modified_vcon.analysis) == 2)
    assert(modified_vcon.analysis[0]["type"] == "transcript")
    assert(modified_vcon.analysis[0]["vendor"] == "deepgram")
    assert(modified_vcon.analysis[0]["product"] == "transcription")
    assert(modified_vcon.analysis[1]["type"] == "summary")
    assert(modified_vcon.analysis[1]["vendor"] == "openai")
    assert(modified_vcon.analysis[1]["product"] == "ChatCompletion")

    # run with vCon in body, should succeed
    post_response = client.post(
      "/pipeline/{}/run".format(
          pipe2_name,
          UUID
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
    assert(pipeline_out_dict["vcons_modified"][0])
    modified_vcon = vcon.Vcon()
    modified_vcon.loadd(pipeline_out_dict["vcons"][0])
    assert(len(modified_vcon.dialog) == 1)
    assert(modified_vcon.dialog[0]["type"] == "recording")
    assert(len(modified_vcon.analysis) == 2)
    assert(modified_vcon.analysis[0]["type"] == "transcript")
    assert(modified_vcon.analysis[0]["vendor"] == "deepgram")
    assert(modified_vcon.analysis[0]["product"] == "transcription")
    assert(modified_vcon.analysis[1]["type"] == "summary")
    assert(modified_vcon.analysis[1]["vendor"] == "openai")
    assert(modified_vcon.analysis[1]["product"] == "ChatCompletion")
    # The pipeline was run with no save of the vCons at the end.
    # Verify that the vCon in Storage did not get updated
    get_response = client.get(
      "/vcon/{}".format(UUID),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    vcon_dict = get_response.json()
    assert(len(vcon_dict["dialog"]) == 1)
    assert(len(vcon_dict["analysis"]) == 0)

    # Run the pipeline again, on a simple/small vCon
    # This time request that the vCon be updated in Storage
    post_response = client.post(
      "/pipeline/{}/run/{}".format(
          pipe2_name,
          UUID
        ),
        params = {
            "save_vcons": True,
            "return_results": False
          },
        headers = {"accept": "application/json"},
      )
    assert(post_response.status_code == 200)
    pipeline_out_dict = post_response.json()
    print("pipe out: {}".format(pipeline_out_dict))
    assert(pipeline_out_dict is None)

    # test commit of vCons after pipeline run
    # Verify that the vCon in Storage DID get updated
    get_response = client.get(
      "/vcon/{}".format(UUID),
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)
    vcon_dict = get_response.json()
    modified_vcon = vcon.Vcon()
    modified_vcon.loadd(vcon_dict)
    assert(len(modified_vcon.dialog) == 1)
    assert(modified_vcon.dialog[0]["type"] == "recording")
    assert(len(modified_vcon.analysis) == 2)
    assert(modified_vcon.analysis[0]["type"] == "transcript")
    assert(modified_vcon.analysis[0]["vendor"] == "deepgram")
    assert(modified_vcon.analysis[0]["product"] == "transcription")
    assert(modified_vcon.analysis[1]["type"] == "summary")
    assert(modified_vcon.analysis[1]["vendor"] == "openai")
    assert(modified_vcon.analysis[1]["product"] == "ChatCompletion")

    # Non existant pipeline
    delete_response = client.delete(
        "/pipeline/{}".format(
          bad_pipe_name
        )
      )
    assert(delete_response.status_code == 404)
    del_json = delete_response.json()
    assert(del_json["detail"] == "pipeline: unit_test_pipe1_bad not found")

    delete_response = client.delete(
        "/pipeline/{}".format(
          pipe_name
        )
      )
    assert(delete_response.status_code == 204)
    assert(len(delete_response.content) == 0)

    delete_response = client.delete(
        "/pipeline/{}".format(
          pipe2_name
        )
      )
    assert(delete_response.status_code == 204)
    assert(len(delete_response.content) == 0)

    get_response = client.get(
        "/pipelines"
      )
    assert(get_response.status_code == 200)
    pipe_list = get_response.json()
    print("pipe list: {}".format(pipe_list))
    assert(isinstance(pipe_list, list))
    assert(not pipe_name in pipe_list)
    assert(not bad_pipe_name in pipe_list)

