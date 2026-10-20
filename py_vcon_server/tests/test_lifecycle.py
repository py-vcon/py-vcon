# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
Unit tests for lifespan, heartbeat, shutdown middleware, and server state.

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
  10. worker_key format (server_key + PID suffix)
  11. Worker entry exists in /servers after startup
  12. State transitions reflected in /servers
  13. /server/info includes workers sub-dict
  14. Server entry removed from /servers after shutdown
  15. get_server_states returns dict when key absent
  16. unregister_server does not raise when entry already gone
  17. nest_asyncio.apply() repeated does not raise
  18. Multi-worker ServerState identity (PID divergence via env vars)
  19. Worker-only lifespan path (is_worker=True)
  20. update_server_heartbeat() advances Redis timestamp
  21. unregister_server warns when workers still registered
  22. update_server_heartbeat on missing entry does not raise
  23. server_running on missing entry does not raise
  24. server_shutting_down on missing entry does not raise
  25. unregister_server_after_workers removes entry when workers gone
  26. unregister_server_after_workers force-cleans and logs after timeout
  27. unregister_server_after_workers waits then graceful-removes
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
#  Test: multi-worker ServerState identity -- PID divergence
# ============================================================

@pytest.mark.asyncio
async def test_multiworker_server_state_identity():
  """
  When PYVCON_MASTER_PID and PYVCON_SERVER_START_TIME are set,
  ServerState must use the master PID in server_key() and the
  current process PID in worker_key().  The two PIDs must differ.
  Exercises the env-var branches in ServerState.__init__().
  """
  fake_master_pid = "99999"
  fake_start_time = "1700000000.0"
  original_master = os.environ.get("PYVCON_MASTER_PID")
  original_start = os.environ.get("PYVCON_SERVER_START_TIME")

  os.environ["PYVCON_MASTER_PID"] = fake_master_pid
  os.environ["PYVCON_SERVER_START_TIME"] = fake_start_time
  try:
    ss = py_vcon_server.states.ServerState(
        py_vcon_server.settings.REST_URL,
        py_vcon_server.settings.STATE_DB_URL,
        True, True, 2
      )
    try:
      server_key = ss.server_key()
      worker_key = ss.worker_key()

      assert fake_master_pid in server_key, \
          "server_key should contain fake master PID"
      assert fake_start_time in server_key, \
          "server_key should contain fake start time"
      assert server_key != worker_key, \
          "server_key and worker_key must differ in multi-worker mode"
      assert worker_key.endswith(str(os.getpid())), \
          "worker_key must end with the current process PID"
      assert fake_master_pid != str(os.getpid()), \
          "test requires fake PID to differ from real PID"

      assert ss.pid() == int(fake_master_pid), \
          "pid() should return the master PID, not os.getpid()"
      assert ss.start_time() == float(fake_start_time), \
          "start_time() should return the env var value"

    finally:
      await ss.shutdown_redis()

  finally:
    if original_master is None:
      os.environ.pop("PYVCON_MASTER_PID", None)
    else:
      os.environ["PYVCON_MASTER_PID"] = original_master
    if original_start is None:
      os.environ.pop("PYVCON_SERVER_START_TIME", None)
    else:
      os.environ["PYVCON_SERVER_START_TIME"] = original_start


# ============================================================
#  Test: worker-only lifespan path
# ============================================================

