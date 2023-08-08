import asyncio
import pytest
import pytest_asyncio
import importlib
import copy
import py_vcon_server.pipeline
from common_setup import UUID, make_2_party_tel_vcon
import vcon


# Stuff to test:
#  add
#  can't add same uuid
#  update
#  can't update non-existing uuid
#  with and without lock
#  readonly and read/write

@pytest.mark.asyncio
async def test_pipeline_io_vcons(make_2_party_tel_vcon: vcon.Vcon):
  vcon_object = make_2_party_tel_vcon
  assert(vcon_object.uuid == UUID)
 
  io_object = py_vcon_server.pipeline.PipelineIO()
  await io_object.add_vcon(vcon_object)
  assert(len(io_object._vcons) == 1)
  assert(len(io_object._vcon_locks) == 1)
  assert(len(io_object._vcon_update) == 1)
  assert(io_object._vcon_locks[0] == None)
  assert(io_object._vcon_update[0] == False)

  vcon2_object = copy.deepcopy(vcon_object)
  assert(vcon2_object.uuid == UUID)
  vcon2_object.parties[0]["tel"] = "abcd"
  vcon2_object.parties[1]["tel"] = "efgh"

  try:
    await io_object.add_vcon(vcon2_object)
    raise Exception("Should fail as vCon with same UUID already exists in io object")

  except Exception as e:
    if(str(e).startswith("('Cannot add duplicate")):
      pass
    else:
      raise e

  # different UUID should now be allowed
  vcon3_object = vcon.Vcon()
  await io_object.add_vcon(vcon3_object)
  assert(len(io_object._vcons) == 2)
  assert(len(io_object._vcon_locks) == 2)
  assert(len(io_object._vcon_update) == 2)
  assert(io_object._vcon_locks[1] == None)
  assert(io_object._vcon_update[1] == False)

  try:
    await io_object.update_vcon(vcon_object)
    raise Exception("same UUID should not be allowed as it was added readonly")

  except Exception as e:
    if("has no write lock" in str(e)):
      pass
    else:
      raise e

  vcon4_object = vcon.Vcon()
  try:
    await io_object.add_vcon(vcon4_object, "lockkey")
    raise Exception("should fail as we have given a new vCon with a locak key, but labeled it readonly")

  except Exception as e:
    if(str(e).startswith("Should not lock readonly vCon")):
      pass
    else:
      raise e


  # New pipeline IO object to test read/write features
  rw_io_object = py_vcon_server.pipeline.PipelineIO()
  # Add with lock and read_write
  await rw_io_object.add_vcon(vcon_object, "fake_key", False)
  assert(len(rw_io_object._vcons) == 1)
  assert(len(rw_io_object._vcon_locks) == 1)
  assert(len(rw_io_object._vcon_update) == 1)
  assert(rw_io_object._vcon_locks[0] == "fake_key")
  assert(rw_io_object._vcon_update[0] == False)


  await rw_io_object.update_vcon(vcon2_object)
  assert(len(rw_io_object._vcons) == 1)
  assert(len(rw_io_object._vcon_locks) == 1)
  assert(len(rw_io_object._vcon_update) == 1)
  assert(rw_io_object._vcon_locks[0] == "fake_key")
  assert(rw_io_object._vcon_update[0] == True)
  assert((await rw_io_object.get_vcon()).parties[0]["tel"] == "abcd")
  assert((await rw_io_object.get_vcon()).parties[1]["tel"] == "efgh")

  # Add with no lock and read_write
  await rw_io_object.add_vcon(vcon4_object, None, False)
  # Assumes the vCon does not exist in VconStorage, so no lock needed
  assert(len(rw_io_object._vcons) == 2)
  assert(len(rw_io_object._vcon_locks) == 2)
  assert(len(rw_io_object._vcon_update) == 2)
  assert(rw_io_object._vcon_locks[0] == "fake_key")
  assert(rw_io_object._vcon_locks[1] == None)
  assert(rw_io_object._vcon_update[0] == True)
  assert(rw_io_object._vcon_update[1] == True)
  assert(len((await rw_io_object.get_vcon(1)).parties) == 0)

