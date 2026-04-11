# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
multiworker/stage6.py — SIGINT graceful shutdown.
"""

import os
import signal
import subprocess
import sys
import time

import httpx

from multiworker.constants import (
  QUEUE_NAME,
  PIPELINE_NAME,
  VCON_UUID,
  VCON_UUID_2,
  SIGINT_UUID,
  SIGINT_QUEUE,
  SIGINT_MARKER,
  SIGINT_JOB_SLEEP,
  SIGINT_SHUTDOWN_TIMEOUT,
  SIGINT_PIPELINE_DEF,
  STARTUP_TIMEOUT,
)
from multiworker.helpers import get, post, put, make_test_vcon_dict
from multiworker.results import Results

# scripts/ directory — one level up from this file's multiworker/ package dir.
# Used for log file placement to match the original single-file behaviour.
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
    6d: /diagnostics returns 200 during the drain window and shows the
        in-flight job — proves the socket stays open for monitoring
        while normal endpoints return 503

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

  # Log file goes in scripts/ to match the original single-file behaviour
  verify_log_path = os.path.join(_SCRIPTS_DIR, "test_multiworker_verify.log")
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
              "Analysis not found — job did not complete. analyses={}".format(
                  analyses))
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
