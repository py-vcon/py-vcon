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

