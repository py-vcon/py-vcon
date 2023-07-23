""" Common test data and tools for conserver unit tests """
import pytest
import vcon

UUID = "01855517-ac4e-8edf-84fd-77776666acbe"

@pytest.fixture(scope="function")
async def make_2_party_tel_vcon() -> vcon.Vcon:
  vCon = vcon.Vcon()
  # Hack a known UUID so that we do not poluted the DB
  vCon._vcon_dict["uuid"] = UUID
  party_1_index = vCon.set_party_parameter("tel", "1234")
  assert(party_1_index == 0)
  party_2_index = vCon.set_party_parameter("tel", "5678")
  assert(party_2_index == 1)

  return(vCon)

