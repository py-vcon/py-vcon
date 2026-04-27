#!/usr/bin/env python3
# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
Extract the top N files with the most uncovered lines from a coverage.xml file.

Usage:
    python3 coverage_uncovered.py [coverage.xml] [--top N] [--filter SUBSTRING]

Examples:
    python3 coverage_uncovered.py coverage.xml
    python3 coverage_uncovered.py coverage.xml --top 20
    python3 coverage_uncovered.py coverage.xml --filter metrics
    python3 coverage_uncovered.py coverage.xml --filter py_vcon_server --top 15
"""
import argparse
import xml.etree.ElementTree as ET


def main():
  parser = argparse.ArgumentParser(
      description="Show files with the most uncovered lines from coverage.xml"
    )
  parser.add_argument("coverage_file", nargs="?", default="coverage.xml",
      help="Path to coverage.xml (default: coverage.xml)")
  parser.add_argument("--top", type=int, default=10,
      help="Number of files to show (default: 10)")
  parser.add_argument("--filter", type=str, default="",
      help="Only show files whose path contains this substring")
  args = parser.parse_args()

  tree = ET.parse(args.coverage_file)
  root = tree.getroot()

  file_stats = []

  for package in root.findall(".//package"):
    for cls in package.findall(".//class"):
      filename = cls.get("filename", "")
      if args.filter and args.filter not in filename:
        continue

      total_lines = 0
      missed_lines = 0
      missed_line_numbers = []

      for line in cls.findall(".//line"):
        total_lines += 1
        hits = int(line.get("hits", "0"))
        if hits == 0:
          missed_lines += 1
          missed_line_numbers.append(int(line.get("number", "0")))

      if total_lines > 0:
        coverage_pct = ((total_lines - missed_lines) / total_lines) * 100
      else:
        coverage_pct = 100.0

      file_stats.append({
          "filename": filename,
          "total": total_lines,
          "missed": missed_lines,
          "coverage_pct": coverage_pct,
          "missed_lines": missed_line_numbers,
        })

  # Sort by missed lines descending
  file_stats.sort(key=lambda f: f["missed"], reverse=True)

  print()
  print("{:<60s}  {:>6s}  {:>6s}  {:>7s}".format(
      "File", "Total", "Missed", "Cover%"))
  print("{:<60s}  {:>6s}  {:>6s}  {:>7s}".format(
      "-" * 60, "-----", "------", "------"))

  for f in file_stats[:args.top]:
    print("{:<60s}  {:>6d}  {:>6d}  {:>6.1f}%".format(
        f["filename"], f["total"], f["missed"], f["coverage_pct"]))

    # Show missed line ranges (compact)
    if f["missed_lines"]:
      ranges = _compact_ranges(f["missed_lines"])
      line_str = ", ".join(ranges)
      # Wrap at ~80 chars
      if len(line_str) > 120:
        line_str = line_str[:117] + "..."
      print("    missed: {}".format(line_str))

  print()


def _compact_ranges(numbers):
  """Convert [1,2,3,5,7,8,9] to ['1-3', '5', '7-9']"""
  if not numbers:
    return []
  numbers = sorted(numbers)
  ranges = []
  start = numbers[0]
  end = numbers[0]
  for n in numbers[1:]:
    if n == end + 1:
      end = n
    else:
      if start == end:
        ranges.append(str(start))
      else:
        ranges.append("{}-{}".format(start, end))
      start = n
      end = n
  if start == end:
    ranges.append(str(start))
  else:
    ranges.append("{}-{}".format(start, end))
  return ranges


if __name__ == "__main__":
  main()