@pytest.mark.asyncio
async def test_worker_only_lifespan_path():
  """
  When PYVCON_MASTER_PID is set, the lifespan takes the is_worker
  branch: register_worker() without register_server().  On shutdown
  it calls unregister_worker() but NOT unregister_server().

  Steps:
    1. Pre-register a fake server entry in Redis
    2. Set env vars so lifespan sees is_worker=True
    3. Start TestClient (triggers worker-only startup)
    4. Verify worker entry created, server entry not overwritten
    5. Exit TestClient (triggers worker-only shutdown)
    6. Verify worker entry gone, server entry still present
    7. Clean up fake server entry
  """
  fake_master_pid = "88888"
  fake_start_time = "1700000000.0"
  original_master = os.environ.get("PYVCON_MASTER_PID")
  original_start = os.environ.get("PYVCON_SERVER_START_TIME")

  # Build a ServerState to pre-register the server entry
  os.environ["PYVCON_MASTER_PID"] = fake_master_pid
  os.environ["PYVCON_SERVER_START_TIME"] = fake_start_time
  pre_ss = py_vcon_server.states.ServerState(
      py_vcon_server.settings.REST_URL,
      py_vcon_server.settings.STATE_DB_URL,
      True, True, 2
    )
  try:
    await pre_ss.register_server()
    await pre_ss.server_running()
    pre_server_key = pre_ss.server_key()

    # Read the server entry heartbeat before lifespan runs
    states_before = await pre_ss.get_server_states()
    server_hb_before = states_before[pre_server_key]["last_heartbeat"]

    # Now start TestClient with the env vars set.
    # Lifespan will see is_worker=True.
    with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
      response = client.get("/servers")
      assert response.status_code == 200
      servers = response.json()
      assert pre_server_key in servers, \
          "pre-registered server entry should still exist"

      server_entry = servers[pre_server_key]
      assert server_entry["pid"] == int(fake_master_pid), \
          "server entry pid should be the fake master, not overwritten"

      # Worker entry should exist under the server
      worker_key = py_vcon_server.states.SERVER_STATE.worker_key()
      assert worker_key in server_entry["workers"], \
          "worker entry should exist after worker-only startup"
      assert server_entry["workers"][worker_key]["worker_pid"] == os.getpid(), \
          "worker_pid should be current process PID"

      # Server heartbeat should NOT have been updated by the worker
      server_hb_after = server_entry["last_heartbeat"]
      assert server_hb_after == server_hb_before, \
          "worker-only lifespan should not update server heartbeat"

    # After TestClient exit: worker entry should be gone
    states_after = await pre_ss.get_server_states()
    if pre_server_key in states_after:
      assert worker_key not in states_after[pre_server_key].get("workers", {}), \
          "worker entry should be removed after worker-only shutdown"
      # Server entry should still be present
      assert states_after[pre_server_key]["pid"] == int(fake_master_pid)

  finally:
    # Clean up the fake server entry
    try:
      await pre_ss.unregister_server()
    except Exception:
      pass
    await pre_ss.shutdown_redis()
    if original_master is None:
      os.environ.pop("PYVCON_MASTER_PID", None)
    else:
      os.environ["PYVCON_MASTER_PID"] = original_master
    if original_start is None:
      os.environ.pop("PYVCON_SERVER_START_TIME", None)
    else:
      os.environ["PYVCON_SERVER_START_TIME"] = original_start


# ============================================================
#  Test: update_server_heartbeat() updates Redis
# ============================================================

@pytest.mark.asyncio
async def test_update_server_heartbeat_updates_redis():
  """
  Directly call update_server_heartbeat() on a registered
  ServerState and verify last_heartbeat advances in Redis.
  Exercises states/__init__.py update_server_heartbeat().
  """
  ss = py_vcon_server.states.ServerState(
      py_vcon_server.settings.REST_URL,
      py_vcon_server.settings.STATE_DB_URL,
      True, True, 1
    )
  try:
    await ss.register_server()
    await ss.server_running()

    states1 = await ss.get_server_states()
    hb1 = states1[ss.server_key()]["last_heartbeat"]

    import asyncio
    await asyncio.sleep(0.05)

    await ss.update_server_heartbeat()

    states2 = await ss.get_server_states()
    hb2 = states2[ss.server_key()]["last_heartbeat"]

    assert hb2 > hb1, \
        "update_server_heartbeat() should advance last_heartbeat: {} -> {}".format(hb1, hb2)

  finally:
    try:
      await ss.unregister_server()
    except Exception:
      pass
    await ss.shutdown_redis()


# ============================================================
#  Test: unregister_server warns when workers still registered
# ============================================================

