# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
integration/results.py -- Stage result tracking and reporting.
"""


class Results:
  """Accumulates pass/fail records for each stage and prints a summary."""

  def __init__(self):
    self._records = []

  def record(self, name, description, passed, detail=""):
    self._records.append({
        "name": name,
        "description": description,
        "passed": passed,
        "detail": detail,
      })
    status = "PASS" if passed else "FAIL"
    print("  [{}] {}".format(status, description))
    if detail:
      print("       {}".format(detail))

  def summary(self):
    """Print summary and return True if all stages passed."""
    total = len(self._records)
    passed = sum(1 for r in self._records if r["passed"])
    failed = total - passed

    print()
    print("=" * 60)
    print("Results: {}/{} passed".format(passed, total))
    print("=" * 60)

    if failed:
      print()
      print("Failed stages:")
      for r in self._records:
        if not r["passed"]:
          print("  FAIL  {} -- {}".format(r["name"], r["description"]))
          if r["detail"]:
            print("        {}".format(r["detail"]))

    return failed == 0
