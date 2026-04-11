# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
multiworker/stage7.py — Prometheus multiprocess metric aggregation.

This stage is self-contained: it starts its own fresh server instance
with ENABLE_PROMETHEUS=true on a different port, runs tests, then shuts
down and cleans up.  It must run before Stage 6 since Stage 6 terminates
the main server.
"""

import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse

import httpx

from multiworker.constants import (
  STARTUP_TIMEOUT,
  PROM_VCON_UUID,
)
from multiworker.helpers import get, make_test_vcon_dict
from multiworker.results import Results

# scripts/ directory — one level up from this file's multiworker/ package dir.
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def stage7_prometheus(
    results: Results,
    base_url: str,
    env: dict,
    num_workers: int
  ) -> bool:
  """
  Stage 7 (prometheus): Prometheus multiprocess metric aggregation.

  Starts a fresh server with ENABLE_PROMETHEUS=true on base_url_port+1.
  __main__.py creates PROMETHEUS_MULTIPROC_DIR before workers start.
  Verifies:

    7a: /metrics returns Prometheus text format (# HELP / # TYPE lines)
    7b: PROMETHEUS_MULTIPROC_DIR was created and contains mmap files
    7c: Concurrent processor calls aggregate across all workers —
        py_vcon_server_processor_duration_seconds_count sums to at
        least the number of successful calls
    7d: PROMETHEUS_MULTIPROC_DIR is removed after server exits —
        stale mmap files would poison the next run's counter values

  Uses /processIO/jinja_report (no Redis storage, no pipeline setup)
  to generate processor metrics cleanly without queue infrastructure.
  """
  print()
  print("Stage 7: Prometheus multiprocess metric aggregation")

  # Run on port+1 to avoid conflicting with the still-running main server
  url_parts = urllib.parse.urlparse(base_url)
  prom_port = (url_parts.port or 8000) + 1
  prom_base_url = "{}://{}:{}".format(
      url_parts.scheme, url_parts.hostname, prom_port
    )

  prom_env = env.copy()
  prom_env["ENABLE_PROMETHEUS"] = "true"
  prom_env["REST_URL"] = prom_base_url
  prom_env["RUN_BACKGROUND_JOBS"] = "False"
  # Do NOT pre-set PROMETHEUS_MULTIPROC_DIR — __main__.py must create it
  prom_env.pop("PROMETHEUS_MULTIPROC_DIR", None)

  prom_log_path = os.path.join(_SCRIPTS_DIR, "test_multiworker_prom.log")
  prom_log_file = open(prom_log_path, "w")
  prom_proc = subprocess.Popen(
      [sys.executable, "-m", "py_vcon_server"],
      env=prom_env,
      stdout=prom_log_file,
      stderr=prom_log_file
    )
  print("  Prometheus server PID={} port={} log={}".format(
      prom_proc.pid, prom_port, prom_log_path))

  prom_dir = None   # resolved from server log after startup
  all_passed = True

  try:
    # ── Wait for server ready ────────────────────────────────────────────────
    deadline = time.time() + STARTUP_TIMEOUT
    ready = False
    while time.time() < deadline:
      if prom_proc.poll() is not None:
        break
      try:
        with httpx.Client(base_url=prom_base_url) as hc:
          r = hc.get("/docs", timeout=1.0)
          if r.status_code == 200:
            ready = True
            break
      except Exception:
        pass
      time.sleep(0.5)

    if not ready:
      results.record(7, "Prometheus server started", False,
          "Did not become ready within {}s".format(STARTUP_TIMEOUT))
      return False
    results.record(7, "Prometheus server started", True,
        "port={}".format(prom_port))

    # Give workers a moment to initialize and write their initial mmap files
    time.sleep(1.0)

    # ── Resolve prom_dir from server log ─────────────────────────────────────
    # __main__.py logs: "Prometheus multiprocess directory created: /path ..."
    prom_log_file.flush()
    try:
      with open(prom_log_path, "r") as lf:
        for line in lf:
          marker = "Prometheus multiprocess directory created: "
          idx = line.find(marker)
          if idx >= 0:
            # Path ends at whitespace or end-of-line
            prom_dir = line[idx + len(marker):].split()[0].rstrip(")")
            break
    except Exception as e:
      print("  Could not read prom_dir from log: {}".format(e))

    with httpx.Client(base_url=prom_base_url) as client:

      # ── 7a: /metrics returns Prometheus text format ──────────────────────
      try:
        r = get(client, "/metrics")
        has_help = "# HELP" in r.text
        has_type = "# TYPE" in r.text
        passed = r.status_code == 200 and has_help and has_type
        results.record(7, "/metrics returns Prometheus format", passed,
            "status={} #HELP={} #TYPE={}".format(
                r.status_code, has_help, has_type))
        if not passed:
          all_passed = False
      except Exception as e:
        results.record(7, "/metrics returns Prometheus format", False, str(e))
        all_passed = False

      # ── 7b: PROMETHEUS_MULTIPROC_DIR created with mmap files ─────────────
      if prom_dir and os.path.isdir(prom_dir):
        mmap_files = sorted(os.listdir(prom_dir))
        passed = len(mmap_files) > 0
        results.record(7, "PROMETHEUS_MULTIPROC_DIR has mmap files", passed,
            "dir={} files={}".format(prom_dir, mmap_files[:4]))
        if not passed:
          all_passed = False
      else:
        results.record(7, "PROMETHEUS_MULTIPROC_DIR has mmap files", False,
            "Could not locate prom_dir from server log "
            "(prom_dir={})".format(prom_dir))
        all_passed = False

      # ── 7c: Concurrent processor calls aggregate across workers ───────────
      # Fire num_workers*3 concurrent /processIO/jinja_report calls.
      # Each call increments py_vcon_server_processor_duration_seconds_count.
      # MultiProcessCollector must sum counts across all workers.
      num_calls = max(num_workers * 3, 6)
      call_statuses = [None] * num_calls
      call_lock = threading.Lock()

      def make_proc_call(idx):
        try:
          with httpx.Client(base_url=prom_base_url) as hc:
            request_body = {
                "processor_io": {
                    "vcons": [make_test_vcon_dict(PROM_VCON_UUID)],
                    "parameters": {}
                  },
                "processor_options": {
                    "template": "test uuid={{ vcons[0].uuid }}"
                  }
              }
            r = hc.post(
                "/processIO/jinja_report",
                json=request_body,
                timeout=15.0
              )
            with call_lock:
              call_statuses[idx] = r.status_code
        except Exception as e:
          with call_lock:
            call_statuses[idx] = str(e)

      threads = [
          threading.Thread(target=make_proc_call, args=(i,))
          for i in range(num_calls)
        ]
      for t in threads:
        t.start()
      for t in threads:
        t.join(timeout=20.0)

      successful_calls = sum(1 for s in call_statuses if s == 200)
      print("  Concurrent processor calls: {}/{} succeeded".format(
          successful_calls, num_calls))

      # Small pause for mmap flush
      time.sleep(0.5)

      # Scrape /metrics and sum py_vcon_server_processor_duration_seconds_count
      # for jinja_report across all label combinations (all workers).
      try:
        r = get(client, "/metrics")
        if r.status_code == 200:
          hist_total = 0.0
          for line in r.text.splitlines():
            # Match any label set that includes processor_name="jinja_report"
            m = re.match(
                r'^py_vcon_server_processor_duration_seconds_count'
                r'\{[^}]*processor_name="jinja_report"[^}]*\}\s+([\d.]+)',
                line
              )
            if m:
              hist_total += float(m.group(1))

          passed = int(hist_total) >= successful_calls
          results.record(
              7,
              "Processor metrics aggregate across {} worker(s)".format(
                  num_workers),
              passed,
              "histogram_count={:.0f} successful_calls={} workers={}".format(
                  hist_total, successful_calls, num_workers)
            )
          if not passed:
            all_passed = False
        else:
          results.record(
              7,
              "Processor metrics aggregate across {} worker(s)".format(
                  num_workers),
              False,
              "/metrics returned {}".format(r.status_code)
            )
          all_passed = False
      except Exception as e:
        results.record(
            7,
            "Processor metrics aggregate across {} worker(s)".format(
                num_workers),
            False, str(e)
          )
        all_passed = False

  finally:
    # ── Shut down the Prometheus server ──────────────────────────────────────
    if prom_proc.poll() is None:
      prom_proc.terminate()
      try:
        prom_proc.wait(timeout=20)
      except subprocess.TimeoutExpired:
        prom_proc.kill()
        prom_proc.wait()
    prom_log_file.close()

  # ── 7d: Verify PROMETHEUS_MULTIPROC_DIR cleaned up after shutdown ─────────
  # __main__.py calls shutil.rmtree(prom_dir) in its finally block.
  # If the dir still exists, cleanup failed — stale counter and histogram
  # files would inflate metrics on the next server start.
  if prom_dir:
    dir_gone = not os.path.exists(prom_dir)
    results.record(7, "PROMETHEUS_MULTIPROC_DIR removed after shutdown",
        dir_gone,
        "Directory removed cleanly"
        if dir_gone else
        "Directory still present: {} — shutil.rmtree may not have run".format(
            prom_dir))
    if not dir_gone:
      all_passed = False
  else:
    results.record(7, "PROMETHEUS_MULTIPROC_DIR removed after shutdown",
        False,
        "Could not locate prom_dir from log — unable to verify cleanup")
    all_passed = False

  return all_passed
