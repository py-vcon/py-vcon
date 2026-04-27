# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
integration/helpers.py -- HTTP helpers, vCon construction, and job matching.
"""

import httpx


def make_test_vcon_dict(uuid):
  """Build a minimal vCon dict with one party and one inline text dialog."""
  return {
    "vcon": "0.0.1",
    "uuid": uuid,
    "created_at": "2024-03-06T20:07:43+00:00",
    "subject": "Integration test conversation",
    "parties": [
      {"tel": "+15551234567", "name": "Test Caller"}
    ],
    "dialog": [
      {
        "type": "text",
        "start": "2024-03-06T20:07:43+00:00",
        "duration": 5.0,
        "parties": 0,
        "mediatype": "text/plain",
        "encoding": "none",
        "body": "Hello, this is an integration test conversation."
      }
    ]
  }


def get(client, path, timeout=10.0):
  return client.get(path, timeout=timeout)


def post(client, path, body, timeout=10.0):
  return client.post(path, json=body, timeout=timeout)


def put(client, path, body, timeout=10.0):
  return client.put(path, json=body, timeout=timeout)


def delete(client, path, timeout=10.0):
  return client.delete(path, timeout=timeout)


def jobs_for_vcon(in_progress, vcon_uuid):
  """
  Return the subset of in-progress jobs whose job.vcon_uuid list
  contains vcon_uuid.
  """
  result = {}
  for job_id, job in in_progress.items():
    try:
      uuids = job.get("job", {}).get("vcon_uuid", [])
      if vcon_uuid in uuids:
        result[job_id] = job
    except Exception:
      pass
  return result
