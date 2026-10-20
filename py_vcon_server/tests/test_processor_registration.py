# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
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


@pytest.mark.asyncio
async def test_registration_module_raises_on_import():
  """
  A VconProcessor module that raises a non-ModuleNotFoundError exception
  at import time must not propagate that exception out of register().
  The registration should be recorded as failed:
    _module_load_attempted == True
    _module_not_found      == False
    _processor_instance    is None
  And the processor must not appear in get_processor_names() (default
  filtering of successfully loaded processors), but must appear when
  successfully_loaded=False.
  """
  init_options_none = py_vcon_server.processor.VconProcessorInitOptions()

  # register() must not raise even though the module's import raises
  # RuntimeError at top level.
  py_vcon_server.processor.VconProcessorRegistry.register(
    init_options_none,
    "raises_on_import",
    "processors_raises",
    "DoesNotMatter"
    )

  # Inspect the registry entry directly to verify the failed-load state.
  registration = py_vcon_server.processor.VCON_PROCESSOR_REGISTRY["raises_on_import"]
  assert(registration._module_load_attempted == True)
  assert(registration._module_not_found == False)
  assert(registration._processor_instance is None)

  # Default filtering (successfully_loaded=True) must exclude it.
  loaded_names = py_vcon_server.processor.VconProcessorRegistry.get_processor_names()
  assert("raises_on_import" not in loaded_names)

  # Unfiltered listing must include it.
  all_names = py_vcon_server.processor.VconProcessorRegistry.get_processor_names(
    successfully_loaded = False
    )
  assert("raises_on_import" in all_names)

  # get_processor_instance() must raise VconProcessorNotInstantiated.
  try:
    py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("raises_on_import")
    raise Exception("get_processor_instance should have raised VconProcessorNotInstantiated")
  except py_vcon_server.processor.VconProcessorNotInstantiated as not_inst:
    # Should reach the generic-fallback branch, not "load not attempted"
    # or "module not found", since _module_load_attempted is True and
    # _module_not_found is False.
    assert("not instantiated for name" in str(not_inst))


@pytest.mark.asyncio
async def test_registration_class_init_raises():
  """
  A VconProcessor class whose __init__ raises a non-TypeError exception
  during instantiation by VconProcessorRegistration must not propagate
  that exception out of register().  The registration should be recorded
  as failed:
    _module_load_attempted == True
    _module_not_found      == False
    _processor_instance    is None
  The module imported successfully -- only the class instantiation failed.
  """
  init_options_none = py_vcon_server.processor.VconProcessorInitOptions()

  # register() must not raise even though InitRaisingProcessor.__init__
  # raises RuntimeError when instantiated.
  py_vcon_server.processor.VconProcessorRegistry.register(
    init_options_none,
    "class_init_raises",
    "processors_init_raises",
    "InitRaisingProcessor"
    )

  registration = py_vcon_server.processor.VCON_PROCESSOR_REGISTRY["class_init_raises"]
  assert(registration._module_load_attempted == True)
  assert(registration._module_not_found == False)
  assert(registration._processor_instance is None)

  loaded_names = py_vcon_server.processor.VconProcessorRegistry.get_processor_names()
  assert("class_init_raises" not in loaded_names)

  all_names = py_vcon_server.processor.VconProcessorRegistry.get_processor_names(
    successfully_loaded = False
    )
  assert("class_init_raises" in all_names)

  try:
    py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("class_init_raises")
    raise Exception("get_processor_instance should have raised VconProcessorNotInstantiated")
  except py_vcon_server.processor.VconProcessorNotInstantiated as not_inst:
    # Should reach the generic-fallback branch, not "load not attempted"
    # or "module not found", since _module_load_attempted is True and
    # _module_not_found is False.
    assert("not instantiated for name" in str(not_inst))


@pytest.mark.asyncio
async def test_scanner_handles_registration_file_top_level_import_failure(caplog):
  """
  db.import_bindings() must not propagate exceptions raised by a registration
  file's own top-level import statements.  Mirrors the production failure of
  py_vcon_server/processor/whisper_base.py when stable_whisper is uninstalled:

    1. Scanner iterates py_vcon_server/processor/*.py
    2. Hits whisper_base.py
    3. whisper_base.py line "import py_vcon_server.processor.builtin.whisper"
       raises ModuleNotFoundError because vcon.filter_plugins.impl.whisper
       re-raises after "import stable_whisper" fails
    4. The exception must not propagate out of import_bindings()
    5. The scanner must log an ERROR identifying the failed module
    6. Subsequent registration files in the same directory must still load

  Whether the registration file is well-written or not, other plugins that
  load successfully must not be blocked by another developer's broken plugin.
  """
  import os
  import logging
  import py_vcon_server.db

  fixtures_dir = os.path.join(
      os.path.dirname(os.path.abspath(__file__)),
      "scanner_fixtures"
      )

  with caplog.at_level(logging.ERROR):
    py_vcon_server.db.import_bindings(
        [fixtures_dir],
        "",
        "scanner_test",
        try_all = True
        )

  assert("scanner_good_registration" in
      py_vcon_server.processor.VCON_PROCESSOR_REGISTRY)

  assert("scanner_unreachable_registration" not in
      py_vcon_server.processor.VCON_PROCESSOR_REGISTRY)

  error_messages = [r.message for r in caplog.records
      if r.levelno == logging.ERROR]
  assert(any("scanner_bad_reg" in m for m in error_messages))


@pytest.mark.asyncio
async def test_scanner_default_behavior_raises_on_failure(caplog):
  """
  Regression guard: db.import_bindings() with try_all unset (default False)
  must propagate exceptions from failed module imports.  This is the
  behavior infrastructure scans (e.g. DB bindings) depend on -- a broken
  DB binding must not be silently skipped.

  Companion test to test_scanner_handles_registration_file_top_level_import_failure,
  which verifies the try_all=True path.
  """
  import os
  import logging
  import py_vcon_server.db

  fixtures_dir = os.path.join(
      os.path.dirname(os.path.abspath(__file__)),
      "scanner_fixtures"
      )

  with caplog.at_level(logging.ERROR):
    try:
      py_vcon_server.db.import_bindings(
          [fixtures_dir],
          "",
          "scanner_test_strict"
          )
      raise Exception("import_bindings should have raised with try_all default")
    except ModuleNotFoundError:
      pass

  error_messages = [r.message for r in caplog.records
      if r.levelno == logging.ERROR]
  assert(any("scanner_bad_reg" in m for m in error_messages))

