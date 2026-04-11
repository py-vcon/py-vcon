# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
multiworker/stage3.py — Health check while worker is blocked synchronously.
"""

import os
import threading
import time

import httpx

from multiworker.constants import HEALTH_TIMEOUT, VCON_UUID
from multiworker.helpers import make_test_vcon_dict
from multiworker.results import Results


def stage3_blocking_isolation(
    results: Results,
    base_url: str,
    block_seconds: int
  ) -> bool:
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

  # Give the blocking request time to reach the server and occupy a worker.
  # CI runners can be slow — allow this to be configured.
  time.sleep(float(os.environ.get("MULTIWORKER_BLOCK_WAIT", "1.5")))

  health_start = time.time()
  try:
    with httpx.Client(base_url=base_url) as client:
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
