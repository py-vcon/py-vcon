# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" Unit tests for jinja_report VconProcessor """

import copy
import datetime
import pytest
import pytest_asyncio
import fastapi.testclient
import vcon
import py_vcon_server
import py_vcon_server.processor
from py_vcon_server.settings import VCON_STORAGE_URL

UUID = "01855517-test-fake-uuid-77776666acbe"

VCON_STORAGE = None


def make_1_dialog_vcon() -> vcon.Vcon:
  """
  Create a vCon with named parties, subject, and a single text dialog
  with start time and duration.  No external files needed.
  """
  v = vcon.Vcon()
  v._vcon_dict["uuid"] = UUID
  v.set_party_parameter("tel", "+15551234567")
  v.set_party_parameter("name", "Alice", 0)
  v.set_party_parameter("tel", "+15559876543")
  v.set_party_parameter("name", "Bob", 1)
  v.set_subject("Sales inquiry from Alice")

  v.add_dialog_inline_text(
    "Hello, I would like to discuss pricing.",
    "2024-03-06T20:07:43+00:00",
    5.0,
    0,
    vcon.Vcon.MEDIATYPE_TEXT_PLAIN
    )

  return(v)


def make_2_dialog_vcon() -> vcon.Vcon:
  """
  Create a vCon with two text dialogs for testing default
  analysis_dialog_index behavior.
  """
  v = make_1_dialog_vcon()

  v.add_dialog_inline_text(
    "Thank you for the information.",
    "2024-03-06T20:08:00+00:00",
    3.0,
    1,
    vcon.Vcon.MEDIATYPE_TEXT_PLAIN
    )

  return(v)


# invoke only once for all the unit test in this module
@pytest_asyncio.fixture(autouse=True)
async def setup():
  """ Setup Vcon storage connection before test """
  vs = py_vcon_server.db.VconStorage.instantiate(VCON_STORAGE_URL)
  global VCON_STORAGE
  VCON_STORAGE = vs

  # wait until teardown time
  yield

  # Shutdown the Vcon storage after test
  VCON_STORAGE = None
  await vs.shutdown()


# ============================================================
#  Test: processor registration
# ============================================================
def test_jinja_report_registration():
  """ Verify jinja_report is registered and can be instantiated """
  names = py_vcon_server.processor.VconProcessorRegistry.get_processor_names()
  assert("jinja_report" in names)

  proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("jinja_report")
  assert(proc_inst is not None)
  assert(proc_inst.title() == "Jinja2 template report generator **VconProcessor**")
  assert(proc_inst.version() == "0.0.1")
  assert(proc_inst.may_modify_vcons() == True)


# ============================================================
#  Test: parameter-only output (default behavior)
# ============================================================
@pytest.mark.asyncio
async def test_jinja_report_parameter_output():
  """ Test rendering a template and storing result as a parameter """
  in_vcon = make_1_dialog_vcon()

  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(in_vcon, "fake_lock", False)
  assert(len(proc_input._vcons) == 1)

  jinja_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("jinja_report")

  template = "UUID: {{ vcons[0].uuid }}"
  jinja_options = jinja_proc_inst.processor_options_class()(
      template = template
    )

  proc_output = await jinja_proc_inst.process(proc_input, jinja_options)

  # Check the rendered output is in the default parameter
  result = proc_output.get_parameter("report_output")
  assert(result == "UUID: {}".format(in_vcon.uuid))

  # Verify vCon was NOT modified (no analysis_type set)
  assert(not proc_output.is_vcon_modified(0))


# ============================================================
#  Test: custom output parameter name
# ============================================================
@pytest.mark.asyncio
async def test_jinja_report_custom_parameter_name():
  """ Test using a custom output parameter name """
  in_vcon = make_1_dialog_vcon()

  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(in_vcon, "fake_lock", False)

  jinja_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("jinja_report")

  jinja_options = jinja_proc_inst.processor_options_class()(
      template = "hello",
      output_parameter_name = "my_custom_output"
    )

  proc_output = await jinja_proc_inst.process(proc_input, jinja_options)

  result = proc_output.get_parameter("my_custom_output")
  assert(result == "hello")

  # Verify default parameter name was NOT set
  try:
    proc_output.get_parameter("report_output")
    raise Exception("expect KeyError as report_output should not be set")
  except KeyError:
    pass


