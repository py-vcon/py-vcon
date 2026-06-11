# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" Unit tests for the context parameters substitution framework.

Pure unit tests for:
  * py_vcon_server.processor.BASE_CONTEXT_PARAMETERS resolution
    (PROCESSOR_NAME, TIMESTAMP, NDATE, VCON_UUID)
  * py_vcon_server.pipeline.PIPELINE_CONTEXT_PARAMETERS and run context
    to template name mapping (ENTRY_POINT, PIPELINE_NAME, PIPELINE_JOB_ID)
  * VconProcessorIO._resolve_vcon_uuid edge cases
  * substitution precedence (context kwarg > auto value > declared default)
  * processor scope context_parameters additions (real AddParty class)
  * undefined parameter error listing all missing names across fields
  * format_parameters_to_options return shape (dict in / pydantic in / bad type)

The REST and pipeline entry point call sites are exercised WRT context
parameters by additions to test_processor_jinja_report.py (/process and
/processIO) and test_pipeline.py (/pipeline/{name}/run and
/pipeline/{name}/run/{uuid}).
"""

import re
import datetime
import pytest
import pytest_asyncio
import vcon
import vcon.pydantic_utils
import py_vcon_server
import py_vcon_server.processor
import py_vcon_server.pipeline
from py_vcon_server.settings import VCON_STORAGE_URL
from common_setup import UUID, make_2_party_tel_vcon


VCON_STORAGE = None


@pytest_asyncio.fixture(autouse=True)
async def setup():
  """ Setup Vcon storage connection before each test """
  vs = py_vcon_server.db.VconStorage.instantiate(VCON_STORAGE_URL)
  global VCON_STORAGE
  VCON_STORAGE = vs
  yield
  VCON_STORAGE = None
  await vs.shutdown()


def merged_base_pipeline():
  """ Build the base + pipeline scope context parameter definitions. """
  merged = {}
  merged.update(py_vcon_server.processor.BASE_CONTEXT_PARAMETERS)
  merged.update(py_vcon_server.pipeline.PIPELINE_CONTEXT_PARAMETERS)
  return(merged)


# ============================================================
#  Module level constants
# ============================================================

def test_base_context_parameters_defined():
  """ BASE_CONTEXT_PARAMETERS declares the four base scope names """
  base = py_vcon_server.processor.BASE_CONTEXT_PARAMETERS
  for name in ["PROCESSOR_NAME", "TIMESTAMP", "NDATE", "VCON_UUID",
      "YEAR", "MONTH", "DAY"]:
    assert(name in base)
    assert("default" in base[name])
    assert("description" in base[name])
    assert("title" in base[name])


def test_pipeline_context_parameters_defined():
  """ PIPELINE_CONTEXT_PARAMETERS declares the three pipeline scope names """
  pipe = py_vcon_server.pipeline.PIPELINE_CONTEXT_PARAMETERS
  for name in ["PIPELINE_NAME", "PIPELINE_JOB_ID", "ENTRY_POINT"]:
    assert(name in pipe)
    assert("default" in pipe[name])


# ============================================================
#  Server scope
# ============================================================

def test_server_context_parameters_defined():
  """ SERVER_CONTEXT_PARAMETERS declares the six server scope names """
  server = py_vcon_server.processor.SERVER_CONTEXT_PARAMETERS
  for name in ["INSTANCE_ID", "REST_SCHEME", "REST_HOST", "REST_PORT",
      "SERVER_VERSION", "VCON_VERSION"]:
    assert(name in server)
    assert("default" in server[name])
    assert("description" in server[name])
    assert("title" in server[name])


def test_server_context_values_resolve():
  """
  Each server scope name resolves to the value derived from settings or
  package version.  Compares against the same sources the resolver uses
  so this test does not depend on a specific server configuration.
  """
  import py_vcon_server
  import py_vcon_server.settings
  import urllib.parse

  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  defs = {}
  defs.update(py_vcon_server.processor.BASE_CONTEXT_PARAMETERS)
  defs.update(py_vcon_server.processor.SERVER_CONTEXT_PARAMETERS)

  options = {"format_options": {
      "label": "id={INSTANCE_ID}|scheme={REST_SCHEME}|host={REST_HOST}"
        "|port={REST_PORT}|sv={SERVER_VERSION}|vv={VCON_VERSION}"
    }}
  io.format_parameters_to_options_dict(options, defs, "p")

  parsed = urllib.parse.urlparse(py_vcon_server.settings.REST_URL)
  expected_scheme = parsed.scheme or ""
  expected_host = parsed.hostname or ""
  expected_port = str(parsed.port) if(parsed.port is not None) else ""

  assert("id={}".format(py_vcon_server.settings.INSTANCE_ID) in options["label"])
  assert("scheme={}".format(expected_scheme) in options["label"])
  assert("host={}".format(expected_host) in options["label"])
  assert("port={}".format(expected_port) in options["label"])
  assert("sv={}".format(py_vcon_server.__version__) in options["label"])
  assert("vv={}".format(vcon.__version__) in options["label"])


def test_server_context_values_cached():
  """
  _get_server_context_values returns the cached dict on repeated calls
  (same object identity).  Confirms the lazy cache is populated once.
  """
  v1 = py_vcon_server.processor._get_server_context_values()
  v2 = py_vcon_server.processor._get_server_context_values()
  assert(v1 is v2)


# ============================================================
#  Base scope resolution
# ============================================================

@pytest.mark.asyncio
async def test_processor_name_substitution(make_2_party_tel_vcon):
  """ PROCESSOR_NAME substitutes the processor_name argument """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await io.add_vcon(make_2_party_tel_vcon, "fake_lock", False)
  options = {"format_options": {"label": "proc={PROCESSOR_NAME}"}}
  io.format_parameters_to_options_dict(options, merged_base_pipeline(), "my_proc")
  assert(options["label"] == "proc=my_proc")


@pytest.mark.asyncio
async def test_timestamp_and_ndate_substitution(make_2_party_tel_vcon):
  """ TIMESTAMP is ISO 8601 and NDATE is yyyymmdd """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await io.add_vcon(make_2_party_tel_vcon, "fake_lock", False)
  options = {"format_options": {
      "label": "{TIMESTAMP}",
      "notes": "{NDATE}"
    }}
  io.format_parameters_to_options_dict(options, merged_base_pipeline(), "p")
  datetime.datetime.fromisoformat(options["label"])
  assert(re.fullmatch(r"\d{8}", options["notes"]) is not None)


@pytest.mark.asyncio
async def test_year_month_day_substitution(make_2_party_tel_vcon):
  """ YEAR/MONTH/DAY are UTC and consistent with NDATE """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await io.add_vcon(make_2_party_tel_vcon, "fake_lock", False)
  options = {"format_options": {
      "label": "{YEAR}|{MONTH}|{DAY}",
      "notes": "{NDATE}"
    }}
  io.format_parameters_to_options_dict(options, merged_base_pipeline(), "p")
  year, month, day = options["label"].split("|")
  assert(re.fullmatch(r"\d{4}", year) is not None)
  assert(re.fullmatch(r"\d{2}", month) is not None)
  assert(re.fullmatch(r"\d{2}", day) is not None)
  assert(options["notes"] == year + month + day)


@pytest.mark.asyncio
async def test_vcon_uuid_resolves_from_io(make_2_party_tel_vcon):
  """ VCON_UUID resolves from the vCon at the default input_vcon_index """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await io.add_vcon(make_2_party_tel_vcon, "fake_lock", False)
  options = {"format_options": {"label": "{VCON_UUID}"}}
  io.format_parameters_to_options_dict(options, merged_base_pipeline(), "p")
  assert(options["label"] == UUID)


# ============================================================
#  VCON_UUID edge cases via _resolve_vcon_uuid
# ============================================================

def test_resolve_vcon_uuid_unset_index_no_vcons():
  """ Empty IO with no input_vcon_index returns empty string """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  assert(io._resolve_vcon_uuid({}) == "")


@pytest.mark.asyncio
async def test_resolve_vcon_uuid_valid_index(make_2_party_tel_vcon):
  """ Valid integer index in range returns the uuid """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await io.add_vcon(make_2_party_tel_vcon, "fake_lock", False)
  assert(io._resolve_vcon_uuid({"input_vcon_index": 0}) == UUID)


@pytest.mark.asyncio
async def test_resolve_vcon_uuid_out_of_range(make_2_party_tel_vcon):
  """ Out of range index returns empty string """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await io.add_vcon(make_2_party_tel_vcon, "fake_lock", False)
  assert(io._resolve_vcon_uuid({"input_vcon_index": 5}) == "")


def test_resolve_vcon_uuid_no_vcons():
  """ No vCons present returns empty string even for index 0 """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  assert(io._resolve_vcon_uuid({"input_vcon_index": 0}) == "")


def test_resolve_vcon_uuid_non_integer_string():
  """ Non integer string (unsubstituted template) returns empty string """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  assert(io._resolve_vcon_uuid({"input_vcon_index": "{x}"}) == "")


def test_resolve_vcon_uuid_none_index():
  """ None index returns empty string """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  assert(io._resolve_vcon_uuid({"input_vcon_index": None}) == "")


def test_resolve_vcon_uuid_vcon_without_uuid_attr():
  """ A vCon object without a uuid attribute returns empty string """
  class _NoUuid:
    pass
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  io._vcons = [_NoUuid()]
  assert(io._resolve_vcon_uuid({"input_vcon_index": 0}) == "")


def test_resolve_vcon_uuid_uuid_none():
  """ A vCon object with uuid set to None returns empty string """
  class _NoneUuid:
    uuid = None
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  io._vcons = [_NoneUuid()]
  assert(io._resolve_vcon_uuid({"input_vcon_index": 0}) == "")


# ============================================================
#  Run context to template name mapping
# ============================================================

def test_run_context_mapping_present():
  """ entry_point/pipeline_name/job_id map to UPPER_CASE template names """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  io.set_run_context({
      py_vcon_server.processor.RUN_CONTEXT_ENTRY_POINT:   "/process",
      py_vcon_server.processor.RUN_CONTEXT_PIPELINE_NAME: "pn",
      py_vcon_server.processor.RUN_CONTEXT_JOB_ID:        "j7"
    })
  options = {"format_options": {
      "label": "{ENTRY_POINT}|{PIPELINE_NAME}|{PIPELINE_JOB_ID}"
    }}
  io.format_parameters_to_options_dict(options, merged_base_pipeline(), "p")
  assert(options["label"] == "/process|pn|j7")


def test_run_context_mapping_absent_defaults():
  """ When run context is empty, pipeline scope names use empty defaults """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  options = {"format_options": {
      "label": "[{ENTRY_POINT}][{PIPELINE_NAME}][{PIPELINE_JOB_ID}]"
    }}
  io.format_parameters_to_options_dict(options, merged_base_pipeline(), "p")
  assert(options["label"] == "[][][]")


# ============================================================
#  Precedence
# ============================================================

def test_context_kwarg_overrides_auto_value():
  """ context kwarg value overrides the auto resolved value """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  options = {"format_options": {"label": "{TIMESTAMP}"}}
  io.format_parameters_to_options_dict(
      options,
      merged_base_pipeline(),
      "p",
      context = {"TIMESTAMP": "PINNED"}
    )
  assert(options["label"] == "PINNED")


def test_context_kwarg_overrides_declared_default():
  """ context kwarg value overrides a declared context parameter default """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  defs = merged_base_pipeline()
  defs["DIALOG_INDEX"] = {"default": 0, "description": "x", "title": "Dialog Index"}
  options = {"format_options": {"label": "{DIALOG_INDEX}"}}
  io.format_parameters_to_options_dict(options, defs, "p", context = {"DIALOG_INDEX": 3})
  assert(options["label"] == "3")


def test_context_param_default_overrides_same_named_pipeline_parameter():
  """ A declared context parameter default overrides a same named pipeline parameter """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  io.set_parameter("FOO", "from_params")
  defs = merged_base_pipeline()
  defs["FOO"] = {"default": "default_foo", "description": "x", "title": "Foo"}
  options = {"format_options": {"label": "{FOO}"}}
  io.format_parameters_to_options_dict(options, defs, "p")
  assert(options["label"] == "default_foo")


def test_pipeline_parameter_used_when_not_a_context_param():
  """ A normal pipeline parameter (not declared as context) substitutes as is """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  io.set_parameter("user_value", "hello")
  options = {"format_options": {"label": "{user_value}"}}
  io.format_parameters_to_options_dict(options, merged_base_pipeline(), "p")
  assert(options["label"] == "hello")


# ============================================================
#  Processor scope additions (real AddParty class)
# ============================================================

def test_add_party_declares_party_index():
  """ The real AddParty test processor declares the PARTY_INDEX context parameter """
  import processors_good
  assert("PARTY_INDEX" in processors_good.AddParty.context_parameters)
  party_index = processors_good.AddParty.context_parameters["PARTY_INDEX"]
  assert("default" in party_index)
  assert("description" in party_index)
  assert("title" in party_index)


def test_add_party_context_param_default_and_override():
  """
  Merging AddParty.context_parameters (processor scope) resolves PARTY_INDEX
  to its declared default, and to a live value when supplied via context.
  This mirrors what the call sites do with processor.context_parameters.
  """
  import processors_good
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  defs = {}
  defs.update(py_vcon_server.processor.BASE_CONTEXT_PARAMETERS)
  defs.update(processors_good.AddParty.context_parameters)

  options = {"format_options": {"label": "[{PARTY_INDEX}]"}}
  io.format_parameters_to_options_dict(options, defs, "test_add_party")
  assert(options["label"] == "[]")

  options = {"format_options": {"label": "[{PARTY_INDEX}]"}}
  io.format_parameters_to_options_dict(options, defs, "test_add_party", context = {"PARTY_INDEX": 0})
  assert(options["label"] == "[0]")


# ============================================================
#  Undefined parameter error
# ============================================================

def test_undefined_parameter_lists_all_missing():
  """ ParameterNotFound lists all missing names across all fields """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  io.set_parameter("known", "k")
  options = {"format_options": {
      "label": "{known} {miss1}",
      "notes": "{miss2} {miss3}",
      "input_vcon_index": "{known}"
    }}
  try:
    io.format_parameters_to_options_dict(options, merged_base_pipeline(), "my_proc")
    raise Exception("expected ParameterNotFound")
  except py_vcon_server.processor.ParameterNotFound as e:
    msg = str(e)
    assert("miss1" in msg)
    assert("miss2" in msg)
    assert("miss3" in msg)
    assert("my_proc" in msg)
    assert("label" in msg)
    assert("notes" in msg)
    assert("available pipeline parameters" in msg)
    assert("available context parameters" in msg)


# ============================================================
#  Return shape and wrong type
# ============================================================

def test_empty_format_options_noop():
  """ Empty format_options is a no op """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  options = {"format_options": {}}
  io.format_parameters_to_options_dict(options, merged_base_pipeline(), "p")
  assert(options == {"format_options": {}})


def test_dict_in_returns_dict():
  """ dict input returns the same dict (mutated in place) """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  options = {"format_options": {"label": "{PROCESSOR_NAME}"}}
  result = io.format_parameters_to_options(options, merged_base_pipeline(), "p")
  assert(result is options)
  assert(result["label"] == "p")


def test_pydantic_in_returns_pydantic():
  """ VconProcessorOptions input returns a reconstructed VconProcessorOptions """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  generic = py_vcon_server.processor.VconProcessorOptions(
      format_options = {"label": "{PROCESSOR_NAME}"}
    )
  result = io.format_parameters_to_options(generic, merged_base_pipeline(), "p")
  assert(isinstance(result, py_vcon_server.processor.VconProcessorOptions))
  assert(result.label == "p")


def test_wrong_type_raises():
  """ Non dict / non VconProcessorOptions input raises """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  try:
    io.format_parameters_to_options([], merged_base_pipeline(), "p")
    raise Exception("expected exception for invalid type")
  except Exception:
    pass

def test_pass2_swallows_malformed_template():
  """ Pass-2 dry run swallows IndexError/ValueError from malformed templates """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  options = {"format_options": {
      "a": "{missing}",
      "b": "{0}"
    }}
  try:
    io.format_parameters_to_options_dict(options, merged_base_pipeline(), "p")
    raise Exception("expected ParameterNotFound")
  except py_vcon_server.processor.ParameterNotFound:
    pass


# ============================================================
#  REST_URL parsing variants
# ============================================================

def test_server_context_values_malformed_rest_url(monkeypatch):
  """
  Malformed REST_URL (urlparse returns empty scheme) logs ERROR and
  all REST_* values fall back to empty strings.
  """
  import py_vcon_server.settings

  monkeypatch.setattr(py_vcon_server.processor, "_SERVER_CONTEXT_VALUES", None)
  monkeypatch.setattr(py_vcon_server.settings, "REST_URL", "not a url")

  values = py_vcon_server.processor._resolve_server_context_values()
  assert(values["REST_SCHEME"] == "")
  assert(values["REST_HOST"] == "")
  assert(values["REST_PORT"] == "")


def test_server_context_values_empty_rest_url(monkeypatch):
  """
  Empty REST_URL is silently treated as all REST_* empty (the
  if(rest_url) guard skips parsing entirely, no error log).
  """
  import py_vcon_server.settings

  monkeypatch.setattr(py_vcon_server.processor, "_SERVER_CONTEXT_VALUES", None)
  monkeypatch.setattr(py_vcon_server.settings, "REST_URL", "")

  values = py_vcon_server.processor._resolve_server_context_values()
  assert(values["REST_SCHEME"] == "")
  assert(values["REST_HOST"] == "")
  assert(values["REST_PORT"] == "")


def test_server_context_values_rest_url_no_port(monkeypatch):
  """
  REST_URL without an explicit port yields REST_PORT='' while
  scheme and host populate normally.
  """
  import py_vcon_server.settings

  monkeypatch.setattr(py_vcon_server.processor, "_SERVER_CONTEXT_VALUES", None)
  monkeypatch.setattr(py_vcon_server.settings, "REST_URL", "https://example.com")

  values = py_vcon_server.processor._resolve_server_context_values()
  assert(values["REST_SCHEME"] == "https")
  assert(values["REST_HOST"] == "example.com")
  assert(values["REST_PORT"] == "")


# ============================================================
#  Recursion guard 
# ============================================================

def test_format_options_recursion_guard():
  """
  A 'format_options' key inside format_options is skipped by the inner
  loop to avoid recursing into the same dict that drives substitution.
  """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  options = {"format_options": {
      "label":          "{PROCESSOR_NAME}",
      "format_options": "this_should_not_be_treated_as_a_template_field"
    }}
  io.format_parameters_to_options_dict(options, merged_base_pipeline(), "p")
  assert(options["label"] == "p")
  assert(isinstance(options["format_options"], dict))
  assert(options["format_options"]["format_options"] ==
      "this_should_not_be_treated_as_a_template_field")


# ============================================================
#  Pass-2 swallows malformed templates 
# ============================================================

def test_pass2_swallows_malformed_template():
  """
  When substitution fails with KeyError, pass-2 iterates every field
  to collect all missing names.  Malformed templates in other fields
  (IndexError/ValueError) are swallowed so the user still gets a
  complete missing-name list.
  """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  options = {"format_options": {
      "a": "{missing_name}",
      "b": "{0}"
    }}
  try:
    io.format_parameters_to_options_dict(options, merged_base_pipeline(), "p")
    raise Exception("expected ParameterNotFound")
  except py_vcon_server.processor.ParameterNotFound as e:
    msg = str(e)
    assert("missing_name" in msg)


# ============================================================
#  Precedence when a processor shadows a reserved name 
# ============================================================

def test_processor_scope_default_shadowed_by_auto_value():
  """
  When a processor declares a context parameter with the same
  UPPER_CASE name as a base scope auto-resolved name (e.g.
  PROCESSOR_NAME), the auto value still wins over the declared
  default.  Precedence: context kwarg > auto_values > declared default.
  """
  io = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  merged = {}
  merged.update(py_vcon_server.processor.BASE_CONTEXT_PARAMETERS)
  merged.update(py_vcon_server.processor.SERVER_CONTEXT_PARAMETERS)
  merged.update(py_vcon_server.pipeline.PIPELINE_CONTEXT_PARAMETERS)
  merged.update({
      "PROCESSOR_NAME": {
          "default":     "shadowed_default",
          "description": "x",
          "title":       "x"
        }
    })

  options = {"format_options": {"label": "{PROCESSOR_NAME}"}}
  io.format_parameters_to_options_dict(options, merged, "actual_name")
  assert(options["label"] == "actual_name"), \
      "auto_values should override declared default for PROCESSOR_NAME"

  options = {"format_options": {"label": "{PROCESSOR_NAME}"}}
  io.format_parameters_to_options_dict(
      options, merged, "actual_name",
      context = {"PROCESSOR_NAME": "context_wins"}
    )
  assert(options["label"] == "context_wins")

