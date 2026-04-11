#!/usr/bin/env python3
# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
Proof of concept for prometheus_client multiprocess mode with
prometheus_fastapi_instrumentator and uvicorn multi-worker.

Proves:
  1. PROMETHEUS_MULTIPROC_DIR must be set before any prometheus_client
     import in worker processes — verified by checking mmap files appear.
  2. prometheus_fastapi_instrumentator works correctly when multiprocess
     mode is active — instrument() must be called at module level, not
     inside lifespan.
  3. Custom Gauge, Histogram, and Counter metrics created inside lifespan
     (after PROMETHEUS_MULTIPROC_DIR is confirmed set) aggregate correctly
     across workers.
  4. A custom /metrics endpoint using MultiProcessCollector returns
     merged data from all workers — not just the worker that handles
     the scrape request.
  5. The PROMETHEUS_MULTIPROC_DIR is cleanable on shutdown with no
     stale mmap files causing problems.

Key findings from PoC development:
  - prometheus_fastapi_instrumentator.instrument() calls
    app.add_middleware() internally.  Starlette raises RuntimeError if
    add_middleware() is called after the app has started, so instrument()
    MUST be called at module level, not inside lifespan.
  - prometheus_client MUST still be imported inside lifespan (not at
    module level) so that PROMETHEUS_MULTIPROC_DIR is already set in
    the environment when prometheus_client first initializes.
  - prometheus_fastapi_instrumentator itself does not import
    prometheus_client at instantiation time, so it is safe to import
    and call instrument() at module level before the env var check.
  - Do NOT call instrumentator.expose() in multiprocess mode — use a
    custom /metrics endpoint with MultiProcessCollector instead.

Architecture:
  Parent process:
    - Creates a temp directory for PROMETHEUS_MULTIPROC_DIR
    - Sets the env var BEFORE forking workers
    - Starts a 2-worker uvicorn server using Multiprocess supervisor
    - After server exits, verifies directory is clean and removes it

  Worker processes (the FastAPI app):
    - prometheus_fastapi_instrumentator.instrument() called at module level
    - prometheus_client imported inside lifespan after env var confirmed
    - Custom /metrics endpoint using MultiProcessCollector
    - /work endpoint increments a custom counter
    - /pid endpoint returns worker PID for load distribution verification

  Test driver (runs in parent after server is up):
    - Hits /pid repeatedly to confirm both workers are reachable
    - Hits /work N times spread across workers
    - Scrapes /metrics and verifies counter aggregates across workers
    - Sends SIGTERM to shut down the server gracefully
    - Verifies PROMETHEUS_MULTIPROC_DIR is removable after shutdown

Usage:
    python3 scripts/test_prometheus_multiprocess_poc.py [--workers N]
                                                        [--hits N]
                                                        [--port N]

Requires (already in py-vcon pip requirements):
    fastapi, uvicorn, prometheus_client, prometheus_fastapi_instrumentator
"""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_PORT     = 18765   # unlikely to conflict with running services
DEFAULT_WORKERS  = 2
DEFAULT_HITS     = 20
STARTUP_TIMEOUT  = 15.0    # seconds to wait for server to become ready
SHUTDOWN_TIMEOUT = 10.0    # seconds to wait for clean shutdown


# ── The FastAPI application ───────────────────────────────────────────────────
# Defined as a string and written to a temp file so uvicorn workers can
# import it by module path string.  uvicorn's Multiprocess supervisor
# re-imports the app module in each worker process — it cannot use an
# in-memory object reference across process boundaries.
#
# Import order inside this module is critical — see module docstring.

APP_SOURCE = """\
# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
\"\"\"
FastAPI application for prometheus multiprocess PoC.

Import order is critical for prometheus_client multiprocess mode:

  1. prometheus_fastapi_instrumentator is imported and instrument() is
     called at module level before the app starts.  This is required
     because Starlette raises RuntimeError if add_middleware() is called
     after the app has started — and instrument() calls add_middleware()
     internally.

  2. prometheus_client is imported inside lifespan ONLY, never at module
     level.  PROMETHEUS_MULTIPROC_DIR must already be set in the
     environment (inherited from parent) before prometheus_client is
     first imported in this process.  Importing prometheus_client before
     the env var is set silently initializes it in single-process mode
     and multiprocess aggregation breaks.

  3. Custom metrics (Counter, Gauge, Histogram) are created inside
     lifespan after confirming PROMETHEUS_MULTIPROC_DIR is set.
