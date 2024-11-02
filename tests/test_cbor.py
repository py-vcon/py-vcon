# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.

import vcon

def test_empty_vcon():
  empty_vcon = vcon.Vcon()
  empty_vcon.set_uuid("py-vcon.dev")
  cbor_bytes = empty_vcon.dumpc()
  print("empty len: {}".format(len(cbor_bytes)))
  print("cbor: {}".format(cbor_bytes))
  print("bype[0]: {}".format(cbor_bytes[0]))
  print("bype[1]: {}".format(cbor_bytes[1]))

  json_str = empty_vcon.dumps()
  print("json: {}".format(json_str))
  print("Size ratio: {}".format(len(cbor_bytes)/len(json_str)))
  reconstituted_vcon = vcon.Vcon()
  reconstituted_vcon.loadc(cbor_bytes)
  print("reconstituted: {}".format(reconstituted_vcon.dumps()))
  assert(empty_vcon.uuid == reconstituted_vcon.uuid)
  assert(empty_vcon.created_at == reconstituted_vcon.created_at)

def test_simple_vcon():
  hello_vcon = vcon.Vcon()
  hello_vcon.load("tests/hello.vcon")

  cbor_bytes = hello_vcon.dumpc()

  print("cbor: {}".format(cbor_bytes))
  print("bype[0]: {}".format(cbor_bytes[0]))
  print("bype[1]: {}".format(cbor_bytes[1]))

  reconstituted_vcon = vcon.Vcon()
  reconstituted_vcon.loadc(cbor_bytes)
  with open("tests/hello.cbor", "wb") as cbor_file:
    cbor_file.write(cbor_bytes)

  json_str = reconstituted_vcon.dumps()
  print("reconstituted: {}".format(json_str))
  print("Size ratio: {}".format(len(cbor_bytes)/len(json_str)))
  assert(hello_vcon.uuid == reconstituted_vcon.uuid)
  assert(hello_vcon.created_at == reconstituted_vcon.created_at)
  assert(hello_vcon.dialog[0]["body"] == reconstituted_vcon.dialog[0]["body"])
  assert(hello_vcon.dialog[0]["encoding"] == reconstituted_vcon.dialog[0]["encoding"])

