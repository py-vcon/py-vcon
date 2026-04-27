# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
integration/stages/stage05_concurrent_jobs.py

Two concurrent jobs complete faster than 2x sequential time.
Proves parallel background processing across workers.
"""

import time

import httpx

from integration.constants import (
  QUEUE_NAME,
  VCON_UUID,
  JOB_POLL_TIMEOUT,
  JOB_POLL_INTERVAL,
)
from integration.helpers import get, post, put, make_test_vcon_dict, jobs_for_vcon

# Stage-specific constants
VCON_UUID_2 = "01855517-intg-rat2n-test-77776666acbe"


class Stage:
  name = "stage05_concurrent_jobs"
  description = "Two concurrent jobs complete faster than 2x sequential time"
  expected_state_after = "running"
  min_workers = 2

  def run(self, context):
    with httpx.Client(base_url=context.base_url) as client:

      def push_and_wait(uuid):
        """Push a job for the given vCon UUID and return elapsed seconds."""
        start = time.time()
        job = {"job_type": "vcon_uuid", "vcon_uuid": [uuid]}
        r = put(client, "/queue/{}".format(QUEUE_NAME), job, timeout=10.0)
        if r.status_code != 200:
          return -1.0

        deadline = time.time() + JOB_POLL_TIMEOUT
        while time.time() < deadline:
          r = get(client, "/in_progress", timeout=5.0)
          if r.status_code == 200:
            our_jobs = jobs_for_vcon(r.json(), uuid)
            if len(our_jobs) == 0:
              r2 = get(
                  client, "/queue/{}".format(QUEUE_NAME), timeout=5.0
                )
              if r2.status_code == 200 and len(r2.json()) == 0:
                return time.time() - start
          time.sleep(JOB_POLL_INTERVAL)
        return -1.0

      # Store second vCon
      try:
        r = post(client, "/vcon", make_test_vcon_dict(VCON_UUID_2))
        if r.status_code != 204:
          context.results.record(
              self.name, "Store second test vCon", False,
              "POST /vcon -> {}".format(r.status_code))
          return False
      except Exception as e:
        context.results.record(
            self.name, "Store second test vCon", False, str(e))
        return False

      # Measure single job time
      print("  Measuring single job time...")
      single_time = push_and_wait(VCON_UUID_2)
      if single_time < 0:
        context.results.record(
            self.name, "Single job timing baseline", False,
            "Job timed out")
        return False
      print("  Single job time: {:.2f}s".format(single_time))

      # Push two jobs simultaneously
      print("  Pushing 2 jobs simultaneously...")
      concurrent_start = time.time()

      for uuid in [VCON_UUID, VCON_UUID_2]:
        job = {"job_type": "vcon_uuid", "vcon_uuid": [uuid]}
        put(client, "/queue/{}".format(QUEUE_NAME), job)

      deadline = time.time() + JOB_POLL_TIMEOUT * 2
      while time.time() < deadline:
        r = get(client, "/in_progress")
        r2 = get(client, "/queue/{}".format(QUEUE_NAME))
        if r.status_code == 200 and r2.status_code == 200:
          our_in_prog = {}
          our_in_prog.update(jobs_for_vcon(r.json(), VCON_UUID))
          our_in_prog.update(jobs_for_vcon(r.json(), VCON_UUID_2))
          if len(r2.json()) == 0 and len(our_in_prog) == 0:
            break
        time.sleep(JOB_POLL_INTERVAL)

      concurrent_time = time.time() - concurrent_start
      print("  Concurrent (2 jobs) wall time: {:.2f}s".format(
          concurrent_time))

      effective_single_time = max(single_time, 0.5)
      threshold = effective_single_time * 1.6
      passed = concurrent_time < threshold
      if passed:
        detail = ("2-job wall time {:.2f}s < threshold {:.2f}s "
            "(1.6x effective single {:.2f}s)").format(
                concurrent_time, threshold, effective_single_time)
      else:
        detail = ("2-job wall time {:.2f}s >= threshold {:.2f}s "
            "-- jobs ran sequentially").format(
                concurrent_time, threshold)

      context.results.record(
          self.name, "Two jobs run concurrently", passed, detail)

      # Cleanup second vCon
      try:
        client.delete("/vcon/{}".format(VCON_UUID_2), timeout=5.0)
      except Exception:
        pass

      return passed