# ============================================================
#  Test: analysis object output
# ============================================================
@pytest.mark.asyncio
async def test_jinja_report_analysis_output():
  """ Test rendering a template and adding as analysis object to vCon """
  in_vcon = make_1_dialog_vcon()

  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(in_vcon, "fake_lock", False)

  jinja_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("jinja_report")

  template = "Report for {{ vcons[0].uuid }}"
  jinja_options = jinja_proc_inst.processor_options_class()(
      template = template,
      analysis_type = "report",
      analysis_vendor = "jinja",
      analysis_dialog_index = 0
    )

  proc_output = await jinja_proc_inst.process(proc_input, jinja_options)

  # Check parameter output
  result = proc_output.get_parameter("report_output")
  assert("Report for" in result)
  assert(UUID in result)

  # Check vCon was modified
  assert(proc_output.is_vcon_modified(0))

  # Check analysis object was added
  out_vcon = await proc_output.get_vcon(0)
  assert(out_vcon.analysis is not None)
  assert(len(out_vcon.analysis) == 1)
  analysis = out_vcon.analysis[0]
  assert(analysis["type"] == "report")
  assert(analysis["vendor"] == "jinja")
  assert(analysis["encoding"] == "none")
  assert(analysis["dialog"] == 0)
  assert(analysis["mediatype"] == "text/plain")
  assert("Report for" in analysis["body"])
  assert(UUID in analysis["body"])


# ============================================================
#  Test: analysis with default dialog index (all dialogs)
# ============================================================
@pytest.mark.asyncio
async def test_jinja_report_analysis_default_dialog_index():
  """ Test that analysis_dialog_index defaults to all dialogs """
  v = make_2_dialog_vcon()
  assert(len(v.dialog) == 2)

  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(v, "fake_lock", False)

  jinja_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("jinja_report")

  jinja_options = jinja_proc_inst.processor_options_class()(
      template = "Report for {{ vcons[0].uuid }}",
      analysis_type = "report"
      # analysis_dialog_index not set, should default to all
    )

  proc_output = await jinja_proc_inst.process(proc_input, jinja_options)

  out_vcon = await proc_output.get_vcon(0)
  assert(len(out_vcon.analysis) == 1)
  # With 2 dialogs and no explicit index, should get a list [0, 1]
  assert(out_vcon.analysis[0]["dialog"] == [0, 1])


# ============================================================
#  Test: analysis with single dialog defaults to int not list
# ============================================================
@pytest.mark.asyncio
async def test_jinja_report_analysis_single_dialog_index():
  """ With one dialog and no explicit index, dialog should be int 0 not list """
  v = make_1_dialog_vcon()
  assert(len(v.dialog) == 1)

  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(v, "fake_lock", False)

  jinja_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("jinja_report")

  jinja_options = jinja_proc_inst.processor_options_class()(
      template = "Report",
      analysis_type = "report"
    )

  proc_output = await jinja_proc_inst.process(proc_input, jinja_options)

  out_vcon = await proc_output.get_vcon(0)
  assert(out_vcon.analysis[0]["dialog"] == 0)


# ============================================================
#  Test: both parameter and analysis output simultaneously
# ============================================================
@pytest.mark.asyncio
async def test_jinja_report_both_outputs():
  """ Test that both parameter and analysis outputs are produced """
  v = make_1_dialog_vcon()

  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(v, "fake_lock", False)

  jinja_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("jinja_report")

  template = "Subject: {{ vcons[0].subject | default('N/A', true) }}"
  jinja_options = jinja_proc_inst.processor_options_class()(
      template = template,
      output_parameter_name = "email_body",
      analysis_type = "report",
      analysis_dialog_index = 0
    )

  proc_output = await jinja_proc_inst.process(proc_input, jinja_options)

  # Both should match
  param_result = proc_output.get_parameter("email_body")
  out_vcon = await proc_output.get_vcon(0)
  analysis_body = out_vcon.analysis[0]["body"]
  assert(param_result == analysis_body)
  assert("Sales inquiry from Alice" in param_result)


