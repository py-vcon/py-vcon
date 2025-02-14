# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" Unit tests for text_pii_redactor processor """
import pydantic
import pytest
import pytest_asyncio
import fastapi.testclient
import vcon
import vcon.pydantic_utils
import py_vcon_server
from py_vcon_server.settings import VCON_STORAGE_URL
from common_setup import UUID

TRANSCRIBED_VCON_FILE = "../tests/example_deepgram_external_dialog.vcon"

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

@pytest.mark.asyncio
async def test_text_pii_redactor_processor() -> None:
  # VCon with transcription should have redacted dialog
  input_transcribed_vcon = vcon.Vcon()
  input_transcribed_vcon.load(TRANSCRIBED_VCON_FILE)
  assert(len(input_transcribed_vcon.analysis) == 1)
  assert(input_transcribed_vcon.analysis[0]["vendor"] == "deepgram")

  proc_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
  await proc_input.add_vcon(input_transcribed_vcon, "fake_lock", False) # read/write
  assert(len(proc_input._vcons) == 1)

  text_redact_proc_inst = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance("text_pii_redactor")
  text_redact_options = {}

  try:
    proc_output = await text_redact_proc_inst.process(proc_input, text_redact_options)
    raise Exception("Should have rasied excepiotn as options parameters jq_redaction_query and redaction_type_label not set")
  except vcon.pydantic_utils.ValidationErrorType as option_error:
    # expected
    pass

  redaction_query = """. + {parties: [.parties[] | delpaths([["foo"], ["tel"]])]} +\
      {dialog: [.dialog[] | delpaths([["body"], ["url"]])]} + {analysis: [.analysis[1]]}"""

  redaction_type = "PII Redaction"
  text_redact_options = {
      "uuid_domain": "py-vcon.org",
      "jq_redaction_query": redaction_query,
      "redaction_type_label": redaction_type
    }

  # Make sure we did not corrupt the input
  assert(proc_input.num_vcons() == 1)
  in_unredacted_vcon = await proc_input.get_vcon(0)
  assert(len(in_unredacted_vcon.analysis) == 1)
  assert(in_unredacted_vcon.analysis[0]["vendor"] == "deepgram")

  proc_output = await text_redact_proc_inst.process(proc_input, text_redact_options)

  assert(proc_output.num_vcons() == 2)
  out_unredacted_vcon = await proc_output.get_vcon(0)
  out_redacted_vcon = await proc_output.get_vcon(1)
  # the redacted transcript should NOT be added to the original vCon by default
  assert(len(out_unredacted_vcon.analysis) == 1)
  assert(out_unredacted_vcon.analysis[0]["vendor"] == "deepgram")
  assert(out_unredacted_vcon.analysis[0]["type"] == "transcript")
  assert(len(out_redacted_vcon.analysis) == 1)
  assert(out_redacted_vcon.analysis[0]["vendor"] != "deepgram")
  assert(out_redacted_vcon.analysis[0]["type"] == vcon.filter_plugins.impl.redact_pii.ANALYSIS_TYPE)

  assert(len(out_redacted_vcon.dialog) == 1)
  assert(out_redacted_vcon.dialog[0].get("body", None) is None)
  assert(out_redacted_vcon.dialog[0].get("url", None) is None)

  assert(out_redacted_vcon.redacted["uuid"] == out_unredacted_vcon.uuid)
  assert(out_redacted_vcon.redacted["type"] == redaction_type)


@pytest.mark.asyncio
async def test_text_pii_redactor_processor_api() -> None:
  # VCon with transcription should have redacted dialog
  input_transcribed_vcon = vcon.Vcon()
  input_transcribed_vcon.load(TRANSCRIBED_VCON_FILE)
  # Hack a known UUID so that we do not poluted the DB
  input_transcribed_vcon._vcon_dict["uuid"] = UUID
  assert(len(input_transcribed_vcon.analysis) == 1)
  assert(input_transcribed_vcon.analysis[0]["vendor"] == "deepgram")
  assert(input_transcribed_vcon.uuid == UUID)
  #validated_vcon = py_vcon_server.processor.VconUnsignedObject(**input_transcribed_vcon.dumpd())
  #assert(validated_vcon.uuid == UUID)

  with fastapi.testclient.TestClient(py_vcon_server.restapi) as client:
    # Put the vCon in the DB
    set_response = client.post("/vcon", json = input_transcribed_vcon.dumpd())
    if(set_response.status_code != 204):
      print(set_response.json())
    assert(set_response.status_code == 204)

    parameters = {
        "commit_changes": True,
        "return_whole_vcon": True
      }

    redaction_query = """. + {parties: [.parties[] | delpaths([["foo"], ["tel"]])]} +\
      {dialog: [.dialog[] | delpaths([["body"], ["url"]])]} + {analysis: [.analysis[1]]}"""

    redaction_type = "PII Redaction"
    redact_options = {
        "uuid_domain": "py-vcon.org",
        "jq_redaction_query": redaction_query,
        "redaction_type_label": redaction_type
      }


    post_response = client.post("/process/{}/text_pii_redactor".format(UUID),
        params = parameters,
        json = redact_options
      )
    print("UUID: {}".format(UUID))
    processor_out_dict = post_response.json()
    if(post_response.status_code != 200):
      print(processor_out_dict)
    assert(post_response.status_code == 200)
    assert(len(processor_out_dict["vcons"]) == 2)
    assert(not processor_out_dict["vcons_modified"][0])
    assert(processor_out_dict["vcons_modified"][1])

    out_unredacted_vcon = vcon.Vcon()
    out_unredacted_vcon.loadd(processor_out_dict["vcons"][0])
    out_redacted_vcon = vcon.Vcon()
    out_redacted_vcon.loadd(processor_out_dict["vcons"][1])
    # the redacted transcript should NOT be added to the original vCon by default
    assert(len(out_unredacted_vcon.analysis) == 1)
    assert(out_unredacted_vcon.analysis[0]["vendor"] == "deepgram")
    assert(out_unredacted_vcon.analysis[0]["type"] == "transcript")
    assert(len(out_redacted_vcon.analysis) == 1)
    assert(out_redacted_vcon.analysis[0]["vendor"] != "deepgram")
    assert(out_redacted_vcon.analysis[0]["type"] == vcon.filter_plugins.impl.redact_pii.ANALYSIS_TYPE)

    assert(len(out_redacted_vcon.dialog) == 1)
    assert(out_redacted_vcon.dialog[0].get("body", None) is None)
    assert(out_redacted_vcon.dialog[0].get("url", None) is None)

    assert(out_redacted_vcon.redacted["uuid"] == out_unredacted_vcon.uuid)
    assert(out_redacted_vcon.redacted["type"] == redaction_type)

