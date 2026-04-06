# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
pytest conftest.py for py_vcon_server tests.

Sets up PLUGIN_PATHS to include test_processors_always (timeout processors).
Does NOT load test_processors (reserved for test_site_plugins.py dynamic loading test).

Note: test_processor_docs.py and test_swagger_docs.py should be run separately
without test plugins to generate clean documentation.
"""
import os


# Add test_processors_always to PLUGIN_PATHS before any py_vcon_server import
existing_paths = os.environ.get("PLUGIN_PATHS", "")
if existing_paths:
    if "test_processors_always" not in existing_paths:
        os.environ["PLUGIN_PATHS"] = existing_paths + ",test_processors_always"
else:
    os.environ["PLUGIN_PATHS"] = "test_processors_always"

