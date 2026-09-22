# Copyright (C) 2026 SIP Spectrum, Inc.  All rights reserved.
""" Unit test for Vcon.jsonpath method (RFC 9535) """
import pytest
import jsonpath_rfc9535
import vcon
from tests.common_utils import call_data , empty_vcon, two_party_tel_vcon

CA_CERT = "certs/fake_ca_root.crt"
GROUP_CERT = "certs/fake_grp.crt"
GROUP_PRIVATE_KEY = "certs/fake_grp.key"
DIVISION_CERT = "certs/fake_div.crt"


def test_jsonpath_str(two_party_tel_vcon):
  a_vcon = two_party_tel_vcon
  a_vcon.set_uuid("py-vcon.org")

  assert(a_vcon.jsonpath("$.parties[0].tel") == [call_data['source']])
  assert(a_vcon.jsonpath("$.parties[*].tel") == [call_data['source'], call_data['destination']])
  assert(a_vcon.jsonpath("$..tel") == [call_data['source'], call_data['destination']])
  # filter selector
  assert(a_vcon.jsonpath('$.parties[?@.tel == "{}"].tel'.format(call_data['destination'])) ==
      [call_data['destination']])
  # a member that is not present selects nothing
  assert(a_vcon.jsonpath("$.subject") == [])
  assert(isinstance(a_vcon.jsonpath("$.uuid")[0], str))


def test_jsonpath_dict(two_party_tel_vcon):
  a_vcon = two_party_tel_vcon
  a_vcon.set_uuid("py-vcon.org")

  result_dict = a_vcon.jsonpath({
      "party_1_tel": "$.parties[0].tel",
      "tels": "$..tel",
      "subject": "$.subject"
    })

  assert(result_dict["party_1_tel"] == [call_data['source']])
  assert(result_dict["tels"] == [call_data['source'], call_data['destination']])
  assert(result_dict["subject"] == [])


def test_jsonpath_syntax_error(two_party_tel_vcon):
  a_vcon = two_party_tel_vcon
  a_vcon.set_uuid("py-vcon.org")

  # SQL/JSON path syntax is not RFC 9535
  with pytest.raises(jsonpath_rfc9535.JSONPathSyntaxError):
    a_vcon.jsonpath('$.parties[*] ? (@.tel == "1234")')


def test_jsonpath_signed(two_party_tel_vcon):
  """ A signed vCon is queried on its content, like attribute access, not its JWS form """
  a_vcon = two_party_tel_vcon
  a_vcon.set_uuid("py-vcon.org")
  a_vcon.sign(GROUP_PRIVATE_KEY, [GROUP_CERT, DIVISION_CERT, CA_CERT])

  assert(a_vcon.jsonpath("$.parties[0].tel") == [call_data['source']])
  assert(a_vcon.jsonpath("$.parties[0].tel") == [a_vcon.parties[0]["tel"]])
  # the JWS members are not part of the content
  assert(a_vcon.jsonpath("$.signatures") == [])

  # read back, a signed vCon cannot be queried until it is verified
  unverified = vcon.Vcon()
  unverified.loadd(a_vcon.dumpd())
  with pytest.raises(vcon.InvalidVconState):
    unverified.jsonpath("$.parties")
  unverified.verify([CA_CERT])
  assert(unverified.jsonpath("$.parties[0].tel") == [call_data['source']])

  # an encrypted vCon cannot be queried at all
  a_vcon.encrypt(GROUP_CERT)
  with pytest.raises(vcon.InvalidVconState):
    a_vcon.jsonpath("$.parties")
