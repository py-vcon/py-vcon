# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
integration/stages/stage03_blocking_isolation.py

Health check responds while one worker is blocked synchronously.
workers=1 would cause health check to hang (documents the bug).
workers>1 proves isolation -- health check returns quickly.
"""

import os
import threading
import time

import httpx

from integration.constants import HEALTH_TIMEOUT, VCON_UUID
from integration.helpers import make_test_vcon_dict

# Stage-specific constants
BLOCK_SECONDS = 8


class Stage:
  name = "stage03_blocking_isolation"
  description = "Health check responds while a worker is blocked"
  expected_state_after = "running"
  min_workers = 2

  def run(self, context):
    block_result = {}
    health_result = {}

    def send_blocking_request():
      try:
        with httpx.Client(base_url=context.base_url) as client:
          request_body = {
            "processor_io": {
              "vcons": [make_test_vcon_dict(VCON_UUID)],
              "parameters": {}
            },
            "processor_options": {
              "sleep_seconds": float(BLOCK_SECONDS)
            }
          }
          r = client.post(
              "/processIO/timeout_test_sleep_sync",
              json=request_body,
              timeout=BLOCK_SECONDS + 5.0
            )
          block_result["status"] = r.status_code
      except Exception as e:
        block_result["error"] = str(e)

    block_thread = threading.Thread(
        target=send_blocking_request, daemon=True
      )
    block_thread.start()

    # Give the blocking request time to reach the server and occupy a worker.
    time.sleep(float(os.environ.get("INTEGRATION_BLOCK_WAIT", "1.5")))

    health_start = time.time()
    try:
      with httpx.Client(base_url=context.base_url) as client:
        r = client.get("/docs", timeout=HEALTH_TIMEOUT)
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

    block_thread.join(timeout=BLOCK_SECONDS + 5.0)

    if health_result.get("timeout"):
      passed = False
      detail = ("Health check timed out after {:.1f}s "
          "-- event loop blocked").format(health_result["elapsed"])
    elif "error" in health_result:
      passed = False
      detail = "Health check error: {}".format(health_result["error"])
    elif health_result.get("status") == 200:
      passed = True
      detail = ("Health check returned 200 in {:.2f}s "
          "while worker was blocked").format(health_result["elapsed"])
    else:
      passed = False
      detail = "Health check returned status {}".format(
          health_result.get("status"))

    context.results.record(self.name, self.description, passed, detail)
    return passed
