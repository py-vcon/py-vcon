# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" Unit tests to test some of the pydantic models """
import py_vcon_server
import vcon.pydantic_utils

def test_parties():
  party = py_vcon_server.processor.VconPartiesObject(**{})

  assert(party.tel is None)
  d = vcon.pydantic_utils.get_dict(party, exclude_none = True)
  print("keys: {}".format(d.keys()))
  print("party: {}".format(d))
  assert(len(d.keys()) == 0)
  assert(party.name is None)

