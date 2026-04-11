# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
multiworker/stage5.py — Concurrent background jobs.
"""

import time

import httpx

from multiworker.constants import (
  QUEUE_NAME,
  VCON_UUID,
  VCON_UUID_2,
  JOB_POLL_TIMEOUT,
  JOB_POLL_INTERVAL,
)
from multiworker.helpers import get, post, put, make_test_vcon_dict, jobs_for_vcon
from multiworker.results import Results


def stage5_concurrent_jobs(results: Results, base_url: str) -> bool:
  """
  Stage 5: Two concurrent jobs complete faster than 2x sequential time.
  Proves parallel background processing across workers.
  """
  print()
  print("Stage 5: Concurrent background jobs")

  with httpx.Client(base_url=base_url) as client:

    def push_and_wait(uuid: str) -> float:
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
          # Use jobs_for_vcon() to match on job["job"]["vcon_uuid"] specifically —
          # a vCon dict may contain the UUID in parties, dialogs and analysis
          # objects so a substring match on the serialized dict would produce
          # false positives.
          our_jobs = jobs_for_vcon(r.json(), uuid)
          if len(our_jobs) == 0:
            r2 = get(client, "/queue/{}".format(QUEUE_NAME), timeout=5.0)
            if r2.status_code == 200 and len(r2.json()) == 0:
              return time.time() - start
        time.sleep(JOB_POLL_INTERVAL)
      return -1.0

    # Store second vCon
    try:
      r = post(client, "/vcon", make_test_vcon_dict(VCON_UUID_2))
      if r.status_code != 204:
        results.record(5, "Store second test vCon", False,
            "POST /vcon → {}".format(r.status_code))
        return False
    except Exception as e:
      results.record(5, "Store second test vCon", False, str(e))
      return False

    # Measure single job time
    print("  Measuring single job time...")
    single_time = push_and_wait(VCON_UUID_2)
    if single_time < 0:
      results.record(5, "Single job timing baseline", False, "Job timed out")
      return False
    print("  Single job time: {:.2f}s".format(single_time))

    # Push two jobs simultaneously and measure total wall time
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
    print("  Concurrent (2 jobs) wall time: {:.2f}s".format(concurrent_time))

    # Use a minimum floor for single_time to avoid an unrealistically tight
    # threshold when the job completes unusually fast on a warm CI runner.
    effective_single_time = max(single_time, 0.5)
    threshold = effective_single_time * 1.6
    passed = concurrent_time < threshold
    results.record(5, "Two jobs run concurrently", passed,
        "2-job wall time {:.2f}s < threshold {:.2f}s "
        "(1.6x effective single {:.2f}s)".format(
            concurrent_time, threshold, effective_single_time)
        if passed else
        "2-job wall time {:.2f}s >= threshold {:.2f}s — jobs ran sequentially".format(
            concurrent_time, threshold))

    return passed
