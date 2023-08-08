import asyncio
import pytest
import pytest_asyncio
import py_vcon_server
from py_vcon_server.db import VconStorage
import vcon
from common_setup import UUID, make_2_party_tel_vcon

# invoke only once for all the unit test in this module
@pytest_asyncio.fixture(autouse=True)
async def setup():
  # Setup Vcon storage connection before test
  await VconStorage.setup()

  # wait until teardown time
  yield

  # Shutdown the Vcon storage after test
  await VconStorage.teardown()

def test_redis_reg():
  print(VconStorage._vcon_storage_implementations)
  class_type = VconStorage._vcon_storage_implementations["redis"]
  assert(class_type is not None)


@pytest.mark.asyncio
async def test_redis_set_get(make_2_party_tel_vcon: vcon.Vcon):
  vCon = make_2_party_tel_vcon

  # Save the vcon
  await VconStorage.set(vCon)

  # Retrived the saved Vcon
  retrieved_vcon = await VconStorage.get(UUID)
  print(retrieved_vcon.dumps())
  # Make sure we get what we saved
  assert retrieved_vcon.parties[0]["tel"] == "1234"
  assert retrieved_vcon.parties[1]["tel"] == "5678"

@pytest.mark.asyncio
async def test_redis_jq(make_2_party_tel_vcon: vcon.Vcon):
  vCon = make_2_party_tel_vcon

  # Save the vcon
  await VconStorage.set(vCon)

  jq_xform = ".parties[]"
  party_dict = await VconStorage.jq_query(UUID, jq_xform)
  #print("party_dict: {}".format(party_dict))
  assert(party_dict[0]["tel"] == "1234")
  assert(party_dict[1]["tel"] == "5678")

@pytest.mark.asyncio
async def test_redis_jsonpath(make_2_party_tel_vcon: vcon.Vcon):
  vCon = make_2_party_tel_vcon

  # Save the vcon
  await VconStorage.set(vCon)

  jsonpath = "$.parties"
  party_dict = await VconStorage.json_path_query(UUID, jsonpath)
  print("party_dict: {}".format(party_dict))
  assert(party_dict[0][0]["tel"] == "1234")
  assert(party_dict[0][1]["tel"] == "5678")

@pytest.mark.asyncio
async def test_redis_delete(make_2_party_tel_vcon: vcon.Vcon):
  vCon = make_2_party_tel_vcon

  # Save the vcon
  await VconStorage.set(vCon)

  retrieved_vcon = await VconStorage.get(UUID)
  assert(retrieved_vcon is not None)

  await VconStorage.delete(UUID)

  retrieved_vcon = await VconStorage.get(UUID)
  assert(retrieved_vcon is None)


