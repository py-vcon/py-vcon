""" Unit tests for **VconStorage** """

import pytest
import pytest_asyncio
from common_setup import UUID, make_inline_audio_vcon, make_2_party_tel_vcon
import py_vcon_server
import py_vcon_server.processor
from py_vcon_server.db import VconStorage
import vcon

VCON_STORAGE = None

# invoke only once for all the unit test in this module
@pytest_asyncio.fixture(autouse=True)
async def setup():
  """ Setup Vcon storage connection before test """
  vs = VconStorage.instantiate()
  global VCON_STORAGE
  VCON_STORAGE = vs


  # wait until teardown time
  yield

  # Shutdown the Vcon storage after test
  VCON_STORAGE = None
  await vs.shutdown()


def test_redis_reg():
  """ Test DB binding registration for redis """
  print(VconStorage._vcon_storage_implementations)
  class_type = VconStorage._vcon_storage_implementations["redis"]
  assert(class_type is not None)


@pytest.mark.asyncio
async def test_redis_set_get(make_2_party_tel_vcon: vcon.Vcon):
  """ Test get and set of a **Vcon** using the redis DB binding """
  vCon = make_2_party_tel_vcon

  # Save the vcon
  await VCON_STORAGE.set(vCon)

  # Retrived the saved Vcon
  retrieved_vcon = await VCON_STORAGE.get(UUID)
  print(retrieved_vcon.dumps())
  # Make sure we get what we saved
  assert retrieved_vcon.parties[0]["tel"] == "1234"
  assert retrieved_vcon.parties[1]["tel"] == "5678"

@pytest.mark.asyncio
async def test_redis_jq(make_2_party_tel_vcon: vcon.Vcon):
  """ Test the jq query on **VconStorage.get** method """
  vCon = make_2_party_tel_vcon

  # Save the vcon
  await VCON_STORAGE.set(vCon)

  jq_xform = ".parties[]"
  party_dict = await VCON_STORAGE.jq_query(UUID, jq_xform)
  #print("party_dict: {}".format(party_dict))
  assert(party_dict[0]["tel"] == "1234")
  assert(party_dict[1]["tel"] == "5678")

@pytest.mark.asyncio
async def test_redis_jsonpath(make_2_party_tel_vcon: vcon.Vcon):
  """ Test the JSONPath query on the get of a **Vcon** from the **VconStorage** """
  vCon = make_2_party_tel_vcon

  # Save the vcon
  await VCON_STORAGE.set(vCon)

  jsonpath = "$.parties"
  party_dict = await VCON_STORAGE.json_path_query(UUID, jsonpath)
  print("party_dict: {}".format(party_dict))
  assert(party_dict[0][0]["tel"] == "1234")
  assert(party_dict[0][1]["tel"] == "5678")

@pytest.mark.asyncio
async def test_redis_delete(make_2_party_tel_vcon: vcon.Vcon):
  """ Test redis delete of a **Vcon** in the **VconStorage** """
  vCon = make_2_party_tel_vcon

  # Save the vcon
  await VCON_STORAGE.set(vCon)

  retrieved_vcon = await VCON_STORAGE.get(UUID)
  assert(retrieved_vcon is not None)

  await VCON_STORAGE.delete(UUID)

  try:
    retrieved_vcon = await VCON_STORAGE.get(UUID)
    raise Exception("vCon deleted, this should fail")
  except py_vcon_server.db.VconNotFound as e:
    # expected
    pass

@pytest.mark.asyncio
async def test_processor_io_commit(
  make_2_party_tel_vcon: vcon.Vcon,
  make_inline_audio_vcon: vcon.Vcon
  ):
  """
  Test the commit of (set on modified **Vcon**s in)
  a **VconProcessorIO** object to the **VconStorage**.
  """
  vcon1 = make_2_party_tel_vcon
  vcon1.set_party_parameter("tel", "444", 0)
  vcon1.set_party_parameter("tel", "888", 1)
  assert(len(vcon1.parties) == 2)
  assert(vcon1.parties[0]["tel"] == "444")
  assert(vcon1.parties[1]["tel"] == "888")
  assert(vcon1.uuid == UUID)
  vcon2 = make_inline_audio_vcon
  # need different UUIDs
  vcon2.set_uuid("py-vcon.org", True)
  assert(vcon2.uuid != UUID)

  io_object = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await io_object.add_vcon(vcon2) # read only
  await io_object.add_vcon(vcon1, None, False) # new/commit
  assert(not io_object.is_vcon_modified(0))
  assert(io_object.is_vcon_modified(1))

  await VCON_STORAGE.commit(io_object)

  assert(vcon1.uuid == UUID)
  retrieved_vcon = await VCON_STORAGE.get(vcon1.uuid)
  assert(len(retrieved_vcon.parties) == 2)
  assert(retrieved_vcon.parties[0]["tel"] == "444")
  assert(retrieved_vcon.parties[1]["tel"] == "888")

  try:
    retrieved_vcon = await VCON_STORAGE.get(vcon2.uuid)
    raise Exception("second vcon UUID: {} should not have been saved".format(
      vcon2.uuid
      ))

  except py_vcon_server.db.VconNotFound as e:
    # expected
    pass

