# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
integration/constants.py -- Shared constants and pipeline definitions.
"""

import os


# -- Timing constants ----------------------------------------------------------

HEALTH_TIMEOUT = 3.0
STARTUP_TIMEOUT = int(os.environ.get("INTEGRATION_STARTUP_TIMEOUT", "30"))
JOB_POLL_TIMEOUT = int(os.environ.get("INTEGRATION_JOB_POLL_TIMEOUT", "30"))
JOB_POLL_INTERVAL = 0.5


# -- Shared identifiers -------------------------------------------------------

QUEUE_NAME = "integ_test_queue"
PIPELINE_NAME = QUEUE_NAME
VCON_UUID = "01855517-intg-ration-test-77776666acbe"


# -- Pipeline definitions -----------------------------------------------------

# Used by stage04 and stage05.
# jinja_report writes a verifiable analysis object.
# No external service dependencies.
ANALYSIS_TYPE = "integration_test"
ANALYSIS_MARKER = "INTEGRATION_TEST_OK"

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
