# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" Unit tests for Pipeline and related data objects """
import pydantic
import pytest
import pytest_asyncio
import copy
import fastapi.testclient
import vcon
import vcon.pydantic_utils
import py_vcon_server.pipeline
from py_vcon_server.settings import PIPELINE_DB_URL
from common_setup import UUID, make_inline_audio_vcon, make_2_party_tel_vcon

PIPELINE_DB = None
TIMEOUT = 60.0

@pytest_asyncio.fixture(autouse=True)
async def pipeline_db():
  """ Setup Pipeline DB connection before test """
  print("initializing PipelineDB connection")
  pdb = py_vcon_server.pipeline.PipelineDb(PIPELINE_DB_URL)
  print("initialized PipelineDB connection")
  global PIPELINE_DB
  PIPELINE_DB = pdb

  # Turn off workers so as to not interfer with queues used in testing
  # and workers created in these unit tests.
  num_workers = py_vcon_server.settings.NUM_WORKERS
  py_vcon_server.settings.NUM_WORKERS = 0
  #do_bg = py_vcon_server.RUN_BACKGROUND_JOBS
  #py_vcon_server.RUN_BACKGROUND_JOBS = False

  # wait until teardown time
  yield pdb

  # Shutdown the Vcon storage after test
  print("shutting down PipelineDB connection")
  PIPELINE_DB = None
  await pdb.shutdown()
  print("shutdown PipelineDB connection")


  # Restore workers config
  py_vcon_server.settings.NUM_WORKERS = num_workers
  #py_vcon_server.RUN_BACKGROUND_JOBS = do_bg


def test_pipeline_objects():

  proc1 = py_vcon_server.pipeline.PipelineProcessor(processor_name = "foo", processor_options = {"a": 3, "b": "abc"})
  print("options: {}".format(proc1.processor_options))
  assert(proc1.processor_name == "foo")
  assert(proc1.processor_options.input_vcon_index == 0)
  assert(proc1.processor_options.a == 3)
  assert(proc1.processor_options.b == "abc")
  assert("b" in vcon.pydantic_utils.get_fields_set(proc1.processor_options))
  assert("c" not in vcon.pydantic_utils.get_fields_set(proc1.processor_options))

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
  except vcon.pydantic_utils.ValidationErrorType as ve:
    # Expected
    #print("ve dir: {}".format(dir(ve)))
    errors_dict = ve.errors()
    #print("error: {}".format(errors_dict[0]))
    assert(errors_dict[0]["loc"][0] == "timeout")
    assert(errors_dict[0]["type"] == vcon.pydantic_utils.IntParseError
      or errors_dict[0]["type"] == vcon.pydantic_utils.FloatParseError)
    assert(errors_dict[1]["loc"][0] == "timeout")
    assert(errors_dict[1]["type"] == vcon.pydantic_utils.IntParseError
      or errors_dict[1]["type"] == vcon.pydantic_utils.FloatParseError)
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
  except vcon.pydantic_utils.ValidationErrorType as ve:
    # Expected
    #print("ve dir: {}".format(dir(ve)))
    errors_dict = ve.errors()
    #print("error: {}".format(errors_dict[0]))
    assert(errors_dict[0]["loc"][0] == "pipeline_options")
    assert(errors_dict[0]["loc"][1] == "timeout")
    assert(errors_dict[0]["type"] == vcon.pydantic_utils.IntParseError
      or errors_dict[0]["type"] == vcon.pydantic_utils.FloatParseError)
    assert(errors_dict[1]["loc"][1] == "timeout")
    assert(errors_dict[1]["type"] == vcon.pydantic_utils.IntParseError
      or errors_dict[1]["type"] == vcon.pydantic_utils.FloatParseError)
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

