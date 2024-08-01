# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.

import vcon

def test_empty_vcon():
  empty_vcon = vcon.Vcon()
  empty_vcon.set_uuid("py-vcon.dev")
  empty_vcon.set_redacted("1234", "PII")
  assert(empty_vcon.redacted["uuid"] == "1234")
  assert(empty_vcon.redacted["type"] == "PII")