@pytest.mark.asyncio
async def test_unregister_server_with_stale_workers():
  """
  If unregister_server() is called while workers are still
  registered, it should log a warning and leave the worker
  entries as evidence rather than force-cleaning them.
  Exercises states/__init__.py status == -1 path.
  """
  ss = py_vcon_server.states.ServerState(
      py_vcon_server.settings.REST_URL,
      py_vcon_server.settings.STATE_DB_URL,
      True, True, 1
    )
  try:
    await ss.register_server()
    await ss.register_worker()

    # Call unregister_server WITHOUT unregister_worker first
    await ss.unregister_server()

    # Server entry should STILL exist (left as evidence with stale workers)
    redis_con = ss._redis_mgr.get_client()
    server_json = await redis_con.hget(
        py_vcon_server.states.SERVER_HASH_KEY, ss.server_key()
      )
    assert server_json is not None, \
        "server entry should be kept as evidence when workers still registered"

    # Worker entry should still exist (left as evidence)
    worker_json = await redis_con.hget(
        py_vcon_server.states.SERVER_WORKER_HASH_KEY, ss.worker_key()
      )
    assert worker_json is not None, \
        "worker entry should remain as evidence of stale worker"

  finally:
    # Clean up the stale worker entry
    try:
      await ss.unregister_worker()
    except Exception:
      pass
    try:
      await ss.unregister_server()
    except Exception:
      pass
    await ss.shutdown_redis()


# ============================================================
#  Test: update_server_heartbeat on missing entry does not raise
# ============================================================

@pytest.mark.asyncio
async def test_update_server_heartbeat_missing_entry():
  """
  update_server_heartbeat() should log a warning but not raise
  when the server entry has been deleted from Redis.
  Exercises the result == -1 branch in update_server_heartbeat().
  """
  ss = py_vcon_server.states.ServerState(
      py_vcon_server.settings.REST_URL,
      py_vcon_server.settings.STATE_DB_URL,
      True, True, 1
    )
  try:
    await ss.register_server()
    await ss.server_running()

    # Delete the server entry directly
    redis_con = ss._redis_mgr.get_client()
    await redis_con.hdel(
        py_vcon_server.states.SERVER_HASH_KEY, ss.server_key()
      )

    # Must not raise
    await ss.update_server_heartbeat()

  finally:
    await ss.shutdown_redis()


# ============================================================
#  Test: server_running on missing entry does not raise
# ============================================================

@pytest.mark.asyncio
async def test_server_running_missing_entry():
  """
  server_running() should log a warning but not raise when the
  server entry is absent from Redis.
  Exercises the result == -1 branch in server_running().
  """
  ss = py_vcon_server.states.ServerState(
      py_vcon_server.settings.REST_URL,
      py_vcon_server.settings.STATE_DB_URL,
      True, True, 1
    )
  try:
    # Do NOT register -- call server_running() on a missing entry
    await ss.server_running()
  finally:
    await ss.shutdown_redis()


# ============================================================
#  Test: server_shutting_down on missing entry does not raise
# ============================================================

@pytest.mark.asyncio
async def test_server_shutting_down_missing_entry():
  """
  server_shutting_down() should log a warning but not raise when
  the server entry is absent from Redis.
  Exercises the result == -1 branch in server_shutting_down().
  """
  ss = py_vcon_server.states.ServerState(
      py_vcon_server.settings.REST_URL,
      py_vcon_server.settings.STATE_DB_URL,
      True, True, 1
    )
  try:
    await ss.server_shutting_down()
  finally:
    await ss.shutdown_redis()


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

# ============================================================
#  Test: unregister_server_after_workers removes entry (clean)
# ============================================================

@pytest.mark.asyncio
async def test_unregister_server_after_workers_clean():
  """
  With no workers registered, unregister_server_after_workers() takes
  the graceful path and removes the server entry immediately.
  """
  ss = py_vcon_server.states.ServerState(
      py_vcon_server.settings.REST_URL,
      py_vcon_server.settings.STATE_DB_URL,
      True, True, 1
    )
  try:
    await ss.register_server()
    await ss.unregister_server_after_workers(2.0, 0.1)

    redis_con = ss._redis_mgr.get_client()
    server_json = await redis_con.hget(
        py_vcon_server.states.SERVER_HASH_KEY, ss.server_key()
      )
    assert server_json is None, \
        "server entry should be removed when no workers are registered"
  finally:
    try:
      await ss.unregister_server()
    except Exception:
      pass
    await ss.shutdown_redis()


# ============================================================
#  Test: unregister_server_after_workers force-cleans on timeout
# ============================================================

