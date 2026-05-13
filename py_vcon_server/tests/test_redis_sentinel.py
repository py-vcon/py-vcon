# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
Unit tests for Redis Sentinel support in redis_mgr.py.

Structure:
  TestSentinelUrlParser  -- pure logic tests, no infrastructure needed
  TestSentinelPool       -- live sentinel required, skipped if not reachable
  TestSentinelFailover   -- live sentinel required, destructive, runs last
"""
import socket
import pytest
import py_vcon_server.db.redis.redis_mgr
from py_vcon_server.db.redis.redis_mgr import parse_sentinel_url
from py_vcon_server.settings import VCON_STORAGE_URL


def sentinel_reachable():
  """
  Return True if VCON_STORAGE_URL is a sentinel:// URL and the first
  sentinel host is reachable.  Used as the skipif condition for live tests.
  """
  if not VCON_STORAGE_URL.startswith("sentinel://"):
    return False
  parsed = parse_sentinel_url(VCON_STORAGE_URL)
  if not parsed["sentinel_hosts"]:
    return False
  host, port = parsed["sentinel_hosts"][0]
  try:
    s = socket.create_connection((host, port), timeout=1.0)
    s.close()
    return True
  except OSError:
    return False


class TestSentinelUrlParser:
  """
  Pure logic tests for parse_sentinel_url().
  No Redis infrastructure required.
  """

  def test_single_host(self):
    r = parse_sentinel_url("sentinel://localhost:26399/mymaster")
    assert r["sentinel_hosts"] == [("localhost", 26399)]
    assert r["master_name"] == "mymaster"

  def test_multi_host(self):
    r = parse_sentinel_url(
        "sentinel://localhost:26399,localhost:26400,localhost:26401/mymaster"
      )
    assert r["sentinel_hosts"] == [
        ("localhost", 26399),
        ("localhost", 26400),
        ("localhost", 26401),
      ]

  def test_mixed_ports(self):
    r = parse_sentinel_url("sentinel://h1:26399,h2:26400,h3:26401/mymaster")
    assert r["sentinel_hosts"] == [("h1", 26399), ("h2", 26400), ("h3", 26401)]

  def test_default_master_name(self):
    r = parse_sentinel_url("sentinel://localhost:26399/")
    assert r["master_name"] == "mymaster"

  def test_default_db(self):
    r = parse_sentinel_url("sentinel://localhost:26399/mymaster")
    assert r["db"] == 0

  def test_db_in_query(self):
    r = parse_sentinel_url("sentinel://localhost:26399/mymaster?db=3")
    assert r["db"] == 3

  def test_default_port(self):
    r = parse_sentinel_url("sentinel://localhost/mymaster")
    assert r["sentinel_hosts"] == [("localhost", 26379)]

  def test_password_in_authority(self):
    r = parse_sentinel_url("sentinel://:secret@localhost:26399/mymaster")
    assert r["password"] == "secret"
    assert r["sentinel_password"] is None

  def test_password_in_query(self):
    r = parse_sentinel_url("sentinel://localhost:26399/mymaster?password=qparam")
    assert r["password"] == "qparam"

  def test_password_query_overrides_authority(self):
    r = parse_sentinel_url(
        "sentinel://:auth@localhost:26399/mymaster?password=override"
      )
    assert r["password"] == "override"

  def test_sentinel_password(self):
    r = parse_sentinel_url(
        "sentinel://localhost:26399/mymaster?sentinel_password=sp"
      )
    assert r["sentinel_password"] == "sp"
    assert r["password"] is None

  def test_no_password(self):
    r = parse_sentinel_url("sentinel://localhost:26399/mymaster")
    assert r["password"] is None
    assert r["sentinel_password"] is None


async def _do_json_set_get_delete(r_mgr):
  """
  Shared test logic: JSON set, get and delete via the given RedisMgr.
  Mirrors test_get_set in test_redis_mgr.py.
  """
  key = "sentinel_test_abc"
  value = {"a": 123}
  r = r_mgr.get_client()
  await r.json().set(key, "$", value)
  value_read = await r.json().get(key)
  assert value_read["a"] == 123
  await r.delete(key)
  result = await r.json().get(key)
  assert result is None


@pytest.mark.skipif(
    not sentinel_reachable(),
    reason="Sentinel not reachable - run scripts/start_sentinel.sh first"
  )
class TestSentinelPool:
  """
  Live sentinel tests.  Each test creates and tears down its own RedisMgr
  so tests are independent and no state leaks into TestSentinelFailover.
  Requires sentinel cluster on ports 26399-26401 (run scripts/start_sentinel.sh).
  """

  @pytest.mark.asyncio
  async def test_json_set_get_delete(self):
    """ Basic JSON set/get/delete via sentinel - mirrors test_get_set """
    r_mgr = py_vcon_server.db.redis.redis_mgr.RedisMgr(VCON_STORAGE_URL, "test_json")
    r_mgr.create_pool()
    try:
      await _do_json_set_get_delete(r_mgr)
    finally:
      await r_mgr.shutdown_pool()

  def test_mode_is_sentinel(self):
    """ RedisMgr detects sentinel:// URL and sets mode correctly """
    r_mgr = py_vcon_server.db.redis.redis_mgr.RedisMgr(VCON_STORAGE_URL, "test_mode")
    assert r_mgr._mode == "sentinel"

  @pytest.mark.asyncio
  async def test_create_pool_sets_sentinel(self):
    """ create_pool() populates _sentinel and _master_name """
    r_mgr = py_vcon_server.db.redis.redis_mgr.RedisMgr(VCON_STORAGE_URL, "test_create")
    r_mgr.create_pool()
    try:
      assert r_mgr._sentinel is not None
      assert r_mgr._master_name == "mymaster"
      assert r_mgr._redis_pool is not None
    finally:
      await r_mgr.shutdown_pool()

  @pytest.mark.asyncio
  async def test_double_create_pool(self):
    """ Second create_pool() call is a no-op """
    r_mgr = py_vcon_server.db.redis.redis_mgr.RedisMgr(VCON_STORAGE_URL, "test_double")
    r_mgr.create_pool()
    pool_before = r_mgr._redis_pool
    r_mgr.create_pool()
    assert r_mgr._redis_pool is pool_before
    await r_mgr.shutdown_pool()

  def test_get_client_not_initialized(self):
    """ get_client() before create_pool() raises RedisPoolNotInitialized """
    r_mgr = py_vcon_server.db.redis.redis_mgr.RedisMgr(VCON_STORAGE_URL, "test_uninit")
    with pytest.raises(py_vcon_server.db.redis.redis_mgr.RedisPoolNotInitialized):
      r_mgr.get_client()

  @pytest.mark.asyncio
  async def test_fail_next(self):
    """ FAIL_NEXT causes get_client() to raise RedisPoolNotInitialized """
    r_mgr = py_vcon_server.db.redis.redis_mgr.RedisMgr(VCON_STORAGE_URL, "test_fail")
    r_mgr.create_pool()
    try:
      py_vcon_server.db.redis.redis_mgr.FAIL_NEXT = 1
      with pytest.raises(py_vcon_server.db.redis.redis_mgr.RedisPoolNotInitialized):
        r_mgr.get_client()
      assert py_vcon_server.db.redis.redis_mgr.FAIL_NEXT == 0
    finally:
      py_vcon_server.db.redis.redis_mgr.FAIL_NEXT = 0
      await r_mgr.shutdown_pool()

  @pytest.mark.asyncio
  async def test_log_pool_stats(self):
    """ log_pool_stats() runs without error with pool active """
    r_mgr = py_vcon_server.db.redis.redis_mgr.RedisMgr(VCON_STORAGE_URL, "test_stats")
    r_mgr.create_pool()
    try:
      r_mgr.log_pool_stats()
    finally:
      await r_mgr.shutdown_pool()

  @pytest.mark.asyncio
  async def test_shutdown_clears_sentinel(self):
    """ shutdown_pool() clears _sentinel, _master_name and _redis_pool """
    r_mgr = py_vcon_server.db.redis.redis_mgr.RedisMgr(VCON_STORAGE_URL, "test_shutdown")
    r_mgr.create_pool()
    await r_mgr.shutdown_pool()
    assert r_mgr._redis_pool is None
    assert r_mgr._sentinel is None
    assert r_mgr._master_name is None

