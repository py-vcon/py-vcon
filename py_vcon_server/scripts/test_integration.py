#!/usr/bin/env python3
# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
test_integration.py -- Integration test runner for py_vcon_server.

Starts py_vcon_server as a subprocess, discovers and runs all stage
tests in scripts/integration/stages/, then shuts down.

Usage (from the py_vcon_server/ directory):

  REST_URL=http://localhost:8000 \\
  VCON_STORAGE_URL=redis://localhost \\
  python3 scripts/test_integration.py --workers 2

Options:
  --workers N       Number of uvicorn workers (default: 2)
  --stages a,b,...  Run only these stages (name or prefix)
  --skip a,b,...    Skip these stages (name or prefix)
  --list-stages     Print discovered stages and exit

Environment variables:
  REST_URL                         Server bind URL (required)
  VCON_STORAGE_URL                 Redis URL (default: redis://localhost)
  INTEGRATION_STARTUP_TIMEOUT      Seconds to wait for server ready (default: 30)
  INTEGRATION_SHUTDOWN_TIMEOUT     Seconds to wait for clean exit (default: 30)
  INTEGRATION_PROM_STARTUP_TIMEOUT Prometheus server timeout (default: STARTUP)

Requirements:
  pip install httpx psutil
  Redis running and accessible via VCON_STORAGE_URL
  py_vcon_server must be importable (via PYTHONPATH or pip install)
  test_processors_always is added to PLUGIN_PATHS automatically.
"""

import argparse
import importlib
import os
import pkgutil
import sys
import urllib.parse

# Ensure scripts/ is on sys.path so integration package is importable
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir not in sys.path:
  sys.path.insert(0, _scripts_dir)

from integration.context import Context
from integration.results import Results
from integration.server_manager import ServerManager, port_is_free


def discover_stages():
  """
  Import all stage modules from integration/stages/ and return
  a list of Stage instances sorted by module filename.
  """
  stages_pkg_dir = os.path.join(_scripts_dir, "integration", "stages")
  stages = []

  for finder, module_name, is_pkg in pkgutil.iter_modules([stages_pkg_dir]):
    if not module_name.startswith("stage"):
      continue
    full_name = "integration.stages.{}".format(module_name)
    try:
      mod = importlib.import_module(full_name)
      stage = mod.Stage()
      stages.append((module_name, stage))
    except Exception as e:
      print("WARNING: could not load stage {}: {}".format(module_name, e))

  stages.sort(key=lambda x: x[0])
  return [s for _, s in stages]


def parse_stage_set(arg):
  """Parse a comma-separated list of stage name prefixes into a set."""
  if not arg:
    return set()
  return set(token.strip() for token in arg.split(",") if token.strip())


def stage_matches(stage, name_set):
  """Return True if the stage name starts with any token in name_set."""
  for token in name_set:
    if stage.name.startswith(token):
      return True
  return False


def preflight_checks(base_url, vcon_storage_url):
  """
  Verify the environment is ready for integration tests.
  Returns True if all checks pass, False otherwise.
  """
  ok = True

  # Check required env vars
  if not base_url:
    print("ERROR: REST_URL environment variable must be set")
    print("  Example: REST_URL=http://localhost:8000")
    ok = False

  if not vcon_storage_url:
    print("ERROR: VCON_STORAGE_URL environment variable must be set")
    print("  Example: VCON_STORAGE_URL=redis://localhost")
    ok = False

  if not ok:
    return False

  # Check port is free
  port = int(urllib.parse.urlparse(base_url).port or 8000)
  if not port_is_free(port):
    print("ERROR: port {} already in use.".format(port))
    print("  Kill the occupying process before running integration tests.")
    ok = False

  # Check Redis is reachable
  try:
    import redis
    r = redis.Redis.from_url(vcon_storage_url)
    r.ping()
  except ImportError:
    print("WARNING: redis package not installed -- skipping Redis pre-check")
  except Exception as e:
    print("ERROR: Cannot reach Redis at {}: {}".format(
        vcon_storage_url, e))
    ok = False

  # Check required packages
  for pkg in ["httpx", "psutil"]:
    try:
      importlib.import_module(pkg)
    except ImportError:
      print("ERROR: required package '{}' not installed".format(pkg))
      ok = False

  # Check py_vcon_server importable
  try:
    importlib.import_module("py_vcon_server")
  except ImportError:
    print("ERROR: py_vcon_server not importable -- check PYTHONPATH")
    ok = False

  return ok


def build_env(base_url, num_workers):
  """Build the subprocess environment for py_vcon_server."""
  env = os.environ.copy()
  env["REST_URL"] = base_url
  env["NUM_RESTAPI_WORKERS"] = str(num_workers)
  env["RUN_BACKGROUND_JOBS"] = "True"

  # Ensure test_processors_always is in PLUGIN_PATHS
  plugin_paths = env.get("PLUGIN_PATHS", "")
  if "test_processors_always" not in plugin_paths:
    plugin_paths = ("test_processors_always" if not plugin_paths
        else plugin_paths + ",test_processors_always")
    env["PLUGIN_PATHS"] = plugin_paths

  return env


def main():
  parser = argparse.ArgumentParser(
      description="py_vcon_server integration test runner"
    )
  parser.add_argument(
      "--workers", type=int, default=2,
      help="Number of uvicorn workers (default: 2)"
    )
  parser.add_argument(
      "--stages", type=str, default="",
      help="Comma-separated stage name prefixes to run (default: all)"
    )
  parser.add_argument(
      "--skip", type=str, default="",
      help="Comma-separated stage name prefixes to skip"
    )
  parser.add_argument(
      "--list-stages", action="store_true",
      help="Print discovered stages and exit"
    )
  args = parser.parse_args()

  stages = discover_stages()

  if args.list_stages:
    print("Discovered stages (in run order):")
    for stage in stages:
      workers_note = ""
      if hasattr(stage, "min_workers") and stage.min_workers > 1:
        workers_note = "  [min_workers={}]".format(stage.min_workers)
      print("  {:40s} {}{}".format(
          stage.name, stage.description, workers_note))
    sys.exit(0)

  only_set = parse_stage_set(args.stages)
  skip_set = parse_stage_set(args.skip)

  def should_run(stage):
    if skip_set and stage_matches(stage, skip_set):
      return False
    if only_set and not stage_matches(stage, only_set):
      return False
    return True

  base_url = os.environ.get("REST_URL", "http://localhost:8000").rstrip("/")
  num_workers = args.workers
  vcon_storage_url = os.environ.get(
      "VCON_STORAGE_URL", "redis://localhost")

  print()
  print("=" * 60)
  print("py_vcon_server integration test")
  print("=" * 60)
  print("  REST_URL        : {}".format(base_url))
  print("  VCON_STORAGE_URL: {}".format(vcon_storage_url))
  print("  Workers         : {}".format(num_workers))
  if only_set:
    print("  Only stages     : {}".format(sorted(only_set)))
  if skip_set:
    print("  Skip stages     : {}".format(sorted(skip_set)))
  print()

  if not preflight_checks(base_url, vcon_storage_url):
    sys.exit(1)

  env = build_env(base_url, num_workers)
  results = Results()

  # Start py_vcon_server
  server_manager = ServerManager(base_url=base_url, env=env)
  print("  Starting server...")
  if not server_manager.start():
    print("ERROR: server failed to start. Log: {}".format(
        server_manager.log_path()))
    sys.exit(1)

  print("  Server started (PID={})".format(server_manager.pid()))
  print("  Log: {}".format(server_manager.log_path()))
  env["PLUGIN_PATHS"] = env.get("PLUGIN_PATHS", "")
  print("  PLUGIN_PATHS: {}".format(env["PLUGIN_PATHS"]))
  print()

  context = Context(
      base_url=base_url,
      num_workers=num_workers,
      env=env,
      results=results,
      server_manager=server_manager,
      vcon_storage_url=vcon_storage_url,
      project_root=os.path.dirname(_scripts_dir),
    )

  try:
    for stage in stages:
      if not should_run(stage):
        print("\n{} -- SKIPPED".format(stage.name))
        continue

      # Check min_workers
      min_w = getattr(stage, "min_workers", 1)
      if num_workers < min_w:
        print("\n{} -- SKIPPED (requires {} workers, have {})".format(
            stage.name, min_w, num_workers))
        continue

      print("\n{}".format(stage.name))
      print("  {}".format(stage.description))

      # Verify server is healthy before running
      if not server_manager.is_healthy():
        print("  WARNING: server not healthy before stage "
            "-- attempting restart")
        if not server_manager.restart():
          results.record(
              stage.name,
              "Pre-stage server health check",
              False,
              "server not healthy and restart failed "
              "-- skipping stage"
            )
          continue

      # Run the stage
      stage.run(context)

      # Verify server state after
      if stage.expected_state_after == "running":
        if not server_manager.is_healthy():
          print("  WARNING: server not healthy after stage "
              "-- attempting restart")
          server_manager.restart()

  finally:
    # Clean up -- stop server if still running
    if server_manager.poll() is None:
      server_manager.stop()
    print()
    print("  Server log: {}".format(server_manager.log_path()))

    success = results.summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
  main()
