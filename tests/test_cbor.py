
import vcon

def test_empty_vcon():
  empty_vcon = vcon.Vcon()
  empty_vcon.set_uuid("py-vcon.dev")
  cbor_bytes = empty_vcon.dumpc()
  print("empty len: {}".format(len(cbor_bytes)))
  print("cbor: {}".format(cbor_bytes))

  print("json: {}".format(empty_vcon.dumps()))
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

  reconstituted_vcon = vcon.Vcon()
  reconstituted_vcon.loadc(cbor_bytes)
  print("reconstituted: {}".format(reconstituted_vcon.dumps()))
  assert(hello_vcon.uuid == reconstituted_vcon.uuid)
  assert(hello_vcon.created_at == reconstituted_vcon.created_at)
  assert(hello_vcon.dialog[0]["body"] == reconstituted_vcon.dialog[0]["body"])
  assert(hello_vcon.dialog[0]["encoding"] == reconstituted_vcon.dialog[0]["encoding"])

