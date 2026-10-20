# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" Vcon serialization tests """

import pytest
import vcon

vcon_json_emptys = """
{
  "vcon": "0.0.1",
  "uuid": "my_fake_uuid",
  "created_at": 0,
  "subject": "string",
  "redacted": [
    {}
  ],
  "amended": [
    {}
  ],
  "group": [
    {}
  ],
  "parties": [
    {}
  ],
  "dialog": [
    {}
  ],
  "analysis": [
    {}
  ],
  "attachments": [
    {}
  ]
}
"""


def test_loads() -> None:
  vCon = vcon.Vcon()
  try:
    vCon.loads(vcon_json_emptys)
    raise Exception("Empty analisis object has no type, should raise exception")

  except vcon.InvalidVconJson as e:
    # expected
    pass

def test_group_absent_by_default() -> None:
  a_vcon = vcon.Vcon()
  a_vcon.set_uuid("py-vcon.dev")

  # Must check the dict before reading the group attribute, as
  # VconDictList currently inserts an empty list on read.
  assert(vcon.Vcon.GROUP not in a_vcon._vcon_dict)
  assert(vcon.Vcon.GROUP not in a_vcon.dumpd())
  assert(vcon.Vcon.GROUP not in a_vcon.dumps())


def test_add_group_object_creates_group() -> None:
  a_vcon = vcon.Vcon()
  a_vcon.set_uuid("py-vcon.dev")
  group_index = a_vcon.add_group_object("fake-uuid-1234")

  assert(group_index == 0)
  assert(a_vcon.group[0]["uuid"] == "fake-uuid-1234")
  assert(vcon.Vcon.GROUP in a_vcon.dumpd())