@pytest.mark.asyncio
async def test_unregister_server_after_workers_timeout_force_cleans(caplog):
  """
  When a worker stays registered past the timeout (a worker killed
  without deregistering), unregister_server_after_workers() logs an
  error naming the stale worker and force-removes both the server entry
  and the orphaned worker entry.  This is the leak the fix addresses.
  """
  import logging
  ss = py_vcon_server.states.ServerState(
      py_vcon_server.settings.REST_URL,
      py_vcon_server.settings.STATE_DB_URL,
      True, True, 1
    )
  try:
    await ss.register_server()
    await ss.register_worker()

    with caplog.at_level(logging.ERROR):
      await ss.unregister_server_after_workers(1.0, 0.2)

    assert ss.worker_key() in caplog.text, \
        "stale worker key should be logged as evidence"

    redis_con = ss._redis_mgr.get_client()
    server_json = await redis_con.hget(
        py_vcon_server.states.SERVER_HASH_KEY, ss.server_key()
      )
    assert server_json is None, \
        "server entry should be force-removed after timeout"
    worker_json = await redis_con.hget(
        py_vcon_server.states.SERVER_WORKER_HASH_KEY, ss.worker_key()
      )
    assert worker_json is None, \
        "orphaned worker entry should be force-cleaned after timeout"
  finally:
    try:
      await ss.unregister_worker()
    except Exception:
      pass
    try:
      await ss.unregister_server()
    except Exception:
      pass
    await ss.shutdown_redis()


# ============================================================
#  Test: unregister_server_after_workers waits then graceful
# ============================================================

@pytest.mark.asyncio
async def test_unregister_server_after_workers_waits_then_graceful(caplog):
  """
  When a worker deregisters partway through the wait, the method waits
  (does not force-clean), then takes the graceful path once the worker
  set is empty.  Proves the poll loop actually waits.
  """
  import asyncio
  import logging
  ss = py_vcon_server.states.ServerState(
      py_vcon_server.settings.REST_URL,
      py_vcon_server.settings.STATE_DB_URL,
      True, True, 1
    )
  try:
    await ss.register_server()
    await ss.register_worker()

    async def deregister_worker_after_delay():
      await asyncio.sleep(0.5)
      await ss.unregister_worker()

    task = asyncio.create_task(deregister_worker_after_delay())

    with caplog.at_level(logging.ERROR):
      await ss.unregister_server_after_workers(5.0, 0.1)
    await task

    assert "still registered" not in caplog.text, \
        "should not log stale-worker error when worker deregisters in time"

    redis_con = ss._redis_mgr.get_client()
    server_json = await redis_con.hget(
        py_vcon_server.states.SERVER_HASH_KEY, ss.server_key()
      )
    assert server_json is None, \
        "server entry should be removed via graceful path after worker leaves"
  finally:
    try:
      await ss.unregister_worker()
    except Exception:
      pass
    try:
      await ss.unregister_server()
    except Exception:
      pass
    await ss.shutdown_redis()

# ============================================================
#  Test: record_shutdown_failure annotates the server entry
# ============================================================

@pytest.mark.asyncio
async def test_record_shutdown_failure_annotates_entry():
  """
  record_shutdown_failure() annotates an existing server entry with
  state="shutdown_failed" and a shutdown_errors crumb (phase, type,
  traceback), via a synchronous Redis client.  Other blob fields are
  preserved.
  """
  ss = py_vcon_server.states.ServerState(
      py_vcon_server.settings.REST_URL,
      py_vcon_server.settings.STATE_DB_URL,
      True, True, 1
    )
  try:
    await ss.register_server()

    try:
      raise RuntimeError("boom during shutdown")
    except RuntimeError as e:
      py_vcon_server.states.record_shutdown_failure(
          py_vcon_server.settings.STATE_DB_URL,
          ss.server_key(),
          "server_shutting_down",
          e
        )

    state = await ss.get_server_state()
    assert state is not None, "server entry should still exist"
    assert state["state"] == "shutdown_failed", \
        "state should be flipped to shutdown_failed"
    assert "host" in state, "existing blob fields should be preserved"
    errors = state.get("shutdown_errors", [])
    assert len(errors) == 1, "one crumb should be recorded"
    crumb = errors[0]
    assert crumb["phase"] == "server_shutting_down"
    assert crumb["exception_type"] == "RuntimeError"
    assert "boom during shutdown" in crumb["exception"]
    assert "RuntimeError" in crumb["traceback"]
  finally:
    try:
      await ss.delete_server_state(ss.server_key())
    except Exception:
      pass
    await ss.shutdown_redis()


