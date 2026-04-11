# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
multiworker/helpers.py — HTTP helpers, vCon construction, and cleanup.
"""

import subprocess

import httpx

from multiworker.constants import (
  QUEUE_NAME,
  PIPELINE_NAME,
  VCON_UUID,
  VCON_UUID_2,
)


# ── vCon construction ─────────────────────────────────────────────────────────

def make_test_vcon_dict(uuid: str) -> dict:
  """Build a minimal vCon dict with one party and one inline text dialog."""
  return {
    "vcon": "0.0.1",
    "uuid": uuid,
    "created_at": "2024-03-06T20:07:43+00:00",
    "subject": "Multiworker test conversation",
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
        "body": "Hello, this is a multiworker test conversation."
      }
    ]
  }


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def get(client: httpx.Client, path: str, timeout: float = 10.0) -> httpx.Response:
  return client.get(path, timeout=timeout)


def post(client: httpx.Client, path: str, body: dict, timeout: float = 10.0) -> httpx.Response:
  return client.post(path, json=body, timeout=timeout)


def put(client: httpx.Client, path: str, body: dict, timeout: float = 10.0) -> httpx.Response:
  return client.put(path, json=body, timeout=timeout)


def delete(client: httpx.Client, path: str, timeout: float = 10.0) -> httpx.Response:
  return client.delete(path, timeout=timeout)


# ── In-progress job matching ──────────────────────────────────────────────────

def jobs_for_vcon(in_progress: dict, vcon_uuid: str) -> dict:
  """
  Return the subset of in-progress jobs whose job.vcon_uuid list contains
  vcon_uuid.

  Uses the structured job["job"]["vcon_uuid"] list rather than a raw
  json.dumps() substring match.  A vCon dict can contain the same UUID
  string in parties, dialogs, and analysis objects, so a substring match
  on the serialized job dict would produce false positives.
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


# ── Cleanup ───────────────────────────────────────────────────────────────────

def cleanup(base_url: str, server_proc: subprocess.Popen):
  """
  Always-run cleanup.  Removes Stage 4/5 test state from Redis and kills the
  server if it is still running.  When Stage 6 runs, the server is already
  gone and these HTTP calls will fail with connection errors — that is expected
  and harmless.  Stage 6 cleans up its own artifacts via the verify server.
  Errors during cleanup are printed but do not raise.
  """
  print()
  print("── Cleanup ──────────────────────────────────────────────")

  try:
    with httpx.Client(base_url=base_url) as client:
      for label, path in [
          ("DELETE /server/queue/{}".format(QUEUE_NAME),  "/server/queue/{}".format(QUEUE_NAME)),
          ("DELETE /queue/{}".format(QUEUE_NAME),         "/queue/{}".format(QUEUE_NAME)),
          ("DELETE /pipeline/{}".format(PIPELINE_NAME),   "/pipeline/{}".format(PIPELINE_NAME)),
          ("DELETE /vcon/{}".format(VCON_UUID),           "/vcon/{}".format(VCON_UUID)),
          ("DELETE /vcon/{}".format(VCON_UUID_2),         "/vcon/{}".format(VCON_UUID_2)),
        ]:
        try:
          r = client.delete(path, timeout=5.0)
          print("  {}: {}".format(label, r.status_code))
        except Exception as e:
          print("  {}: ERROR {}".format(label, e))

  except Exception as e:
    print("  HTTP cleanup failed: {}".format(e))

  # Kill server if still running (Stage 6 terminates it; other stages do not)
  if server_proc is not None and server_proc.poll() is None:
    print("  Sending SIGTERM to server PID {}".format(server_proc.pid))
    server_proc.terminate()
    try:
      server_proc.wait(timeout=30)
      print("  Server exited cleanly")
    except subprocess.TimeoutExpired:
      print("  Server did not exit after 30s — sending SIGKILL")
      server_proc.kill()
      server_proc.wait()
      print("  Server killed")

  print("── Cleanup done ─────────────────────────────────────────")
