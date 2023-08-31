""" Common Vcon unit test fixtures, data and funcitons """
import pytest
import vcon


call_data = {
      "epoch" : "1652552179",
      "destination" : "2117",
      "source" : "+19144345359",
      "rfc2822" : "Sat, 14 May 2022 18:16:19 -0000",
      "rfc3339" : "2022-05-14T18:16:19.000+00:00",
      "file_extension" : "WAV",
      "duration" : 94.84,
      "channels" : 1
}


#empty_count = 0
@pytest.fixture(scope="function")
def empty_vcon() -> vcon.Vcon:
  """ construct vCon with no data """
  #empty_count += 1
  #print("empty invoked: {}".format(empty_count))
  a_vcon = vcon.Vcon()
  #print("empty_vcon invoked:")
  #pprint.pprint(vCon._vcon_dict)
  return(a_vcon)


@pytest.fixture(scope="function")
def two_party_tel_vcon(empty_vcon : vcon.Vcon) -> vcon.Vcon:
  """ construct vCon with two tel URL """
  a_vcon = empty_vcon
  first_party = a_vcon.set_party_parameter("tel", call_data['source'])
  assert(first_party == 0)
  second_party = a_vcon.set_party_parameter("tel", call_data['destination'])
  assert(second_party == 1)
  return(a_vcon)

