#!/usr/bin/env python3
# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
test_multiworker.py — Integration test for multiple Uvicorn workers.

Starts py_vcon_server as a subprocess with NUM_RESTAPI_WORKERS set to the
--workers argument, then exercises:

  Stage 1: Server starts and health check responds
  Stage 2: Correct number of worker processes spawned  (workers > 1 only)
  Stage 3: Health check responds while a worker is blocked synchronously
           workers=1 → FAIL expected (documents the bug)
           workers>1 → PASS expected (proves isolation)
  Stage 4: Background job runs through a jinja_report pipeline and writes
           a verifiable analysis object to the vCon
  Stage 5: Two concurrent jobs complete faster than 2x sequential time
           (workers > 1 only — proves parallel background processing)
  Stage 6: SIGINT graceful shutdown (workers > 1 only)
           6a: In-flight background job completes before shutdown
           6b: New HTTP requests receive 503 during shutdown window
           6c: Redis fully cleaned up after all workers exit
           6d: /diagnostics returns 200 during the drain window and shows the
               in-flight job — proves the socket stays open for monitoring
               while normal endpoints return 503

Usage:
  From the py_vcon_server/ directory:

    REST_URL=http://localhost:8000 \\
    VCON_STORAGE_URL=redis://localhost \\
    python3 scripts/test_multiworker.py --workers 1

    REST_URL=http://localhost:8000 \\
    VCON_STORAGE_URL=redis://localhost \\
    python3 scripts/test_multiworker.py --workers 2

  test_processors_always is added to PLUGIN_PATHS automatically if not present.
  It is required for Stage 3 (timeout_test_sleep_sync) and Stage 6b
  (timeout_test_sleep_async).

Requirements:
  pip install httpx psutil
  Redis running and accessible via VCON_STORAGE_URL
  py_vcon_server must be importable (via PYTHONPATH or pip install)
