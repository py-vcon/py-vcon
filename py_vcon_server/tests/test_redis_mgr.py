# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
import os 
import sys
import uuid
import pytest
import pytest_asyncio
import random
import string
sys.path.append("..")
sys.path.append("py_vcon_server")
sys.path.append("py_vcon_server/db")
sys.path.append("py_vcon_server/db/redis")
print("CWD: {}".format(os.getcwd()))
print(sys.path, file=sys.stderr)
import py_vcon_server.db.redis.redis_mgr
from py_vcon_server.settings import VCON_STORAGE_URL

r_mgr = py_vcon_server.db.redis.redis_mgr.RedisMgr(VCON_STORAGE_URL)

# Run before each test function
@pytest_asyncio.fixture(autouse=True)
async def setup_teardown():
    # Before test
    r_mgr.create_pool()

    yield 0

    # after test
    await r_mgr.shutdown_pool()

@pytest.mark.asyncio
async def test_get_set():
    key = "abc"
    value = { 'a': 123}
    r = r_mgr.get_client()
    await r.json().set(key, "$", value)
    value_read = await r.json().get(key)
    assert(value_read["a"] == 123)
    await r.delete(key)
    result = await r.json().get(key)
    assert(result==None)


