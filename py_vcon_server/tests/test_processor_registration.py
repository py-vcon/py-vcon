# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" unit tests to test VconProcessorRegistration and VconProcessorRegistry """
import asyncio
import pytest
import pytest_asyncio
import importlib
import copy
import py_vcon_server.processor
import vcon
from common_setup import make_2_party_tel_vcon
from py_vcon_server.settings import VCON_STORAGE_URL


VCON_STORAGE = None

@pytest_asyncio.fixture(autouse=True)
async def setup_db():
  # Init storge
  vs = py_vcon_server.db.VconStorage.instantiate(VCON_STORAGE_URL)
  global VCON_STORAGE
  VCON_STORAGE = vs

  yield
  # teardown storage
  VCON_STORAGE = None
  await vs.shutdown()
 
 
@pytest.mark.asyncio
async def test_registration(make_2_party_tel_vcon: vcon.Vcon):
  vCon = make_2_party_tel_vcon

  init_options_none = py_vcon_server.processor.VconProcessorInitOptions()

  try:
    py_vcon_server.processor.VconProcessorRegistry.register(
      init_options_none,
      "impls_nothing",
      "processors_bad",
      "ImplementsNothing"
      )
    raise Exception("should fail as __init__ (inherited from VconProcessor, and not implemented) takes wrong arguments")

  except py_vcon_server.processor.InvalidVconProcessorClass as e:
    pass



  try:
    py_vcon_server.processor.VconProcessorRegistry.register(
      init_options_none,
      "impls_min_init",
      "processors_bad",
      "ImplementsMinimalInitOnly"
      )

  except Exception as e:
    raise e

  names = py_vcon_server.processor.VconProcessorRegistry.get_processor_names()
  assert("impls_min_init" in names)

  proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("impls_min_init")
  assert(proc_inst.title() == "ImplementsMinimalInitOnly")
  assert(proc_inst.description() == " Attempt to hide abstract class ")
  assert(proc_inst.version() == "0.0.0")
  assert(proc_inst.may_modify_vcons() == True)

  # Setup inputs
  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(vCon, "fake_lock", False) # read/write
  proc_options = py_vcon_server.processor.VconProcessorOptions()
  assert(len(proc_input._vcons) == 1)
  vCon = await proc_input.get_vcon(0)
  assert(vCon is not None)

  try:
    proc_output = await proc_inst.process(proc_input, proc_options)
    raise Exception("Should fail as process is not implemented by ImplementsMinimalInitOnly")

  except py_vcon_server.processor.InvalidVconProcessorClass as e:
    # expected
    pass



  py_vcon_server.processor.VconProcessorRegistry.register(
    init_options_none,
    "add_party",
    "processors_good",
    "AddParty"
    )


  proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("add_party")
  assert(proc_inst.title() == "Add party to Vcon")
  assert(proc_inst.description() ==
    " adds a new party with the Vcon Party Object parameters provided in the **AddPartyOptions** ")
  assert(proc_inst.version() == "0.0.1")
  assert(proc_inst.may_modify_vcons() == True)

  add_party_options = proc_inst.processor_options_class()(tel = "8888")
  proc_output = await proc_inst.process(proc_input, add_party_options)
  assert(isinstance(proc_output, py_vcon_server.processor.VconProcessorIO))
  vCon = await proc_input.get_vcon(0)
  assert(len(vCon.parties) == 3)
  assert(vCon.parties[2]["tel"] == "8888")
  assert(proc_output._vcon_update[0] == True)

