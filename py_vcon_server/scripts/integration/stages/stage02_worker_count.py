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

    if not passed:
      return False

    child_pids = set(c.pid for c in children)
    master_pid = pid

    # 02b: /server/info worker count matches expected
    try:
      import httpx
      with httpx.Client(base_url=context.base_url) as client:
        # Poll until all workers have registered in Redis
        poll_deadline = time.time() + 15.0
        info = {}
        workers = {}
        while time.time() < poll_deadline:
          r = client.get("/server/info", timeout=10.0)
          if r.status_code == 200:
            info = r.json()
            workers = info.get("workers", {})
            if len(workers) >= context.num_workers:
              break
          time.sleep(0.5)
        worker_count = len(workers)
        count_match = worker_count == context.num_workers
        if count_match:
          context.results.record(
              self.name,
              "/server/info worker count matches",
              count_match,
              "found {} worker entries (expected {})".format(
                  worker_count, context.num_workers)
            )

          # 02c: server entry PID is master PID
          server_pid = info.get("pid")
          pid_match = server_pid == master_pid
          context.results.record(
              self.name,
              "server entry pid matches master",
              pid_match,
              "server pid={} master pid={}".format(server_pid, master_pid)
            )

          # 02d: each worker_pid is a child of master
          all_workers_valid = True
          for wk, wv in workers.items():
            wpid = wv.get("worker_pid")
            if wpid not in child_pids:
              all_workers_valid = False
              context.results.record(
                  self.name,
                  "worker pid is child of master",
                  False,
                  "worker_pid {} not in child PIDs {}".format(
                      wpid, child_pids)
                )
              break
            if not wk.endswith(str(wpid)):
              all_workers_valid = False
              context.results.record(
                  self.name,
                  "worker key ends with worker pid",
                  False,
                  "key {} does not end with pid {}".format(wk, wpid)
                )
              break
          if all_workers_valid:
            context.results.record(
                self.name,
                "all worker pids are children of master",
                True,
                "all {} worker_pids found in child PIDs".format(
                    worker_count)
              )

        else:
          context.results.record(
              self.name,
              "/server/info worker count matches",
              False,
              "found {} worker entries (expected {}) after 15s polling".format(
                  worker_count, context.num_workers)
            )
          return passed
    except Exception as e:
      context.results.record(
          self.name,
          "/server/info worker validation",
          False,
          str(e)
        )

    return passed

