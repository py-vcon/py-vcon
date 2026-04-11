# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
multiworker/stage1.py — Server startup health check.
"""

import subprocess
import time

import httpx

from multiworker.constants import STARTUP_TIMEOUT
from multiworker.results import Results


def stage1_startup(
    results: Results,
    base_url: str,
    server_proc: subprocess.Popen
  ) -> bool:
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
        r = client.get("/docs", timeout=2.0)
        if r.status_code == 200:
          results.record(1, "Server started and health check responds", True,
              "GET /docs → 200 in {:.1f}s".format(
                  STARTUP_TIMEOUT - (deadline - time.time())))
          return True
    except Exception:
      pass
    time.sleep(0.5)

  results.record(1, "Server started and health check responds", False,
      "Timed out after {}s".format(STARTUP_TIMEOUT))
  return False
