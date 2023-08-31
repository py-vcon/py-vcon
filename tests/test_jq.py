""" Unit test for Vcon.jq method """
from tests.common_utils import call_data , empty_vcon, two_party_tel_vcon

def test_jq_str(two_party_tel_vcon):
  a_vcon = two_party_tel_vcon
  a_vcon.set_uuid("py-vcon.org")

  assert(a_vcon.jq(".parties[0].tel")[0] == call_data['source'])
  assert(a_vcon.jq(".parties | length")[0] == 2)
  assert(a_vcon.jq(".analysis | length")[0] == 0)
  assert(a_vcon.jq(".dialog | length")[0] == 0)
  assert(a_vcon.jq(".attachment | length")[0] == 0)
  assert(a_vcon.jq(".group | length")[0] == 0)
  assert(a_vcon.jq(".subject")[0] is None)
  assert(len(a_vcon.jq(".uuid")[0]) > 16)
  assert(isinstance(a_vcon.jq(".uuid")[0], str))


def test_jq_dict(two_party_tel_vcon):
  a_vcon = two_party_tel_vcon
  a_vcon.set_uuid("py-vcon.org")

  query_dict = {
    "party_1_tel": ".parties[0].tel",
    "num_parties": ".parties | length",
    "num_analysis": ".analysis | length",
    "subject": ".subject"
    }

  result_dict = a_vcon.jq(query_dict)

  assert(result_dict["party_1_tel"] == call_data['source'])
  assert(result_dict["num_parties"] == 2)
  assert(result_dict["num_analysis"] == 0)
  assert(result_dict["subject"] is None)

