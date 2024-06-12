# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.

import asyncio
import pytest
import pytest_asyncio
import fastapi.testclient
import vcon
import py_vcon_server
from py_vcon_server.settings import VCON_STORAGE_URL
from common_setup import make_inline_audio_vcon, make_2_party_tel_vcon, UUID

# invoke only once for all the unit test in this module
@pytest_asyncio.fixture(autouse=True)
async def setup():
  """ Setup Vcon storage connection before test """
  vs = py_vcon_server.db.VconStorage.instantiate(VCON_STORAGE_URL)
  global VCON_STORAGE
  VCON_STORAGE = vs


  # wait until teardown time
  yield

  # Shutdown the Vcon storage after test
  VCON_STORAGE = None
  await vs.shutdown()

@pytest.mark.asyncio
async def test_jq(make_inline_audio_vcon):
  in_vcon = make_inline_audio_vcon
  assert(isinstance(in_vcon, vcon.Vcon))

  # Setup inputs
  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(in_vcon, "fake_lock", False) # read/write
  assert(len(proc_input._vcons) == 1)
  proc_input.set_parameter("three", "three")

  jq_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("jq")

  queries = {
      "num_vcons": ".vcons | length",
      "num_dialogs": ".vcons[0].dialog | length",
      "num_analysis": ".vcons[0].analysis | length",
      "is_three": ".parameters.three == \"three\"",
      "is_four": ".parameters.four == \"four\""
    }

  jq_proc_options = jq_proc_inst.processor_options_class()(
      jq_queries = queries
    )

  proc_output = await jq_proc_inst.process(proc_input, jq_proc_options)

  assert(proc_output.get_parameter("num_vcons") == 1)
  assert(proc_output.get_parameter("num_dialogs") == 1)
  assert(proc_output.get_parameter("num_analysis") == 0)
  assert(proc_output.get_parameter("three") == "three")
  try:
    proc_output.get_parameter("four")
    raise Exception("expect exception as 'four' is not set")
  except KeyError:
    # expected
    pass
  assert(proc_output.get_parameter("is_three") == True)
  assert(proc_output.get_parameter("is_four") == False)


@pytest.mark.asyncio
async def test_jq_proc_api(make_inline_audio_vcon):
  in_vcon = make_inline_audio_vcon
  assert(isinstance(in_vcon, vcon.Vcon))

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    # Put the vCon in the DB, don't really care what is looks like as
    # its not used.
    set_response = client.post("/vcon", json = in_vcon.dumpd())
    assert(set_response.status_code == 204)

    parameters = {
        "commit_changes": False,
        "return_whole_vcon": False
      }

    jq_proc_options = {
        "jq_queries": {
            "num_vcons": ".vcons | length",
            "num_dialogs": ".vcons[0].dialog | length",
            "num_analysis": ".vcons[0].analysis | length",
            "is_three": ".parameters.three == \"three\"",
            "is_four": ".parameters.four == \"four\""
          }
      }

    post_response = client.post("/process/{}/jq".format(UUID),
        params = parameters,
        json = jq_proc_options
      )
    assert(post_response.status_code == 200)
    proc_io_out = post_response.json()

    assert(proc_io_out["parameters"]["num_vcons"] == 1)
    assert(proc_io_out["parameters"]["num_dialogs"] == 1)
    assert(proc_io_out["parameters"]["num_analysis"] == 0)
    try:
      assert(proc_io_out["parameters"]["four"])
      raise Exception("expect exception as 'four' is not set")
    except KeyError:
      # expected
      pass
    assert(proc_io_out["parameters"]["is_three"] == False)
    assert(proc_io_out["parameters"]["is_four"] == False)

