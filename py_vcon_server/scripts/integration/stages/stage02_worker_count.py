# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
integration/stages/stage02_worker_count.py

Verifies that the correct number of uvicorn worker processes are
running as children of the parent py_vcon_server process.
"""
import os
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

          # 02d: each worker_pid is a child of master.
          # Do not break on first failure -- collect every worker's status
          # so the diagnostic shows the full picture.  When any worker fails
          # the check, dump a comprehensive snapshot to aid root-cause
          # analysis across Python versions where this test flakes.
          bad_pid_workers = []   # list of (wk, wpid, reason)
          for wk, wv in workers.items():
            wpid = wv.get("worker_pid")
            if wpid not in child_pids:
              bad_pid_workers.append(
                  (wk, wpid, "worker_pid not in initial child set")
                )
            elif not wk.endswith(str(wpid)):
              bad_pid_workers.append(
                  (wk, wpid, "worker_key suffix does not match worker_pid")
                )

          if bad_pid_workers:
            diag = self._collect_diagnostics(
                context, master_pid, child_pids, workers, bad_pid_workers,
                client
              )
            context.results.record(
                self.name,
                "worker pid is child of master",
                False,
                diag
              )
          else:
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


def _collect_diagnostics(
      self, context, master_pid, initial_child_pids,
      workers, bad_pid_workers, http_client
    ):
    """ Build a multi-line diagnostic string for a stage02 failure.
    Captures process tree snapshots, per-PID metadata for the offending
    worker_pids, a re-poll of /server/info, and grepped lines from the
    server log file.
    """
    lines = []
    lines.append("worker pid is child of master -- FAILED")
    lines.append("master_pid = {}".format(master_pid))
    lines.append("initial child_pids (recursive=False) = {}".format(
        sorted(initial_child_pids)
      ))

    # Re-snapshot children NOW (after HTTP polling).  The original snapshot
    # was taken before /server/info polling; if the child set has drifted
    # the difference between then and now is the smoking gun.
    try:
      parent = psutil.Process(master_pid)
      now_children = parent.children(recursive=False)
      now_child_pids = sorted(c.pid for c in now_children)
      lines.append("current child_pids (recursive=False) = {}".format(
          now_child_pids
        ))
      now_descendants = parent.children(recursive=True)
      now_descendant_pids = sorted(c.pid for c in now_descendants)
      lines.append("current descendant_pids (recursive=True) = {}".format(
          now_descendant_pids
        ))
      try:
        lines.append("master create_time = {} status = {}".format(
            parent.create_time(), parent.status()
          ))
      except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        lines.append("master process metadata unavailable: {}".format(e))
    except psutil.NoSuchProcess:
      lines.append("master process disappeared during diagnostics")

    # Workers reported by /server/info
    lines.append("/server/info workers (worker_key -> worker_pid):")
    for wk, wv in workers.items():
      lines.append("  {} -> worker_pid={}".format(wk, wv.get("worker_pid")))

    # Re-poll /server/info to see if state has drifted since the check
    try:
      r2 = http_client.get("/server/info", timeout=10.0)
      if r2.status_code == 200:
        info2 = r2.json()
        workers2 = info2.get("workers", {})
        lines.append("/server/info re-poll workers (worker_key -> worker_pid):")
        for wk, wv in workers2.items():
          lines.append("  {} -> worker_pid={}".format(
              wk, wv.get("worker_pid")
            ))
      else:
        lines.append("/server/info re-poll status = {}".format(
            r2.status_code
          ))
    except Exception as e:
      lines.append("/server/info re-poll error: {}".format(e))

    # Per-offending-PID introspection
    lines.append("offending worker entries:")
    for wk, wpid, reason in bad_pid_workers:
      lines.append("  worker_key = {}".format(wk))
      lines.append("    reason = {}".format(reason))
      lines.append("    worker_pid = {}".format(wpid))
      try:
        proc = psutil.Process(wpid)
        try:
          ppid = proc.ppid()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
          ppid = "unavailable"
        try:
          ctime = proc.create_time()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
          ctime = "unavailable"
        try:
          status = proc.status()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
          status = "unavailable"
        try:
          cmdline = " ".join(proc.cmdline())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
          cmdline = "unavailable"
        lines.append(
            "    proc: ppid={} create_time={} status={} cmdline={}".format(
                ppid, ctime, status, cmdline
              )
          )
        lines.append("    is_child_of_master = {}".format(
            ppid == master_pid
          ))
      except psutil.NoSuchProcess:
        lines.append("    proc: NoSuchProcess (worker_pid {} not running)".format(
            wpid
          ))

    # Grep the server log
    try:
      log_path = context.server_manager.log_path()
    except Exception:
      log_path = None
    if log_path and os.path.isfile(log_path):
      lines.append("server log excerpt ({}):".format(log_path))
      grep_terms = [
          "register_worker", "unregister_worker",
          "Started parent process", "Started server process",
          "Starting worker", "Stopping worker", "Booting worker",
          "Worker exited", "worker exited",
          "register_server", "unregister_server",
          "lifespan", "PYVCON_MASTER_PID",
        ]
      for wk, wpid, _ in bad_pid_workers:
        grep_terms.append(str(wpid))
      try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
          for line in f:
            for term in grep_terms:
              if term in line:
                lines.append("  {}".format(line.rstrip()))
                break
      except Exception as e:
        lines.append("  log read error: {}".format(e))
    else:
      lines.append("server log path not available")

    return "\n".join(lines)

