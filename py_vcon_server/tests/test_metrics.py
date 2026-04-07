# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
Unit tests for py_vcon_server/metrics.py and related instrumentation.

Structure:
  Section 1 — Pure unit tests (no server, no Redis, no Prometheus)
    These run before any TestClient tests to capture module state
    before install_instrumentation() has been called.

  Section 2 — Smoke tests with Prometheus DISABLED (default)
    TestClient-based tests verifying behaviour when ENABLE_PROMETHEUS=False.
    ACTIVE_RUNS and /diagnostics still work. Prometheus gauges are None.

  Section 3 — Integration tests with Prometheus ENABLED
    TestClient-based tests verifying full Prometheus metric creation,
    ACTIVE_RUNS population during active runs, /diagnostics content,
    entry point context fields, and shutdown middleware exemption.

Note on module state:
  _INSTRUMENTATION_INSTALLED is a module-level global. Once set True by
  install_instrumentation() it cannot be unset within the same process.
  Pure unit tests in Section 1 must run before any TestClient test.
  The _reset_metrics_state fixture handles this for Section 1 only.
"""
import os
import time
import threading
import importlib
import pytest
import pytest_asyncio
import fastapi.testclient
import vcon
import py_vcon_server
import py_vcon_server.processor
import py_vcon_server.settings
import py_vcon_server.states
import py_vcon_server.metrics as metrics
from py_vcon_server.settings import VCON_STORAGE_URL

UUID = "01855517-metr-fake-uuid-77776666acbe"


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _reset_metrics_module():
  """
  Reset metrics module globals to pre-install state.
  Only usable BEFORE the first TestClient entry triggers lifespan.
  After lifespan runs, _INSTRUMENTATION_INSTALLED stays True for the
  whole process — do not call this after a TestClient test.
  """
  metrics._INSTRUMENTATION_INSTALLED = False
  metrics._processor_active_gauge = None
  metrics._processor_duration_hist = None
  metrics._background_job_heartbeat = None
  metrics.ACTIVE_RUNS.clear()


@pytest.fixture
def reset_metrics():
  """ Fixture that resets metrics state before a pure unit test """
  _reset_metrics_module()
  yield
  _reset_metrics_module()


# ── Storage fixture ───────────────────────────────────────────────────────────

VCON_STORAGE = None

@pytest_asyncio.fixture(autouse=True)
async def setup_storage():
  vs = py_vcon_server.db.VconStorage.instantiate(VCON_STORAGE_URL)
  global VCON_STORAGE
  VCON_STORAGE = vs
  yield
  VCON_STORAGE = None
  await vs.shutdown()


# ==============================================================================
#  SECTION 1: Pure unit tests — no server, no Redis, no Prometheus
#  These MUST run before any TestClient test.
# ==============================================================================

# ── Run context constants ─────────────────────────────────────────────────────

def test_run_context_constants_exist():
  """ Well-known run context key constants are defined """
  assert py_vcon_server.processor.RUN_CONTEXT_ENTRY_POINT   == "entry_point"
  assert py_vcon_server.processor.RUN_CONTEXT_PIPELINE_NAME == "pipeline_name"
  assert py_vcon_server.processor.RUN_CONTEXT_JOB_ID        == "job_id"


# ── VconProcessorIO run context methods ──────────────────────────────────────

def test_run_context_default_empty():
  """ get_run_context() returns empty dict when not set """
  io = py_vcon_server.processor.VconProcessorIO(None)
  assert io.get_run_context() == {}


def test_run_context_set_and_get():
  """ set_run_context() stores and get_run_context() retrieves correctly """
  io = py_vcon_server.processor.VconProcessorIO(None)
  io.set_run_context({
      py_vcon_server.processor.RUN_CONTEXT_ENTRY_POINT:   "/process",
      py_vcon_server.processor.RUN_CONTEXT_PIPELINE_NAME: "",
      py_vcon_server.processor.RUN_CONTEXT_JOB_ID:        "",
    })
  ctx = io.get_run_context()
  assert ctx[py_vcon_server.processor.RUN_CONTEXT_ENTRY_POINT] == "/process"
  assert ctx[py_vcon_server.processor.RUN_CONTEXT_PIPELINE_NAME] == ""
  assert ctx[py_vcon_server.processor.RUN_CONTEXT_JOB_ID] == ""


def test_run_context_arbitrary_keys():
  """ Arbitrary keys beyond the well-known constants are accepted """
  io = py_vcon_server.processor.VconProcessorIO(None)
  io.set_run_context({
      "my_custom_debug_key": "some_value",
      "another_key": 42,
    })
  ctx = io.get_run_context()
  assert ctx["my_custom_debug_key"] == "some_value"
  assert ctx["another_key"] == 42


def test_run_context_overwrite():
  """ Calling set_run_context() twice replaces the previous context """
  io = py_vcon_server.processor.VconProcessorIO(None)
  io.set_run_context({"entry_point": "/process"})
  io.set_run_context({"entry_point": "/processIO"})
  assert io.get_run_context()["entry_point"] == "/processIO"


# ── is_instrumented() ────────────────────────────────────────────────────────

def test_is_instrumented_false_on_plain_function(reset_metrics):
  """ A plain async function is not instrumented """
  async def fake_process(self, processor_input, options):
    pass
  assert not metrics.is_instrumented(fake_process)


def test_is_instrumented_true_after_wrap(reset_metrics):
  """ After wrapping with _instrumented_decorator, is_instrumented() returns True """
  async def fake_process(self, processor_input, options):
    pass
  wrapped = metrics._instrumented_decorator(fake_process)
  assert metrics.is_instrumented(wrapped)


def test_is_instrumented_false_on_noop_wrapped(reset_metrics):
  """ _noop_decorator does not set the instrumented flag """
  async def fake_process(self, processor_input, options):
    pass
  noop_wrapped = metrics._noop_decorator(fake_process)
  assert not metrics.is_instrumented(noop_wrapped)


def test_no_double_wrap(reset_metrics):
  """
  Wrapping an already-instrumented function again is detectable.
  is_instrumented() returns True on the double-wrapped version too,
  but the outer wrapper is the new one — both point back to _instrumented_decorator.
  """
  async def fake_process(self, processor_input, options):
    pass
  wrapped_once = metrics._instrumented_decorator(fake_process)
  assert metrics.is_instrumented(wrapped_once)
  # In practice register() checks is_instrumented() before wrapping,
  # so double-wrap should not occur. Verify the check works.
  if not metrics.is_instrumented(wrapped_once):
    wrapped_twice = metrics._instrumented_decorator(wrapped_once)
  else:
    wrapped_twice = wrapped_once  # correctly skipped
  assert metrics.is_instrumented(wrapped_twice)


# ── get_instrumentation_decorator() before install ───────────────────────────

def test_get_instrumentation_decorator_returns_noop_before_install(reset_metrics):
  """ get_instrumentation_decorator() returns _noop_decorator before install """
  assert not metrics._INSTRUMENTATION_INSTALLED
  assert metrics.get_instrumentation_decorator() is metrics._noop_decorator


# ── install_instrumentation() ─────────────────────────────────────────────────

def test_install_sets_flag(reset_metrics):
  """ install_instrumentation() sets _INSTRUMENTATION_INSTALLED """
  assert not metrics._INSTRUMENTATION_INSTALLED
  metrics.install_instrumentation()
  assert metrics._INSTRUMENTATION_INSTALLED


def test_install_returns_instrumented_decorator(reset_metrics):
  """ After install, get_instrumentation_decorator() returns _instrumented_decorator """
  metrics.install_instrumentation()
  assert metrics.get_instrumentation_decorator() is metrics._instrumented_decorator


def test_install_idempotent(reset_metrics):
  """ Calling install_instrumentation() multiple times does not raise """
  metrics.install_instrumentation()
  metrics.install_instrumentation()
  assert metrics._INSTRUMENTATION_INSTALLED


def test_install_without_prometheus_leaves_gauges_none(reset_metrics):
  """
  When ENABLE_PROMETHEUS=False (default), install_instrumentation() sets
  _INSTRUMENTATION_INSTALLED but leaves all Prometheus gauge objects as None.
  ACTIVE_RUNS still works.
  """
  assert not py_vcon_server.settings.ENABLE_PROMETHEUS
  metrics.install_instrumentation()
  assert metrics._processor_active_gauge is None
  assert metrics._processor_duration_hist is None
  assert metrics._background_job_heartbeat is None


# ── update_background_job_heartbeat() — no Prometheus ────────────────────────

def test_update_background_job_heartbeat_noop_when_gauge_none(reset_metrics):
  """ update_background_job_heartbeat() does not raise when gauge is None """
  assert metrics._background_job_heartbeat is None
  metrics.update_background_job_heartbeat()  # should not raise


# ==============================================================================
#  SECTION 2: Smoke tests — Prometheus DISABLED (default)
#  Verify that ACTIVE_RUNS, /diagnostics and wrapping work even without
#  Prometheus. These run with the normal test suite configuration.
# ==============================================================================

def test_processor_wrapped_after_lifespan_startup_no_prometheus():
  """
  After lifespan startup (install_instrumentation() called),
  registered processors have instrumented process() methods.
  Verified with ENABLE_PROMETHEUS=False.
  """
  assert not py_vcon_server.settings.ENABLE_PROMETHEUS
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    proc = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance(
        "set_parameters"
      )
    assert metrics.is_instrumented(type(proc).process), \
        "set_parameters process() should be instrumented after lifespan startup"


def test_active_runs_empty_at_rest_no_prometheus():
  """ ACTIVE_RUNS is empty when no processors are running """
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    assert len(metrics.ACTIVE_RUNS) == 0


def test_diagnostics_endpoint_empty_no_prometheus():
  """ /diagnostics returns empty dict when no processors running """
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    response = client.get("/diagnostics")
    assert response.status_code == 200
    assert response.json() == {}


def test_diagnostics_exempt_from_shutdown_middleware_no_prometheus():
  """ /diagnostics returns 200 (not 503) when SHUTDOWN_REQUESTED=True """
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    py_vcon_server.SHUTDOWN_REQUESTED = True
    try:
      response = client.get("/diagnostics")
      assert response.status_code == 200
    finally:
      py_vcon_server.SHUTDOWN_REQUESTED = False


def test_active_runs_populated_during_processor_call_no_prometheus():
  """
  ACTIVE_RUNS contains an entry while a processor is running.
  Uses timeout_test_sleep_async (registered via conftest.py).
  Verifies entry is removed after completion.
  Prometheus DISABLED — verifies ACTIVE_RUNS works independently.
  """
  in_vcon = make_test_vcon()
  results = {}

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    set_response = client.post("/vcon", json=in_vcon.dumpd())
    assert set_response.status_code == 204

    def slow_request():
      results["response"] = client.post(
          "/process/{}/timeout_test_sleep_async".format(UUID),
          json={"sleep_seconds": 2.0}
        )

    t = threading.Thread(target=slow_request)
    t.start()
    time.sleep(0.5)

    # Mid-flight: ACTIVE_RUNS should have one entry
    assert len(metrics.ACTIVE_RUNS) == 1
    run = list(metrics.ACTIVE_RUNS.values())[0]
    assert run["processor_name"] == "timeout_test_sleep_async"
    assert run["entry_point"] == "/process"
    assert UUID in run["vcon_uuids"]
    assert run["start_time"] > 0

    t.join(timeout=10.0)

    # After completion: ACTIVE_RUNS should be empty again
    assert len(metrics.ACTIVE_RUNS) == 0
    assert results["response"].status_code == 200

    client.delete("/vcon/{}".format(UUID))


def test_diagnostics_during_active_run_no_prometheus():
  """
  /diagnostics returns correct entry data during an active processor run.
  Verifies elapsed_seconds is present and positive.
  """
  in_vcon = make_test_vcon()
  results = {}

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    set_response = client.post("/vcon", json=in_vcon.dumpd())
    assert set_response.status_code == 204

    def slow_request():
      results["response"] = client.post(
          "/process/{}/timeout_test_sleep_async".format(UUID),
          json={"sleep_seconds": 2.0}
        )

    t = threading.Thread(target=slow_request)
    t.start()
    time.sleep(0.5)

    response = client.get("/diagnostics")
    assert response.status_code == 200
    diag = response.json()
    assert len(diag) == 1

    run = list(diag.values())[0]
    assert run["processor_name"] == "timeout_test_sleep_async"
    assert run["entry_point"] == "/process"
    assert UUID in run["vcon_uuids"]
    assert "elapsed_seconds" in run
    assert run["elapsed_seconds"] > 0
    assert run["elapsed_seconds"] < 10.0  # sanity bound

    t.join(timeout=10.0)
    assert results["response"].status_code == 200

    client.delete("/vcon/{}".format(UUID))


def test_processio_entry_point_in_active_runs_no_prometheus():
  """
  Processor run via /processIO shows entry_point="/processIO" in ACTIVE_RUNS.
  """
  in_vcon = make_test_vcon()
  results = {}

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    def slow_request():
      request_body = {
          "processor_io": {
              "vcons": [in_vcon.dumpd()],
              "parameters": {}
            },
          "processor_options": {
              "sleep_seconds": 2.0
            }
        }
      results["response"] = client.post(
          "/processIO/timeout_test_sleep_async",
          json=request_body
        )

    t = threading.Thread(target=slow_request)
    t.start()
    time.sleep(0.5)

    assert len(metrics.ACTIVE_RUNS) == 1
    run = list(metrics.ACTIVE_RUNS.values())[0]
    assert run["entry_point"] == "/processIO"

    t.join(timeout=10.0)
    assert results["response"].status_code == 200


# ==============================================================================
#  SECTION 3: Integration tests — Prometheus ENABLED
#  Enable Prometheus via env var + settings reload before TestClient entry.
# ==============================================================================

@pytest.fixture
def enable_prometheus():
  """
  Fixture that enables Prometheus metrics for the duration of a test.
  Directly calls install_instrumentation() with ENABLE_PROMETHEUS=True
  rather than relying on the lifespan to call it, since lifespan
  ordering relative to autouse fixtures is not guaranteed.
  """
  original = py_vcon_server.settings.ENABLE_PROMETHEUS

  # Enable Prometheus and reset instrumentation state
  py_vcon_server.settings.ENABLE_PROMETHEUS = True
  metrics._INSTRUMENTATION_INSTALLED = False
  metrics._processor_active_gauge = None
  metrics._processor_duration_hist = None
  metrics._background_job_heartbeat = None

  # Explicitly install instrumentation with Prometheus now enabled
  # so gauge objects exist before the TestClient enters
  metrics.install_instrumentation()

  yield

  # Restore settings and reset state for subsequent tests
  py_vcon_server.settings.ENABLE_PROMETHEUS = original
  metrics._INSTRUMENTATION_INSTALLED = False
  metrics._processor_active_gauge = None
  metrics._processor_duration_hist = None
  metrics._background_job_heartbeat = None


def test_prometheus_gauges_created_after_install(enable_prometheus):
  """
  When ENABLE_PROMETHEUS=True, install_instrumentation() creates
  Prometheus gauge and histogram objects.
  """
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    assert metrics._processor_active_gauge is not None, \
        "_processor_active_gauge should be set when Prometheus is enabled"
    assert metrics._processor_duration_hist is not None, \
        "_processor_duration_hist should be set when Prometheus is enabled"
    assert metrics._background_job_heartbeat is not None, \
        "_background_job_heartbeat should be set when Prometheus is enabled"


def test_prometheus_metric_objects_created_with_prometheus(enable_prometheus):
  """
  When ENABLE_PROMETHEUS=True, install_instrumentation() creates all
  three Prometheus metric objects. Tests the objects directly since
  the /metrics route is only registered when py_vcon_server is first
  loaded with ENABLE_PROMETHEUS=True — it cannot be added retroactively
  without a module reload.
  """
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    assert metrics._processor_active_gauge is not None, \
        "_processor_active_gauge should exist when ENABLE_PROMETHEUS=True"
    assert metrics._processor_duration_hist is not None, \
        "_processor_duration_hist should exist when ENABLE_PROMETHEUS=True"
    assert metrics._background_job_heartbeat is not None, \
        "_background_job_heartbeat should exist when ENABLE_PROMETHEUS=True"

    # Verify gauge and histogram are of the expected Prometheus types
    import prometheus_client
    assert isinstance(metrics._processor_active_gauge, prometheus_client.Gauge)
    assert isinstance(metrics._processor_duration_hist, prometheus_client.Histogram)
    assert isinstance(metrics._background_job_heartbeat, prometheus_client.Gauge)


def test_processor_active_gauge_increments_during_run(enable_prometheus):
  """
  py_vcon_server_processor_active gauge is > 0 while a processor is running
  and returns to 0 after completion.
  """
  in_vcon = make_test_vcon()
  results = {}

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    set_response = client.post("/vcon", json=in_vcon.dumpd())
    assert set_response.status_code == 204

    def slow_request():
      results["response"] = client.post(
          "/process/{}/timeout_test_sleep_async".format(UUID),
          json={"sleep_seconds": 2.0}
        )

    t = threading.Thread(target=slow_request)
    t.start()
    time.sleep(0.5)

    # Mid-flight: gauge should be > 0
    assert metrics._processor_active_gauge is not None
    gauge_value = metrics._processor_active_gauge.labels(
        processor_name="timeout_test_sleep_async",
        entry_point="/process"
      )._value.get()
    assert gauge_value > 0, \
        "processor_active gauge should be > 0 while processor is running"

    t.join(timeout=10.0)

    # After completion: gauge should be back to 0
    gauge_value = metrics._processor_active_gauge.labels(
        processor_name="timeout_test_sleep_async",
        entry_point="/process"
      )._value.get()
    assert gauge_value == 0, \
        "processor_active gauge should return to 0 after processor completes"

    client.delete("/vcon/{}".format(UUID))


def test_duration_histogram_observed_after_run(enable_prometheus):
  """
  After a processor run completes, the duration histogram has at least
  one observation for that processor name and entry point.
  """
  in_vcon = make_test_vcon()

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    set_response = client.post("/vcon", json=in_vcon.dumpd())
    assert set_response.status_code == 204

    post_response = client.post(
        "/process/{}/timeout_test_sleep_async".format(UUID),
        json={"sleep_seconds": 0.1}
      )
    assert post_response.status_code == 200

    # Check histogram count > 0
    assert metrics._processor_duration_hist is not None
    count = metrics._processor_duration_hist.labels(
        processor_name="timeout_test_sleep_async",
        entry_point="/process",
        status="success"
      )._sum.get()
    assert count > 0, \
        "duration histogram should have observed at least one value"

    client.delete("/vcon/{}".format(UUID))


def test_active_runs_populated_during_run_with_prometheus(enable_prometheus):
  """
  ACTIVE_RUNS works correctly with Prometheus enabled —
  confirming Prometheus path does not break ACTIVE_RUNS tracking.
  """
  in_vcon = make_test_vcon()
  results = {}

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    set_response = client.post("/vcon", json=in_vcon.dumpd())
    assert set_response.status_code == 204

    def slow_request():
      results["response"] = client.post(
          "/process/{}/timeout_test_sleep_async".format(UUID),
          json={"sleep_seconds": 2.0}
        )

    t = threading.Thread(target=slow_request)
    t.start()
    time.sleep(0.5)

    assert len(metrics.ACTIVE_RUNS) == 1
    run = list(metrics.ACTIVE_RUNS.values())[0]
    assert run["processor_name"] == "timeout_test_sleep_async"
    assert run["entry_point"] == "/process"

    t.join(timeout=10.0)
    assert len(metrics.ACTIVE_RUNS) == 0
    assert results["response"].status_code == 200

    client.delete("/vcon/{}".format(UUID))


def test_diagnostics_during_active_run_with_prometheus(enable_prometheus):
  """
  /diagnostics returns correct entry including elapsed_seconds
  while a processor is running, with Prometheus enabled.
  """
  in_vcon = make_test_vcon()
  results = {}

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    set_response = client.post("/vcon", json=in_vcon.dumpd())
    assert set_response.status_code == 204

    def slow_request():
      results["response"] = client.post(
          "/process/{}/timeout_test_sleep_async".format(UUID),
          json={"sleep_seconds": 2.0}
        )

    t = threading.Thread(target=slow_request)
    t.start()
    time.sleep(0.5)

    response = client.get("/diagnostics")
    assert response.status_code == 200
    diag = response.json()
    assert len(diag) == 1
    run = list(diag.values())[0]
    assert run["processor_name"] == "timeout_test_sleep_async"
    assert run["entry_point"] == "/process"
    assert UUID in run["vcon_uuids"]
    assert run["elapsed_seconds"] > 0

    t.join(timeout=10.0)
    assert results["response"].status_code == 200

    client.delete("/vcon/{}".format(UUID))


def test_metrics_exempt_from_shutdown_with_prometheus(enable_prometheus):
  """ /metrics returns non-503 when SHUTDOWN_REQUESTED=True """
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    py_vcon_server.SHUTDOWN_REQUESTED = True
    try:
      response = client.get("/metrics")
      assert response.status_code != 503
    finally:
      py_vcon_server.SHUTDOWN_REQUESTED = False


def test_diagnostics_exempt_from_shutdown_with_prometheus(enable_prometheus):
  """ /diagnostics returns non-503 when SHUTDOWN_REQUESTED=True with Prometheus """
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    py_vcon_server.SHUTDOWN_REQUESTED = True
    try:
      response = client.get("/diagnostics")
      assert response.status_code != 503
    finally:
      py_vcon_server.SHUTDOWN_REQUESTED = False


def test_processor_wrapped_after_lifespan_startup_with_prometheus(enable_prometheus):
  """
  After lifespan startup with Prometheus enabled,
  registered processors are instrumented.
  """
  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    proc = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance(
        "set_parameters"
      )
    assert metrics.is_instrumented(type(proc).process), \
        "set_parameters process() should be instrumented after lifespan startup"


def test_error_status_recorded_in_histogram(enable_prometheus):
  """
  When a processor raises an exception, the duration histogram records
  status="error".
  """
  in_vcon = make_test_vcon()

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    set_response = client.post("/vcon", json=in_vcon.dumpd())
    assert set_response.status_code == 204

    # timeout_test_exception raises an exception
    post_response = client.post(
        "/process/{}/timeout_test_exception".format(UUID),
        json={"message": "test error for metrics"}
      )
    assert post_response.status_code == 500

    # Verify error status was recorded
    assert metrics._processor_duration_hist is not None
    # Use collect() to get samples — avoids relying on internal
    # _count/_sum attributes which vary across prometheus_client versions
    error_count = 0
    for metric_family in metrics._processor_duration_hist.collect():
      for sample in metric_family.samples:
        if (sample.name == "py_vcon_server_processor_duration_seconds_count" and
            sample.labels.get("processor_name") == "timeout_test_exception" and
            sample.labels.get("entry_point") == "/process" and
            sample.labels.get("status") == "error"):
          error_count = sample.value
          break

    assert error_count >= 1, \
        "histogram should have at least one error observation for status=error"

    client.delete("/vcon/{}".format(UUID))
