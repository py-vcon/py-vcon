# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" Unit test for the sample redaction filter plugin """

import json
import pytest
import vcon
# Register and load the redaction filter plugin

TRANSCRIBED_VCON_FILE       = "tests/example_deepgram_external_dialog.vcon"
VCON_WITHOUT_TRANSCRIPTION  = "examples/test.vcon"

pytest_plugins = ('pytest_asyncio')

@pytest.mark.asyncio
async def test_pii_redaction():
  redaction_plugin = vcon.filter_plugins.FilterPluginRegistry.get("redact_pii")
  init_options = {}
  options = {}
  assert(redaction_plugin is not None)
  assert(redaction_plugin.import_plugin(init_options))

  # VCon with transcription should have redacted dialog
  input_transcribed_vcon = vcon.Vcon()
  input_transcribed_vcon.load(TRANSCRIBED_VCON_FILE)
  original_text = " ".join([text_dict["text"] for text_dict in await input_transcribed_vcon.get_dialog_text(0, True, False)])
  out_redacted_vcon = await input_transcribed_vcon.redact_pii(options)
  out_redacted_json = json.dumps(out_redacted_vcon.dumps(), indent=4)
  assert(vcon.filter_plugins.impl.redact_pii.ANALYSIS_TYPE in out_redacted_json)

  # each redacted string is replaced by the marker of its Redacted_string
  redacted_analysis = [analysis for analysis in out_redacted_vcon.analysis
    if(analysis["type"] == vcon.filter_plugins.impl.redact_pii.ANALYSIS_TYPE)]
  assert(len(redacted_analysis) == 1)
  redacted_text = " ".join([text_dict["text"] for text_dict in redacted_analysis[0]["body"]])
  assert("{{" not in redacted_text)
  assert(len(out_redacted_vcon.redacted_strings) > 0)
  for redacted_string in out_redacted_vcon.redacted_strings:
    assert(redacted_string["marker"] == "__REDACTED_REF_{}__".format(redacted_string["ref"]))
    assert(redacted_string["marker"] in redacted_text)
    assert(redacted_string["orig"] not in ("", None))
    assert(redacted_string["type"] not in ("", None))
    # the labeler marks spans, not words: the same word may be left elsewhere
    assert(redacted_string["orig"] in original_text)

  # Redact is a no-op if the Vcon does not contain transcription
  test_vcon = vcon.Vcon()
  test_vcon.load(VCON_WITHOUT_TRANSCRIPTION)
  #out_vcon = await test_vcon.redact(options)
  #out_json = json.dumps(out_vcon.dumps(), indent=4)
  #assert(vcon.filter_plugins.impl.redact_pii.ANALYSIS_TYPE not in out_json)

  out_redacted_vcon.dump("pii_redacted.vcon")

  # Save the redacted output
  #with open("tests/redacted_vcon.json", "w") as output_file:
  #  output_file.write(out_redacted_json)

  vcon.filter_plugins.FilterPluginRegistry.shutdown_plugins()