# ============================================================
#  Test: template with loops and filters
# ============================================================
@pytest.mark.asyncio
async def test_jinja_report_complex_template():
  """ Test a template with loops, filters and multi-line output """
  v = make_1_dialog_vcon()

  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(v, "fake_lock", False)

  jinja_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("jinja_report")

  template = """Conversation Report
===================
UUID: {{ vcons[0].uuid }}
Subject: {{ vcons[0].subject | default("N/A", true) }}
Date: {{ vcons[0].dialog[0].start | default("N/A", true) }}
Duration: {{ vcons[0].dialog[0].duration | default("N/A", true) }} seconds

Parties:
{% for p in vcons[0].parties -%}
  - {{ p.name | default("Unknown", true) }}
{% endfor %}"""

  jinja_options = jinja_proc_inst.processor_options_class()(
      template = template
    )

  proc_output = await jinja_proc_inst.process(proc_input, jinja_options)

  result = proc_output.get_parameter("report_output")
  assert("Conversation Report" in result)
  assert(UUID in result)
  assert("Sales inquiry from Alice" in result)
  assert("2024-03-06T20:07:43" in result)
  assert("5.0 seconds" in result)
  assert("Alice" in result)
  assert("Bob" in result)


# ============================================================
#  Test: template accessing parameters from prior pipeline steps
# ============================================================
@pytest.mark.asyncio
async def test_jinja_report_with_parameters():
  """ Test template accessing VconProcessorIO parameters """
  in_vcon = make_1_dialog_vcon()

  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(in_vcon, "fake_lock", False)
  proc_input.set_parameter("summary", "Customer asked about pricing.")
  proc_input.set_parameter("sentiment", "positive")

  jinja_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("jinja_report")

  template = "Summary: {{ parameters.summary }}\nSentiment: {{ parameters.sentiment }}"
  jinja_options = jinja_proc_inst.processor_options_class()(
      template = template
    )

  proc_output = await jinja_proc_inst.process(proc_input, jinja_options)

  result = proc_output.get_parameter("report_output")
  assert("Summary: Customer asked about pricing." in result)
  assert("Sentiment: positive" in result)


# ============================================================
#  Test: template error handling (StrictUndefined)
# ============================================================
@pytest.mark.asyncio
async def test_jinja_report_template_error():
  """ Test that referencing undefined variables raises an error """
  in_vcon = make_1_dialog_vcon()

  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(in_vcon, "fake_lock", False)

  jinja_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("jinja_report")

  # Reference a parameter that does not exist without using default filter
  template = "Missing: {{ parameters.nonexistent_param }}"
  jinja_options = jinja_proc_inst.processor_options_class()(
      template = template
    )

  try:
    await jinja_proc_inst.process(proc_input, jinja_options)
    raise Exception("Expected jinja2 UndefinedError to be raised")
  except Exception as e:
    # jinja2.exceptions.UndefinedError expected
    assert("nonexistent_param" in str(e) or "Undefined" in str(type(e).__name__))


# ============================================================
#  Test: missing template raises validation error
# ============================================================
def test_jinja_report_missing_template():
  """ Test that omitting the required template field raises a validation error """
  jinja_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("jinja_report")

  try:
    options = jinja_proc_inst.processor_options_class()()
    raise Exception("Expected validation error for missing template field")
  except Exception as e:
    # pydantic should raise a validation error
    assert("template" in str(e).lower() or "field required" in str(e).lower())


# ============================================================
#  Test: analysis with optional product and schema
# ============================================================
@pytest.mark.asyncio
async def test_jinja_report_analysis_product_schema():
  """ Test that product and schema are set on analysis when provided """
  v = make_1_dialog_vcon()

  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(v, "fake_lock", False)

  jinja_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("jinja_report")

  jinja_options = jinja_proc_inst.processor_options_class()(
      template = "test",
      analysis_type = "structured_report",
      analysis_vendor = "custom_vendor",
      analysis_product = "custom_product",
      analysis_schema = "custom_schema",
      media_type = "application/json",
      analysis_dialog_index = 0
    )

  proc_output = await jinja_proc_inst.process(proc_input, jinja_options)

  out_vcon = await proc_output.get_vcon(0)
  analysis = out_vcon.analysis[0]
  assert(analysis["type"] == "structured_report")
  assert(analysis["vendor"] == "custom_vendor")
  assert(analysis["product"] == "custom_product")
  assert(analysis["schema"] == "custom_schema")
  assert(analysis["mediatype"] == "application/json")


