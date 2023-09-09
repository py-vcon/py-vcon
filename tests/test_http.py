""" Unit test for HTTP depdendent Vcon functionality (e.g. get and post) """

import httpretty
import vcon
from tests.common_utils import empty_vcon, two_party_tel_vcon, call_data

HTTP_HOST = "example.com"
HTTP_PORT = 8000
UUID = "test_fake_uuid"

@httpretty.activate(verbose = True, allow_net_connect = False)
def test_vcon_get(two_party_tel_vcon):
  # Hack UUID for testing
  two_party_tel_vcon._vcon_dict[vcon.Vcon.UUID] = UUID

  httpretty.register_uri(
    httpretty.GET,
    "http://{host}:{port}{path}".format(
      host = HTTP_HOST,
      port = HTTP_PORT,
      path = "/vcon/{}".format(UUID)
      ),
    body = two_party_tel_vcon.dumps()
    )

  got_vcon = vcon.Vcon()
  got_vcon.get(
    uuid = UUID,
    host = HTTP_HOST,
    port = HTTP_PORT
    )

  assert(httpretty.latest_requests()[0].headers["accept"] == vcon.Vcon.MIMETYPE_JSON)
  assert(len(got_vcon.parties) == 2)
  assert(got_vcon.parties[0]['tel'] == call_data['source'])
  assert(got_vcon.parties[1]['tel'] == call_data['destination'])
  assert(got_vcon.uuid == UUID)


@httpretty.activate(verbose = True, allow_net_connect = False)
def test_vcon_post(two_party_tel_vcon):
  # Hack UUID for testing
  two_party_tel_vcon._vcon_dict[vcon.Vcon.UUID] = UUID

  httpretty.register_uri(
    httpretty.POST,
    "http://{host}:{port}/vcon".format(
      host = HTTP_HOST,
      port = HTTP_PORT
      ),
      status = 200
      )

  two_party_tel_vcon.post(
    host = HTTP_HOST,
    port = HTTP_PORT
    )

  posted_vcon = vcon.Vcon()
  assert(httpretty.latest_requests()[0].headers["Content-Type"] == vcon.Vcon.MIMETYPE_JSON)
  print("type: " + str(type(httpretty.latest_requests()[0].body)))
  print(httpretty.latest_requests()[0].body)
  posted_vcon.loads(httpretty.latest_requests()[0].body)

  assert(len(posted_vcon.parties) == 2)
  assert(posted_vcon.parties[0]['tel'] == call_data['source'])
  assert(posted_vcon.parties[1]['tel'] == call_data['destination'])
  assert(posted_vcon.uuid == UUID)

