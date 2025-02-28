# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" Common test data and tools for conserver unit tests """

import os
import datetime
import copy
import pytest
import vcon

UUID = "01855517-test-fake-uuid-77776666acbe"

@pytest.fixture(scope="function")
def make_2_party_tel_vcon() -> vcon.Vcon:
  """ test fixture to create a simple **Vcon** with two parties """
  vCon = vcon.Vcon()
  # Hack a known UUID so that we do not poluted the DB
  vCon._vcon_dict["uuid"] = UUID
  party_1_index = vCon.set_party_parameter("tel", "1234")
  assert(party_1_index == 0)
  party_2_index = vCon.set_party_parameter("tel", "5678")
  assert(party_2_index == 1)

  return(vCon)


@pytest.fixture(scope="function")
def make_inline_audio_vcon(make_2_party_tel_vcon: vcon.Vcon) -> vcon.Vcon:
  """ test figure to create a Vcon with a very small inline audio dialog """
  vCon = copy.deepcopy(make_2_party_tel_vcon)

  file_path = "tests/hello.wav"
  file_content = b""
  with open(file_path, "rb") as file_handle:
    file_content = file_handle.read()
    print("body length: {}".format(len(file_content)))
    assert(len(file_content) > 10000)

  vCon.add_dialog_inline_recording(file_content,
  datetime.datetime.utcnow(),
  0, # duration TODO
  [0,1],
  vcon.Vcon.MEDIATYPE_AUDIO_WAV,
  os.path.basename(file_path))

  save_as = "tests/hello.vcon"
  if( not os.path.isfile(save_as)):
    vCon.dump(save_as)

  return(vCon)
