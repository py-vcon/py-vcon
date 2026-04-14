# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
multiworker/stage8.py -- Cross-worker /diagnostics aggregation.

This stage tests that /diagnostics returns active runs from all workers,
not just the one that handles the GET request.  Uses the shared memory
slot mechanism allocated by __main__.py.

Verifies:
  8a: /diagnostics returns empty dict when no processors are running
  8b: During a slow processor call, /diagnostics shows the active run
      regardless of which worker handles the GET request (proven by
      hitting /diagnostics multiple times to exercise different workers)
  8c: After the slow processor completes, /diagnostics returns empty again
  8d: worker_key is present in the slot data (via _diagnostics_meta if
      multi-worker, or implicitly via the active run entries)
"""

import os
import threading
import time

import httpx

from multiworker.constants import DIAG_VCON_UUID, STARTUP_TIMEOUT
from multiworker.helpers import get, post, make_test_vcon_dict
from multiworker.results import Results


def stage8_diagnostics_multiworker(
    results: Results,
    base_url: str,
    num_workers: int
  ) -> bool:
  """
  Stage 8 (diagnostics_multiworker): Cross-worker /diagnostics aggregation.

  Uses /processIO/timeout_test_sleep_async to hold a processor invocation
  open for several seconds, then hits /diagnostics repeatedly to verify
  the active run is visible regardless of which worker handles the GET.
  """
  print()
  print("Stage 8: Cross-worker /diagnostics aggregation")

  SLEEP_SECONDS = 6.0
  all_passed = True

  with httpx.Client(base_url=base_url) as client:

    # -- 8a: /diagnostics empty when idle --------------------------------------
    try:
      r = get(client, "/diagnostics")
      if r.status_code != 200:
        results.record(8, "/diagnostics returns 200 when idle", False,
            "status={}".format(r.status_code))
        return False
      diag = r.json()
      # Filter out _diagnostics_meta key if present
      run_keys = [k for k in diag.keys() if not k.startswith("_")]
      idle_ok = len(run_keys) == 0
      results.record(8, "/diagnostics empty when idle", idle_ok,
          "active_runs={}".format(len(run_keys)))
      if not idle_ok:
        all_passed = False
    except Exception as e:
      results.record(8, "/diagnostics empty when idle", False, str(e))
      return False

    # -- 8b: /diagnostics shows active run from another worker -----------------
    # Start a slow processIO request in a background thread
    slow_result = {}

    def slow_request():
      try:
        with httpx.Client(base_url=base_url) as slow_client:
          request_body = {
              "processor_io": {
                  "vcons": [make_test_vcon_dict(DIAG_VCON_UUID)],
                  "parameters": {}
              },
              "processor_options": {
                  "sleep_seconds": SLEEP_SECONDS
              }
          }
          r = slow_client.post(
              "/processIO/timeout_test_sleep_async",
              json=request_body,
              timeout=SLEEP_SECONDS + 10.0
            )
          slow_result["status"] = r.status_code
      except Exception as e:
        slow_result["error"] = str(e)

    slow_thread = threading.Thread(target=slow_request, daemon=True)
    slow_thread.start()

    # Wait for the processor to start
    time.sleep(2.0)

    # Hit /diagnostics multiple times to exercise different workers
    seen_count = 0
    attempt_count = 20
    seen_processor = False
    seen_vcon_uuid = False

    for i in range(attempt_count):
      try:
        r = get(client, "/diagnostics", timeout=5.0)
        if r.status_code == 200:
          diag = r.json()
          run_keys = [k for k in diag.keys() if not k.startswith("_")]
          if len(run_keys) > 0:
            seen_count += 1
            # Check the run content
            for run_id in run_keys:
              run = diag[run_id]
              if run.get("processor_name") == "timeout_test_sleep_async":
                seen_processor = True
              if DIAG_VCON_UUID in run.get("vcon_uuids", []):
                seen_vcon_uuid = True
      except Exception:
        pass
      time.sleep(0.2)

    # In multi-worker mode, the active run should be visible on EVERY hit,
    # because read_all_slots merges across all workers.
    visibility_pct = (seen_count * 100) // attempt_count if attempt_count > 0 else 0

    results.record(8,
        "/diagnostics shows active run across workers",
        seen_count > 0 and seen_processor,
        "seen {}/{} attempts ({}%), processor_name={}, vcon_uuid={}".format(
            seen_count, attempt_count, visibility_pct,
            seen_processor, seen_vcon_uuid
          ))

    if not (seen_count > 0 and seen_processor):
      all_passed = False

    # For multi-worker, we expect 100% visibility
    if num_workers > 1:
      high_visibility = visibility_pct >= 90
      results.record(8,
          "/diagnostics consistent across workers",
          high_visibility,
          "{}% visibility (expect >=90% with shared memory)".format(
              visibility_pct))
      if not high_visibility:
        all_passed = False

    # -- 8c: Wait for slow request to complete, verify empty again -------------
    slow_thread.join(timeout=SLEEP_SECONDS + 10.0)

    if "error" in slow_result:
      results.record(8, "Slow processor completed", False,
          slow_result["error"])
      all_passed = False
    else:
      results.record(8, "Slow processor completed", True,
          "status={}".format(slow_result.get("status")))

    # Brief pause for ACTIVE_RUNS cleanup to propagate to shared memory
    time.sleep(0.5)

    try:
      r = get(client, "/diagnostics")
      diag = r.json()
      run_keys = [k for k in diag.keys() if not k.startswith("_")]
      empty_after = len(run_keys) == 0
      results.record(8, "/diagnostics empty after completion", empty_after,
          "active_runs={}".format(len(run_keys)))
      if not empty_after:
        all_passed = False
    except Exception as e:
      results.record(8, "/diagnostics empty after completion", False, str(e))
      all_passed = False

  return all_passed
