# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" Working registration file in the scanner fixtures directory.

Used to verify that db.import_bindings() continues iterating to later
files after an earlier file (scanner_bad_reg.py) fails to import.

Points at the existing processors_good.AddParty class which is already
on the test PYTHONPATH via the workflow env var
"PYTHONPATH: tests/processors".
"""

import py_vcon_server.processor

py_vcon_server.processor.VconProcessorRegistry.register(
    py_vcon_server.processor.VconProcessorInitOptions(),
    "scanner_good_registration",
    "processors_good",
    "AddParty"
    )