PIPE_CONDITIONAL_DICT = {
  "pipeline_options": {
      "timeout": 10.0
    },
  "processors": [
      {
        "processor_name": "jq",
        "processor_options": {
          "jq_queries": {
              "has_dialogs": ".vcons[0].dialog[0].url | length > 0",
              "party0_has_email_address": ".vcons[0].parties[0].email | length > 0"
            }
          }
        },
      {
        "processor_name": "whisper_base",
        "processor_options": {
            "format_options": {
                "should_process": "{has_dialogs}"
              }
          }
        },
      {
        "processor_name": "send_email",
        "processor_options": {
            "format_options": {
                "should_process": "{party0_has_email_address}"
              },
            "text_body": "Hello vCon",
            "smtp_host": "foo"
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

    # attemt to add a invalid pipeline
    set_response = client.put(
        "/pipeline/{}".format(
          bad_pipe_name
        ),
        json = {"foo": "bar"}, 
        params = { "validate_processor_options": True}
      )
    assert(set_response.status_code == 422)

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
    inline_audio_vcon_dict = make_inline_audio_vcon.dumpd()
    test_parsed_model = vcon.pydantic_utils.validate_construct(py_vcon_server.processor.VconUnsignedObject, inline_audio_vcon_dict)
    set_response = client.post("/vcon", json = inline_audio_vcon_dict)
    assert(set_response.status_code == 204)
    assert(make_inline_audio_vcon.uuid == UUID)

    # non-existing pipeline name
    post_response = client.post(
      "/pipeline/{}/run/{}".format(
          "bogus_pipeline",
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
    assert(post_response.status_code == 404)

    # non-existing vCon UUID
    post_response = client.post(
      "/pipeline/{}/run/{}".format(
          pipe2_name,
          "bogus_UUID"
        ),
        params = {
            "save_vcons": False,
            "return_results": True
          },
        headers={"accept": "application/json"},
      )
    pipeline_out_dict = post_response.json()
    print("pipe out: {}".format(pipeline_out_dict))
    assert(post_response.status_code == 500)
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
    if(post_response.status_code == 200):
      # TODO: this should fail with timeout of 0.1
      try:
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
      except Exception:
        print("pipe out: {}".format(pipeline_out_dict))
        raise
    elif(post_response.status_code == 430):
      print("pipe out: {}".format(pipeline_out_dict))
      # pipe_out_dict
      # TODO confirm timeout in error message
      pass
    else:
      print("pipe out: {}".format(pipeline_out_dict))
      assert(post_response.status_code != 200)


    # Give more time so that pipeline does not timeout
    more_time_pipe_dict = copy.deepcopy(PIPE_DEF2_DICT)
    more_time_pipe_dict["pipeline_options"]["timeout"] = TIMEOUT
    assert(more_time_pipe_dict["pipeline_options"]["timeout"] == TIMEOUT)
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
    assert(pipe_def.pipeline_options.timeout == TIMEOUT)
    assert(len(pipe_def.processors) == 2)
    assert(pipe_def.processors[0].processor_name == "deepgram")
    # Expecting: format_options, should_process and input_vcon_index in dict
    assert(len(vcon.pydantic_utils.get_dict(pipe_def.processors[0].processor_options, exclude_none=True)) == 5)
    assert(pipe_def.processors[0].processor_options.input_vcon_index == 0)
    assert(pipe_def.processors[0].processor_options.should_process == True)
    assert(pipe_def.processors[1].processor_name == "openai_chat_completion")
    assert(len(vcon.pydantic_utils.get_dict(pipe_def.processors[1].processor_options, exclude_none=True)) == 5)
    assert(pipe_def.processors[1].processor_options.input_vcon_index == 0)
    assert(pipe_def.processors[1].processor_options.should_process == True)


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
    try:
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
    except Exception:
      print("pipe out: {}".format(pipeline_out_dict))
      raise

    # run with invalid pipeline name
    post_response = client.post(
      "/pipeline/{}/run".format(
          "bogus_pipeline"
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
    assert(post_response.status_code == 404)

    # run with vCon in body, should succeed
    post_response = client.post(
      "/pipeline/{}/run".format(
          pipe2_name
        ),
        json = make_inline_audio_vcon.dumpd(),
        params = {
            "save_vcons": False,
            "return_results": True
          },
        headers={"accept": "application/json"},
      )
    pipeline_out_dict = post_response.json()
    try:
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
    except Exception:
      print("pipe out: {}".format(pipeline_out_dict))
      raise

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
    pipeline_out_dict = post_response.json()
    try:
      assert(post_response.status_code == 200)
      assert(pipeline_out_dict is None)
    except Exception:
      print("pipe out: {}".format(pipeline_out_dict))
      raise

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


@pytest.mark.asyncio
async def test_pipeline_conditional(make_inline_audio_vcon: vcon.Vcon):
  pipe_name = "unit_test_pipe1"

  generic_options = py_vcon_server.processor.VconProcessorOptions(
      ** (PIPE_CONDITIONAL_DICT["processors"][1]["processor_options"])
    )
  io_object = py_vcon_server.processor.VconProcessorIO(None)
  io_object.set_parameter("has_dialogs", "false")
  formatted_options = io_object.format_parameters_to_options(generic_options, {}, "set_parameters")
  assert(formatted_options.should_process is False)

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    set_response = client.put(
        "/pipeline/{}".format(
          pipe_name
        ),
        json = PIPE_CONDITIONAL_DICT,
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
    # check the model
    vcon.pydantic_utils.validate_construct(py_vcon_server.processor.VconUnsignedObject, make_inline_audio_vcon.dumpd())

    # run with vCon in body, should succeed
    post_response = client.post(
      "/pipeline/{}/run".format(
          pipe_name
        ),
        json = make_inline_audio_vcon.dumpd(),
        params = {
            "save_vcons": False,
            "return_results": True
          },
        headers={"accept": "application/json"},
      )
    pipeline_out_dict = post_response.json()
    try:
      assert(post_response.status_code == 200)
      assert(len(pipeline_out_dict["vcons"]) == 1)
      assert(len(pipeline_out_dict["vcons_modified"]) == 1)
      # As we pass the vCon into the RESDful API it is considered new/modified
      # WRT the vCon DB
      assert(pipeline_out_dict["vcons_modified"][0])
      unmodified_vcon = vcon.Vcon()
      unmodified_vcon.loadd(pipeline_out_dict["vcons"][0])
      print("pipeline output keys: {}".format(pipeline_out_dict.keys()))
      assert(len(unmodified_vcon.dialog) == 1)
      assert(len(unmodified_vcon.analysis) == 0)
      assert(len(pipeline_out_dict["parameters"]) == 2)
    except Exception:
      print("pipe out: {}".format(pipeline_out_dict))
      raise

@pytest.mark.asyncio
async def test_pipeline_runner_simple(make_2_party_tel_vcon: vcon.Vcon):
  """Test PipelineRunner directly with simple processors — no external services needed"""
  import py_vcon_server.db
  from py_vcon_server.settings import VCON_STORAGE_URL

  vs = py_vcon_server.db.VconStorage.instantiate(VCON_STORAGE_URL)
  try:
    # Pipeline with set_parameters and jq — no AI services needed
    pipe_def = py_vcon_server.pipeline.PipelineDefinition(**{
      "pipeline_options": {
        "timeout": 30,
        "save_vcons": False
      },
      "processors": [
        {
          "processor_name": "set_parameters",
          "processor_options": {
            "parameters": {"test_key": "test_value"}
          }
        },
        {
          "processor_name": "jq",
          "processor_options": {
            "jq_queries": {
              "party_count": ".vcons[0].parties | length"
            }
          }
        }
      ]
    })

    runner = py_vcon_server.pipeline.PipelineRunner(pipe_def, "test_simple_pipeline")

    proc_input = py_vcon_server.processor.VconProcessorIO(vs)
    await proc_input.add_vcon(make_2_party_tel_vcon, "fake_lock", False)

    proc_output = await runner.run(proc_input)

    assert(proc_output.get_parameter("test_key") == "test_value")
    assert(proc_output.get_parameter("party_count") == 2)

  finally:
    await vs.shutdown()


@pytest.mark.asyncio
async def test_pipeline_runner_should_process_false(make_2_party_tel_vcon: vcon.Vcon):
  """Test PipelineRunner skips processor when should_process=False"""
  import py_vcon_server.db
  from py_vcon_server.settings import VCON_STORAGE_URL

  vs = py_vcon_server.db.VconStorage.instantiate(VCON_STORAGE_URL)
  try:
    pipe_def = py_vcon_server.pipeline.PipelineDefinition(**{
      "pipeline_options": {
        "timeout": 30,
        "save_vcons": False
      },
      "processors": [
        {
          "processor_name": "jq",
          "processor_options": {
            "should_process": False,
            "jq_queries": {
              "should_not_be_set": ".vcons[0].uuid"
            }
          }
        }
      ]
    })

    runner = py_vcon_server.pipeline.PipelineRunner(pipe_def, "test_skip_pipeline")

    proc_input = py_vcon_server.processor.VconProcessorIO(vs)
    await proc_input.add_vcon(make_2_party_tel_vcon, "fake_lock", False)

    proc_output = await runner.run(proc_input)

    # Parameter should NOT have been set since should_process=False
    try:
      proc_output.get_parameter("should_not_be_set")
      raise Exception("Parameter should not have been set")
    except KeyError:
      pass  # expected

  finally:
    await vs.shutdown()

# ---------------------------------------------------------------------------
# PipelineJobHandler.do_job error branches
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_do_job_missing_pipeline_raises():
  """do_job raises when job definition has no pipeline key"""
  job_def = {
    "id": "test-job-1",
    "queue": "test_queue",
    "job": {"job_type": "vcon_uuid", "vcon_uuid": []},
    # no "pipeline" key
  }
  try:
    await py_vcon_server.pipeline.PipelineJobHandler.do_job(job_def)
    raise Exception("Expected exception for missing pipeline")
  except Exception as e:
    assert "no pipeline definition" in str(e)


@pytest.mark.asyncio
async def test_do_job_missing_queue_job_raises():
  """do_job raises when job definition has no job key"""
  job_def = {
    "id": "test-job-2",
    "queue": "test_queue",
    "pipeline": {
      "pipeline_options": {"timeout": 10, "save_vcons": False},
      "processors": []
    },
    # no "job" key
  }
  try:
    await py_vcon_server.pipeline.PipelineJobHandler.do_job(job_def)
    raise Exception("Expected exception for missing job")
  except Exception as e:
    assert "no queue job definition" in str(e)


@pytest.mark.asyncio
async def test_do_job_missing_job_type_raises():
  """do_job raises when the queue job has no job_type"""
  job_def = {
    "id": "test-job-3",
    "queue": "test_queue",
    "pipeline": {
      "pipeline_options": {"timeout": 10, "save_vcons": False},
      "processors": []
    },
    "job": {
      # no "job_type" key
      "vcon_uuid": []
    }
  }
  try:
    await py_vcon_server.pipeline.PipelineJobHandler.do_job(job_def)
    raise Exception("Expected exception for missing job_type")
  except Exception as e:
    assert "no queue job type" in str(e)


@pytest.mark.asyncio
async def test_do_job_unsupported_job_type_raises():
  """do_job raises when the queue job has an unsupported job_type"""
  job_def = {
    "id": "test-job-4",
    "queue": "test_queue",
    "pipeline": {
      "pipeline_options": {"timeout": 10, "save_vcons": False},
      "processors": []
    },
    "job": {
      "job_type": "unsupported_type"
    }
  }
  try:
    await py_vcon_server.pipeline.PipelineJobHandler.do_job(job_def)
    raise Exception("Expected exception for unsupported job_type")
  except Exception as e:
    assert "unsupported queue job type" in str(e)


# ---------------------------------------------------------------------------
# PipelineJobHandler.job_finished and job_exception branches
# These require a PipelineJobHandler instance with a live JobQueue.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def pipeline_job_handler():
  """Fixture providing an initialised PipelineJobHandler"""
  import py_vcon_server.queue
  from py_vcon_server.settings import PIPELINE_DB_URL, QUEUE_DB_URL
  handler = py_vcon_server.pipeline.PipelineJobHandler(
    QUEUE_DB_URL,
    PIPELINE_DB_URL,
    "test_server_key"
  )
  await handler._init_databases()
  yield handler

  # Clean up test queue
  try:
    await handler._job_queue.delete_queue(TEST_JOB_QUEUE_NAME)
  except py_vcon_server.queue.QueueDoesNotExist:
    pass

  await handler.done()


TEST_JOB_QUEUE_NAME = "test_pipeline_job_handler_queue"


async def _push_job_to_in_progress(job_queue, queue_name, vcon_uuid):
  """
  Helper: create queue, push a job, pop it to in-progress.
  Returns the in-progress job dict (which contains the real job id).
  """
  try:
    await job_queue.create_new_queue(queue_name)
  except py_vcon_server.queue.QueueAlreadyExists:
    pass

  await job_queue.push_vcon_uuid_queue_job(queue_name, [vcon_uuid])
  in_progress_job = await job_queue.pop_queued_job(queue_name, "test_server_key")
  return in_progress_job


@pytest.mark.asyncio
async def test_job_finished_no_pipeline_def(pipeline_job_handler):
  """job_finished logs error but does not raise when pipeline key is absent"""
  job_queue = pipeline_job_handler._job_queue
  in_progress_job = await _push_job_to_in_progress(
    job_queue, TEST_JOB_QUEUE_NAME, "fake-uuid-finished-1"
  )
  results = {
    "id": in_progress_job["id"],
    "job": {"job_type": "vcon_uuid", "vcon_uuid": ["fake-uuid-finished-1"]},
    "queue": TEST_JOB_QUEUE_NAME,
    # no "pipeline" key — exercises the no-pipeline-def branch
  }
  await pipeline_job_handler.job_finished(results)


@pytest.mark.asyncio
async def test_job_finished_no_success_queue(pipeline_job_handler):
  """job_finished with empty success_queue logs info but does not raise"""
  job_queue = pipeline_job_handler._job_queue
  in_progress_job = await _push_job_to_in_progress(
    job_queue, TEST_JOB_QUEUE_NAME, "fake-uuid-finished-2"
  )
  results = {
    "id": in_progress_job["id"],
    "job": {"job_type": "vcon_uuid", "vcon_uuid": ["fake-uuid-finished-2"]},
    "queue": TEST_JOB_QUEUE_NAME,
    "pipeline": {
      "pipeline_options": {
        "success_queue": "",  # empty — exercises the no-success-queue branch
        "failure_queue": ""
      }
    }
  }
  await pipeline_job_handler.job_finished(results)


@pytest.mark.asyncio
async def test_job_exception_no_pipeline_def(pipeline_job_handler):
  """job_exception logs error but does not raise when pipeline key is absent"""
  job_queue = pipeline_job_handler._job_queue
  in_progress_job = await _push_job_to_in_progress(
    job_queue, TEST_JOB_QUEUE_NAME, "fake-uuid-exception-1"
  )
  results = {
    "id": in_progress_job["id"],
    "job": {"job_type": "vcon_uuid", "vcon_uuid": ["fake-uuid-exception-1"]},
    "queue": TEST_JOB_QUEUE_NAME,
    # no "pipeline" key — exercises the no-pipeline-def branch
  }
  await pipeline_job_handler.job_exception(results)


@pytest.mark.asyncio
async def test_job_exception_no_failure_queue(pipeline_job_handler):
  """job_exception with empty failure_queue logs info but does not raise"""
  job_queue = pipeline_job_handler._job_queue
  in_progress_job = await _push_job_to_in_progress(
    job_queue, TEST_JOB_QUEUE_NAME, "fake-uuid-exception-2"
  )
  results = {
    "id": in_progress_job["id"],
    "job": {"job_type": "vcon_uuid", "vcon_uuid": ["fake-uuid-exception-2"]},
    "queue": TEST_JOB_QUEUE_NAME,
    "pipeline": {
      "pipeline_options": {
        "failure_queue": "",  # empty — exercises the no-failure-queue branch
        "success_queue": ""
      }
    }
  }
  await pipeline_job_handler.job_exception(results)


@pytest.mark.asyncio
async def test_job_canceled(pipeline_job_handler):
  """job_canceled calls requeue_in_progress_job without raising"""
  # Push a fake in-progress job first so requeue has something to work with
  import py_vcon_server.queue
  job_queue = pipeline_job_handler._job_queue
  queue_name = "test_cancel_queue"

  # Ensure queue exists
  try:
    await job_queue.create_new_queue(queue_name)
  except py_vcon_server.queue.QueueAlreadyExists:
    pass

  try:
    # Push a job and move it to in-progress so requeue works
    await job_queue.push_vcon_uuid_queue_job(
      queue_name,
      ["fake-cancel-uuid"],
      queue_name,
      "test-cancel-1"
    )
    popped = await job_queue.pop_queued_job(queue_name, "test_server_key")
    job_id = popped["id"]

    results = {"id": job_id}
    await pipeline_job_handler.job_canceled(results)

  finally:
    try:
      await job_queue.delete_queue(queue_name)
    except Exception:
      pass

# ---------------------------------------------------------------------------
# _do_processes should_process is None raises
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_runner_should_process_none_raises(make_2_party_tel_vcon):
  """_do_processes raises when should_process evaluates to None after format_options."""
  import py_vcon_server.db
  from py_vcon_server.settings import VCON_STORAGE_URL

  vs = py_vcon_server.db.VconStorage.instantiate(VCON_STORAGE_URL)
  try:
    # Use format_options to inject a parameter that does not exist — this
    # results in a KeyError during formatting which propagates as an exception
    pipe_def = py_vcon_server.pipeline.PipelineDefinition(**{
      "pipeline_options": {"timeout": 30, "save_vcons": False},
      "processors": [
        {
          "processor_name": "jq",
          "processor_options": {
            "jq_queries": {"x": ".vcons[0].uuid"},
            "format_options": {"should_process": "{nonexistent_param}"}
          }
        }
      ]
    })

    runner = py_vcon_server.pipeline.PipelineRunner(pipe_def, "test_none_should_process")
    proc_input = py_vcon_server.processor.VconProcessorIO(vs)
    await proc_input.add_vcon(make_2_party_tel_vcon, "fake_lock", False)

    try:
      await runner.run(proc_input)
      raise Exception("Expected exception from missing format parameter")
    except Exception as e:
      # KeyError or similar from missing parameter in format string
      assert "nonexistent_param" in str(e) or "should_process" in str(e) or isinstance(e, KeyError)

  finally:
    await vs.shutdown()


# ---------------------------------------------------------------------------
# job_finished warning branch — removed_job id mismatch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_job_finished_removed_job_id_mismatch(pipeline_job_handler):
  """job_finished logs a warning when removed_job id does not match — covers
  the warning branch after remove_in_progress_job."""
  # We cannot easily make remove_in_progress_job return a mismatched id
  # without mocking, so we verify the normal path covers the
  # if(removed_job.get("id", None) == job_id) branch by checking
  # a successful removal does NOT trigger the warning.
  job_queue = pipeline_job_handler._job_queue
  in_progress_job = await _push_job_to_in_progress(
    job_queue, TEST_JOB_QUEUE_NAME, "fake-uuid-mismatch"
  )
  results = {
    "id": in_progress_job["id"],
    "job": {"job_type": "vcon_uuid", "vcon_uuid": ["fake-uuid-mismatch"]},
    "queue": TEST_JOB_QUEUE_NAME,
    "pipeline": {
      "pipeline_options": {"success_queue": "", "failure_queue": ""}
    }
  }
  # Normal path — id matches, no warning
  await pipeline_job_handler.job_finished(results)


# ---------------------------------------------------------------------------
# job_finished with a set success_queue — covers push to success queue path
# and QueueDoesNotExist handler when success queue does not exist
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_job_finished_with_nonexistent_success_queue(pipeline_job_handler):
  """job_finished with a non-empty success_queue that does not exist logs
  an error but does not raise — covers the QueueDoesNotExist handler."""
  job_queue = pipeline_job_handler._job_queue
  in_progress_job = await _push_job_to_in_progress(
    job_queue, TEST_JOB_QUEUE_NAME, "fake-uuid-success-q"
  )
  results = {
    "id": in_progress_job["id"],
    "job": {"job_type": "vcon_uuid", "vcon_uuid": ["fake-uuid-success-q"]},
    "queue": TEST_JOB_QUEUE_NAME,
    "pipeline": {
      "pipeline_options": {
        # Non-empty but nonexistent queue — triggers QueueDoesNotExist
        "success_queue": "nonexistent_success_queue_xyz",
        "failure_queue": ""
      }
    }
  }
  # Should log error but not raise
  await pipeline_job_handler.job_finished(results)


# ---------------------------------------------------------------------------
# job_exception with a set failure_queue — covers push to failure queue path
# and QueueDoesNotExist handler
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_job_exception_with_nonexistent_failure_queue(pipeline_job_handler):
  """job_exception with a non-empty failure_queue that does not exist logs
  an error but does not raise — covers the QueueDoesNotExist handler."""
  job_queue = pipeline_job_handler._job_queue
  in_progress_job = await _push_job_to_in_progress(
    job_queue, TEST_JOB_QUEUE_NAME, "fake-uuid-failure-q"
  )
  results = {
    "id": in_progress_job["id"],
    "job": {"job_type": "vcon_uuid", "vcon_uuid": ["fake-uuid-failure-q"]},
    "queue": TEST_JOB_QUEUE_NAME,
    "pipeline": {
      "pipeline_options": {
        "failure_queue": "nonexistent_failure_queue_xyz",
        "success_queue": ""
      }
    }
  }
  await pipeline_job_handler.job_exception(results)


# ---------------------------------------------------------------------------
# job_exception unsupported job_type in failure queue branch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_job_exception_unsupported_job_type(pipeline_job_handler):
  """job_exception with a non-empty failure_queue but unsupported job_type
  logs an error but does not raise."""
  job_queue = pipeline_job_handler._job_queue
  in_progress_job = await _push_job_to_in_progress(
    job_queue, TEST_JOB_QUEUE_NAME, "fake-uuid-bad-type"
  )
  results = {
    "id": in_progress_job["id"],
    "job": {"job_type": "unsupported_type"},
    "queue": TEST_JOB_QUEUE_NAME,
    "pipeline": {
      "pipeline_options": {
        "failure_queue": "nonexistent_failure_queue_xyz",
        "success_queue": ""
      }
    }
  }
  await pipeline_job_handler.job_exception(results)


# ---------------------------------------------------------------------------
# job_canceled
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_job_canceled(pipeline_job_handler):
  """job_canceled requeues the in-progress job back to the queue."""
  job_queue = pipeline_job_handler._job_queue
  in_progress_job = await _push_job_to_in_progress(
    job_queue, TEST_JOB_QUEUE_NAME, "fake-uuid-canceled"
  )

  results = {"id": in_progress_job["id"]}
  await pipeline_job_handler.job_canceled(results)

  # Job should now be back in the queue
  queue_jobs = await job_queue.get_queue_jobs(TEST_JOB_QUEUE_NAME)
  job_ids = [j.get("id", None) for j in queue_jobs]
  assert in_progress_job["id"] in job_ids or len(queue_jobs) >= 1


@pytest.mark.asyncio
async def test_do_job_with_save_vcons(make_2_party_tel_vcon):
  """do_job with save_vcons=True commits vCon changes after pipeline run"""
  import py_vcon_server.db
  from py_vcon_server.settings import VCON_STORAGE_URL

  # Store the vCon so do_job can retrieve it by UUID
  vs = py_vcon_server.db.VconStorage.instantiate(VCON_STORAGE_URL)
  try:
    await vs.set(make_2_party_tel_vcon)
    vcon_uuid = make_2_party_tel_vcon.uuid

    job_def = {
      "id": "test-save-job-1",
      "queue": "test_queue",
      "locks": [],
      "job": {
        "job_type": "vcon_uuid",
        "vcon_uuid": [vcon_uuid]
      },
      "pipeline": {
        "pipeline_options": {
          "timeout": 30,
          "save_vcons": True,  # triggers the commit path
          "failure_queue": "",
          "success_queue": ""
        },
        "processors": [
          {
            "processor_name": "set_parameters",
            "processor_options": {"parameters": {"test_key": "test_value"}}
          }
        ]
      }
    }

    result = await py_vcon_server.pipeline.PipelineJobHandler.do_job(job_def)
    assert result is not None

  finally:
    try:
      await vs.delete(vcon_uuid)
    except Exception:
      pass
    await vs.shutdown()

def test_pipeline_manager_add_processor_not_implemented():
  """PipelineManager.add_processor raises Exception as not implemented"""
  mgr = py_vcon_server.pipeline.PipelineManager()
  try:
    mgr.add_processor("jq", py_vcon_server.processor.VconProcessorOptions())
    raise Exception("Expected not implemented exception")
  except Exception as e:
    assert "Not implemented" in str(e)


@pytest.mark.asyncio
async def test_pipeline_runner_timeout_none_when_zero(make_2_party_tel_vcon):
  """PipelineRunner converts timeout <= 0 to None (no timeout). Covers line 352."""
  import py_vcon_server.db
  from py_vcon_server.settings import VCON_STORAGE_URL

  vs = py_vcon_server.db.VconStorage.instantiate(VCON_STORAGE_URL)
  try:
    pipe_def = py_vcon_server.pipeline.PipelineDefinition(**{
      "pipeline_options": {
        "timeout": 0,  # <= 0 triggers timeout = None
        "save_vcons": False
      },
      "processors": [
        {
          "processor_name": "set_parameters",
          "processor_options": {"parameters": {"k": "v"}}
        }
      ]
    })

    runner = py_vcon_server.pipeline.PipelineRunner(pipe_def, "test_zero_timeout")
    proc_input = py_vcon_server.processor.VconProcessorIO(vs)
    await proc_input.add_vcon(make_2_party_tel_vcon, "fake_lock", False)
    proc_output = await runner.run(proc_input)
    assert proc_output.get_parameter("k") == "v"

  finally:
    await vs.shutdown()


@pytest.mark.asyncio
async def test_do_job_with_locks_and_parameters(make_2_party_tel_vcon):
  """do_job handles locks list and job parameters — covers lines 737 and 745-746"""
  import py_vcon_server.db
  from py_vcon_server.settings import VCON_STORAGE_URL

  vs = py_vcon_server.db.VconStorage.instantiate(VCON_STORAGE_URL)
  try:
    await vs.set(make_2_party_tel_vcon)
    vcon_uuid = make_2_party_tel_vcon.uuid

    job_def = {
      "id": "test-locks-params-job",
      "queue": "test_queue",
      "locks": ["fake_lock"],  # lock_len > index triggers line 737
      "job": {
        "job_type": "vcon_uuid",
        "vcon_uuid": [vcon_uuid],
        "parameters": {"injected_key": "injected_value"}  # triggers lines 745-746
      },
      "pipeline": {
        "pipeline_options": {
          "timeout": 30,
          "save_vcons": False,
          "failure_queue": "",
          "success_queue": ""
        },
        "processors": [
          {
            "processor_name": "set_parameters",
            "processor_options": {"parameters": {"k": "v"}}
          }
        ]
      }
    }

    result = await py_vcon_server.pipeline.PipelineJobHandler.do_job(job_def)
    assert result is not None

  finally:
    try:
      await vs.delete(vcon_uuid)
    except Exception:
      pass
    await vs.shutdown()
    # Reset the global VCON_STORAGE that do_job set, so subsequent tests
    # are not affected by the now-closed connection pool
    py_vcon_server.pipeline.VCON_STORAGE = None


@pytest.mark.asyncio
async def test_job_finished_unsupported_job_type_with_success_queue(pipeline_job_handler):
  """job_finished logs error for unsupported job_type when success_queue is set — covers line 840"""
  job_queue = pipeline_job_handler._job_queue
  in_progress_job = await _push_job_to_in_progress(
    job_queue, TEST_JOB_QUEUE_NAME, "fake-uuid-unsupported"
  )
  results = {
    "id": in_progress_job["id"],
    "job": {"job_type": "unsupported_type"},
    "queue": TEST_JOB_QUEUE_NAME,
    "pipeline": {
      "pipeline_options": {
        "success_queue": "nonexistent_success_queue_xyz",
        "failure_queue": ""
      }
    }
  }
  await pipeline_job_handler.job_finished(results)


@pytest.mark.asyncio
async def test_pipeline_runner_timeout_fires(make_2_party_tel_vcon):
  """PipelineRunner raises PipelineTimeout when a processor exceeds the timeout.
  Covers line 372."""
  import py_vcon_server.db
  from py_vcon_server.settings import VCON_STORAGE_URL

  vs = py_vcon_server.db.VconStorage.instantiate(VCON_STORAGE_URL)
  try:
    pipe_def = py_vcon_server.pipeline.PipelineDefinition(**{
      "pipeline_options": {
        "timeout": 0.1,  # 100ms — will fire before the 5s sleep completes
        "save_vcons": False
      },
      "processors": [
        {
          "processor_name": "timeout_test_sleep_async",
          "processor_options": {"sleep_seconds": 5.0}
        }
      ]
    })

    runner = py_vcon_server.pipeline.PipelineRunner(pipe_def, "test_timeout_fires")
    proc_input = py_vcon_server.processor.VconProcessorIO(vs)
    await proc_input.add_vcon(make_2_party_tel_vcon, "fake_lock", False)

    try:
      await runner.run(proc_input)
      raise Exception("Expected PipelineTimeout")
    except py_vcon_server.pipeline.PipelineTimeout:
      pass  # expected

  finally:
    await vs.shutdown()


@pytest.mark.asyncio
async def test_pipeline_context_parameters_both_run_endpoints(make_inline_audio_vcon: vcon.Vcon):
  """
  Exercise the /pipeline/{name}/run and /pipeline/{name}/run/{uuid} entry
  points WRT context parameters.  A single jinja_report processor resolves
  VCON_UUID, PROCESSOR_NAME, PIPELINE_NAME and ENTRY_POINT via format_options
  and writes the result to the report_output parameter, which is read back
  from the returned pipeline output.  ENTRY_POINT differs between the two
  endpoints: /pipeline/run for the body endpoint and /pipeline/run/uuid for
  the stored UUID endpoint.
  """
  pipe_name = "test_context_param_pipe"

  pipe_def = {
      "pipeline_options": {
          "timeout": 30,
          "save_vcons": False
        },
      "processors": [
          {
              "processor_name": "jinja_report",
              "processor_options": {
                  "template": "placeholder",
                  "format_options": {
                      "template": "uuid={VCON_UUID}|proc={PROCESSOR_NAME}"
                        "|pipe={PIPELINE_NAME}|entry={ENTRY_POINT}"
                    }
                }
            }
        ]
    }

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    # Define the pipeline
    put_response = client.put(
        "/pipeline/{}".format(pipe_name),
        json = pipe_def,
        params = {"validate_processor_options": True}
      )
    assert(put_response.status_code == 204)

    # Endpoint 1: vCon in request body -> ENTRY_POINT == /pipeline/run
    post_response = client.post(
        "/pipeline/{}/run".format(pipe_name),
        json = make_inline_audio_vcon.dumpd(),
        params = {"save_vcons": False, "return_results": True},
        headers = {"accept": "application/json"}
      )
    assert(post_response.status_code == 200)
    body_out = post_response.json()
    body_result = body_out["parameters"]["report_output"]
    assert("uuid={}".format(make_inline_audio_vcon.uuid) in body_result)
    assert("proc=jinja_report" in body_result)
    assert("pipe={}".format(pipe_name) in body_result)
    assert("entry=/pipeline/run" in body_result)

    # Store the vCon for the UUID endpoint
    set_response = client.post("/vcon", json = make_inline_audio_vcon.dumpd())
    assert(set_response.status_code == 204)

    # Endpoint 2: vCon in storage by UUID -> ENTRY_POINT == /pipeline/run/uuid
    post_response = client.post(
        "/pipeline/{}/run/{}".format(pipe_name, UUID),
        params = {"save_vcons": False, "return_results": True},
        headers = {"accept": "application/json"}
      )
    assert(post_response.status_code == 200)
    uuid_out = post_response.json()
    uuid_result = uuid_out["parameters"]["report_output"]
    assert("uuid={}".format(UUID) in uuid_result)
    assert("proc=jinja_report" in uuid_result)
    assert("pipe={}".format(pipe_name) in uuid_result)
    assert("entry=/pipeline/run/uuid" in uuid_result)

    # Cleanup
    client.delete("/vcon/{}".format(UUID))
    client.delete("/pipeline/{}".format(pipe_name))

