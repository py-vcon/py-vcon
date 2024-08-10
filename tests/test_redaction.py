""" Unit test for the sample redaction filter plugin """

import sys
import vcon
import pytest
import json
import asyncio

# This test requires ML libraries to be installed manually. 
# Skip when running the unit test suite.
pytest.importorskip("pandas")

# Register and load the redaction filter plugin
import examples.redact_vcon
 
TRANSCRIBED_VCON_FILE       = "tests/example_deepgram_external_dialog.vcon"
VCON_WITHOUT_TRANSCRIPTION  = "examples/test.vcon"

pytest_plugins = ('pytest_asyncio')

@pytest.mark.asyncio
async def test_redaction():
  redaction_plugin = vcon.filter_plugins.FilterPluginRegistry.get("redact")
  init_options = examples.redact_vcon.RedactInitOptions()
  options = examples.redact_vcon.RedactOptions()
  assert(redaction_plugin is not None)
  assert(redaction_plugin.import_plugin(init_options))
  
  # VCon with transcription should have redacted dialog
  input_transcribed_vcon = vcon.Vcon()
  input_transcribed_vcon.load(TRANSCRIBED_VCON_FILE)
  out_redacted_vcon = await input_transcribed_vcon.redact(options)
  out_redacted_json = json.dumps(out_redacted_vcon.dumps(), indent=4)
  assert(examples.redact_vcon.ANALYSIS_TYPE in out_redacted_json)

  # Redact is a no-op if the Vcon does not contain transcription
  test_vcon = vcon.Vcon()
  test_vcon.load(VCON_WITHOUT_TRANSCRIPTION)
  #out_vcon = await test_vcon.redact(options)
  #out_json = json.dumps(out_vcon.dumps(), indent=4)
  #assert(examples.redact_vcon.ANALYSIS_TYPE not in out_json)

  print(out_redacted_json)

  # Save the redacted output
  #with open("tests/redacted_vcon.json", "w") as output_file:
  #  output_file.write(out_redacted_json)
    
  vcon.filter_plugins.FilterPluginRegistry.shutdown_plugins()