\"\"\"
import os
import fastapi
import prometheus_fastapi_instrumentator
from contextlib import asynccontextmanager


# ── Metric objects -- populated in lifespan after prometheus_client import ----
_work_counter   = None   # prometheus_client.Counter
_work_histogram = None   # prometheus_client.Histogram
_worker_gauge   = None   # prometheus_client.Gauge


@asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
  global _work_counter, _work_histogram, _worker_gauge

  # Verify PROMETHEUS_MULTIPROC_DIR is set before importing prometheus_client.
  prom_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR", "")
  if not prom_dir:
    raise RuntimeError(
        "PROMETHEUS_MULTIPROC_DIR must be set before starting workers. "
        "Set it in the parent process before calling Multiprocess.run()."
      )
  if not os.path.isdir(prom_dir):
    raise RuntimeError(
        "PROMETHEUS_MULTIPROC_DIR={} does not exist. "
        "Parent must create the directory before forking.".format(prom_dir)
      )

  # NOW it is safe to import prometheus_client -- env var is set.
  import prometheus_client
  import prometheus_client.multiprocess

  # Create custom metrics.  In multiprocess mode, prometheus_client writes
  # each metric to an mmap file in PROMETHEUS_MULTIPROC_DIR.  Multiple
  # workers each get their own file; MultiProcessCollector merges them.
  _work_counter = prometheus_client.Counter(
      "poc_work_total",
      "Total number of /work requests handled",
      ["worker_pid"],
    )
  _work_histogram = prometheus_client.Histogram(
      "poc_work_duration_seconds",
      "Duration of /work requests",
      buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
    )
  _worker_gauge = prometheus_client.Gauge(
      "poc_worker_pid",
      "PID of this worker process",
      ["pid"],
      multiprocess_mode="liveall",   # report value from ALL live workers
    )
  _worker_gauge.labels(pid=str(os.getpid())).set(1)

  print("[worker pid={}] lifespan startup complete prom_dir={}".format(
      os.getpid(), prom_dir), flush=True)

  yield

  # -- Shutdown ----------------------------------------------------------------
  # Mark this worker's mmap files as belonging to a dead process so
  # MultiProcessCollector stops including them in future scrapes.
  prometheus_client.multiprocess.mark_process_dead(os.getpid())
  print("[worker pid={}] lifespan shutdown complete".format(
      os.getpid()), flush=True)


app = fastapi.FastAPI(lifespan=lifespan)

# -- prometheus_fastapi_instrumentator setup -- must be at module level --------
# instrument() calls app.add_middleware() internally.  Starlette does not
# allow add_middleware() after the app has started, so this cannot be
# done inside lifespan.  prometheus_fastapi_instrumentator does not import
# prometheus_client at instantiation time so it is safe to set up here
# before PROMETHEUS_MULTIPROC_DIR is confirmed in lifespan.
#
# NOTE: do NOT call instrumentator.expose(app) in multiprocess mode.
# expose() uses the default single-process registry.  We provide our
# own /metrics endpoint below using MultiProcessCollector instead.
_instrumentator = prometheus_fastapi_instrumentator.Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=False,
    should_respect_env_var=False,
    should_instrument_requests_inprogress=True,
    excluded_handlers=["/metrics"],
    inprogress_labels=True,
  )
_instrumentator.add(prometheus_fastapi_instrumentator.metrics.requests())
_instrumentator.add(
    prometheus_fastapi_instrumentator.metrics.latency(
        buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)
      )
  )
_instrumentator.instrument(app)


@app.get("/pid")
async def get_pid():
  \"\"\" Return this worker's PID -- used to verify load distribution. \"\"\"
  return {"pid": os.getpid()}


@app.get("/work")
async def do_work():
  \"\"\"
  Simulate a unit of work.  Increments the custom counter and records
  a histogram observation.  Used to generate cross-worker metric data.
  \"\"\"
  import time as _time
  import asyncio
  start = _time.time()
  await asyncio.sleep(0.001)
  elapsed = _time.time() - start

  if _work_counter is not None:
    _work_counter.labels(worker_pid=str(os.getpid())).inc()
  if _work_histogram is not None:
    _work_histogram.observe(elapsed)

  return {"pid": os.getpid(), "elapsed": elapsed}


