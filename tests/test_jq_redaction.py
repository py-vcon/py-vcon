# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" Unit test for jq_redaction plugin """
import vcon
import pytest
#from tests.common_utils import call_data , empty_vcon, two_party_tel_vcon


@pytest.mark.asyncio
async def test_jq_redaction():
  unredacted = vcon.Vcon()
  unredacted.load("tests/example_external_dialog.vcon")
  unredacted.set_party_parameter("name", "Alice", 0)
  unredacted.set_party_parameter("name", "Bob", 1)
  assert(len(unredacted.dialog) == 1)
  assert(len(unredacted.analysis) == 3)

  redaction_query = """. + {parties: [.parties[] | delpaths([["foo"], ["tel"]])]} +\
    {dialog: [.dialog[] | delpaths([["body"], ["url"]])]} + {analysis: [.analysis[0]]}"""

  options = {
      "jq_redaction_query": redaction_query,
      "redaction_type_label": "Test Redaction",
      "uuid_domain": "py-vcon.org"
    }

  redacted = await unredacted.jq_redaction(options)

  assert(len(redacted.parties) == 2)
  assert(len(redacted.parties[0]) == 1)
  assert(redacted.parties[0]["name"] == "Alice")
  assert(len(redacted.parties[1]) == 1)
  assert(redacted.parties[1]["name"] == "Bob")

  assert(len(redacted.dialog) == 1)
  assert(redacted.dialog[0].get("url", None) is None)
  assert(redacted.dialog[0].get("body", None) is None)
  assert(redacted.dialog[0]["type"] == "recording")

  assert(len(redacted.analysis) == 1)
  assert(redacted.uuid is not None)
  assert(redacted.uuid != unredacted.uuid)

  assert(len(redacted.attachments) == 0)

  assert(redacted.redacted["uuid"] == unredacted.uuid)
  assert(redacted.uuid != unredacted.uuid)

  assert(unredacted.redacted is None or
      unredacted.redacted == {}
    )
  assert(len(unredacted.dialog) == 1)
  assert(len(unredacted.analysis) == 3)

