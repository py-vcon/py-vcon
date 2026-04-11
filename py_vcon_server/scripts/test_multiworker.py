#!/usr/bin/env python3
# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
test_multiworker.py — Integration test for multiple Uvicorn workers.

Starts py_vcon_server as a subprocess with NUM_RESTAPI_WORKERS set to the
--workers argument, then exercises:

  Stage 1: Server starts and health check responds
  Stage 2: Correct number of worker processes spawned  (workers > 1 only)
  Stage 3: Health check responds while a worker is blocked synchronously
           workers=1 → FAIL expected (documents the bug)
           workers>1 → PASS expected (proves isolation)
  Stage 4: Background job runs through a jinja_report pipeline and writes
           a verifiable analysis object to the vCon
  Stage 5: Two concurrent jobs complete faster than 2x sequential time
           (workers > 1 only — proves parallel background processing)
  Stage 6: SIGINT graceful shutdown (workers > 1 only)
           6a: In-flight background job completes before shutdown
           6b: New HTTP requests receive 503 during shutdown window
           6c: Redis fully cleaned up after all workers exit
           6d: /diagnostics returns 200 during the drain window and shows the
               in-flight job — proves the socket stays open for monitoring
               while normal endpoints return 503

Usage:
  From the py_vcon_server/ directory:

    REST_URL=http://localhost:8000 \\
    VCON_STORAGE_URL=redis://localhost \\
    python3 scripts/test_multiworker.py --workers 1

    REST_URL=http://localhost:8000 \\
    VCON_STORAGE_URL=redis://localhost \\
    python3 scripts/test_multiworker.py --workers 2

  Run only specific stages with --stages (comma-separated):

    python3 scripts/test_multiworker.py --workers 2 --stages 1,2,4

  Skip specific stages with --skip (comma-separated):

    python3 scripts/test_multiworker.py --workers 2 --skip 5,6

  test_processors_always is added to PLUGIN_PATHS automatically if not present.
  It is required for Stage 3 (timeout_test_sleep_sync) and Stage 6b
  (timeout_test_sleep_async).

Requirements:
  pip install httpx psutil
  Redis running and accessible via VCON_STORAGE_URL
  py_vcon_server must be importable (via PYTHONPATH or pip install)