@app.get("/metrics")
async def metrics():
  \"\"\"
  Custom /metrics endpoint using MultiProcessCollector.
  This is the correct pattern for multiprocess mode -- it merges mmap
  files from all workers rather than returning only this worker's data.
  DO NOT use prometheus_fastapi_instrumentator.expose() in multiprocess mode.
  \"\"\"
  import prometheus_client
  import prometheus_client.multiprocess

  registry = prometheus_client.CollectorRegistry()
  prometheus_client.multiprocess.MultiProcessCollector(registry)
  data = prometheus_client.generate_latest(registry)
  return fastapi.Response(
      content=data,
      media_type=prometheus_client.CONTENT_TYPE_LATEST,
    )
"""


# ── Server launcher (runs in a subprocess) ────────────────────────────────────

LAUNCHER_SOURCE = """\
# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
\"\"\"
Launcher script for the prometheus multiprocess PoC server.
Run as a subprocess by the test driver.  Reads config from env vars
set by the parent before fork.

PROMETHEUS_MULTIPROC_DIR must already be set in the environment before
this script runs -- it is inherited automatically since we use subprocess.

The if __name__ == "__main__" guard is required because uvicorn's
Multiprocess supervisor uses multiprocessing.Process to start workers.
The default start method on this platform may be "spawn", which
re-executes this script in each worker process.  The guard prevents
the server from being started recursively in those worker processes.
This matches the pattern used by py_vcon_server.__main__ which defines
Server in py_vcon_server.__init__ so it is importable by fully qualified
name when workers are spawned.
\"\"\"
import os
import uvicorn


def main():
  app_module = os.environ["POC_APP_MODULE"]
  port       = int(os.environ["POC_PORT"])
  workers    = int(os.environ["POC_WORKERS"])

  config = uvicorn.Config(
      app_module,
      workers=workers,
      loop="asyncio",
      host="127.0.0.1",
      port=port,
      log_level="warning",
    )
  server = uvicorn.Server(config=config)

  if workers > 1:
    from uvicorn.supervisors import Multiprocess
    sock = config.bind_socket()
    Multiprocess(config, target=server.run, sockets=[sock]).run()
  else:
    server.run()


if __name__ == "__main__":
  main()
