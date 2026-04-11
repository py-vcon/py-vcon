# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
multiworker/stage2.py — Worker process count verification.
"""

import subprocess
import time

import psutil

from multiworker.results import Results


def stage2_worker_count(
    results: Results,
    base_url: str,
    server_proc: subprocess.Popen,
    expected_workers: int
  ) -> bool:
  """
  Stage 2: Correct number of worker processes spawned.

  With uvicorn.run() + workers=N, Uvicorn forks N worker processes as children
  of the master process.  We poll for up to 10 seconds to give them time to fork.
  With the old asyncio.create_task() approach, no children are spawned — the
  server runs in a single process.
  """
  print()
  print("Stage 2: Worker process count")

  try:
    parent = psutil.Process(server_proc.pid)

    deadline = time.time() + 10.0
    worker_count = 0
    pids = []
    while time.time() < deadline:
      try:
        children = parent.children(recursive=False)
        worker_count = len(children)
        pids = [c.pid for c in children]
        if worker_count >= expected_workers:
          break
      except psutil.NoSuchProcess:
        break
      time.sleep(0.5)

    passed = worker_count >= expected_workers
    results.record(2, "Worker processes spawned", passed,
        "found {} worker(s) (expected >= {}), PIDs: {}{}".format(
            worker_count, expected_workers, pids,
            " — old __main__.py does not fork workers" if worker_count == 0 else ""))
    return passed

  except Exception as e:
    results.record(2, "Worker processes spawned", False, str(e))
    return False