"""

import os
import sys
import argparse
import subprocess

# Ensure the scripts/ directory is on sys.path so the multiworker package
# is importable regardless of how this script is invoked.
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir not in sys.path:
  sys.path.insert(0, _scripts_dir)

from multiworker.constants import BLOCK_SECONDS
from multiworker.helpers import cleanup
from multiworker.results import Results
from multiworker.stage1 import stage1_startup
from multiworker.stage2 import stage2_worker_count
from multiworker.stage3 import stage3_blocking_isolation
from multiworker.stage4 import stage4_pipeline_job
from multiworker.stage5 import stage5_concurrent_jobs
from multiworker.stage6 import stage6_sigint_shutdown


def main():
  parser = argparse.ArgumentParser(
      description="Test py_vcon_server multi-worker behavior"
    )
  parser.add_argument(
      "--workers",
      type=int,
      default=1,
      help="Number of Uvicorn workers (1=documents bug, 2+=proves fix)"
    )
  parser.add_argument(
      "--stages",
      type=str,
      default="",
      help="Comma-separated list of stage numbers to run (default: all). "
           "Example: --stages 1,2,4"
    )
  parser.add_argument(
      "--skip",
      type=str,
      default="",
      help="Comma-separated list of stage numbers to skip. "
           "Example: --skip 5,6"
    )
  args = parser.parse_args()

  # Parse --stages and --skip into sets
  only_stages = set()
  if args.stages:
    try:
      only_stages = {int(s.strip()) for s in args.stages.split(",")}
    except ValueError:
      print("ERROR: --stages must be comma-separated integers, e.g. --stages 1,2,4")
      sys.exit(1)

  skip_stages = set()
  if args.skip:
    try:
      skip_stages = {int(s.strip()) for s in args.skip.split(",")}
    except ValueError:
      print("ERROR: --skip must be comma-separated integers, e.g. --skip 5,6")
      sys.exit(1)

  def should_run(stage_num: int) -> bool:
    """Return True if this stage should be executed."""
    if only_stages and stage_num not in only_stages:
      return False
    if stage_num in skip_stages:
      return False
    return True

  # Require REST_URL from environment
  rest_url = os.environ.get("REST_URL", "")
  if not rest_url:
    print("ERROR: REST_URL environment variable must be set")
    print("  Example: REST_URL=http://localhost:8000")
    sys.exit(1)

  base_url = rest_url.rstrip("/")
  num_workers = args.workers
  multi_worker = num_workers > 1

  # Ensure test_processors_always is in PLUGIN_PATHS.
  # Required for Stage 3 (timeout_test_sleep_sync blocks a worker) and
  # Stage 6b (timeout_test_sleep_async holds a job open to observe 503).
  # Set it now so env = os.environ.copy() below picks it up correctly.
  plugin_paths = os.environ.get("PLUGIN_PATHS", "")
  if "test_processors_always" not in plugin_paths:
    plugin_paths = ("test_processors_always" if not plugin_paths
                    else plugin_paths + ",test_processors_always")
    os.environ["PLUGIN_PATHS"] = plugin_paths

  # Build subprocess environment once here so every stage and the header
  # print all reference exactly what the server process will receive.
  env = os.environ.copy()
  env["NUM_RESTAPI_WORKERS"] = str(num_workers)
  env["RUN_BACKGROUND_JOBS"] = "True"

  print("=" * 60)
  print("py_vcon_server Multi-Worker Test")
  print("=" * 60)
  print("  REST_URL:     {}".format(base_url))
  print("  Workers:      {}".format(num_workers))
  print("  Mode:         {}".format(
      "FIXED (multi-worker)" if multi_worker else "BASELINE (documents bug)"))
  print("  PLUGIN_PATHS: {}".format(env.get("PLUGIN_PATHS")))
  if only_stages:
    print("  Only stages:  {}".format(sorted(only_stages)))
  if skip_stages:
    print("  Skip stages:  {}".format(sorted(skip_stages)))
  print()

  if not multi_worker:
    print("NOTE: workers=1 — Stage 3 FAIL and Stage 5/6 SKIP are expected.")
    print("      This documents the existing single-worker blocking bug.")
    print()

  results = Results()
  server_proc = None
  server_log_file = None
  server_log_path = os.path.join(
      os.path.dirname(os.path.abspath(__file__)),
      "test_multiworker_server.log"
    )

  try:
    print("Starting server: python3 -m py_vcon_server")
    print("  NUM_RESTAPI_WORKERS={}".format(num_workers))
    print("  Server log: {}".format(server_log_path))
    server_log_file = open(server_log_path, "w")
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "py_vcon_server"],
        env=env,
        stdout=server_log_file,
        stderr=server_log_file
      )
    print("  Server PID: {}".format(server_proc.pid))

    # Stage 1: Startup — always required; abort if it fails
    if should_run(1):
      if not stage1_startup(results, base_url, server_proc):
        print("\nServer failed to start — aborting remaining stages")
        print("  See server log for details: {}".format(server_log_path))
        server_log_file.flush()
        results.summary()
        return False
    else:
      print()
      print("Stage 1: Server startup — SKIPPED")

    # Stage 2: Worker count (multi-worker only)
    if should_run(2):
      if multi_worker:
        stage2_worker_count(results, base_url, server_proc, num_workers)
      else:
        print()
        print("Stage 2: Worker process count — SKIPPED (workers=1)")
    else:
      print()
      print("Stage 2: Worker process count — SKIPPED")

    # Stage 3: Blocking isolation
    if should_run(3):
      stage3_blocking_isolation(results, base_url, BLOCK_SECONDS)
    else:
      print()
      print("Stage 3: Blocking isolation — SKIPPED")

    # Stage 4: Pipeline job via queue
    if should_run(4):
      stage4_pipeline_job(results, base_url)
    else:
      print()
      print("Stage 4: Background pipeline job — SKIPPED")

    # Stage 5: Concurrent jobs (multi-worker only)
    if should_run(5):
      if multi_worker:
        stage5_concurrent_jobs(results, base_url)
      else:
        print()
        print("Stage 5: Concurrent jobs — SKIPPED (workers=1)")
    else:
      print()
      print("Stage 5: Concurrent jobs — SKIPPED")

    # Stage 6: SIGINT graceful shutdown (multi-worker only).
    # Must be last — terminates the server.
    if should_run(6):
      if multi_worker:
        stage6_sigint_shutdown(results, base_url, server_proc, env, num_workers)
      else:
        print()
        print("Stage 6: SIGINT graceful shutdown — SKIPPED (workers=1)")
    else:
      print()
      print("Stage 6: SIGINT graceful shutdown — SKIPPED")

  finally:
    cleanup(base_url, server_proc)
    if server_log_file is not None:
      try:
        server_log_file.flush()
        server_log_file.close()
      except Exception:
        pass
    print("  Server log saved to: {}".format(server_log_path))

  return results.summary()


if __name__ == "__main__":
  success = main()
  sys.exit(0 if success else 1)
