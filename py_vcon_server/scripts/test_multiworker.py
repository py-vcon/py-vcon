#!/usr/bin/env python3
# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
test_multiworker.py — Integration test for multiple Uvicorn workers.

Starts py_vcon_server as a subprocess with NUM_RESTAPI_WORKERS set to the
--workers argument, then exercises the stages listed below.

Use --list-stages to print the stage table and exit.

Usage:
  From the py_vcon_server/ directory:

    REST_URL=http://localhost:8000 \\
    VCON_STORAGE_URL=redis://localhost \\
    python3 scripts/test_multiworker.py --workers 2

  Run only specific stages (numbers or names, comma-separated):

    python3 scripts/test_multiworker.py --workers 2 --stages 1,4,7
    python3 scripts/test_multiworker.py --workers 2 --stages startup,pipeline_job,prometheus

  Skip specific stages:

    python3 scripts/test_multiworker.py --workers 2 --skip 5,6
    python3 scripts/test_multiworker.py --workers 2 --skip concurrent,sigint_shutdown

  List all stages and exit:

    python3 scripts/test_multiworker.py --list-stages

  test_processors_always is added to PLUGIN_PATHS automatically if not present.
  It is required for Stage 3 (blocking) and Stage 6 (sigint_shutdown).

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

from multiworker.constants import BLOCK_SECONDS, STAGE_NAMES, STAGE_NUMBERS
from multiworker.helpers import cleanup
from multiworker.results import Results
from multiworker.stage1 import stage1_startup
from multiworker.stage2 import stage2_worker_count
from multiworker.stage3 import stage3_blocking_isolation
from multiworker.stage4 import stage4_pipeline_job
from multiworker.stage5 import stage5_concurrent_jobs
from multiworker.stage6 import stage6_sigint_shutdown
from multiworker.stage7 import stage7_prometheus


def print_stage_table():
  """Print the stage number/name table and descriptions."""
  print()
  print("Available stages:")
  print()
  descriptions = {
    1: "Server starts and health check responds",
    2: "Correct number of worker processes spawned (workers > 1 only)",
    3: "Health check responds while a worker is blocked synchronously",
    4: "Background job runs through a jinja_report pipeline",
    5: "Two concurrent jobs complete faster than 2x sequential time (workers > 1 only)",
    6: "SIGINT graceful shutdown — drain, 503, Redis cleanup (workers > 1 only)",
    7: "Prometheus multiprocess metric aggregation (self-contained server)",
  }
  print("  {:<4}  {:<20}  {}".format("Num", "Name", "Description"))
  print("  {:<4}  {:<20}  {}".format("---", "----", "-----------"))
  for num in sorted(STAGE_NAMES):
    name = STAGE_NAMES[num]
    desc = descriptions.get(num, "")
    print("  {:<4}  {:<20}  {}".format(num, name, desc))
  print()
  print("Use --stages or --skip with numbers or names (comma-separated).")
  print()


def parse_stage_set(value: str, arg_name: str) -> set:
  """
  Parse a comma-separated list of stage numbers and/or names into a set
  of stage numbers.  Exits with an error message on invalid input.
  """
  result = set()
  for token in value.split(","):
    token = token.strip()
    if not token:
      continue
    # Try as integer first
    try:
      result.add(int(token))
      continue
    except ValueError:
      pass
    # Try as name
    if token in STAGE_NUMBERS:
      result.add(STAGE_NUMBERS[token])
      continue
    # Unknown
    print("ERROR: '{}' in {} is not a valid stage number or name.".format(
        token, arg_name))
    print("       Run with --list-stages to see valid values.")
    sys.exit(1)
  return result