# ============================================================
#  Test: analysis without product and schema omits them
# ============================================================
@pytest.mark.asyncio
async def test_jinja_report_analysis_no_product_schema():
  """ Test that product and schema are NOT in analysis when not provided """
  v = make_1_dialog_vcon()

  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(v, "fake_lock", False)

  jinja_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("jinja_report")

  jinja_options = jinja_proc_inst.processor_options_class()(
      template = "test",
      analysis_type = "report",
      analysis_dialog_index = 0
    )

  proc_output = await jinja_proc_inst.process(proc_input, jinja_options)

  out_vcon = await proc_output.get_vcon(0)
  analysis = out_vcon.analysis[0]
  assert("product" not in analysis)
  assert("schema" not in analysis)


# ============================================================
#  Test: format_options injects parameters into options
# ============================================================
@pytest.mark.asyncio
async def test_jinja_report_format_options():
  """ Test that format_options correctly injects parameter values into options """
  v = make_1_dialog_vcon()

  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(v, "fake_lock", False)
  proc_input.set_parameter("my_template", "UUID is {{ vcons[0].uuid }}")
  proc_input.set_parameter("my_param_name", "formatted_output")

  jinja_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("jinja_report")

  jinja_options = {
      "template": "placeholder",
      "output_parameter_name": "placeholder",
      "format_options": {
          "template": "{my_template}",
          "output_parameter_name": "{my_param_name}"
        }
    }

  formatted_options = proc_input.format_parameters_to_options(jinja_options)
  formatted_options = jinja_proc_inst.processor_options_class()(**formatted_options)

  proc_output = await jinja_proc_inst.process(proc_input, formatted_options)

  result = proc_output.get_parameter("formatted_output")
  assert(UUID in result)
  assert("UUID is" in result)


# ============================================================
#  Test: RESTful API - /process/{vcon_uuid}/jinja_report
# ============================================================
@pytest.mark.asyncio
async def test_jinja_report_proc_api():
  """ Test jinja_report processor via the RESTful API """
  in_vcon = make_1_dialog_vcon()

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    # Put the vCon in the DB
    set_response = client.post("/vcon", json = in_vcon.dumpd())
    assert(set_response.status_code == 204)

    parameters = {
        "commit_changes": False,
        "return_whole_vcon": False
      }

    jinja_options = {
        "template": "UUID: {{ vcons[0].uuid }}, Dialogs: {{ vcons[0].dialog | length }}"
      }

    post_response = client.post("/process/{}/jinja_report".format(UUID),
        params = parameters,
        json = jinja_options
      )
    assert(post_response.status_code == 200)
    proc_io_out = post_response.json()

    assert("report_output" in proc_io_out["parameters"])
    result = proc_io_out["parameters"]["report_output"]
    assert(UUID in result)
    assert("Dialogs: 1" in result)

    # Cleanup
    delete_response = client.delete("/vcon/{}".format(UUID))
    assert(delete_response.status_code == 204)


# ============================================================
#  Test: RESTful API with analysis output
# ============================================================
@pytest.mark.asyncio
async def test_jinja_report_proc_api_with_analysis():
  """ Test jinja_report processor via RESTful API with analysis object """
  in_vcon = make_1_dialog_vcon()

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    # Put the vCon in the DB
    set_response = client.post("/vcon", json = in_vcon.dumpd())
    assert(set_response.status_code == 204)

    parameters = {
        "commit_changes": False,
        "return_whole_vcon": True
      }

    jinja_options = {
        "template": "Report for {{ vcons[0].uuid }}",
        "analysis_type": "report",
        "analysis_vendor": "jinja",
        "analysis_dialog_index": 0
      }

    post_response = client.post("/process/{}/jinja_report".format(UUID),
        params = parameters,
        json = jinja_options
      )
    assert(post_response.status_code == 200)
    proc_io_out = post_response.json()

    # Check parameter output
    assert("report_output" in proc_io_out["parameters"])

    # Check vCon was modified
    assert(proc_io_out["vcons_modified"][0])

    # Check analysis was added to the vCon
    assert(len(proc_io_out["vcons"]) == 1)
    out_vcon_dict = proc_io_out["vcons"][0]
    assert(out_vcon_dict["analysis"] is not None)
    assert(len(out_vcon_dict["analysis"]) == 1)
    analysis = out_vcon_dict["analysis"][0]
    assert(analysis["type"] == "report")
    assert(analysis["vendor"] == "jinja")
    assert(analysis["encoding"] == "none")
    assert(analysis["dialog"] == 0)
    assert(UUID in analysis["body"])

    # Cleanup
    delete_response = client.delete("/vcon/{}".format(UUID))
    assert(delete_response.status_code == 204)


