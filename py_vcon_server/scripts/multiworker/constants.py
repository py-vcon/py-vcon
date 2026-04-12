# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
multiworker/constants.py — Shared constants and pipeline definitions.
"""

import os

# ── Stage registry ────────────────────────────────────────────────────────────
# Maps stage number to short name.  Used by Results for readable output and
# by the CLI --stages / --skip arguments (both numbers and names accepted).

STAGE_NAMES = {
  1: "startup",
  2: "worker_count",
  3: "blocking",
  4: "pipeline_job",
  5: "concurrent",
  6: "sigint_shutdown",
  7: "prometheus",
}

# Reverse map: name -> number, for CLI parsing
STAGE_NUMBERS = {v: k for k, v in STAGE_NAMES.items()}

# ── Stage 4/5 constants ───────────────────────────────────────────────────────

QUEUE_NAME       = "mw_test_queue"
PIPELINE_NAME    = QUEUE_NAME          # must match queue name
VCON_UUID        = "01855517-mult-iworker-test-77776666acbe"
VCON_UUID_2      = "01855517-mult-iwork2-test-77776666acbe"
ANALYSIS_TYPE    = "multiworker_test"
ANALYSIS_MARKER  = "MULTIWORKER_TEST_OK"

# ── Stage 3 constants ─────────────────────────────────────────────────────────

BLOCK_SECONDS    = 8     # how long timeout_test_sleep_sync blocks

# ── Timing constants ──────────────────────────────────────────────────────────

HEALTH_TIMEOUT    = 3.0  # health check must respond within this many seconds
# seconds to wait for server to become ready
STARTUP_TIMEOUT   = int(os.environ.get("MULTIWORKER_STARTUP_TIMEOUT", "30"))
# seconds to wait for the Stage 7 Prometheus test server to become ready.
# Separate from STARTUP_TIMEOUT since Stage 7 starts a second server while
# the main server is running, increasing resource pressure on slow CI runners.
PROM_STARTUP_TIMEOUT = int(os.environ.get(
    "MULTIWORKER_PROM_STARTUP_TIMEOUT",
    str(STARTUP_TIMEOUT)
  ))
# max seconds to wait for a single job to complete
JOB_POLL_TIMEOUT  = int(os.environ.get("MULTIWORKER_JOB_POLL_TIMEOUT", "30"))
JOB_POLL_INTERVAL = 0.5  # seconds between job completion polls

# ── Stage 6 constants ─────────────────────────────────────────────────────────

SIGINT_UUID             = "01855517-mult-sigint-test-77776666acbe"
SIGINT_QUEUE            = "mw_sigint_queue"
SIGINT_MARKER           = "SIGINT_SHUTDOWN_OK"
SIGINT_JOB_SLEEP        = 4.0  # job sleeps this long — must still be running when SIGINT fires
SIGINT_SHUTDOWN_TIMEOUT = 35   # max seconds for server to exit after SIGINT

# ── Stage 7 constants ─────────────────────────────────────────────────────────

PROM_VCON_UUID  = "01855517-mult-prom7s-test-77776666acbe"

# ── Pipeline definitions ──────────────────────────────────────────────────────

# Stage 4/5 pipeline — jinja_report writes a verifiable analysis object.
# No external service dependencies.
PIPELINE_DEF = {
  "pipeline_options": {
    "save_vcons": True,
    "timeout": 20
  },
  "processors": [
    {
      "processor_name": "jinja_report",
      "processor_options": {
        "template": "{} uuid={{{{ vcons[0].uuid }}}}".format(ANALYSIS_MARKER),
        "analysis_type": ANALYSIS_TYPE,
        "analysis_vendor": "test"
      }
    }
  ]
}

# Stage 6 pipeline — jinja_report writes the analysis immediately, then
# timeout_test_sleep_async holds the job open for SIGINT_JOB_SLEEP seconds
# so SIGINT arrives while the job is still running.
SIGINT_PIPELINE_DEF = {
  "pipeline_options": {
    "save_vcons": True,
    "timeout": 60,
    "failure_queue": "",
    "success_queue": ""
  },
  "processors": [
    {
      "processor_name": "jinja_report",
      "processor_options": {
        "template": "{} uuid={{{{ vcons[0].uuid }}}}".format(SIGINT_MARKER),
        "analysis_type": "sigint_test",
        "analysis_vendor": "test"
      }
    },
    {
      "processor_name": "timeout_test_sleep_async",
      "processor_options": {
        "sleep_seconds": SIGINT_JOB_SLEEP
      }
    }
  ]
}
