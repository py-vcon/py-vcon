# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
integration/stages/stage08_diagnostics.py

Cross-worker /diagnostics aggregation via shared memory.

Verifies:
  8a: /diagnostics returns empty dict when no processors are running
  8b: During a slow processor call, /diagnostics shows the active run
  8c: After the slow processor completes, /diagnostics returns empty again
"""

import threading
import time

import httpx

from integration.helpers import get, make_test_vcon_dict

# Stage-specific constants
DIAG_VCON_UUID = "01855517-intg-diag8s-test-77776666acbe"
DIAG_SLEEP_SECONDS = 5.0


class Stage:
  name = "stage08_diagnostics"
  description = "Cross-worker /diagnostics aggregation via shared memory"
  expected_state_after = "running"
  min_workers = 2

  def run(self, context):
    with httpx.Client(base_url=context.base_url) as client:

      # 8a: /diagnostics empty when idle
      try:
        r = get(client, "/diagnostics", timeout=5.0)
        passed = r.status_code == 200 and len(r.json()) == 0
        context.results.record(self.name,
            "/diagnostics empty when idle", passed,
            "status={} entries={}".format(r.status_code, len(r.json())))
        if not passed and r.status_code == 200:
          print("  Active runs (should be empty): {}".format(r.json()))
      except Exception as e:
        context.results.record(self.name,
            "/diagnostics empty when idle", False, str(e))

      # Fire a slow processor call in a thread
      slow_result = {}

      def send_slow_request():
        try:
          with httpx.Client(base_url=context.base_url) as hc:
            request_body = {
              "processor_io": {
                "vcons": [make_test_vcon_dict(DIAG_VCON_UUID)],
                "parameters": {}
              },
              "processor_options": {
                "sleep_seconds": DIAG_SLEEP_SECONDS
              }
            }
            r = hc.post(
                "/processIO/timeout_test_sleep_async",
                json=request_body,
                timeout=DIAG_SLEEP_SECONDS + 10.0
              )
            slow_result["status"] = r.status_code
        except Exception as e:
          slow_result["error"] = str(e)

      slow_thread = threading.Thread(
          target=send_slow_request, daemon=True
        )
      slow_thread.start()

      # Wait for the slow request to be picked up
      time.sleep(1.5)

      # 8b: /diagnostics shows active run during slow processor
      seen_active = False
      for _ in range(context.num_workers * 3):
        try:
          r = get(client, "/diagnostics", timeout=3.0)
          if r.status_code == 200:
            diag_data = r.json()
            if any(
                run.get("processor_name") == "timeout_test_sleep_async"
                for run in diag_data.values()
              ):
              seen_active = True
              break
        except Exception:
          pass
        time.sleep(0.3)

      context.results.record(self.name,
          "/diagnostics shows active run during slow processor",
          seen_active,
          "timeout_test_sleep_async visible"
          if seen_active else
          "Active run not visible -- may need more poll attempts")

      # Wait for slow request to complete
      slow_thread.join(timeout=DIAG_SLEEP_SECONDS + 10.0)

      # 8c: /diagnostics empty again after completion
      time.sleep(0.5)
      try:
        r = get(client, "/diagnostics", timeout=5.0)
        passed = r.status_code == 200 and len(r.json()) == 0
        context.results.record(self.name,
            "/diagnostics empty after slow processor completes", passed,
            "status={} entries={}".format(r.status_code, len(r.json())))
      except Exception as e:
        context.results.record(self.name,
            "/diagnostics empty after slow processor completes",
            False, str(e))

      return seen_active
