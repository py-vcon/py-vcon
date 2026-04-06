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
  """ Helper: read last_heartbeat for this server via /servers REST endpoint """
  response = client.get("/servers")
  assert response.status_code == 200, \
      "Failed to get server states: {}".format(response.text)
  server_key = py_vcon_server.states.SERVER_STATE.server_key()
  return response.json()[server_key]["last_heartbeat"]


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

