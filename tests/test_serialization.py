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
  "appended": [
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

