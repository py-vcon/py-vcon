# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
multiworker/stage4.py — Background pipeline job via queue.
"""

import time

import httpx

from multiworker.constants import (
  QUEUE_NAME,
  PIPELINE_NAME,
  PIPELINE_DEF,
  VCON_UUID,
  ANALYSIS_TYPE,
  ANALYSIS_MARKER,
  JOB_POLL_TIMEOUT,
  JOB_POLL_INTERVAL,
)
from multiworker.helpers import get, post, put, make_test_vcon_dict, jobs_for_vcon
from multiworker.results import Results


def stage4_pipeline_job(results: Results, base_url: str) -> bool:
  """
  Stage 4: Push a vCon through a real pipeline via the job queue.
  Verifies the jinja_report processor wrote an analysis object to the vCon.
  """
  print()
  print("Stage 4: Background pipeline job via queue")

  with httpx.Client(base_url=base_url) as client:

    # 4a: Store vCon
    try:
      r = post(client, "/vcon", make_test_vcon_dict(VCON_UUID))
      passed = r.status_code == 204
      results.record(4, "Store test vCon", passed,
          "POST /vcon → {}".format(r.status_code))
      if not passed:
        return False
    except Exception as e:
      results.record(4, "Store test vCon", False, str(e))
      return False

    # 4b: Create pipeline
    try:
      r = client.put(
          "/pipeline/{}".format(PIPELINE_NAME),
          json=PIPELINE_DEF,
          params={"validate_processor_options": False},
          timeout=10.0
        )
      passed = r.status_code == 204
      results.record(4, "Create pipeline", passed,
          "PUT /pipeline/{} → {}".format(PIPELINE_NAME, r.status_code))
      if not passed:
        print("  Response body: {}".format(r.text))
        return False
    except Exception as e:
      results.record(4, "Create pipeline", False, str(e))
      return False

    # 4c: Create queue — delete first to handle leftover state from prior runs
    try:
      client.delete("/queue/{}".format(QUEUE_NAME), timeout=5.0)
    except Exception:
      pass
    try:
      r = post(client, "/queue/{}".format(QUEUE_NAME), {})
      passed = r.status_code == 204
      results.record(4, "Create job queue", passed,
          "POST /queue/{} → {}".format(QUEUE_NAME, r.status_code))
      if not passed:
        return False
    except Exception as e:
      results.record(4, "Create job queue", False, str(e))
      return False

    # 4d: Configure server to watch queue
    try:
      r = post(client, "/server/queue/{}".format(QUEUE_NAME), {"weight": 1})
      passed = r.status_code == 204
      results.record(4, "Configure server queue", passed,
          "POST /server/queue/{} → {}".format(QUEUE_NAME, r.status_code))
      if not passed:
        return False
    except Exception as e:
      results.record(4, "Configure server queue", False, str(e))
      return False

    # 4e: Push job to queue
    try:
      job = {"job_type": "vcon_uuid", "vcon_uuid": [VCON_UUID]}
      r = put(client, "/queue/{}".format(QUEUE_NAME), job)
      passed = r.status_code == 200
      results.record(4, "Push job to queue", passed,
          "PUT /queue/{} → {}".format(QUEUE_NAME, r.status_code))
      if not passed:
        return False
    except Exception as e:
      results.record(4, "Push job to queue", False, str(e))
      return False

    # 4f: Poll until queue is empty (job was picked up)
    print("  Waiting for job to be picked up (max {}s)...".format(JOB_POLL_TIMEOUT))
    deadline = time.time() + JOB_POLL_TIMEOUT
    job_picked_up = False
    while time.time() < deadline:
      try:
        r = get(client, "/queue/{}".format(QUEUE_NAME))
        if r.status_code == 200 and len(r.json()) == 0:
          job_picked_up = True
          break
      except Exception:
        pass
      time.sleep(JOB_POLL_INTERVAL)

    results.record(4, "Job picked up from queue", job_picked_up,
        "Queue empty after {:.1f}s".format(
            JOB_POLL_TIMEOUT - (deadline - time.time())) if job_picked_up
        else "Timed out after {}s — job still in queue".format(JOB_POLL_TIMEOUT))
    if not job_picked_up:
      return False

    # 4g: Poll until in-progress is clear (job completed).
    # Use jobs_for_vcon() to match on job["job"]["vcon_uuid"] specifically —
    # a vCon dict may contain the UUID in parties, dialogs and analysis objects
    # so a substring match on the serialized job dict would produce false positives.
    print("  Waiting for job to complete (max {}s)...".format(JOB_POLL_TIMEOUT))
    deadline = time.time() + JOB_POLL_TIMEOUT
    job_completed = False
    while time.time() < deadline:
      try:
        r = get(client, "/in_progress")
        if r.status_code == 200:
          our_jobs = jobs_for_vcon(r.json(), VCON_UUID)
          if len(our_jobs) == 0:
            job_completed = True
            break
      except Exception:
        pass
      time.sleep(JOB_POLL_INTERVAL)

    results.record(4, "Job completed", job_completed,
        "In-progress cleared" if job_completed
        else "Timed out — job still in progress")
    if not job_completed:
      return False

    # Give the server a moment to commit the vCon back to Redis
    time.sleep(1.0)

    # 4h: Verify analysis object was written to vCon
    try:
      r = get(client, "/vcon/{}".format(VCON_UUID))
      if r.status_code != 200:
        results.record(4, "Analysis object written to vCon", False,
            "GET /vcon/{} → {}".format(VCON_UUID, r.status_code))
        return False

      analyses = r.json().get("analysis", [])
      found = any(
          a.get("type") == ANALYSIS_TYPE and
          ANALYSIS_MARKER in str(a.get("body", "")) and
          VCON_UUID in str(a.get("body", ""))
          for a in analyses
        )
      results.record(4, "Analysis object written to vCon", found,
          "Found analysis type={} containing marker and UUID".format(ANALYSIS_TYPE)
          if found else
          "No matching analysis object found. analyses={}".format(analyses))
      return found

    except Exception as e:
      results.record(4, "Analysis object written to vCon", False, str(e))
      return False
