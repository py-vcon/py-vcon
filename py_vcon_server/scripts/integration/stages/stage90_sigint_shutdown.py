# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
integration/stages/stage90_sigint_shutdown.py

SIGINT graceful shutdown.  While a background pipeline job is sleeping,
send SIGINT to the server parent process.  Verify:

  90a: The in-flight background job completes (analysis written)
  90b: New HTTP requests receive 503 during the shutdown window
  90c: Redis is fully cleaned up after all workers exit
  90d: /diagnostics returns 200 during the drain window

Because this stage terminates the server, it must be the last stage.
"""

import os
import signal
import subprocess
import sys
import time

import httpx

from integration.constants import (
  QUEUE_NAME,
  PIPELINE_NAME,
  VCON_UUID,
  STARTUP_TIMEOUT,
)
from integration.helpers import get, post, put, make_test_vcon_dict
from integration.server_manager import wait_for_port_free

# Stage-specific constants
SIGINT_UUID = "01855517-intg-signt-test-77776666acbe"
SIGINT_QUEUE = "integ_sigint_queue"
SIGINT_MARKER = "SIGINT_SHUTDOWN_OK"
SIGINT_JOB_SLEEP = 4.0
SIGINT_SHUTDOWN_TIMEOUT = 35

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

# Stage-specific constants for second vCon cleanup
VCON_UUID_2 = "01855517-intg-rat2n-test-77776666acbe"

# scripts/ directory -- two levels up from this file's stages/ package dir.
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))


class Stage:
  name = "stage90_sigint_shutdown"
  description = "SIGINT graceful shutdown with drain, 503, Redis cleanup"
  expected_state_after = "stopped"
  min_workers = 2

  def run(self, context):
    server_proc_pid = context.server_manager.pid()
    if server_proc_pid is None:
      context.results.record(
          self.name, "Server PID available", False,
          "server PID not available")
      return False

    with httpx.Client(base_url=context.base_url) as client:

      # -- Setup ---------------------------------------------------------------

      try:
        r = post(client, "/vcon", make_test_vcon_dict(SIGINT_UUID))
        if r.status_code != 204:
          context.results.record(self.name, "Setup: store vCon", False,
              "POST /vcon -> {}".format(r.status_code))
          return False
      except Exception as e:
        context.results.record(
            self.name, "Setup: store vCon", False, str(e))
        return False

      try:
        r = client.put(
            "/pipeline/{}".format(SIGINT_QUEUE),
            json=SIGINT_PIPELINE_DEF,
            params={"validate_processor_options": False},
            timeout=10.0
          )
        if r.status_code != 204:
          context.results.record(self.name,
              "Setup: create pipeline", False,
              "PUT /pipeline/{} -> {}".format(
                  SIGINT_QUEUE, r.status_code))
          return False
      except Exception as e:
        context.results.record(
            self.name, "Setup: create pipeline", False, str(e))
        return False

      try:
        client.delete(
            "/queue/{}".format(SIGINT_QUEUE), timeout=5.0)
      except Exception:
        pass
      try:
        r = post(client, "/queue/{}".format(SIGINT_QUEUE), {})
        if r.status_code != 204:
          context.results.record(self.name,
              "Setup: create queue", False,
              "POST /queue/{} -> {}".format(
                  SIGINT_QUEUE, r.status_code))
          return False
      except Exception as e:
        context.results.record(
            self.name, "Setup: create queue", False, str(e))
        return False

      try:
        r = post(client, "/server/queue/{}".format(SIGINT_QUEUE),
            {"weight": 1})
        if r.status_code != 204:
          context.results.record(self.name,
              "Setup: configure server queue", False,
              "POST /server/queue/{} -> {}".format(
                  SIGINT_QUEUE, r.status_code))
          return False
      except Exception as e:
        context.results.record(self.name,
            "Setup: configure server queue", False, str(e))
        return False

      try:
        job = {"job_type": "vcon_uuid", "vcon_uuid": [SIGINT_UUID]}
        r = put(client, "/queue/{}".format(SIGINT_QUEUE), job)
        if r.status_code != 200:
          context.results.record(self.name,
              "Setup: push job", False,
              "PUT /queue/{} -> {}".format(
                  SIGINT_QUEUE, r.status_code))
          return False
      except Exception as e:
        context.results.record(
            self.name, "Setup: push job", False, str(e))
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
        context.results.record(self.name,
            "Setup: job picked up", False,
            "Job not picked up within 15s")
        return False

      print("  Job picked up and running -- sending SIGINT in 1.0s...")
      time.sleep(1.0)

    # -- Send SIGINT -----------------------------------------------------------

    sigint_time = time.time()
    try:
      os.kill(server_proc_pid, signal.SIGINT)
      print("  SIGINT sent to server PID {}".format(server_proc_pid))
    except ProcessLookupError:
      context.results.record(self.name, "SIGINT sent", False,
          "Server process not found")
      return False

    # -- 90b/90d combined: poll /docs (for 503) and /diagnostics (for
    # in-flight job) concurrently from this single loop.  Both checks
    # need the server to be transitioning to shutdown but still reachable
    # for /diagnostics.  Running them sequentially (as the original code
    # did) means the 503-wait loop can consume the entire drain window
    # before /diagnostics polling even starts -- the in-flight job then
    # finishes before we look for it.  We poll both endpoints from the
    # same loop iteration so both observations have an equal chance.

    got_503 = False
    diagnostics_ok = False
    diagnostics_showed_job = False
    diag_poll_log = []   # list of (elapsed_since_sigint, status, processor_names_or_error)
    server_exit_observed_at = None
    docs_503_observed_at = None
    poll_deadline = sigint_time + SIGINT_JOB_SLEEP + 5.0
    with httpx.Client(base_url=context.base_url) as hc:
      while time.time() < poll_deadline:
        if context.server_manager.poll() is not None:
          server_exit_observed_at = time.time() - sigint_time
          break
        poll_elapsed = time.time() - sigint_time

        # /docs probe -- looking for 503 (shutdown middleware active)
        if not got_503:
          try:
            r_docs = hc.get("/docs", timeout=1.0)
            if r_docs.status_code == 503:
              got_503 = True
              docs_503_observed_at = poll_elapsed
          except (httpx.ConnectError, httpx.RemoteProtocolError,
              httpx.TimeoutException):
            pass
          except Exception:
            pass

        # /diagnostics probe -- looking for the in-flight job
        if not diagnostics_showed_job:
          try:
            r_diag = hc.get("/diagnostics", timeout=1.0)
            if r_diag.status_code == 200:
              diagnostics_ok = True
              diag_data = r_diag.json()
              proc_names = [
                  run.get("processor_name") for run in diag_data.values()
                ]
              diag_poll_log.append(
                  (poll_elapsed, 200, proc_names)
                )
              if any(
                  p == "timeout_test_sleep_async" for p in proc_names
                ):
                diagnostics_showed_job = True
            else:
              diag_poll_log.append(
                  (poll_elapsed, r_diag.status_code, None)
                )
          except Exception as e:
            diag_poll_log.append(
                (poll_elapsed, "error", "{}: {}".format(
                    type(e).__name__, e))
              )

        if got_503 and diagnostics_showed_job:
          break
        time.sleep(0.05)

    context.results.record(self.name,
        "503 returned during shutdown window", got_503,
        "503 first observed at t={:.2f}s".format(docs_503_observed_at)
        if got_503 else
        "Never observed 503 -- shutdown completed before "
        "middleware could respond")

    context.results.record(self.name,
        "/diagnostics accessible during shutdown",
        diagnostics_ok,
        "/diagnostics returned 200 during drain window"
        if diagnostics_ok else
        "/diagnostics was not reachable during drain window")


    if diagnostics_showed_job:
      job_detail = "timeout_test_sleep_async visible"
    else:
      # Build a diagnostic timeline of every poll result.
      lines = ["Job not visible -- timeline of /diagnostics polls:"]
      lines.append(
          "  SIGINT sent at t=0, SIGINT_JOB_SLEEP={}s, poll window={}s".format(
              SIGINT_JOB_SLEEP, SIGINT_JOB_SLEEP + 5.0
            )
        )
      if server_exit_observed_at is not None:
        lines.append(
            "  server exit observed at t={:.2f}s".format(
                server_exit_observed_at
              )
          )
      lines.append("  total polls: {}".format(len(diag_poll_log)))
      empty_200_count = sum(
          1 for (_, status, names) in diag_poll_log
          if status == 200 and names == []
        )
      nonempty_200_count = sum(
          1 for (_, status, names) in diag_poll_log
          if status == 200 and names not in ([], None)
        )
      error_count = sum(
          1 for (_, status, _) in diag_poll_log if status == "error"
        )
      lines.append(
          "  polls returning 200 with empty processor list: {}".format(
              empty_200_count
            )
        )
      lines.append(
          "  polls returning 200 with non-empty processor list: {}".format(
              nonempty_200_count
            )
        )
      lines.append("  polls returning error: {}".format(error_count))
      # Show first 10, last 10, and any nonempty-list polls
      shown = set()
      lines.append("  poll details (first 10):")
      for i, (t, status, names) in enumerate(diag_poll_log[:10]):
        lines.append(
            "    t={:.2f}s status={} names={}".format(t, status, names)
          )
        shown.add(i)
      for i, (t, status, names) in enumerate(diag_poll_log):
        if status == 200 and names not in ([], None) and i not in shown:
          lines.append(
              "    t={:.2f}s status={} names={}".format(t, status, names)
            )
          shown.add(i)
      if len(diag_poll_log) > 10:
        lines.append("  poll details (last 10):")
        for i in range(max(0, len(diag_poll_log) - 10), len(diag_poll_log)):
          if i not in shown:
            t, status, names = diag_poll_log[i]
            lines.append(
                "    t={:.2f}s status={} names={}".format(t, status, names)
              )
      job_detail = "\n".join(lines)

    context.results.record(self.name,
        "/diagnostics shows in-flight job during shutdown",
        diagnostics_showed_job,
        "timeout_test_sleep_async visible"
        if diagnostics_showed_job else
        job_detail)

    # -- Wait for server to exit -----------------------------------------------

    print("  Waiting for server to exit (max {}s)...".format(
        SIGINT_SHUTDOWN_TIMEOUT))
    try:
      # Use poll loop since we do not own the Popen object
      exit_deadline = time.time() + SIGINT_SHUTDOWN_TIMEOUT
      while time.time() < exit_deadline:
        if context.server_manager.poll() is not None:
          break
        time.sleep(0.5)

      exit_code = context.server_manager.poll()
      if exit_code is None:
        context.results.record(self.name,
            "Server exited after SIGINT", False,
            "Did not exit within {}s".format(SIGINT_SHUTDOWN_TIMEOUT))
        return False

      shutdown_duration = time.time() - sigint_time
      print("  Server exited {:.1f}s after SIGINT (exit code {})".format(
          shutdown_duration, exit_code))
      server_exited_cleanly = exit_code in (
          0, -signal.SIGINT, -signal.SIGTERM)
      context.results.record(self.name,
          "Server exited after SIGINT", server_exited_cleanly,
          "Exit code {}".format(exit_code))
    except Exception as e:
      context.results.record(self.name,
          "Server exited after SIGINT", False, str(e))
      return False

    # -- Verify via a fresh server instance ------------------------------------

    print("  Waiting for port to become free...")
    url_parts = urllib.parse.urlparse(context.base_url)
    port = url_parts.port or 8000
    if not wait_for_port_free(port):
      context.results.record(self.name,
          "Port free after shutdown", False,
          "Port {} still in use after 30s".format(port))
      return False

    print("  Starting verify server to check Redis state and vCon...")
    verify_env = context.env.copy()
    verify_env["RUN_BACKGROUND_JOBS"] = "False"

    verify_log_path = os.path.join(
        _SCRIPTS_DIR, "test_integration_verify.log")
    verify_log_file = open(verify_log_path, "w")
    verify_proc = subprocess.Popen(
        [sys.executable, "-m", "py_vcon_server"],
        env=verify_env,
        stdout=verify_log_file,
        stderr=verify_log_file
      )

    try:
      # Wait for verify server
      import urllib.request
      vdeadline = time.time() + STARTUP_TIMEOUT
      verify_ready = False
      while time.time() < vdeadline:
        if verify_proc.poll() is not None:
          break
        try:
          with urllib.request.urlopen(
              "{}/docs".format(context.base_url), timeout=1.0
            ) as resp:
            if resp.status == 200:
              verify_ready = True
              break
        except Exception:
          pass
        time.sleep(0.5)

      if not verify_ready:
        context.results.record(self.name,
            "Verify server started", False,
            "Did not become ready within {}s".format(STARTUP_TIMEOUT))
        return False

      with httpx.Client(base_url=context.base_url) as client:

        # -- 90c: Redis cleanup check ------------------------------------------
        try:
          r = get(client, "/servers")
          if r.status_code == 200:
            servers = r.json()
            old_pid_str = str(server_proc_pid)
            stale = [k for k in servers if old_pid_str in k]
            redis_clean = len(stale) == 0
            context.results.record(self.name,
                "Redis clean after shutdown", redis_clean,
                "No stale entries for old PID {}".format(
                    server_proc_pid)
                if redis_clean else
                "Stale entries found: {}".format(stale))
          else:
            context.results.record(self.name,
                "Redis clean after shutdown", False,
                "GET /servers -> {}".format(r.status_code))
        except Exception as e:
          context.results.record(self.name,
              "Redis clean after shutdown", False, str(e))

        # -- 90c2: worker hash has no entries for old server ----
        try:
          import redis
          import urllib.parse
          redis_url = context.env.get(
              "VCON_STORAGE_URL", "redis://localhost"
            )
          parsed = urllib.parse.urlparse(redis_url)
          r_client = redis.Redis(
              host=parsed.hostname or "localhost",
              port=parsed.port or 6379,
              decode_responses=True
            )
          worker_keys = r_client.hkeys("server_worker_states")
          stale_workers = [
              k for k in worker_keys if old_pid_str in k
            ]
          workers_clean = len(stale_workers) == 0
          context.results.record(self.name,
              "Worker hash clean after shutdown",
              workers_clean,
              "No stale worker entries for PID {}".format(
                  server_proc_pid)
              if workers_clean else
              "Stale worker entries: {}".format(stale_workers))
          r_client.close()
        except Exception as e:
          context.results.record(self.name,
              "Worker hash clean after shutdown",
              False, str(e))

        # -- 90a: In-flight job completed --------------------------------------
        try:
          r = get(client, "/vcon/{}".format(SIGINT_UUID))
          if r.status_code == 200:
            analyses = r.json().get("analysis", [])
            found = any(
                a.get("type") == "sigint_test" and
                SIGINT_MARKER in str(a.get("body", ""))
                for a in analyses
              )
            context.results.record(self.name,
                "In-flight job completed before shutdown",
                found,
                "Analysis with type=sigint_test and marker found"
                if found else
                "Analysis not found -- job did not complete. "
                "analyses={}".format(analyses))
          else:
            context.results.record(self.name,
                "In-flight job completed before shutdown", False,
                "GET /vcon -> {}".format(r.status_code))
        except Exception as e:
          context.results.record(self.name,
              "In-flight job completed before shutdown",
              False, str(e))

        # -- Cleanup all test artifacts via verify server ----------------------
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
