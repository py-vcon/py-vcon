""" Unit tests for Pipeline and related data objects """
import pydantic
import pytest
import pytest_asyncio
import fastapi.testclient
import py_vcon_server.pipeline
from py_vcon_server.settings import PIPELINE_DB_URL


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
    assert(errors_dict[0]["type"] == "type_error.integer")
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
    assert(errors_dict[0]["type"] == "type_error.integer")
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
async def test_pipeline_restapi():

  pipe_name = "unit_test_pipe1"
  bad_pipe_name = pipe_name + "_bad"
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

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

