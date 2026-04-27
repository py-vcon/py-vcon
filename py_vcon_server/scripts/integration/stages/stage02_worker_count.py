# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
integration/stages/stage02_worker_count.py

Verifies that the correct number of uvicorn worker processes are
running as children of the parent py_vcon_server process.
"""

import time

import psutil


class Stage:
  name = "stage02_worker_count"
  description = "Correct number of worker processes spawned"
  expected_state_after = "running"
  min_workers = 2

  def run(self, context):
    pid = context.server_manager.pid()
    if pid is None:
      context.results.record(
          self.name, self.description, False, "server PID not available"
        )
      return False

    # Poll for up to 10s for workers to appear
    deadline = time.time() + 10.0
    children = []
    while time.time() < deadline:
      try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=False)
        if len(children) >= context.num_workers:
          break
      except psutil.NoSuchProcess:
        break
      time.sleep(0.5)

    actual = len(children)
    pids = [c.pid for c in children]
    passed = actual >= context.num_workers

    context.results.record(
        self.name,
        self.description,
        passed,
        "found {} worker(s) (expected >= {}), PIDs: {}".format(
            actual, context.num_workers, pids
          )
      )
    return passed
