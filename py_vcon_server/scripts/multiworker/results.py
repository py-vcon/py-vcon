# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
multiworker/results.py — Stage pass/fail tracking.
"""

from multiworker.constants import STAGE_NAMES


class Results:
  def __init__(self):
    self._results = []   # list of (stage, name, passed, detail)

  def record(self, stage, name, passed, detail=""):
    self._results.append((stage, name, passed, detail))
    marker = "✓" if passed else "✗"
    stage_label = _stage_label(stage)
    print("  {} {}: {} {}".format(
        marker, stage_label, name,
        "— {}".format(detail) if detail else ""
      ))

  def summary(self):
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed = sum(1 for _, _, p, _ in self._results if p)
    failed = sum(1 for _, _, p, _ in self._results if not p)
    for stage, name, p, detail in self._results:
      status = "PASS" if p else "FAIL"
      stage_label = _stage_label(stage)
      print("  [{}] {}: {}{}".format(
          status, stage_label, name,
          " — {}".format(detail) if detail else ""
        ))
    print()
    print("Total: {} passed, {} failed".format(passed, failed))
    return failed == 0


def _stage_label(stage: int) -> str:
  """Return 'Stage N (name)' if name known, else 'Stage N'."""
  name = STAGE_NAMES.get(stage)
  if name:
    return "Stage {} ({})".format(stage, name)
  return "Stage {}".format(stage)
