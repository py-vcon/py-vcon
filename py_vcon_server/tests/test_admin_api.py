import os
import time
import asyncio
import pytest
import pytest_asyncio
import py_vcon_server
import vcon
import fastapi.testclient

@pytest.mark.asyncio
async def test_get_server_info():
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    get_response = client.get(
      "/server/info",
      headers={"accept": "application/json"},
      )
    assert(get_response.status_code == 200)

    version_dict = get_response.json()

    assert(version_dict["py_vcon_server"] == py_vcon_server.__version__)
    assert(version_dict["vcon"] == vcon.__version__)
    assert(version_dict["pid"] == os.getpid())
    assert(version_dict["start_time"] <= time.time())
    assert(version_dict["start_time"] > time.time() - 1000)