def main():
  parser = argparse.ArgumentParser(
      description="Test py_vcon_server multi-worker behavior",
      add_help=True,
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
      metavar="STAGES",
      help="Comma-separated stage numbers or names to run (default: all). "
           "Example: --stages 1,4,7  or  --stages startup,pipeline_job"
    )
  parser.add_argument(
      "--skip",
      type=str,
      default="",
      metavar="STAGES",
      help="Comma-separated stage numbers or names to skip. "
           "Example: --skip 5,6  or  --skip concurrent,sigint_shutdown"
    )
  parser.add_argument(
      "--list-stages",
      action="store_true",
      help="Print the table of stage numbers and names, then exit"
    )
  args = parser.parse_args()

  if args.list_stages:
    print_stage_table()
    sys.exit(0)

  only_stages = parse_stage_set(args.stages, "--stages") if args.stages else set()
  skip_stages  = parse_stage_set(args.skip,   "--skip")   if args.skip   else set()

  def should_run(stage_num: int) -> bool:
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
  # Required for Stage 3 (blocking) and Stage 6 (sigint_shutdown).
  plugin_paths = os.environ.get("PLUGIN_PATHS", "")
  if "test_processors_always" not in plugin_paths:
    plugin_paths = ("test_processors_always" if not plugin_paths
                    else plugin_paths + ",test_processors_always")
    os.environ["PLUGIN_PATHS"] = plugin_paths

  # Build subprocess environment once — every stage and the server
  # process will use exactly this environment.
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
    print("  Only stages:  {}".format(
        sorted("{}({})".format(n, STAGE_NAMES.get(n, "?")) for n in only_stages)))
  if skip_stages:
    print("  Skip stages:  {}".format(
        sorted("{}({})".format(n, STAGE_NAMES.get(n, "?")) for n in skip_stages)))
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

    # Stage 1: Startup — abort if it fails since remaining stages need the server
    if should_run(1):
      if not stage1_startup(results, base_url, server_proc):
        print("\nServer failed to start — aborting remaining stages")
        print("  See server log for details: {}".format(server_log_path))
        server_log_file.flush()
        results.summary()
        return False
    else:
      print()
      print("Stage 1 (startup) — SKIPPED")

    # Stage 2: Worker count (multi-worker only)
    if should_run(2):
      if multi_worker:
        stage2_worker_count(results, base_url, server_proc, num_workers)
      else:
        print()
        print("Stage 2 (worker_count) — SKIPPED (workers=1)")
    else:
      print()
      print("Stage 2 (worker_count) — SKIPPED")

    # Stage 3: Blocking isolation
    if should_run(3):
      stage3_blocking_isolation(results, base_url, BLOCK_SECONDS)
    else:
      print()
      print("Stage 3 (blocking) — SKIPPED")

    # Stage 4: Pipeline job via queue
    if should_run(4):
      stage4_pipeline_job(results, base_url)
    else:
      print()
      print("Stage 4 (pipeline_job) — SKIPPED")

    # Stage 5: Concurrent jobs (multi-worker only)
    if should_run(5):
      if multi_worker:
        stage5_concurrent_jobs(results, base_url)
      else:
        print()
        print("Stage 5 (concurrent) — SKIPPED (workers=1)")
    else:
      print()
      print("Stage 5 (concurrent) — SKIPPED")

    # Stage 7: Prometheus multiprocess aggregation.
    # Runs here — before Stages 3/4/5 add load — because Stage 7 starts
    # a second server on port+1 while the main server is running.  Running
    # early minimises total process count on slow CI runners.
    # Must still run before Stage 6 since Stage 6 terminates the main server.
    if should_run(7):
      stage7_prometheus(results, base_url, env, num_workers)
    else:
      print()
      print("Stage 7 (prometheus) — SKIPPED")

    # Stage 6: SIGINT graceful shutdown (multi-worker only).
    # Must be last — terminates the main server.
    if should_run(6):
      if multi_worker:
        stage6_sigint_shutdown(results, base_url, server_proc, env, num_workers)
      else:
        print()
        print("Stage 6 (sigint_shutdown) — SKIPPED (workers=1)")
    else:
      print()
      print("Stage 6 (sigint_shutdown) — SKIPPED")

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