"""

import os
import sys
import time
import json
import signal
import argparse
import threading
import subprocess

import httpx
import psutil


# ── Constants ─────────────────────────────────────────────────────────────────

QUEUE_NAME       = "mw_test_queue"
PIPELINE_NAME    = QUEUE_NAME          # must match queue name
VCON_UUID        = "01855517-mult-iworker-test-77776666acbe"
VCON_UUID_2      = "01855517-mult-iwork2-test-77776666acbe"
ANALYSIS_TYPE    = "multiworker_test"
ANALYSIS_MARKER  = "MULTIWORKER_TEST_OK"
BLOCK_SECONDS    = 8     # how long timeout_test_sleep_sync blocks
HEALTH_TIMEOUT   = 3.0   # health check must respond within this many seconds
# seconds to wait for server to become ready
STARTUP_TIMEOUT  = int(os.environ.get("MULTIWORKER_STARTUP_TIMEOUT", "30"))
# max seconds to wait for a single job to complete
JOB_POLL_TIMEOUT = int(os.environ.get("MULTIWORKER_JOB_POLL_TIMEOUT", "30"))
JOB_POLL_INTERVAL = 0.5  # seconds between job completion polls

SIGINT_UUID             = "01855517-mult-sigint-test-77776666acbe"
SIGINT_QUEUE            = "mw_sigint_queue"
SIGINT_MARKER           = "SIGINT_SHUTDOWN_OK"
SIGINT_JOB_SLEEP        = 4.0   # job sleeps this long — must still be running when SIGINT fires
SIGINT_SHUTDOWN_TIMEOUT = 35    # max seconds for server to exit after SIGINT

# Pipeline definition — jinja_report writes a verifiable analysis object.
# No external service dependencies.
PIPELINE_DEF = {
  "pipeline_options": {
    "save_vcons": True,
    "timeout": 20
  },
  "processors": [
    {
      "processor_name": "jinja_report",
      "processor_options": {
        "template": "{} uuid={{{{ vcons[0].uuid }}}}".format(ANALYSIS_MARKER),
        "analysis_type": ANALYSIS_TYPE,
        "analysis_vendor": "test"
      }
    }
  ]
}

# Stage 6 pipeline — jinja_report writes the analysis immediately, then
# timeout_test_sleep_async holds the job open for SIGINT_JOB_SLEEP seconds
# so SIGINT arrives while the job is still running.
SIGINT_PIPELINE_DEF = {
  "pipeline_options": {
    "save_vcons": True,
    "timeout": 60,
    "failure_queue": "",
    "success_queue": ""
  },
  "processors": [
    {
      "processor_name": "jinja_report",
      "processor_options": {
        "template": "{} uuid={{{{ vcons[0].uuid }}}}".format(SIGINT_MARKER),
        "analysis_type": "sigint_test",
        "analysis_vendor": "test"
      }
    },
    {
      "processor_name": "timeout_test_sleep_async",
      "processor_options": {
        "sleep_seconds": SIGINT_JOB_SLEEP
      }
    }
  ]
}


# ── Results tracking ──────────────────────────────────────────────────────────

class Results:
  def __init__(self):
    self._results = []   # list of (stage, name, passed, detail)

  def record(self, stage, name, passed, detail=""):
    self._results.append((stage, name, passed, detail))
    marker = "✓" if passed else "✗"
    print("  {} Stage {}: {} {}".format(
        marker, stage, name,
        "— {}".format(detail) if detail else ""
      ))

  def summary(self):
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = sum(1 for _, _, p, _ in self._results if p)
    failed = sum(1 for _, _, p, _ in self._results if not p)
    for stage, name, p, detail in self._results:
      status = "PASS" if p else "FAIL"
      print("  [{}] Stage {}: {}{}".format(
          status, stage, name,
          " — {}".format(detail) if detail else ""
        ))
    print()
    print("Total: {} passed, {} failed".format(passed, failed))
    return failed == 0


# ── vCon construction ─────────────────────────────────────────────────────────

def make_test_vcon_dict(uuid: str) -> dict:
  """Build a minimal vCon dict with one party and one inline text dialog."""
  return {
    "vcon": "0.0.1",
    "uuid": uuid,
    "created_at": "2024-03-06T20:07:43+00:00",
    "subject": "Multiworker test conversation",
    "parties": [
      {"tel": "+15551234567", "name": "Test Caller"}
    ],
    "dialog": [
      {
        "type": "text",
        "start": "2024-03-06T20:07:43+00:00",
        "duration": 5.0,
        "parties": 0,
        "mediatype": "text/plain",
        "encoding": "none",
        "body": "Hello, this is a multiworker test conversation."
      }
    ]
  }


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def get(client: httpx.Client, path: str, timeout: float = 10.0) -> httpx.Response:
  return client.get(path, timeout=timeout)


def post(client: httpx.Client, path: str, body: dict, timeout: float = 10.0) -> httpx.Response:
  return client.post(path, json=body, timeout=timeout)


def put(client: httpx.Client, path: str, body: dict, timeout: float = 10.0) -> httpx.Response:
  return client.put(path, json=body, timeout=timeout)


def delete(client: httpx.Client, path: str, timeout: float = 10.0) -> httpx.Response:
  return client.delete(path, timeout=timeout)


# ── Cleanup ───────────────────────────────────────────────────────────────────

def cleanup(base_url: str, server_proc: subprocess.Popen):
  """
  Always-run cleanup.  Removes Stage 4/5 test state from Redis and kills the
  server if it is still running.  When Stage 6 runs, the server is already
  gone and these HTTP calls will fail with connection errors — that is expected
  and harmless.  Stage 6 cleans up its own artifacts via the verify server.
  Errors during cleanup are printed but do not raise.
  """
  print()
  print("── Cleanup ──────────────────────────────────────────────")

  try:
    with httpx.Client(base_url=base_url) as client:
      for label, path in [
          ("DELETE /server/queue/{}".format(QUEUE_NAME),  "/server/queue/{}".format(QUEUE_NAME)),
          ("DELETE /queue/{}".format(QUEUE_NAME),         "/queue/{}".format(QUEUE_NAME)),
          ("DELETE /pipeline/{}".format(PIPELINE_NAME),   "/pipeline/{}".format(PIPELINE_NAME)),
          ("DELETE /vcon/{}".format(VCON_UUID),           "/vcon/{}".format(VCON_UUID)),
          ("DELETE /vcon/{}".format(VCON_UUID_2),         "/vcon/{}".format(VCON_UUID_2)),
        ]:
        try:
          r = client.delete(path, timeout=5.0)
          print("  {}: {}".format(label, r.status_code))
        except Exception as e:
          print("  {}: ERROR {}".format(label, e))

  except Exception as e:
    print("  HTTP cleanup failed: {}".format(e))

  # Kill server if still running (Stage 6 terminates it; other stages do not)
  if server_proc is not None and server_proc.poll() is None:
    print("  Sending SIGTERM to server PID {}".format(server_proc.pid))
    server_proc.terminate()
    try:
      server_proc.wait(timeout=30)
      print("  Server exited cleanly")
    except subprocess.TimeoutExpired:
      print("  Server did not exit after 30s — sending SIGKILL")
      server_proc.kill()
      server_proc.wait()
      print("  Server killed")

  print("── Cleanup done ─────────────────────────────────────────")


# ── Stage implementations ─────────────────────────────────────────────────────

def stage1_startup(results: Results, base_url: str, server_proc: subprocess.Popen):
  """Stage 1: Server starts and health check responds."""
  print()
  print("Stage 1: Server startup")
  deadline = time.time() + STARTUP_TIMEOUT
  while time.time() < deadline:
    if server_proc.poll() is not None:
      results.record(1, "Server started", False,
          "Process exited with code {}".format(server_proc.returncode))
      return False
    try:
      with httpx.Client(base_url=base_url) as client:
        r = get(client, "/docs", timeout=2.0)
        if r.status_code == 200:
          results.record(1, "Server started and health check responds", True,
              "GET /docs → 200 in {:.1f}s".format(STARTUP_TIMEOUT - (deadline - time.time())))
          return True
    except Exception:
      pass
    time.sleep(0.5)

  results.record(1, "Server started and health check responds", False,
      "Timed out after {}s".format(STARTUP_TIMEOUT))
  return False


def stage2_worker_count(results: Results, base_url: str,
    server_proc: subprocess.Popen, expected_workers: int):
  """
  Stage 2: Correct number of worker processes spawned.

  With uvicorn.run() + workers=N, Uvicorn forks N worker processes as children
  of the master process.  We poll for up to 10 seconds to give them time to fork.
  With the old asyncio.create_task() approach, no children are spawned — the
  server runs in a single process.
  """
  print()
  print("Stage 2: Worker process count")

  try:
    parent = psutil.Process(server_proc.pid)

    deadline = time.time() + 10.0
    worker_count = 0
    pids = []
    while time.time() < deadline:
      try:
        children = parent.children(recursive=False)
        worker_count = len(children)
        pids = [c.pid for c in children]
        if worker_count >= expected_workers:
          break
      except psutil.NoSuchProcess:
        break
      time.sleep(0.5)

    passed = worker_count >= expected_workers
    results.record(2, "Worker processes spawned", passed,
        "found {} worker(s) (expected >= {}), PIDs: {}{}".format(
            worker_count, expected_workers, pids,
            " — old __main__.py does not fork workers" if worker_count == 0 else ""))
    return passed

  except Exception as e:
    results.record(2, "Worker processes spawned", False, str(e))
    return False


def stage3_blocking_isolation(results: Results, base_url: str, block_seconds: int):
  """
  Stage 3: Health check responds while one worker is blocked.
  workers=1 → health check will hang → FAIL (documents the bug)
  workers>1 → health check returns quickly → PASS (proves isolation)
  """
  print()
  print("Stage 3: Health check while worker is blocked")

  block_result = {}
  health_result = {}

  def send_blocking_request():
    try:
      with httpx.Client(base_url=base_url) as client:
        request_body = {
          "processor_io": {
            "vcons": [make_test_vcon_dict(VCON_UUID)],
            "parameters": {}
          },
          "processor_options": {
            "sleep_seconds": float(block_seconds)
          }
        }
        r = client.post(
            "/processIO/timeout_test_sleep_sync",
            json=request_body,
            timeout=block_seconds + 5.0
          )
        block_result["status"] = r.status_code
    except Exception as e:
      block_result["error"] = str(e)

  block_thread = threading.Thread(target=send_blocking_request, daemon=True)
  block_thread.start()

  # Give the blocking request time to reach the server and occupy a worker
  time.sleep(1.5)

  health_start = time.time()
  try:
    with httpx.Client(base_url=base_url) as client:
      r = get(client, "/docs", timeout=HEALTH_TIMEOUT)
      health_elapsed = time.time() - health_start
      health_result["status"] = r.status_code
      health_result["elapsed"] = health_elapsed
  except httpx.TimeoutException:
    health_elapsed = time.time() - health_start
    health_result["timeout"] = True
    health_result["elapsed"] = health_elapsed
  except Exception as e:
    health_elapsed = time.time() - health_start
    health_result["error"] = str(e)
    health_result["elapsed"] = health_elapsed

  block_thread.join(timeout=block_seconds + 5.0)

  if health_result.get("timeout"):
    passed = False
    detail = "Health check timed out after {:.1f}s — event loop blocked".format(
        health_result["elapsed"])
  elif "error" in health_result:
    passed = False
    detail = "Health check error: {}".format(health_result["error"])
  elif health_result.get("status") == 200:
    passed = True
    detail = "Health check returned 200 in {:.2f}s while worker was blocked".format(
        health_result["elapsed"])
  else:
    passed = False
    detail = "Health check returned status {}".format(health_result.get("status"))

  results.record(3, "Health check responds while worker is blocked", passed, detail)
  return passed


def stage4_pipeline_job(results: Results, base_url: str):
  """
  Stage 4: Push a vCon through a real pipeline via the job queue.
  Verifies the jinja_report processor wrote an analysis object to the vCon.
  """
  print()
  print("Stage 4: Background pipeline job via queue")

  with httpx.Client(base_url=base_url) as client:

    # 4a: Store vCon
    try:
      r = post(client, "/vcon", make_test_vcon_dict(VCON_UUID))
      passed = r.status_code == 204
      results.record(4, "Store test vCon", passed,
          "POST /vcon → {}".format(r.status_code))
      if not passed:
        return False
    except Exception as e:
      results.record(4, "Store test vCon", False, str(e))
      return False

    # 4b: Create pipeline
    try:
      r = client.put(
          "/pipeline/{}".format(PIPELINE_NAME),
          json=PIPELINE_DEF,
          params={"validate_processor_options": False},
          timeout=10.0
        )
      passed = r.status_code == 204
      results.record(4, "Create pipeline", passed,
          "PUT /pipeline/{} → {}".format(PIPELINE_NAME, r.status_code))
      if not passed:
        print("  Response body: {}".format(r.text))
        return False
    except Exception as e:
      results.record(4, "Create pipeline", False, str(e))
      return False

    # 4c: Create queue — delete first to handle leftover state from prior runs
    try:
      client.delete("/queue/{}".format(QUEUE_NAME), timeout=5.0)
    except Exception:
      pass
    try:
      r = post(client, "/queue/{}".format(QUEUE_NAME), {})
      passed = r.status_code == 204
      results.record(4, "Create job queue", passed,
          "POST /queue/{} → {}".format(QUEUE_NAME, r.status_code))
      if not passed:
        return False
    except Exception as e:
      results.record(4, "Create job queue", False, str(e))
      return False

    # 4d: Configure server to watch queue
    try:
      r = post(client, "/server/queue/{}".format(QUEUE_NAME), {"weight": 1})
      passed = r.status_code == 204
      results.record(4, "Configure server queue", passed,
          "POST /server/queue/{} → {}".format(QUEUE_NAME, r.status_code))
      if not passed:
        return False
    except Exception as e:
      results.record(4, "Configure server queue", False, str(e))
      return False

    # 4e: Push job to queue
    try:
      job = {"job_type": "vcon_uuid", "vcon_uuid": [VCON_UUID]}
      r = put(client, "/queue/{}".format(QUEUE_NAME), job)
      passed = r.status_code == 200
      results.record(4, "Push job to queue", passed,
          "PUT /queue/{} → {}".format(QUEUE_NAME, r.status_code))
      if not passed:
        return False
    except Exception as e:
      results.record(4, "Push job to queue", False, str(e))
      return False

    # 4f: Poll until queue is empty (job was picked up)
    print("  Waiting for job to be picked up (max {}s)...".format(JOB_POLL_TIMEOUT))
    deadline = time.time() + JOB_POLL_TIMEOUT
    job_picked_up = False
    while time.time() < deadline:
      try:
        r = get(client, "/queue/{}".format(QUEUE_NAME))
        if r.status_code == 200 and len(r.json()) == 0:
          job_picked_up = True
          break
      except Exception:
        pass
      time.sleep(JOB_POLL_INTERVAL)

    results.record(4, "Job picked up from queue", job_picked_up,
        "Queue empty after {:.1f}s".format(
            JOB_POLL_TIMEOUT - (deadline - time.time())) if job_picked_up
        else "Timed out after {}s — job still in queue".format(JOB_POLL_TIMEOUT))
    if not job_picked_up:
      return False

    # 4g: Poll until in-progress is clear (job completed)
    print("  Waiting for job to complete (max {}s)...".format(JOB_POLL_TIMEOUT))
    deadline = time.time() + JOB_POLL_TIMEOUT
    job_completed = False
    while time.time() < deadline:
      try:
        r = get(client, "/in_progress")
        if r.status_code == 200:
          our_jobs = {
            k: v for k, v in r.json().items()
            if VCON_UUID in json.dumps(v)
          }
          if len(our_jobs) == 0:
            job_completed = True
            break
      except Exception:
        pass
      time.sleep(JOB_POLL_INTERVAL)

    results.record(4, "Job completed", job_completed,
        "In-progress cleared" if job_completed
        else "Timed out — job still in progress")
    if not job_completed:
      return False

    # Give the server a moment to commit the vCon back to Redis
    time.sleep(1.0)

    # 4h: Verify analysis object was written to vCon
    try:
      r = get(client, "/vcon/{}".format(VCON_UUID))
      if r.status_code != 200:
        results.record(4, "Analysis object written to vCon", False,
            "GET /vcon/{} → {}".format(VCON_UUID, r.status_code))
        return False

      analyses = r.json().get("analysis", [])
      found = any(
          a.get("type") == ANALYSIS_TYPE and
          ANALYSIS_MARKER in str(a.get("body", "")) and
          VCON_UUID in str(a.get("body", ""))
          for a in analyses
        )
      results.record(4, "Analysis object written to vCon", found,
          "Found analysis type={} containing marker and UUID".format(ANALYSIS_TYPE)
          if found else
          "No matching analysis object found. analyses={}".format(analyses))
      return found

    except Exception as e:
      results.record(4, "Analysis object written to vCon", False, str(e))
      return False


def stage5_concurrent_jobs(results: Results, base_url: str):
  """
  Stage 5: Two concurrent jobs complete faster than 2x sequential time.
  Proves parallel background processing across workers.
  """
  print()
  print("Stage 5: Concurrent background jobs")

  with httpx.Client(base_url=base_url) as client:

    def push_and_wait(uuid: str) -> float:
      """Push a job for the given vCon UUID and return elapsed seconds."""
      start = time.time()
      job = {"job_type": "vcon_uuid", "vcon_uuid": [uuid]}
      r = put(client, "/queue/{}".format(QUEUE_NAME), job, timeout=10.0)
      if r.status_code != 200:
        return -1.0

      deadline = time.time() + JOB_POLL_TIMEOUT
      while time.time() < deadline:
        r = get(client, "/in_progress", timeout=5.0)
        if r.status_code == 200:
          our_jobs = {
            k: v for k, v in r.json().items()
            if uuid in json.dumps(v)
          }
          if len(our_jobs) == 0:
            r2 = get(client, "/queue/{}".format(QUEUE_NAME), timeout=5.0)
            if r2.status_code == 200 and len(r2.json()) == 0:
              return time.time() - start
        time.sleep(JOB_POLL_INTERVAL)
      return -1.0

    # Store second vCon
    try:
      r = post(client, "/vcon", make_test_vcon_dict(VCON_UUID_2))
      if r.status_code != 204:
        results.record(5, "Store second test vCon", False,
            "POST /vcon → {}".format(r.status_code))
        return False
    except Exception as e:
      results.record(5, "Store second test vCon", False, str(e))
      return False

    # Measure single job time
    print("  Measuring single job time...")
    single_time = push_and_wait(VCON_UUID_2)
    if single_time < 0:
      results.record(5, "Single job timing baseline", False, "Job timed out")
      return False
    print("  Single job time: {:.2f}s".format(single_time))

    # Push two jobs simultaneously and measure total wall time
    print("  Pushing 2 jobs simultaneously...")
    concurrent_start = time.time()

    for uuid in [VCON_UUID, VCON_UUID_2]:
      job = {"job_type": "vcon_uuid", "vcon_uuid": [uuid]}
      put(client, "/queue/{}".format(QUEUE_NAME), job)

    deadline = time.time() + JOB_POLL_TIMEOUT * 2
    while time.time() < deadline:
      r = get(client, "/in_progress")
      r2 = get(client, "/queue/{}".format(QUEUE_NAME))
      if r.status_code == 200 and r2.status_code == 200:
        our_in_prog = {
          k: v for k, v in r.json().items()
          if VCON_UUID in json.dumps(v) or VCON_UUID_2 in json.dumps(v)
        }
        if len(r2.json()) == 0 and len(our_in_prog) == 0:
          break
      time.sleep(JOB_POLL_INTERVAL)

    concurrent_time = time.time() - concurrent_start
    print("  Concurrent (2 jobs) wall time: {:.2f}s".format(concurrent_time))

    threshold = single_time * 1.6
    passed = concurrent_time < threshold
    results.record(5, "Two jobs run concurrently", passed,
        "2-job wall time {:.2f}s < threshold {:.2f}s (1.6x single {:.2f}s)".format(
            concurrent_time, threshold, single_time)
        if passed else
        "2-job wall time {:.2f}s >= threshold {:.2f}s — jobs ran sequentially".format(
            concurrent_time, threshold))
    return passed


def stage6_sigint_shutdown(
    results: Results,
    base_url: str,
    server_proc: subprocess.Popen,
    env: dict,
    num_workers: int
  ) -> bool:
  """
  Stage 6: SIGINT graceful shutdown.

  While a background pipeline job is sleeping (SIGINT_JOB_SLEEP seconds),
  send SIGINT to the server parent process.  Uvicorn propagates SIGTERM to
  its worker children.  Verify:

    6a: The in-flight background job completes (analysis written to vCon)
    6b: New HTTP requests receive 503 during the shutdown window
    6c: Redis is fully cleaned up after all workers exit — no stale
        server or worker entries (exercises deregister_server status==-2
        path for workers 2..N)

  Because Stage 6 terminates the server, it must be the last stage.
  cleanup() detects server_proc.poll() is not None and skips the SIGTERM.
  Stage 6 also cleans up all Stage 4/5 Redis artifacts via the verify server,
  since the original server is gone by the time cleanup() runs.
  """
  print()
  print("Stage 6: SIGINT graceful shutdown")

  with httpx.Client(base_url=base_url) as client:

    # ── Setup ─────────────────────────────────────────────────────────────────

    try:
      r = post(client, "/vcon", make_test_vcon_dict(SIGINT_UUID))
      if r.status_code != 204:
        results.record(6, "Setup: store vCon", False,
            "POST /vcon → {}".format(r.status_code))
        return False
    except Exception as e:
      results.record(6, "Setup: store vCon", False, str(e))
      return False

    try:
      r = client.put(
          "/pipeline/{}".format(SIGINT_QUEUE),
          json=SIGINT_PIPELINE_DEF,
          params={"validate_processor_options": False},
          timeout=10.0
        )
      if r.status_code != 204:
        results.record(6, "Setup: create pipeline", False,
            "PUT /pipeline/{} → {}".format(SIGINT_QUEUE, r.status_code))
        return False
    except Exception as e:
      results.record(6, "Setup: create pipeline", False, str(e))
      return False

    try:
      client.delete("/queue/{}".format(SIGINT_QUEUE), timeout=5.0)
    except Exception:
      pass
    try:
      r = post(client, "/queue/{}".format(SIGINT_QUEUE), {})
      if r.status_code != 204:
        results.record(6, "Setup: create queue", False,
            "POST /queue/{} → {}".format(SIGINT_QUEUE, r.status_code))
        return False
    except Exception as e:
      results.record(6, "Setup: create queue", False, str(e))
      return False

    try:
      r = post(client, "/server/queue/{}".format(SIGINT_QUEUE), {"weight": 1})
      if r.status_code != 204:
        results.record(6, "Setup: configure server queue", False,
            "POST /server/queue/{} → {}".format(SIGINT_QUEUE, r.status_code))
        return False
    except Exception as e:
      results.record(6, "Setup: configure server queue", False, str(e))
      return False

    try:
      job = {"job_type": "vcon_uuid", "vcon_uuid": [SIGINT_UUID]}
      r = put(client, "/queue/{}".format(SIGINT_QUEUE), job)
      if r.status_code != 200:
        results.record(6, "Setup: push job", False,
            "PUT /queue/{} → {}".format(SIGINT_QUEUE, r.status_code))
        return False
    except Exception as e:
      results.record(6, "Setup: push job", False, str(e))
      return False

    # Wait for job to be picked up
    print("  Waiting for job to be picked up (max 15s)...")
    deadline = time.time() + 15
    picked_up = False
    while time.time() < deadline:
      try:
        r = get(client, "/queue/{}".format(SIGINT_QUEUE))
        if r.status_code == 200 and len(r.json()) == 0:
          picked_up = True
          break
      except Exception:
        pass
      time.sleep(0.3)

    if not picked_up:
      results.record(6, "Setup: job picked up", False,
          "Job not picked up within 15s")
      return False

    print("  Job picked up and running — sending SIGINT in 1.0s...")
    time.sleep(1.0)   # let the job reach the sleep phase inside timeout_test_sleep_async

    # ── Send SIGINT to the server parent process ───────────────────────────────
    # We do NOT use killpg because the test script shares the process group.
    # Sending SIGINT only to the parent is equivalent to Ctrl+C directed at
    # the server — uvicorn catches it and sends SIGTERM to its worker children.
    sigint_time = time.time()
    try:
      os.kill(server_proc.pid, signal.SIGINT)
      print("  SIGINT sent to server PID {}".format(server_proc.pid))
    except ProcessLookupError:
      results.record(6, "SIGINT sent", False, "Server process not found")
      return False

    # ── 6b: Poll for 503 during shutdown window ────────────────────────────────
    # Workers set SHUTDOWN_REQUESTED=True on receiving their shutdown signal,
    # after which the middleware returns 503 for new requests.
    # timeout_test_sleep_async holds the job open for SIGINT_JOB_SLEEP seconds,
    # giving us a window to observe 503 before the server fully exits.
    # Do NOT break on ConnectError — with multiple workers, one worker may close
    # its connection while another is still serving 503s.  Keep polling until
    # we observe a 503, the full window expires, or the server process exits.
    got_503 = False
    poll_deadline = time.time() + 15
    while time.time() < poll_deadline:
      if server_proc.poll() is not None:
        break  # server fully exited — no more chances to observe 503
      try:
        with httpx.Client(base_url=base_url) as hc:
          r = hc.get("/docs", timeout=1.0)
          if r.status_code == 503:
            got_503 = True
            break
          # 200 means this worker hasn't entered shutdown yet — keep polling
      except (httpx.ConnectError, httpx.RemoteProtocolError):
        # This worker closed its connection — try again immediately,
        # another worker may still be running and returning 503
        pass
      except httpx.TimeoutException:
        pass
      except Exception:
        pass
      time.sleep(0.05)

    results.record(6, "503 returned during shutdown window", got_503,
        "Middleware correctly rejected new requests during shutdown"
        if got_503 else
        "Never observed 503 — shutdown completed before middleware could respond")


    # ── 6d: /diagnostics accessible during drain window ──────────────────────
    # While the job is sleeping and SHUTDOWN_REQUESTED=True, the socket stays
    # open and /diagnostics must return 200 (it is exempt from 503).
    # We poll for up to SIGINT_JOB_SLEEP seconds to catch the drain window.
    diagnostics_ok = False
    diagnostics_showed_job = False
    diag_deadline = time.time() + SIGINT_JOB_SLEEP + 2.0
    while time.time() < diag_deadline:
      if server_proc.poll() is not None:
        break
      try:
        with httpx.Client(base_url=base_url) as hc:
          r = hc.get("/diagnostics", timeout=1.0)
          if r.status_code == 200:
            diagnostics_ok = True
            diag_data = r.json()
            # Check if the sleeping job is visible
            if any(
                run.get("processor_name") == "timeout_test_sleep_async"
                for run in diag_data.values()
              ):
              diagnostics_showed_job = True
              break
      except Exception:
        pass
      time.sleep(0.1)

    results.record(6, "/diagnostics accessible during shutdown", diagnostics_ok,
        "/diagnostics returned 200 during drain window"
        if diagnostics_ok else
        "/diagnostics was not reachable during drain window")
    results.record(6, "/diagnostics shows in-flight job during shutdown",
        diagnostics_showed_job,
        "timeout_test_sleep_async visible in /diagnostics during drain"
        if diagnostics_showed_job else
        "Job not visible in /diagnostics — may have completed before poll")


  # ── Wait for server to exit ────────────────────────────────────────────────
  print("  Waiting for server to exit (max {}s)...".format(SIGINT_SHUTDOWN_TIMEOUT))
  try:
    server_proc.wait(timeout=SIGINT_SHUTDOWN_TIMEOUT)
    shutdown_duration = time.time() - sigint_time
    print("  Server exited {:.1f}s after SIGINT (exit code {})".format(
        shutdown_duration, server_proc.returncode))
    server_exited_cleanly = server_proc.returncode in (0, -signal.SIGINT, -signal.SIGTERM)
    results.record(6, "Server exited after SIGINT", server_exited_cleanly,
        "Exit code {}".format(server_proc.returncode))
  except subprocess.TimeoutExpired:
    results.record(6, "Server exited after SIGINT", False,
        "Did not exit within {}s".format(SIGINT_SHUTDOWN_TIMEOUT))
    return False

  # ── Verify via a fresh server instance ────────────────────────────────────
  # Start a temporary server (background jobs disabled) to read Redis state
  # and clean up all test artifacts.
  print("  Starting verify server to check Redis state and vCon...")
  verify_env = env.copy()
  verify_env["RUN_BACKGROUND_JOBS"] = "False"

  verify_log_path = os.path.join(
      os.path.dirname(os.path.abspath(__file__)),
      "test_multiworker_verify.log"
    )
  verify_log_file = open(verify_log_path, "w")
  verify_proc = subprocess.Popen(
      [sys.executable, "-m", "py_vcon_server"],
      env=verify_env,
      stdout=verify_log_file,
      stderr=verify_log_file
    )

  try:
    # Wait for verify server to be ready
    vdeadline = time.time() + STARTUP_TIMEOUT
    verify_ready = False
    while time.time() < vdeadline:
      if verify_proc.poll() is not None:
        break
      try:
        with httpx.Client(base_url=base_url) as hc:
          r = hc.get("/docs", timeout=1.0)
          if r.status_code == 200:
            verify_ready = True
            break
      except Exception:
        pass
      time.sleep(0.5)

    if not verify_ready:
      results.record(6, "Verify server started", False,
          "Did not become ready within {}s".format(STARTUP_TIMEOUT))
      return False

    with httpx.Client(base_url=base_url) as client:

      # ── 6c: Redis cleanup check ──────────────────────────────────────────────
      # /servers should contain only the verify server's entries.
      # Any entry containing the old server's PID is stale.
      try:
        r = get(client, "/servers")
        if r.status_code == 200:
          servers = r.json()
          old_pid_str = str(server_proc.pid)
          stale = [k for k in servers if old_pid_str in k]
          redis_clean = len(stale) == 0
          results.record(6, "Redis clean after shutdown", redis_clean,
              "No stale entries for old PID {}".format(server_proc.pid)
              if redis_clean else
              "Stale entries found: {}".format(stale))
        else:
          results.record(6, "Redis clean after shutdown", False,
              "GET /servers → {}".format(r.status_code))
      except Exception as e:
        results.record(6, "Redis clean after shutdown", False, str(e))

      # ── 6a: In-flight job completed ──────────────────────────────────────────
      # The background job (jinja_report + sleep) must have written its analysis
      # before the worker's lifespan shutdown completed.
      try:
        r = get(client, "/vcon/{}".format(SIGINT_UUID))
        if r.status_code == 200:
          analyses = r.json().get("analysis", [])
          found = any(
              a.get("type") == "sigint_test" and
              SIGINT_MARKER in str(a.get("body", ""))
              for a in analyses
            )
          results.record(6, "In-flight job completed before shutdown", found,
              "Analysis with type=sigint_test and marker found"
              if found else
              "Analysis not found — job did not complete. analyses={}".format(analyses))
        else:
          results.record(6, "In-flight job completed before shutdown", False,
              "GET /vcon → {}".format(r.status_code))
      except Exception as e:
        results.record(6, "In-flight job completed before shutdown", False, str(e))

      # ── Cleanup all test artifacts via verify server ─────────────────────────
      # Stage 4/5 artifacts cannot be cleaned by cleanup() since the original
      # server is already gone by then.
      for path in [
          "/server/queue/{}".format(SIGINT_QUEUE),
          "/queue/{}".format(SIGINT_QUEUE),
          "/pipeline/{}".format(SIGINT_QUEUE),
          "/vcon/{}".format(SIGINT_UUID),
          "/server/queue/{}".format(QUEUE_NAME),
          "/queue/{}".format(QUEUE_NAME),
          "/pipeline/{}".format(PIPELINE_NAME),
          "/vcon/{}".format(VCON_UUID),
          "/vcon/{}".format(VCON_UUID_2),
        ]:
        try:
          client.delete(path, timeout=5.0)
        except Exception:
          pass

  finally:
    verify_proc.terminate()
    try:
      verify_proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
      verify_proc.kill()
      verify_proc.wait()
    verify_log_file.close()

  return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
  parser = argparse.ArgumentParser(
      description="Test py_vcon_server multi-worker behavior"
    )
  parser.add_argument(
      "--workers",
      type=int,
      default=1,
      help="Number of Uvicorn workers (1=documents bug, 2+=proves fix)"
    )
  args = parser.parse_args()

  # Require REST_URL from environment
  rest_url = os.environ.get("REST_URL", "")
  if not rest_url:
    print("ERROR: REST_URL environment variable must be set")
    print("  Example: REST_URL=http://localhost:8000")
    sys.exit(1)

  base_url = rest_url.rstrip("/")
  num_workers = args.workers
  multi_worker = num_workers > 1

  # Ensure test_processors_always is in PLUGIN_PATHS.
  # Required for Stage 3 (timeout_test_sleep_sync blocks a worker) and
  # Stage 6b (timeout_test_sleep_async holds a job open to observe 503).
  # Set it now so env = os.environ.copy() below picks it up correctly.
  plugin_paths = os.environ.get("PLUGIN_PATHS", "")
  if "test_processors_always" not in plugin_paths:
    plugin_paths = ("test_processors_always" if not plugin_paths
                    else plugin_paths + ",test_processors_always")
    os.environ["PLUGIN_PATHS"] = plugin_paths

  # Build subprocess environment once here so every stage and the header
  # print all reference exactly what the server process will receive.
  env = os.environ.copy()
  env["NUM_RESTAPI_WORKERS"] = str(num_workers)
  env["RUN_BACKGROUND_JOBS"] = "True"

  print("=" * 60)
  print("py_vcon_server Multi-Worker Test")
  print("=" * 60)
  print("  REST_URL:     {}".format(base_url))
  print("  Workers:      {}".format(num_workers))
  print("  Mode:         {}".format(
      "FIXED (multi-worker)" if multi_worker else "BASELINE (documents bug)"))
  print("  PLUGIN_PATHS: {}".format(env.get("PLUGIN_PATHS")))
  print()

  if not multi_worker:
    print("NOTE: workers=1 — Stage 3 FAIL and Stage 5/6 SKIP are expected.")
    print("      This documents the existing single-worker blocking bug.")
    print()

  results = Results()
  server_proc = None
  server_log_file = None
  server_log_path = os.path.join(
      os.path.dirname(os.path.abspath(__file__)),
      "test_multiworker_server.log"
    )

  try:
    print("Starting server: python3 -m py_vcon_server")
    print("  NUM_RESTAPI_WORKERS={}".format(num_workers))
    print("  Server log: {}".format(server_log_path))
    server_log_file = open(server_log_path, "w")
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "py_vcon_server"],
        env=env,
        stdout=server_log_file,
        stderr=server_log_file
      )
    print("  Server PID: {}".format(server_proc.pid))

    # Stage 1: Startup
    if not stage1_startup(results, base_url, server_proc):
      print("\nServer failed to start — aborting remaining stages")
      print("  See server log for details: {}".format(server_log_path))
      server_log_file.flush()
      results.summary()
      return False

    # Stage 2: Worker count (multi-worker only)
    if multi_worker:
      stage2_worker_count(results, base_url, server_proc, num_workers)
    else:
      print()
      print("Stage 2: Worker process count — SKIPPED (workers=1)")

    # Stage 3: Blocking isolation
    stage3_blocking_isolation(results, base_url, BLOCK_SECONDS)

    # Stage 4: Pipeline job via queue
    stage4_pipeline_job(results, base_url)

    # Stage 5: Concurrent jobs (multi-worker only)
    if multi_worker:
      stage5_concurrent_jobs(results, base_url)
    else:
      print()
      print("Stage 5: Concurrent jobs — SKIPPED (workers=1)")

    # Stage 6: SIGINT graceful shutdown (multi-worker only).
    # Must be last — terminates the server.
    if multi_worker:
      stage6_sigint_shutdown(results, base_url, server_proc, env, num_workers)
    else:
      print()
      print("Stage 6: SIGINT graceful shutdown — SKIPPED (workers=1)")

  finally:
    cleanup(base_url, server_proc)
    if server_log_file is not None:
      try:
        server_log_file.flush()
        server_log_file.close()
      except Exception:
        pass
    print("  Server log saved to: {}".format(server_log_path))

  return results.summary()


if __name__ == "__main__":
  success = main()
  sys.exit(0 if success else 1)