"""


# ── Test stages ───────────────────────────────────────────────────────────────

def wait_for_ready(base_url: str, timeout: float) -> bool:
  """
  Poll /pid until the server responds or timeout expires.
  Returns True if ready, False if timed out.
  """
  import urllib.request
  import urllib.error

  deadline = time.time() + timeout
  while time.time() < deadline:
    try:
      with urllib.request.urlopen(
          "{}/pid".format(base_url), timeout=1.0
        ) as resp:
        if resp.status == 200:
          return True
    except Exception:
      pass
    time.sleep(0.2)
  return False


def http_get(url: str) -> tuple:
  """
  Simple HTTP GET.  Returns (status_code, body_str).
  No external dependencies beyond stdlib.
  """
  import urllib.request
  import urllib.error

  try:
    with urllib.request.urlopen(url, timeout=5.0) as resp:
      return resp.status, resp.read().decode("utf-8")
  except urllib.error.HTTPError as e:
    return e.code, e.read().decode("utf-8")
  except Exception as e:
    return 0, str(e)


def run_poc(num_workers: int, num_hits: int, port: int) -> bool:
  """
  Main PoC driver.  Creates temp files, starts server, runs tests,
  shuts down, verifies cleanup.
  """
  import json

  base_url = "http://127.0.0.1:{}".format(port)
  passed = True

  # -- Stage 1: Create PROMETHEUS_MULTIPROC_DIR before any worker starts ------
  print("\n=== Stage 1: Create PROMETHEUS_MULTIPROC_DIR ===", flush=True)
  prom_dir = tempfile.mkdtemp(prefix="poc_prom_")
  print("  prom_dir={}".format(prom_dir), flush=True)

  # Write the app and launcher to temp files so uvicorn can import them
  app_dir = tempfile.mkdtemp(prefix="poc_app_")
  app_file      = os.path.join(app_dir, "poc_app.py")
  launcher_file = os.path.join(app_dir, "poc_launcher.py")
  with open(app_file, "w") as f:
    f.write(APP_SOURCE)
  with open(launcher_file, "w") as f:
    f.write(LAUNCHER_SOURCE)

  print("  app_dir={}".format(app_dir), flush=True)

  # -- Stage 2: Start the server subprocess -----------------------------------
  print("\n=== Stage 2: Start uvicorn server ({} workers) ===".format(
      num_workers), flush=True)

  env = os.environ.copy()
  env["PROMETHEUS_MULTIPROC_DIR"] = prom_dir   # MUST be set before fork
  env["POC_APP_MODULE"]           = "poc_app:app"
  env["POC_PORT"]                 = str(port)
  env["POC_WORKERS"]              = str(num_workers)
  env["PYTHONPATH"]               = app_dir + (
      (":" + env["PYTHONPATH"]) if "PYTHONPATH" in env else ""
    )

  proc = subprocess.Popen(
      [sys.executable, launcher_file],
      env=env,
    )
  print("  server pid={}".format(proc.pid), flush=True)

  # -- Stage 3: Wait for server to become ready -------------------------------
  print("\n=== Stage 3: Wait for server ready ===", flush=True)
  if not wait_for_ready(base_url, STARTUP_TIMEOUT):
    print("  FAIL: server did not become ready within {}s".format(
        STARTUP_TIMEOUT), flush=True)
    proc.terminate()
    proc.wait(timeout=5.0)
    shutil.rmtree(prom_dir, ignore_errors=True)
    shutil.rmtree(app_dir, ignore_errors=True)
    return False
  print("  server is ready", flush=True)

  # -- Stage 4: Verify multiple workers are reachable -------------------------
  print("\n=== Stage 4: Verify worker distribution ===", flush=True)
  pids_seen = set()
  for _ in range(30):
    status, body = http_get("{}/pid".format(base_url))
    if status == 200:
      try:
        pid = json.loads(body)["pid"]
        pids_seen.add(pid)
      except Exception:
        pass
    time.sleep(0.05)

  print("  unique worker PIDs seen: {}".format(sorted(pids_seen)), flush=True)
  if num_workers > 1 and len(pids_seen) < 2:
    print("  WARNING: only saw {} unique worker PID(s) -- "
        "load may not be distributed across workers".format(
            len(pids_seen)), flush=True)
  else:
    print("  load distribution confirmed: {} workers observed".format(
        len(pids_seen)), flush=True)

  # -- Stage 5: Hit /work N times concurrently to stress worker distribution --
  # Sequential requests bias to one worker because the OS routes new
  # connections to the already-warm accept loop.  Concurrent requests
  # force the load balancer to distribute across workers.
  print("\n=== Stage 5: Generate work across workers ({} concurrent hits) ===".format(
      num_hits), flush=True)
  import threading
  work_hits = 0
  work_pids = {}
  results_lock = threading.Lock()
  work_url = "{}/work".format(base_url)

  def do_one_hit():
    nonlocal work_hits
    status, body = http_get(work_url)
    with results_lock:
      if status == 200:
        work_hits += 1
        try:
          pid = json.loads(body)["pid"]
          work_pids[pid] = work_pids.get(pid, 0) + 1
        except Exception:
          pass
      else:
        print("  /work hit returned status {}".format(status), flush=True)

  threads = [threading.Thread(target=do_one_hit) for _ in range(num_hits)]
  for t in threads:
    t.start()
  for t in threads:
    t.join(timeout=10.0)

  print("  successful /work hits: {}/{}".format(work_hits, num_hits), flush=True)
  for pid, count in sorted(work_pids.items()):
    print("  worker pid={}: {} hits".format(pid, count), flush=True)

  if num_workers > 1 and len(work_pids) < 2:
    print("  WARNING: all hits went to one worker -- "
        "distribution check inconclusive but aggregation test still valid",
        flush=True)

  if work_hits != num_hits:
    print("  FAIL: not all /work requests succeeded")
    passed = False

  # Small pause to let all workers flush their mmap files
  time.sleep(0.5)

  # -- Stage 6: Scrape /metrics and verify aggregation ------------------------
  print("\n=== Stage 6: Scrape /metrics and verify cross-worker aggregation ===",
      flush=True)

  status, metrics_body = http_get("{}/metrics".format(base_url))
  if status != 200:
    print("  FAIL: /metrics returned status {}".format(status), flush=True)
    passed = False
    metrics_body = ""

  # Verify poc_work_total counter sums to work_hits across all workers
  import re
  poc_total = 0
  for line in metrics_body.splitlines():
    m = re.match(r'^poc_work_total\{.*\}\s+([\d.]+)', line)
    if m:
      poc_total += float(m.group(1))

  print("  poc_work_total across all workers: {:.0f} (expected {})".format(
      poc_total, work_hits), flush=True)
  if int(poc_total) != work_hits:
    print("  FAIL: poc_work_total={:.0f} != work_hits={}".format(
        poc_total, work_hits))
    passed = False
  else:
    print("  PASS: counter correctly aggregated across workers")

  # Verify poc_work_duration_seconds histogram is present and has observations
  if "poc_work_duration_seconds_count" in metrics_body:
    hist_count = 0
    for line in metrics_body.splitlines():
      m = re.match(r'^poc_work_duration_seconds_count\s+([\d.]+)', line)
      if m:
        hist_count += float(m.group(1))
    print("  poc_work_duration_seconds_count: {:.0f}".format(
        hist_count), flush=True)
    if hist_count >= work_hits:
      print("  PASS: histogram observations present across workers")
    else:
      print("  FAIL: histogram count {:.0f} < work_hits {}".format(
          hist_count, work_hits))
      passed = False
  else:
    print("  FAIL: poc_work_duration_seconds_count not found in /metrics")
    passed = False

  # Verify prometheus_fastapi_instrumentator http_requests_total is present
  if "http_requests_total" in metrics_body:
    print("  PASS: http_requests_total present "
        "(prometheus_fastapi_instrumentator working)")
  else:
    print("  FAIL: http_requests_total not found -- "
        "prometheus_fastapi_instrumentator may not be working in "
        "multiprocess mode")
    passed = False

  # Verify poc_worker_pid gauge shows all workers (liveall mode)
  worker_pids_in_metrics = set()
  for line in metrics_body.splitlines():
    m = re.match(r'^poc_worker_pid\{pid="(\d+)"\}\s+([\d.]+)', line)
    if m and float(m.group(2)) > 0:
      worker_pids_in_metrics.add(int(m.group(1)))
  print("  poc_worker_pid gauge PIDs: {}".format(
      sorted(worker_pids_in_metrics)), flush=True)
  if num_workers > 1 and len(worker_pids_in_metrics) < 2:
    print("  FAIL: poc_worker_pid gauge shows fewer workers than expected")
    passed = False
  else:
    print("  PASS: poc_worker_pid gauge shows all {} worker(s)".format(
        len(worker_pids_in_metrics)))

  # -- Stage 7: Check mmap files exist in PROMETHEUS_MULTIPROC_DIR ------------
  print("\n=== Stage 7: Verify mmap files in PROMETHEUS_MULTIPROC_DIR ===",
      flush=True)
  mmap_files = os.listdir(prom_dir)
  print("  mmap files: {}".format(sorted(mmap_files)), flush=True)
  if len(mmap_files) == 0:
    print("  FAIL: no mmap files found -- multiprocess mode may not be active")
    passed = False
  else:
    print("  PASS: {} mmap file(s) present".format(len(mmap_files)))

  # -- Stage 8: Shutdown server gracefully ------------------------------------
  print("\n=== Stage 8: Graceful shutdown ===", flush=True)
  proc.send_signal(signal.SIGTERM)
  try:
    proc.wait(timeout=SHUTDOWN_TIMEOUT)
    print("  server exited with code {}".format(proc.returncode), flush=True)
  except subprocess.TimeoutExpired:
    print("  WARNING: server did not exit within {}s -- killing".format(
        SHUTDOWN_TIMEOUT), flush=True)
    proc.kill()
    proc.wait()

  # -- Stage 9: Verify PROMETHEUS_MULTIPROC_DIR can be cleaned up -------------
  print("\n=== Stage 9: Verify cleanup of PROMETHEUS_MULTIPROC_DIR ===",
      flush=True)
  remaining = os.listdir(prom_dir)
  print("  files remaining after shutdown: {}".format(
      sorted(remaining)), flush=True)
  # Note: prometheus_client does NOT automatically delete mmap files on
  # shutdown.  The real server must clean up the directory explicitly.
  # This stage verifies the directory is removable -- not that it is empty.
  if remaining:
    print("  NOTE: {} mmap file(s) remained after shutdown -- "
        "real server must call shutil.rmtree(prom_dir) on exit "
        "to avoid stale data poisoning the next run.".format(
            len(remaining)), flush=True)
  try:
    shutil.rmtree(prom_dir)
    print("  PASS: prom_dir removed successfully")
  except Exception as e:
    print("  FAIL: could not remove prom_dir: {}".format(e))
    passed = False

  # -- Stage 10: Verify shutil.rmtree prevents stale data on restart ----------
  print("\n=== Stage 10: Verify clean restart after shutil.rmtree ===",
      flush=True)

  # Create a fresh prom_dir — simulates what the real server does on startup
  prom_dir_2 = tempfile.mkdtemp(prefix="poc_prom2_")
  print("  fresh prom_dir={}".format(prom_dir_2), flush=True)

  env2 = os.environ.copy()
  env2["PROMETHEUS_MULTIPROC_DIR"] = prom_dir_2
  env2["POC_APP_MODULE"]           = "poc_app:app"
  env2["POC_PORT"]                 = str(port)
  env2["POC_WORKERS"]              = str(num_workers)
  env2["PYTHONPATH"]               = app_dir + (
      (":" + env2["PYTHONPATH"]) if "PYTHONPATH" in env2 else ""
    )

  proc2 = subprocess.Popen(
      [sys.executable, launcher_file],
      env=env2,
    )
  print("  second server pid={}".format(proc2.pid), flush=True)

  if not wait_for_ready(base_url, STARTUP_TIMEOUT):
    print("  FAIL: second server did not become ready within {}s".format(
        STARTUP_TIMEOUT), flush=True)
    proc2.terminate()
    proc2.wait(timeout=5.0)
    shutil.rmtree(prom_dir_2, ignore_errors=True)
    passed = False
  else:
    print("  second server is ready", flush=True)

    # Hit /work a known number of times on the fresh server
    second_hits = 10
    threads2 = []
    second_work_hits = 0
    second_results_lock = threading.Lock()

    def do_one_hit2():
      nonlocal second_work_hits
      status, body = http_get("{}/work".format(base_url))
      with second_results_lock:
        if status == 200:
          second_work_hits += 1

    threads2 = [threading.Thread(target=do_one_hit2) for _ in range(second_hits)]
    for t in threads2:
      t.start()
    for t in threads2:
      t.join(timeout=10.0)

    print("  second server /work hits: {}/{}".format(
        second_work_hits, second_hits), flush=True)

    # Small pause for mmap flush
    time.sleep(0.5)

    # Scrape /metrics on the fresh server
    status2, metrics_body2 = http_get("{}/metrics".format(base_url))
    if status2 != 200:
      print("  FAIL: second /metrics returned status {}".format(
          status2), flush=True)
      passed = False
    else:
      # Counter should equal exactly second_hits — not accumulated from
      # the previous run.  If stale mmap files were present, the total
      # would be work_hits + second_hits instead of just second_hits.
      poc_total2 = 0
      for line in metrics_body2.splitlines():
        m = re.match(r'^poc_work_total\{.*\}\s+([\d.]+)', line)
        if m:
          poc_total2 += float(m.group(1))

      print("  poc_work_total on fresh server: {:.0f} (expected {}, "
          "stale would show {})".format(
          poc_total2, second_work_hits, work_hits + second_work_hits),
          flush=True)

      if int(poc_total2) == second_work_hits:
        print("  PASS: fresh server counter starts from 0 -- "
            "shutil.rmtree correctly prevents stale data")
      elif int(poc_total2) == work_hits + second_work_hits:
        print("  FAIL: counter includes stale data from previous run -- "
            "shutil.rmtree did not clean up correctly or was not called")
        passed = False
      else:
        print("  FAIL: unexpected counter value {:.0f}".format(poc_total2))
        passed = False

    # Shutdown second server
    proc2.send_signal(signal.SIGTERM)
    try:
      proc2.wait(timeout=SHUTDOWN_TIMEOUT)
      print("  second server exited with code {}".format(
          proc2.returncode), flush=True)
    except subprocess.TimeoutExpired:
      proc2.kill()
      proc2.wait()

    shutil.rmtree(prom_dir_2, ignore_errors=True)
    print("  second prom_dir removed", flush=True)

  # -- Cleanup temp app files -------------------------------------------------
  shutil.rmtree(app_dir, ignore_errors=True)

  return passed

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
  parser = argparse.ArgumentParser(
      description="Prometheus multiprocess mode PoC with "
          "prometheus_fastapi_instrumentator"
    )
  parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
      help="Number of uvicorn worker processes (default: {})".format(
          DEFAULT_WORKERS))
  parser.add_argument("--hits", type=int, default=DEFAULT_HITS,
      help="Number of /work requests to make (default: {})".format(
          DEFAULT_HITS))
  parser.add_argument("--port", type=int, default=DEFAULT_PORT,
      help="Port to bind the test server on (default: {})".format(
          DEFAULT_PORT))
  args = parser.parse_args()

  passed = run_poc(args.workers, args.hits, args.port)

  print("\n=== Summary ===")
  stages = 10
  if passed:
    print("All {} stages PASSED".format(stages))
    sys.exit(0)
  else:
    print("Some stages FAILED")
    sys.exit(1)

if __name__ == "__main__":
  main()
