# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
integration/stages/stage07_prometheus.py

Self-contained stage: starts its own fresh server instance with
ENABLE_PROMETHEUS=true on a different port, runs tests, then shuts
down and cleans up.

Verifies:
  7a: /metrics returns Prometheus text format (# HELP / # TYPE lines)
  7b: PROMETHEUS_MULTIPROC_DIR was created and contains mmap files
  7c: Concurrent processor calls aggregate across all workers
  7d: PROMETHEUS_MULTIPROC_DIR is removed after server exits
"""

import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse

import httpx

from integration.constants import STARTUP_TIMEOUT
from integration.helpers import make_test_vcon_dict

# Stage-specific constants
PROM_STARTUP_TIMEOUT = int(os.environ.get(
    "INTEGRATION_PROM_STARTUP_TIMEOUT",
    str(STARTUP_TIMEOUT)
  ))
PROM_VCON_UUID = "01855517-intg-prom7s-test-77776666acbe"

# scripts/ directory -- two levels up from this file's stages/ package dir.
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))


class Stage:
  name = "stage07_prometheus"
  description = "Prometheus multiprocess metric aggregation"
  expected_state_after = "running"
  min_workers = 2

  def run(self, context):
    # Run on port+1 to avoid conflicting with the main server
    url_parts = urllib.parse.urlparse(context.base_url)
    prom_port = (url_parts.port or 8000) + 1
    prom_base_url = "{}://{}:{}".format(
        url_parts.scheme, url_parts.hostname, prom_port
      )

    prom_env = context.env.copy()
    prom_env["ENABLE_PROMETHEUS"] = "true"
    prom_env["REST_URL"] = prom_base_url
    prom_env["RUN_BACKGROUND_JOBS"] = "False"
    # Do NOT pre-set PROMETHEUS_MULTIPROC_DIR -- __main__.py must create it
    prom_env.pop("PROMETHEUS_MULTIPROC_DIR", None)

    prom_log_path = os.path.join(
        _SCRIPTS_DIR, "test_integration_prom.log")
    prom_log_file = open(prom_log_path, "w")
    prom_proc = subprocess.Popen(
        [sys.executable, "-m", "py_vcon_server"],
        env=prom_env,
        stdout=prom_log_file,
        stderr=prom_log_file
      )
    print("  Prometheus server PID={} port={} log={}".format(
        prom_proc.pid, prom_port, prom_log_path))

    prom_dir = None
    all_passed = True

    try:
      # Wait for server ready
      deadline = time.time() + PROM_STARTUP_TIMEOUT
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
        prom_log_file.flush()
        self._print_prom_log_errors(prom_log_path)
        rc = prom_proc.poll()
        print("  Prometheus server process exit code: {}".format(
            rc if rc is not None else "still running"))
        context.results.record(self.name,
            "Prometheus server started", False,
            "Did not become ready within {}s".format(
                PROM_STARTUP_TIMEOUT))
        return False

      context.results.record(self.name,
          "Prometheus server started", True,
          "port={}".format(prom_port))

      time.sleep(1.0)

      # Resolve prom_dir from server log
      prom_log_file.flush()
      try:
        with open(prom_log_path, "r") as lf:
          for line in lf:
            marker = "Prometheus multiprocess directory created: "
            idx = line.find(marker)
            if idx >= 0:
              prom_dir = line[idx + len(marker):].split()[0].rstrip(")")
              break
      except Exception as e:
        print("  Could not read prom_dir from log: {}".format(e))

      with httpx.Client(base_url=prom_base_url) as client:

        # 7a: /metrics returns Prometheus text format
        try:
          r = client.get("/metrics", timeout=5.0)
          has_help = "# HELP" in r.text
          has_type = "# TYPE" in r.text
          passed = r.status_code == 200 and has_help and has_type
          context.results.record(self.name,
              "/metrics returns Prometheus format", passed,
              "status={} #HELP={} #TYPE={}".format(
                  r.status_code, has_help, has_type))
          if not passed:
            all_passed = False
        except Exception as e:
          context.results.record(self.name,
              "/metrics returns Prometheus format", False, str(e))
          all_passed = False

        # 7b: PROMETHEUS_MULTIPROC_DIR created with mmap files
        if prom_dir and os.path.isdir(prom_dir):
          mmap_files = sorted(os.listdir(prom_dir))
          passed = len(mmap_files) > 0
          context.results.record(self.name,
              "PROMETHEUS_MULTIPROC_DIR has mmap files", passed,
              "dir={} files={}".format(prom_dir, mmap_files[:4]))
          if not passed:
            all_passed = False
        else:
          context.results.record(self.name,
              "PROMETHEUS_MULTIPROC_DIR has mmap files", False,
              "Could not locate prom_dir from server log "
              "(prom_dir={})".format(prom_dir))
          all_passed = False

        # 7c: Concurrent processor calls aggregate across workers
        num_calls = context.num_workers * 3
        call_results = []
        threads = []

        def fire_processio(idx):
          try:
            request_body = {
              "processor_io": {
                "vcons": [make_test_vcon_dict(PROM_VCON_UUID)],
                "parameters": {}
              },
              "processor_options": {
                "template": "prom test {{ vcons[0].uuid }}",
                "analysis_type": "prom_test",
                "analysis_vendor": "test"
              }
            }
            r = client.post(
                "/processIO/jinja_report",
                json=request_body,
                timeout=15.0
              )
            call_results.append({"idx": idx, "status": r.status_code})
          except Exception as e:
            call_results.append({"idx": idx, "error": str(e)})

        for i in range(num_calls):
          t = threading.Thread(target=fire_processio, args=(i,))
          threads.append(t)
          t.start()

        for t in threads:
          t.join(timeout=30.0)

        successful = sum(
            1 for cr in call_results if cr.get("status") == 200
          )

        # Scrape /metrics and check processor count
        time.sleep(0.5)
        try:
          r = client.get("/metrics", timeout=5.0)
          total_count = 0
          for line in r.text.splitlines():
            m = re.match(
                r'^py_vcon_server_processor_duration_seconds_count'
                r'\{.*\}\s+([\d.]+)',
                line
              )
            if m:
              total_count += float(m.group(1))

          passed = total_count >= successful and successful > 0
          context.results.record(self.name,
              "Processor metrics aggregate across workers", passed,
              "total_count={} successful_calls={}".format(
                  int(total_count), successful))
          if not passed:
            all_passed = False
        except Exception as e:
          context.results.record(self.name,
              "Processor metrics aggregate across workers",
              False, str(e))
          all_passed = False

    finally:
      # Shut down prometheus server
      prom_proc.terminate()
      try:
        prom_proc.wait(timeout=30)
      except subprocess.TimeoutExpired:
        prom_proc.kill()
        prom_proc.wait()
      prom_log_file.close()

    # 7d: PROMETHEUS_MULTIPROC_DIR removed after exit
    if prom_dir:
      prom_dir_gone = not os.path.exists(prom_dir)
      context.results.record(self.name,
          "PROMETHEUS_MULTIPROC_DIR removed after exit", prom_dir_gone,
          "dir={} exists={}".format(prom_dir, not prom_dir_gone))
      if not prom_dir_gone:
        all_passed = False
    else:
      context.results.record(self.name,
          "PROMETHEUS_MULTIPROC_DIR removed after exit", False,
          "Could not determine prom_dir")
      all_passed = False

    return all_passed

  def _print_prom_log_errors(self, log_path):
    """Print ERROR/exception lines from the prometheus server log."""
    try:
      with open(log_path, "r") as lf:
        lines = lf.readlines()
      error_keywords = (
          "ERROR", "Traceback", "Error", "Exception",
          "CRITICAL", "Address already in use"
        )
      important_indices = set()
      for i, line in enumerate(lines):
        if any(k in line for k in error_keywords):
          for j in range(max(0, i - 2), min(len(lines), i + 5)):
            important_indices.add(j)
      if important_indices:
        print("  ERROR lines from prom log (with context):")
        for idx in sorted(important_indices)[:60]:
          print("    {:4d}: {}".format(idx, lines[idx].rstrip()))
      tail = lines[-50:] if len(lines) > 50 else lines
      print("  Last {} lines of prom log:".format(len(tail)))
      for line in tail:
        print("    {}".format(line.rstrip()))
    except Exception as read_err:
      print("  Could not read prom log: {}".format(read_err))
