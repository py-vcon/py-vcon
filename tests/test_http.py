# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" Unit test for HTTP depdendent Vcon functionality (e.g. get and post) """

#import httpretty
import vcon
from tests.common_utils import empty_vcon, two_party_tel_vcon, call_data
import pytest
import pytest_httpserver

HTTP_HOST = "example.com"
HTTP_PORT = 8000
UUID = "test_fake_uuid"


@pytest.mark.asyncio
#@httpretty.activate(verbose = True, allow_net_connect = False)
async def test_vcon_get(two_party_tel_vcon, httpserver: pytest_httpserver.HTTPServer):
  # Hack UUID for testing
  two_party_tel_vcon._vcon_dict[vcon.Vcon.UUID] = UUID

  headers = {"accept": vcon.Vcon.MEDIATYPE_JSON}
  httpserver.expect_request(
      "/vcon/{}".format(UUID),
      method = "GET",
      headers = headers
    ).respond_with_json(two_party_tel_vcon.dumpd())
  # httpretty.register_uri(
  #   httpretty.GET,
  #   "http://{host}:{port}{path}".format(
  #     host = HTTP_HOST,
  #     port = HTTP_PORT,
  #     path = "/vcon/{}".format(UUID)
  #     ),
  #   body = two_party_tel_vcon.dumps()
  #   )

  got_vcon = vcon.Vcon()
  await got_vcon.get(
    uuid = UUID,
    host = httpserver.host,
    port = httpserver.port
    )

  #assert(httpretty.latest_requests()[0].headers["accept"] == vcon.Vcon.MEDIATYPE_JSON)
  assert(len(got_vcon.parties) == 2)
  assert(got_vcon.parties[0]['tel'] == call_data['source'])
  assert(got_vcon.parties[1]['tel'] == call_data['destination'])
  assert(got_vcon.uuid == UUID)


@pytest.mark.asyncio
#@httpretty.activate(verbose = True, allow_net_connect = False)
async def test_vcon_post(two_party_tel_vcon, httpserver: pytest_httpserver.HTTPServer):
  # Hack UUID for testing
  two_party_tel_vcon._vcon_dict[vcon.Vcon.UUID] = UUID

  headers = {"Content-Type": vcon.Vcon.MEDIATYPE_JSON}
  vcon_dict_copy = two_party_tel_vcon.dumpd().copy()
  # force request body not to match
  # vcon_dict_copy["a"] = 2

  httpserver.expect_request(
      "/vcon",
      method = "POST",
      headers = headers,
      json = vcon_dict_copy
    ).respond_with_json(two_party_tel_vcon.dumpd())
  # httpretty.register_uri(
  #   httpretty.POST,
  #   "http://{host}:{port}/vcon".format(
  #     host = HTTP_HOST,
  #     port = HTTP_PORT
  #     ),
  #     status = 200
  #     )

  try:
    await two_party_tel_vcon.post(
      host = httpserver.host,
      port = httpserver.port
      )
  except Exception as e:
    print(httpserver.check_assertions())
    raise e

  #posted_vcon = vcon.Vcon()
  # httpserver tests all of this:
  #assert(httpretty.latest_requests()[0].headers["Content-Type"] == vcon.Vcon.MEDIATYPE_JSON)
  #print("type: " + str(type(httpretty.latest_requests()[0].body)))
  #print(httpretty.latest_requests()[0].body)
  #posted_vcon.loads(httpretty.latest_requests()[0].body)
  # assert(len(posted_vcon.parties) == 2)
  # assert(posted_vcon.parties[0]['tel'] == call_data['source'])
  # assert(posted_vcon.parties[1]['tel'] == call_data['destination'])
  # assert(posted_vcon.uuid == UUID)

