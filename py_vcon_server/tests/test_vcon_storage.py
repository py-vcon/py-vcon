import asyncio
import pytest
import pytest_asyncio
import py_vcon_server.db
import vcon
import common_setup

# invoike only once for all the unit test in this module
@pytest_asyncio.fixture(autouse=True)
async def setup():
  # Setup Vcon storage connection before test
  await py_vcon_server.db.VconStorage.setup()

  # wait until teardown time
  yield

  # Shutdown the Vcon storage after test
  await py_vcon_server.db.VconStorage.teardown()

def test_redis_reg():
  print(py_vcon_server.db.VconStorage._vcon_storage_implementations)
  class_type = py_vcon_server.db.VconStorage._vcon_storage_implementations["redis"]
  assert(class_type is not None)

async def make_2_party_tel_vcon():
  vCon = vcon.Vcon()
  # Hack a known UUID so that we do not poluted the DB
  vCon._vcon_dict["uuid"] = common_setup.UUID
  party_1_index = vCon.set_party_parameter("tel", "1234")
  assert(party_1_index == 0)
  party_2_index = vCon.set_party_parameter("tel", "5678")
  assert(party_2_index == 1)

  # Save the vcon
  await py_vcon_server.db.VconStorage.set(vCon)

@pytest.mark.asyncio
async def test_redis_set_get():
  await make_2_party_tel_vcon()

  # Retrived the saved Vcon
  retrieved_vcon = await py_vcon_server.db.VconStorage.get(common_setup.UUID)
  print(retrieved_vcon.dumps())
  # Make sure we get what we saved
  assert retrieved_vcon.parties[0]["tel"] == "1234"
  assert retrieved_vcon.parties[1]["tel"] == "5678"

@pytest.mark.asyncio
async def test_redis_jq():

  await make_2_party_tel_vcon()

  jq_xform = ".parties[]"
  party_dict = await py_vcon_server.db.VconStorage.jq_query(common_setup.UUID, jq_xform)
  #print("party_dict: {}".format(party_dict))
  assert(party_dict[0]["tel"] == "1234")
  assert(party_dict[1]["tel"] == "5678")

@pytest.mark.asyncio
async def test_redis_jsonpath():

  await make_2_party_tel_vcon()

  jsonpath = "$.parties"
  party_dict = await py_vcon_server.db.VconStorage.json_path_query(common_setup.UUID, jsonpath)
  print("party_dict: {}".format(party_dict))
  assert(party_dict[0][0]["tel"] == "1234")
  assert(party_dict[0][1]["tel"] == "5678")


