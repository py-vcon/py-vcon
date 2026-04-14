# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
multiworker — support package for test_multiworker.py integration test.

Modules:
  constants  — shared constants and pipeline definitions
  results    — Results class for stage pass/fail tracking
  helpers    — HTTP helpers, vCon construction, cleanup
  stage1     — Server startup
  stage2     — Worker process count
  stage3     — Blocking isolation
  stage4     — Background pipeline job
  stage5     — Concurrent jobs
  stage6     — SIGINT graceful shutdown
  stage7     -- Prometheus multiprocess aggregation
  stage8     -- Cross-worker /diagnostics aggregation

"""
