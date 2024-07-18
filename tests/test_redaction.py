""" Redactor transcription plugin unit test """

import os
import datetime
import json
import vcon
import vcon.filter_plugins
import pytest


def test_redactor_options():
  import vcon.filter_plugins.impl.redactor
  init_options = vcon.filter_plugins.impl.Redactor.RedactorInitOptions()
  assert(init_options.redaction_key == "")

  init_options = vcon.filter_plugins.impl.Redactor.RedactorInitOptions(**{})
  assert(init_options.redaction_key == "")


@pytest.mark.asyncio
async def test_redact_inline_dialog():
  """ Test Redactor plugin with an inline audio dialog """
  in_vcon = vcon.Vcon()


  # Register the Redactor filter plugin
  init_options = {"Redactor_key": "123456"}

  with open("examples/test.vcon", "r") as vcon_file:
    in_vcon.load(vcon_file)

  assert(len(in_vcon.dialog) > 0)

  analysis_count = len(in_vcon.analysis)
  out_vcon = await in_vcon.Redactor({})
  # Test that we still have a valid serializable Vcon
  out_vcon_json = out_vcon.dumps()
  json.loads(out_vcon_json )

  text_list = await out_vcon.get_dialog_text(0)
  print("text: {}".format(json.dumps(text_list, indent = 2)))
  assert(52 <= len(text_list) <= 62)


@pytest.mark.asyncio
async def test_Redactor_no_dialog():
  """ Test Redactor plugin on Vcon with no dialogs """
  in_vcon = vcon.Vcon()
  vcon_json = """
  {
    "vcon": "0.0.1",
    "uuid": "my_fake_uuid",
    "created_at": "2023-08-18T07:14:45.894+00:00",
    "parties": [
      {
        "tel": "+1 123 456 7890"
      }
    ]
  }
  """
  in_vcon.loads(vcon_json)

  options = vcon.filter_plugins.TranscribeOptions(
    )

  assert(in_vcon.dialog is None)
  out_vcon = await in_vcon.Redactor(options)
  assert(out_vcon.analysis is None)