# ============================================================
#  Test: RESTful API - /processIO/jinja_report
# ============================================================
@pytest.mark.asyncio
async def test_jinja_report_processio_api():
  """ Test jinja_report processor via the processIO RESTful API """
  in_vcon = make_1_dialog_vcon()

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    parameters = {
        "commit_changes": False
      }

    request_body = {
        "processor_io": {
            "vcons": [in_vcon.dumpd()],
            "parameters": {
                "prior_step_value": "hello"
              }
          },
        "processor_options": {
            "template": "UUID: {{ vcons[0].uuid }}, Prior: {{ parameters.prior_step_value }}"
          }
      }

    post_response = client.post("/processIO/jinja_report",
        params = parameters,
        json = request_body
      )
    assert(post_response.status_code == 200)
    proc_io_out = post_response.json()

    assert("report_output" in proc_io_out["parameters"])
    result = proc_io_out["parameters"]["report_output"]
    assert(UUID in result)
    assert("Prior: hello" in result)

# ============================================================
#  Test: RESTful API - /processIO/jinja_report format_options
#  with missing parameter
# ============================================================
@pytest.mark.asyncio
async def test_jinja_report_processio_api_missing_format_param():
  """ Test that format_options referencing a nonexistent parameter returns 500 """
  in_vcon = make_1_dialog_vcon()

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    parameters = {
        "commit_changes": False
      }

    request_body = {
        "processor_io": {
            "vcons": [in_vcon.dumpd()],
            "parameters": {}
          },
        "processor_options": {
            "template": "{{ vcons[0].uuid }}",
            "format_options": {
                "output_parameter_name": "{nonexistent_param}"
              }
          }
      }

    post_response = client.post("/processIO/jinja_report",
        params = parameters,
        json = request_body
      )
    assert(post_response.status_code == 500)
    error_body = post_response.json()
    print(f"paramter not found respoinse: {error_body}")
    assert("detail" in error_body or "error" in error_body or "traceback" in error_body)
    # Verify the error message references the missing parameter
    error_text = str(error_body)
    assert("nonexistent_param" in error_text or "ParameterNotFound" in error_text)

# ============================================================
#  Test: RESTful API - /process/{vcon_uuid}/jinja_report
#  format_options with missing parameter
# ============================================================
@pytest.mark.asyncio
async def test_jinja_report_proc_api_missing_format_param():
  """ Test that format_options referencing a nonexistent parameter returns 500 """
  in_vcon = make_1_dialog_vcon()

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:

    # Put the vCon in the DB
    set_response = client.post("/vcon", json = in_vcon.dumpd())
    assert(set_response.status_code == 204)

    parameters = {
        "commit_changes": False,
        "return_whole_vcon": False
      }

    jinja_options = {
        "template": "{{ vcons[0].uuid }}",
        "format_options": {
            "output_parameter_name": "{nonexistent_param}"
          }
      }

    post_response = client.post("/process/{}/jinja_report".format(UUID),
        params = parameters,
        json = jinja_options
      )
    assert(post_response.status_code == 500)
    error_body = post_response.json()
    error_text = str(error_body)
    assert("nonexistent_param" in error_text or "ParameterNotFound" in error_text)

    # Cleanup
    delete_response = client.delete("/vcon/{}".format(UUID))
    assert(delete_response.status_code == 204)