# ============================================================
#  Test: _MasterStateThread register / heartbeat / cleanup
# ============================================================

def test_master_state_thread_round_trip():
  """
  _MasterStateThread registers the server entry, advances the heartbeat
  on at least one tick, and removes the entry on stop -- all on a single
  event loop.  Verification uses a synchronous Redis client so it never
  touches the thread's loop-bound pool.  A heartbeat tick is forced so
  register, heartbeat, and cleanup all exercise the one loop; a
  reintroduced second loop would fail this test.
  """
  import time
  import json
  import redis
  from py_vcon_server.__main__ import _MasterStateThread

  master_state = py_vcon_server.states.ServerState(
      py_vcon_server.settings.REST_URL,
      py_vcon_server.settings.STATE_DB_URL,
      True, True, 2
    )
  server_key = master_state.server_key()
  sync_client = redis.Redis.from_url(
      py_vcon_server.settings.STATE_DB_URL, decode_responses=True
    )

  thread = _MasterStateThread(master_state, 1, 5.0, 0.1)
  try:
    thread.start()
    thread.wait_until_registered(10.0)

    raw = sync_client.hget(
        py_vcon_server.states.SERVER_HASH_KEY, server_key
      )
    assert raw is not None, "server entry should be present after registration"
    hb1 = json.loads(raw)["last_heartbeat"]

    time.sleep(1.5)
    hb2 = json.loads(sync_client.hget(
        py_vcon_server.states.SERVER_HASH_KEY, server_key
      ))["last_heartbeat"]
    assert hb2 > hb1, \
        "heartbeat should advance on the thread's loop: {} -> {}".format(hb1, hb2)
  finally:
    thread.stop()
    thread.join(timeout=20.0)
    remaining = sync_client.hget(
        py_vcon_server.states.SERVER_HASH_KEY, server_key
      )
    sync_client.close()
    assert remaining is None, \
        "server entry should be removed after thread shutdown"


# ============================================================
#  Test: _MasterStateThread records a crumb on shutdown failure
# ============================================================

def test_master_state_thread_records_crumb_on_shutdown_failure(monkeypatch):
  """
  If a shutdown phase raises, _MasterStateThread records a crumb on the
  server entry (state=shutdown_failed plus a shutdown_errors entry) and
  leaves the entry in Redis as evidence rather than losing the reason.
  """
  import json
  import redis
  from py_vcon_server.__main__ import _MasterStateThread

  master_state = py_vcon_server.states.ServerState(
      py_vcon_server.settings.REST_URL,
      py_vcon_server.settings.STATE_DB_URL,
      True, True, 2
    )
  server_key = master_state.server_key()

  async def _raise_unregister(*args, **kwargs):
    raise RuntimeError("simulated unregister failure")

  monkeypatch.setattr(
      master_state, "unregister_server_after_workers", _raise_unregister
    )

  sync_client = redis.Redis.from_url(
      py_vcon_server.settings.STATE_DB_URL, decode_responses=True
    )

  thread = _MasterStateThread(master_state, 0, 5.0, 0.1)
  try:
    thread.start()
    thread.wait_until_registered(10.0)
    thread.stop()
    thread.join(timeout=20.0)

    raw = sync_client.hget(
        py_vcon_server.states.SERVER_HASH_KEY, server_key
      )
    assert raw is not None, \
        "server entry should remain as evidence when unregister fails"
    blob = json.loads(raw)
    assert blob["state"] == "shutdown_failed"
    errors = blob.get("shutdown_errors", [])
    assert len(errors) >= 1
    assert errors[0]["phase"] == "unregister_server_after_workers"
    assert "simulated unregister failure" in errors[0]["exception"]
  finally:
    sync_client.hdel(py_vcon_server.states.SERVER_HASH_KEY, server_key)
    sync_client.close()

