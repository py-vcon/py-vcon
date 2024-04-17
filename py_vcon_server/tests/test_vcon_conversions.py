# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" Unit tests for MultifariousVcon and conversion between forms """

import pytest
import pytest_asyncio
import itertools
import py_vcon_server.processor
from py_vcon_server.db import VconStorage
from common_setup import UUID, make_2_party_tel_vcon
import vcon
from py_vcon_server.settings import VCON_STORAGE_URL

VCON_STORAGE = None

# invoke only once for all the unit test in this module
@pytest_asyncio.fixture(autouse=True)
async def setup():
  # Setup Vcon storage connection before test
  vs = VconStorage.instantiate(VCON_STORAGE_URL)
  assert(vs is not None)
  global VCON_STORAGE
  VCON_STORAGE = vs

  # wait until teardown time
  yield

  # Shutdown the Vcon storage after test
  VCON_STORAGE = None
  await vs.shutdown()


@pytest.fixture()
def vcon_data() -> dict:
  vcon_object = common_setup.make_2_party_tel_vcon()
  
@pytest.mark.asyncio
async def test_conversions(make_2_party_tel_vcon: vcon.Vcon):
  # Create our test Vcon and put it in the DB so that it can be retrived via UUID
  vcon_object = make_2_party_tel_vcon
  await VCON_STORAGE.set(vcon_object)

  vcon_json = vcon_object.dumps()
  vcon_dict = vcon_object.dumpd()
  vcon_uuid = vcon_object.uuid

  all_forms = {}
  all_forms[py_vcon_server.processor.VconTypes.OBJECT] = vcon_object
  all_forms[py_vcon_server.processor.VconTypes.DICT] = vcon_dict
  all_forms[py_vcon_server.processor.VconTypes. JSON] = vcon_json
  all_forms[py_vcon_server.processor.VconTypes.UUID] = vcon_uuid

  forms = [
    py_vcon_server.processor.VconTypes.UUID,
    py_vcon_server.processor.VconTypes.JSON,
    py_vcon_server.processor.VconTypes.DICT,
    py_vcon_server.processor.VconTypes.OBJECT
    ]

  for length in range(len(forms) + 1):
    for subset in itertools.combinations(forms, length):
      print("set vcon forms: {}".format(subset))
      mVcon = py_vcon_server.processor.MultifariousVcon(VCON_STORAGE)
      if(len(subset) == 0):
        pass

      elif(len(subset) >= 1):
        extra_data = subset[1:]
        vcon_uuid = None
        vcon_json = None
        vcon_dict = None
        vcon_object = None
        if(py_vcon_server.processor.VconTypes.UUID in extra_data):
          vcon_uuid = all_forms[py_vcon_server.processor.VconTypes.UUID]
        if(py_vcon_server.processor.VconTypes.JSON in extra_data):
          vcon_json = all_forms[py_vcon_server.processor.VconTypes.JSON]
        if(py_vcon_server.processor.VconTypes.DICT in extra_data):
          vcon_dict = all_forms[py_vcon_server.processor.VconTypes.DICT]
        if(py_vcon_server.processor.VconTypes.OBJECT in extra_data):
          vcon_object = all_forms[py_vcon_server.processor.VconTypes.OBJECT]

        mVcon.update_vcon(all_forms[subset[0]],
          vcon_uuid = vcon_uuid,
          vcon_json = vcon_json,
          vcon_dict = vcon_dict,
          vcon_object = vcon_object)

      else:
        assert(0)

      for form in forms:
        print("getting form: {}".format(form))
        #print("forms contain: {}".format(mVcon._vcon_forms))
        got_vcon = await mVcon.get_vcon(form)

        if(len(subset) == 0):
          if(len(mVcon._vcon_forms) != 0):
            print("forms contain: {}".format(mVcon._vcon_forms))
          assert(len(mVcon._vcon_forms) == 0)
          assert(got_vcon == None)
        else:
          if(isinstance(got_vcon, vcon.Vcon)):
            assert(got_vcon.uuid == all_forms[form].uuid)
            assert(got_vcon.parties[0]["tel"] == all_forms[form].parties[0]["tel"])
            assert(got_vcon.parties[1]["tel"] == all_forms[form].parties[1]["tel"])
          else:
            assert(got_vcon == all_forms[form])

