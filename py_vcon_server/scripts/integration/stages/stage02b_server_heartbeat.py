# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
integration/stages/stage02b_server_heartbeat.py

Verifies that the server entry last_heartbeat in /servers advances
over time, proving the master heartbeat thread is running.
"""

import time

import httpx

from integration.helpers import get


class Stage:
  name = "stage02b_server_heartbeat"
  description = "Server heartbeat advances over time"
  expected_state_after = "running"
  min_workers = 2

  def run(self, context):
    master_pid = context.server_manager.pid()

    try:
      with httpx.Client(base_url=context.base_url) as client:
        r = get(client, "/servers")
        if r.status_code != 200:
          context.results.record(
              self.name, self.description, False,
              "GET /servers -> {}".format(r.status_code))
          return False

        servers = r.json()
        master_pid_str = str(master_pid)
        server_key = None
        for k in servers:
          if master_pid_str in k:
            server_key = k
            break

        if server_key is None:
          context.results.record(
              self.name, self.description, False,
              "no server entry found for master PID {}".format(master_pid))
          return False

        hb1 = servers[server_key].get("last_heartbeat", 0)

        # Wait for at least one heartbeat tick.
        # Default HEARTBEAT_PERIOD is 60s but integration tests
        # may override.  Wait up to 90s, polling every 2s.
        deadline = time.time() + 90.0
        hb2 = hb1
        while time.time() < deadline:
          time.sleep(2.0)
          r = get(client, "/servers")
          if r.status_code == 200:
            s = r.json().get(server_key, {})
            hb2 = s.get("last_heartbeat", 0)
            if hb2 > hb1:
              break

        passed = hb2 > hb1
        context.results.record(
            self.name, self.description, passed,
            "heartbeat {} -> {} (delta={:.1f}s)".format(
                hb1, hb2, hb2 - hb1)
            if passed else
            "heartbeat did not advance within 90s")
        return passed

    except Exception as e:
      context.results.record(
          self.name, self.description, False, str(e))
      return False

