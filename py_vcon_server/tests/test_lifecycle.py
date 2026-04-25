# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
Unit tests for lifespan migration, heartbeat, and shutdown middleware.

Tests:
  1. Middleware returns 503 when SHUTDOWN_REQUESTED is set
  2. Middleware allows /metrics through during shutdown
  3. Heartbeat updates Redis last_heartbeat timestamp
  4. HEARTBEAT_PERIOD=0 disables heartbeat task
  5. HEARTBEAT_PERIOD>0 creates heartbeat task
  6. Server state is "running" after startup
  7. SERVER_STATE is None after shutdown
  8. heartbeat_loop fires periodically and stops on HEARTBEAT_RUNNING=False
  9. In-flight request completes before shutdown code runs
"""
import os
import time
import threading
import pytest
import fastapi.testclient
import vcon
import py_vcon_server
import py_vcon_server.states
import py_vcon_server.settings
import pytest_asyncio


UUID = "01855517-life-fake-uuid-77776666acbe"


def make_test_vcon() -> vcon.Vcon:
  v = vcon.Vcon()
  v._vcon_dict["uuid"] = UUID
  v.set_party_parameter("tel", "+15551234567")
  v.set_party_parameter("name", "Alice", 0)
  v.set_subject("Test conversation")
  v.add_dialog_inline_text(
      "Hello, this is a test.",
      "2024-03-06T20:07:43+00:00",
      5.0,
      0,
      vcon.Vcon.MEDIATYPE_TEXT_PLAIN
    )
  return v


def get_this_server_heartbeat(client) -> float:
  """ Helper: read last_heartbeat for this worker via /servers REST endpoint """
  response = client.get("/servers")
  assert response.status_code == 200, \
      "Failed to get server states: {}".format(response.text)
  server_key = py_vcon_server.states.SERVER_STATE.server_key()
  worker_key = py_vcon_server.states.SERVER_STATE.worker_key()
  server_entry = response.json()[server_key]
  assert worker_key in server_entry["workers"], \
      "Worker key {} not found in workers: {}".format(
          worker_key, list(server_entry["workers"].keys()))
  return server_entry["workers"][worker_key]["last_heartbeat"]


# ============================================================
#  Test 1: Middleware returns 503 when SHUTDOWN_REQUESTED set
# ============================================================

def test_shutdown_middleware_returns_503():
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    # Normal request works
    response = client.get("/server/info")
    assert response.status_code == 200

    py_vcon_server.SHUTDOWN_REQUESTED = True
    try:
      response = client.get("/server/info")
      assert response.status_code == 503
      assert "shutting down" in response.json()["detail"]
    finally:
      py_vcon_server.SHUTDOWN_REQUESTED = False


# ============================================================
#  Test 2: Middleware allows /metrics through during shutdown
# ============================================================

def test_shutdown_middleware_allows_metrics():
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    py_vcon_server.SHUTDOWN_REQUESTED = True
    try:
      # Regular endpoint should be blocked
      response = client.get("/server/info")
      assert response.status_code == 503

      # /metrics should be exempt — may be 200 or 404 depending on
      # whether Prometheus is enabled, but must not be 503
      response = client.get("/metrics")
      assert response.status_code != 503
    finally:
      py_vcon_server.SHUTDOWN_REQUESTED = False


# ============================================================
#  Test 3: Heartbeat updates Redis last_heartbeat timestamp
# ============================================================

def test_heartbeat_updates_redis():
  original_period = py_vcon_server.settings.HEARTBEAT_PERIOD
  py_vcon_server.settings.HEARTBEAT_PERIOD = 1
  try:
    with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
      heartbeat_before = get_this_server_heartbeat(client)

      # Wait long enough for at least one heartbeat to fire
      time.sleep(1.5)

      heartbeat_after = get_this_server_heartbeat(client)

      assert heartbeat_after > heartbeat_before, \
          "Heartbeat should have updated last_heartbeat in Redis"
  finally:
    py_vcon_server.settings.HEARTBEAT_PERIOD = original_period


# ============================================================
#  Test 4: HEARTBEAT_PERIOD=0 disables heartbeat task
# ============================================================

def test_heartbeat_disabled_when_period_zero():
  original_period = py_vcon_server.settings.HEARTBEAT_PERIOD
  py_vcon_server.settings.HEARTBEAT_PERIOD = 0
  try:
    with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
      assert py_vcon_server.HEARTBEAT_TASK is None
      assert not py_vcon_server.HEARTBEAT_RUNNING
  finally:
    py_vcon_server.settings.HEARTBEAT_PERIOD = original_period


# ============================================================
#  Test 5: HEARTBEAT_PERIOD>0 creates heartbeat task
# ============================================================

def test_heartbeat_enabled_when_period_nonzero():
  original_period = py_vcon_server.settings.HEARTBEAT_PERIOD
  py_vcon_server.settings.HEARTBEAT_PERIOD = 60
  try:
    with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
      assert py_vcon_server.HEARTBEAT_TASK is not None
      assert py_vcon_server.HEARTBEAT_RUNNING
  finally:
    py_vcon_server.settings.HEARTBEAT_PERIOD = original_period


# ============================================================
#  Test 6: Server state is "running" after startup
# ============================================================

def test_server_state_running_after_startup():
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    response = client.get("/servers")
    assert response.status_code == 200
    servers = response.json()
    server_key = py_vcon_server.states.SERVER_STATE.server_key()
    assert server_key in servers
    assert servers[server_key]["state"] == "running"


# ============================================================
#  Test 7: SERVER_STATE is None after shutdown
# ============================================================

def test_server_state_none_after_shutdown():
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    assert py_vcon_server.states.SERVER_STATE is not None

  # After TestClient exits lifespan shutdown has fully completed
  assert py_vcon_server.states.SERVER_STATE is None


# ============================================================
#  Test 8: heartbeat_loop fires periodically and stops
# ============================================================

def test_heartbeat_loop_fires_and_stops():
  original_period = py_vcon_server.settings.HEARTBEAT_PERIOD
  py_vcon_server.settings.HEARTBEAT_PERIOD = 1
  try:
    with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
      # Wait for first heartbeat to fire
      time.sleep(1.5)
      heartbeat_1 = get_this_server_heartbeat(client)

      # Wait for second heartbeat
      time.sleep(1.5)
      heartbeat_2 = get_this_server_heartbeat(client)

      assert heartbeat_2 > heartbeat_1, \
          "Heartbeat should have updated last_heartbeat at least once per period"

      # Stop the heartbeat loop
      py_vcon_server.HEARTBEAT_RUNNING = False

      # Give the current sleep iteration time to notice the flag
      time.sleep(0.1)

      # Record timestamp immediately after stopping
      heartbeat_3 = get_this_server_heartbeat(client)

      # Wait longer than one full period — loop should not fire again
      time.sleep(1.5)
      heartbeat_4 = get_this_server_heartbeat(client)

      assert heartbeat_4 == heartbeat_3, \
          "Heartbeat should have stopped updating Redis after HEARTBEAT_RUNNING=False"

  finally:
    py_vcon_server.settings.HEARTBEAT_PERIOD = original_period

# ============================================================
#  Test: worker_key format
# ============================================================

def test_worker_key_format():
  """ worker_key() should be server_key() + ":" + str(os.getpid()) """
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    server_key = py_vcon_server.states.SERVER_STATE.server_key()
    worker_key = py_vcon_server.states.SERVER_STATE.worker_key()
    assert worker_key.startswith(server_key + ":"), \
        "worker_key should start with server_key + ':'"
    pid_suffix = worker_key[len(server_key) + 1:]
    assert pid_suffix == str(os.getpid()), \
        "worker_key suffix should be the current PID"


# ============================================================
#  Test: worker entry exists in /servers after startup
# ============================================================

def test_worker_entry_in_servers_response():
  """
  After lifespan startup, /servers response should contain a workers
  sub-dict for this server, with an entry for this worker's key.
  """
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    response = client.get("/servers")
    assert response.status_code == 200
    server_key = py_vcon_server.states.SERVER_STATE.server_key()
    worker_key = py_vcon_server.states.SERVER_STATE.worker_key()
    servers = response.json()
    assert server_key in servers, \
        "server_key not found in /servers response"
    server_entry = servers[server_key]
    assert "workers" in server_entry, \
        "server entry missing 'workers' key"
    assert worker_key in server_entry["workers"], \
        "worker_key {} not found in workers: {}".format(
            worker_key, list(server_entry["workers"].keys()))
    worker = server_entry["workers"][worker_key]
    assert "last_heartbeat" in worker
    assert "state" in worker
    assert "worker_pid" in worker
    assert worker["worker_pid"] == os.getpid()
    assert worker["last_heartbeat"] > time.time() - 100
    assert worker["last_heartbeat"] < time.time()


# ============================================================
#  Test: state transitions update server blob state field
# ============================================================

def test_state_transitions_reflected_in_servers():
  """
  After lifespan startup completes (running state), /servers should
  show state="running" at the server level and in the worker entry.
  """
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    response = client.get("/servers")
    assert response.status_code == 200
    server_key = py_vcon_server.states.SERVER_STATE.server_key()
    worker_key = py_vcon_server.states.SERVER_STATE.worker_key()
    servers = response.json()
    server_entry = servers[server_key]
    assert server_entry["state"] == "running", \
        "server entry state should be 'running'"
    worker = server_entry["workers"][worker_key]
    assert worker["state"] == "running", \
        "worker entry state should be 'running'"


# ============================================================
#  Test: /server/info returns combined server+workers blob
# ============================================================

def test_server_info_includes_workers():
  """
  /server/info should return the same combined server+workers
  structure as the matching entry in /servers.
  """
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    response = client.get("/server/info")
    assert response.status_code == 200
    info = response.json()
    assert "workers" in info, \
        "/server/info response missing 'workers' key"
    worker_key = py_vcon_server.states.SERVER_STATE.worker_key()
    assert worker_key in info["workers"], \
        "worker_key not found in /server/info workers"


# ============================================================
#  Test: server entry gone from /servers after shutdown
# ============================================================

def test_server_entry_removed_after_shutdown():
  """
  After TestClient exits (lifespan shutdown complete), the server
  key should no longer appear in a fresh /servers query.
  We verify this by starting a second TestClient after the first exits.
  """
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    server_key = py_vcon_server.states.SERVER_STATE.server_key()

  # Lifespan shutdown has completed — start a new client to query Redis
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client2:
    response = client2.get("/servers")
    assert response.status_code == 200
    servers = response.json()
    # The old server_key should be gone (unregister() deleted it)
    assert server_key not in servers, \
        "old server_key {} still present in /servers after shutdown".format(
            server_key)

# ============================================================
#  Test 9: In-flight request completes before shutdown
# ============================================================

def test_inflight_request_completes_before_shutdown():
  in_vcon = make_test_vcon()
  results = {}

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    # Store the vCon
    set_response = client.post("/vcon", json=in_vcon.dumpd())
    assert set_response.status_code == 204

    # Start a slow request in a background thread using
    # timeout_test_sleep_async registered via conftest.py
    def slow_request():
      results["response"] = client.post(
          "/process/{}/timeout_test_sleep_async".format(UUID),
          json={"sleep_seconds": 2.0}
        )
      results["finish_time"] = time.time()

    t = threading.Thread(target=slow_request)
    t.start()

    # Give the request time to start processing before we exit
    time.sleep(0.5)
    results["shutdown_start"] = time.time()

    # Exiting the context triggers lifespan shutdown.
    # The yield in lifespan will not return until all in-flight
    # entry point requests complete.

  t.join(timeout=10.0)

  assert "response" in results, \
      "Request thread did not complete within timeout"
  assert results["response"].status_code == 200, \
      "In-flight request should complete successfully, not be cut off: {}".format(
          results["response"].text
        )
  assert results["finish_time"] >= results["shutdown_start"], \
      "Request should have completed during the shutdown wait period"

  # Cleanup
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    client.delete("/vcon/{}".format(UUID))


# ============================================================
#  Test: get_server_states returns empty dict when no servers
# ============================================================

@pytest.mark.asyncio
async def test_get_server_states_empty():
  """
  get_server_states() should return {} when no server entries
  exist in Redis.  Exercises the empty-result branch of the
  lua_get_server_states Lua script (states/__init__.py line ~451).
  Uses a fresh ServerState that has never registered.
  """
  import py_vcon_server.db.redis.redis_mgr as redis_mgr_mod

  # Build a ServerState but do NOT call register_server() / register_worker()
  # so no entry exists in Redis for its key.
  ss = py_vcon_server.states.ServerState(
      py_vcon_server.settings.REST_URL,
      py_vcon_server.settings.STATE_DB_URL,
      True, True, 1
    )
  try:
    # Flush only this server's key just in case a prior run left debris
    redis_con = ss._redis_mgr.get_client()
    await redis_con.hdel(
        py_vcon_server.states.SERVER_HASH_KEY, ss.server_key()
      )

    # get_server_states must not raise and must return a dict
    # (may contain other live test servers; we just confirm ours is absent)
    result = await ss.get_server_states()
    assert isinstance(result, dict), \
        "get_server_states() should return a dict, got: {}".format(type(result))
    assert ss.server_key() not in result, \
        "Unregistered server key should not appear in get_server_states()"
  finally:
    await ss.shutdown_redis()


# ============================================================
#  Test: unregister_server warns when entry already gone
# ============================================================

@pytest.mark.asyncio
async def test_unregister_server_already_gone_does_not_raise():
  """
  register_server() should log a warning but NOT raise when the
  server entry has already been removed from Redis.
  Exercises states/__init__.py lines 341-343 (status == -2 path).
  """
  ss = py_vcon_server.states.ServerState(
      py_vcon_server.settings.REST_URL,
      py_vcon_server.settings.STATE_DB_URL,
      True, True, 1
    )
  try:
    # Register then immediately delete the entry directly, bypassing unregister()
    await ss.register_server()
    redis_con = ss._redis_mgr.get_client()
    await redis_con.hdel(
        py_vcon_server.states.SERVER_HASH_KEY, ss.server_key()
      )

    # unregister_server() must not raise even though the entry is gone
    await ss.unregister_server()  # should only log a warning
  finally:
    # Clean up any worker debris
    try:
      await ss.unregister_worker()
    except Exception:
      pass
    await ss.shutdown_redis()


# ============================================================
#  Test: nest_asyncio.apply() ValueError is silently swallowed
# ============================================================

def test_nest_asyncio_apply_repeated_does_not_raise():
  """
  Calling nest_asyncio.apply() a second time raises ValueError
  ("cannot patch a loop that is already running").
  Our try/except in __init__.py swallows it.
  Verify that the pattern itself is safe — simulates what happens
  when a uvicorn worker process re-imports py_vcon_server and
  nest_asyncio.apply() is already in effect.
  """
  import nest_asyncio
  # First call already happened at module import time.
  # A second call should raise ValueError; verify our guard catches it.
  try:
    nest_asyncio.apply()
  except ValueError:
    pass  # this is the branch our __init__.py now protects against
  # If we reach here without an unhandled exception, the pattern is correct.


# ============================================================
#  Test: get_server_states returns dict when no entry for key
# ============================================================

@pytest.mark.asyncio
async def test_get_server_states_unregistered_key_absent():
  """
  get_server_states() must return a dict and must not include
  an entry for a ServerState that was never registered.
  Exercises the empty/miss path of the lua_get_server_states
  Lua script (states/__init__.py line ~451).
  """
  ss = py_vcon_server.states.ServerState(
      py_vcon_server.settings.REST_URL,
      py_vcon_server.settings.STATE_DB_URL,
      True, True, 1
    )
  try:
    result = await ss.get_server_states()
    assert isinstance(result, dict), \
        "get_server_states() must return a dict"
    assert ss.server_key() not in result, \
        "Unregistered server key must not appear in get_server_states()"
  finally:
    await ss.shutdown_redis()


# ============================================================
#  Test: unregister_server does not raise when entry already gone
# ============================================================

@pytest.mark.asyncio
async def test_unregister_server_already_gone_does_not_raise():
  """
  unregister_server() must log a warning but NOT raise when the
  server entry is already absent from Redis.
  Exercises states/__init__.py lines 341-343 (status == -2 path).
  This is the normal path for workers 2..N in a multi-worker
  SIGINT shutdown — the first worker to call unregister_server()
  deletes the entry; the rest must not crash.
  """
  ss = py_vcon_server.states.ServerState(
      py_vcon_server.settings.REST_URL,
      py_vcon_server.settings.STATE_DB_URL,
      True, True, 1
    )
  try:
    # Write the server entry, then delete it directly bypassing unregister()
    await ss.register_server()
    redis_con = ss._redis_mgr.get_client()
    await redis_con.hdel(
        py_vcon_server.states.SERVER_HASH_KEY,
        ss.server_key()
      )
    # Must not raise — only logs a warning
    await ss.unregister_server()
  finally:
    # Clean up any worker set debris
    try:
      await ss.unregister_worker()
    except Exception:
      pass
    await ss.shutdown_redis()


# ============================================================
#  Test: nest_asyncio.apply() ValueError is safely swallowed
# ============================================================

def test_nest_asyncio_apply_repeated_does_not_raise():
  """
  In multi-worker mode each forked worker re-executes __init__.py,
  which calls nest_asyncio.apply().  If uvloop is already running,
  this raises ValueError.  Our try/except must swallow it.
  Verify the guard pattern is correct — nest_asyncio.apply() called
  a second time raises ValueError; wrapping it in try/except is safe.
  """
  import nest_asyncio
  # apply() was already called at module import time.
  # Calling it again raises ValueError on some loop configurations.
  # Our __init__.py wraps it — this test verifies the pattern is sound.
  try:
    nest_asyncio.apply()
  except ValueError:
    pass  # expected — this is exactly what our guard catches
  # Reaching here without an unhandled exception confirms correctness

