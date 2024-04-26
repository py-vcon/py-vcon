# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
import os
import asyncio
import pytest
import pytest_asyncio
import importlib
import py_vcon_server
import py_vcon_server.settings
import fastapi.testclient

os.environ["WORK_QUEUES"] = "A:4,DDD:5,C:1,E:,F,G:a"

try:
  importlib.reload(py_vcon_server.settings)
  # Should not get here, invalid weight for queue "G"
  assert(0)
except Exception as e:
  if(str(e).startswith("WORK_QUEUE weights must be an integer value")):
    # Expected and ignored
    pass
  else:
    raise e

os.environ["WORK_QUEUES"] = "A:4,DDD:5,C:1,E:,F,G:1:4"

try:
  importlib.reload(py_vcon_server.settings)
  # Should not get here, invalid weight for queue "G"
  assert(0)
except Exception as e:
  if(str(e).startswith("Invalid WORK_QUEUE token:")):
    # Expected and ignored
    pass
  else:
    raise e

@pytest.mark.asyncio
async def test_queue_config():
  # Need to reset WORK_QUEUES dict???
  py_vcon_server.settings.WORK_QUEUES = {}
  os.environ["WORK_QUEUES"] = "A:4,DDD:5,C:1,E:,F,G:14"
  importlib.reload(py_vcon_server.settings)

  print("WORK_QUEUES in test: {}".format(py_vcon_server.settings.WORK_QUEUES))
  assert(len(py_vcon_server.settings.WORK_QUEUES.items()) == 6)
  assert(py_vcon_server.settings.WORK_QUEUES["A"]["weight"] == 4)
  assert(py_vcon_server.settings.WORK_QUEUES["DDD"]["weight"] == 5)
  assert(py_vcon_server.settings.WORK_QUEUES["C"]["weight"] == 1)
  assert(py_vcon_server.settings.WORK_QUEUES["E"]["weight"] == 1)
  assert(py_vcon_server.settings.WORK_QUEUES["F"]["weight"] == 1)
  assert(py_vcon_server.settings.WORK_QUEUES["G"]["weight"] == 14)

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    get_response = client.get(
      "/server/queues",
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)

    queue_dict = get_response.json()
    assert(len(queue_dict.items()) == 6)
    assert(queue_dict["A"]["weight"] == 4)
    assert(queue_dict["DDD"]["weight"] == 5)
    assert(queue_dict["C"]["weight"] == 1)
    assert(queue_dict["E"]["weight"] == 1)
    assert(queue_dict["F"]["weight"] == 1)
    assert(queue_dict["G"]["weight"] == 14)

    post_response = client.post(
      "/server/queue/Q",
      json = {"weight": 9},
      headers={"accept": "application/json"}
      )

    assert(post_response.status_code == 204)
    assert(post_response.text == "")

    assert(len(py_vcon_server.settings.WORK_QUEUES.items()) == 7)
    assert(py_vcon_server.settings.WORK_QUEUES["A"]["weight"] == 4)
    assert(py_vcon_server.settings.WORK_QUEUES["DDD"]["weight"] == 5)
    assert(py_vcon_server.settings.WORK_QUEUES["C"]["weight"] == 1)
    assert(py_vcon_server.settings.WORK_QUEUES["E"]["weight"] == 1)
    assert(py_vcon_server.settings.WORK_QUEUES["F"]["weight"] == 1)
    assert(py_vcon_server.settings.WORK_QUEUES["G"]["weight"] == 14)
    assert(py_vcon_server.settings.WORK_QUEUES["Q"]["weight"] == 9)

    delete_response = client.delete("/server/queue/{}".format("DDD"))
    assert(delete_response.status_code == 204)
    assert(delete_response.text == "")

    assert(len(py_vcon_server.settings.WORK_QUEUES.items()) == 6)
    assert(py_vcon_server.settings.WORK_QUEUES["A"]["weight"] == 4)
    assert(py_vcon_server.settings.WORK_QUEUES.get("DDD", None) is None)
    assert(py_vcon_server.settings.WORK_QUEUES["C"]["weight"] == 1)
    assert(py_vcon_server.settings.WORK_QUEUES["E"]["weight"] == 1)
    assert(py_vcon_server.settings.WORK_QUEUES["F"]["weight"] == 1)
    assert(py_vcon_server.settings.WORK_QUEUES["G"]["weight"] == 14)
    assert(py_vcon_server.settings.WORK_QUEUES["Q"]["weight"] == 9)

