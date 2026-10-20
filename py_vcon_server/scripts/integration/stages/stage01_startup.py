# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
integration/stages/stage01_startup.py

Verifies the server started and is serving requests.
Must run first -- all other stages depend on this.
"""

import urllib.request


class Stage:
  name = "stage01_startup"
  description = "Server starts and /docs responds with 200"
  expected_state_after = "running"
  min_workers = 1

  def run(self, context):
    try:
      with urllib.request.urlopen(
          "{}/docs".format(context.base_url), timeout=5.0
        ) as resp:
        passed = resp.status == 200
        context.results.record(
            self.name,
            self.description,
            passed,
            "status={}".format(resp.status)
          )
        return passed
    except Exception as e:
      context.results.record(self.name, self.description, False, str(e))
      return False
