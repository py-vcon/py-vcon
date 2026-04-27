# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
integration/stages/stage04_pipeline_job.py

Push a vCon through a real pipeline via the job queue.
Verifies the jinja_report processor wrote an analysis object to the vCon.
"""

import time

import httpx

from integration.constants import (
  QUEUE_NAME,
  PIPELINE_NAME,
  PIPELINE_DEF,
  VCON_UUID,
  ANALYSIS_TYPE,
  ANALYSIS_MARKER,
  JOB_POLL_TIMEOUT,
  JOB_POLL_INTERVAL,
)
from integration.helpers import get, post, put, make_test_vcon_dict, jobs_for_vcon


class Stage:
  name = "stage04_pipeline_job"
  description = "Background job runs through a jinja_report pipeline"
  expected_state_after = "running"
  min_workers = 1

  def run(self, context):
    with httpx.Client(base_url=context.base_url) as client:

      # 4a: Store vCon
      try:
        r = post(client, "/vcon", make_test_vcon_dict(VCON_UUID))
        passed = r.status_code == 204
        context.results.record(self.name, "Store test vCon", passed,
            "POST /vcon -> {}".format(r.status_code))
        if not passed:
          return False
      except Exception as e:
        context.results.record(self.name, "Store test vCon", False, str(e))
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
        context.results.record(self.name, "Create pipeline", passed,
            "PUT /pipeline/{} -> {}".format(PIPELINE_NAME, r.status_code))
        if not passed:
          print("  Response body: {}".format(r.text))
          return False
      except Exception as e:
        context.results.record(self.name, "Create pipeline", False, str(e))
        return False

      # 4c: Create queue (delete first to handle leftover state)
      try:
        client.delete("/queue/{}".format(QUEUE_NAME), timeout=5.0)
      except Exception:
        pass
      try:
        r = post(client, "/queue/{}".format(QUEUE_NAME), {})
        passed = r.status_code == 204
        context.results.record(self.name, "Create job queue", passed,
            "POST /queue/{} -> {}".format(QUEUE_NAME, r.status_code))
        if not passed:
          return False
      except Exception as e:
        context.results.record(self.name, "Create job queue", False, str(e))
        return False

      # 4d: Configure server to watch queue
      try:
        r = post(client, "/server/queue/{}".format(QUEUE_NAME), {"weight": 1})
        passed = r.status_code == 204
        context.results.record(self.name, "Configure server queue", passed,
            "POST /server/queue/{} -> {}".format(QUEUE_NAME, r.status_code))
        if not passed:
          return False
      except Exception as e:
        context.results.record(
            self.name, "Configure server queue", False, str(e))
        return False

      # 4e: Push job to queue
      try:
        job = {"job_type": "vcon_uuid", "vcon_uuid": [VCON_UUID]}
        r = put(client, "/queue/{}".format(QUEUE_NAME), job)
        passed = r.status_code == 200
        context.results.record(self.name, "Push job to queue", passed,
            "PUT /queue/{} -> {}".format(QUEUE_NAME, r.status_code))
        if not passed:
          return False
      except Exception as e:
        context.results.record(self.name, "Push job to queue", False, str(e))
        return False

      # 4f: Poll for job completion
      deadline = time.time() + JOB_POLL_TIMEOUT
      completed = False
      while time.time() < deadline:
        r = get(client, "/in_progress", timeout=5.0)
        if r.status_code == 200:
          our_jobs = jobs_for_vcon(r.json(), VCON_UUID)
          if len(our_jobs) == 0:
            r2 = get(client, "/queue/{}".format(QUEUE_NAME), timeout=5.0)
            if r2.status_code == 200 and len(r2.json()) == 0:
              completed = True
              break
        time.sleep(JOB_POLL_INTERVAL)

      context.results.record(self.name, "Job completed", completed,
          "Completed within {}s".format(JOB_POLL_TIMEOUT)
          if completed else
          "Job did not complete within {}s".format(JOB_POLL_TIMEOUT))
      if not completed:
        return False

      # 4g: Verify analysis object
      try:
        r = get(client, "/vcon/{}".format(VCON_UUID))
        if r.status_code != 200:
          context.results.record(
              self.name, "Analysis object written to vCon",
              False, "GET /vcon -> {}".format(r.status_code))
          return False

        analyses = r.json().get("analysis", [])
        found = any(
            a.get("type") == ANALYSIS_TYPE and
            ANALYSIS_MARKER in str(a.get("body", ""))
            for a in analyses
          )
        context.results.record(
            self.name, "Analysis object written to vCon", found,
            "type={} marker found".format(ANALYSIS_TYPE)
            if found else
            "Analysis not found. analyses={}".format(analyses))
        return found

      except Exception as e:
        context.results.record(
            self.name, "Analysis object written to vCon", False, str(e))
        return False
