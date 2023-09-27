"""
unit tests for the vcon command line script
"""

import sys
import io
import os.path
#import httpretty
import pytest_httpserver
from tests.common_utils import empty_vcon, two_party_tel_vcon, call_data
import pytest

IN_VCON_JSON = """
{"uuid": "0183878b-dacf-8e27-973a-91e26eb8001b", "vcon": "0.0.1", "attachments": [], "parties": [{"name": "Alice", "tel": "+12345678901"}, {"name": "Bob", "tel": "+19876543210"}]}
"""

WAVE_FILE_NAME = "examples/agent_sample.wav"
WAVE_FILE_URL = "https://github.com/vcon-dev/vcon/blob/main/examples/agent_sample.wav?raw=true"
WAVE_FILE_SIZE = os.path.getsize(WAVE_FILE_NAME)
VCON_WITH_DIALOG_FILE_NAME = "py_vcon_server/tests/hello.vcon"
SMTP_MESSAGE_W_IMAGE_FILE_NAME = "tests/email_acct_prob_bob_image.txt"
GOOGLE_MEET_RECORDING = "tests/google_meet/test meeting (2023-09-06 20:27 GMT-4) (18af10d0)"
ZOOM_MEETING_RECORDING = "tests/zoom/Zoom recording to computer 09 18 23"


@pytest.mark.asyncio
async def test_vcon_new(capsys):
  """ test vcon -n """
  # Importing vcon here so that we catch any junk stdout which will break ths CLI
  import vcon.cli
  # Note: can provide stdin using:
  # sys.stdin = io.StringIO('{"vcon": "0.0.1", "parties": [], "dialog": [], "analysis": [], "attachments": [], "uuid": "0183866c-df92-89ab-973a-91e26eb8001b"}')
  await vcon.cli.main(["-n"])

  new_vcon_json, error = capsys.readouterr()
  # As we captured the stderr, we need to re-emmit it for unit test feedback
  print("stderr: {}".format(error), file=sys.stderr)

  new_vcon = vcon.Vcon()
  try:
    new_vcon.loads(new_vcon_json)
  except Exception as e:
    print("Most likely an error has occurred as something has written to stdout, causing junk to be include in the JSON also on stdout")
    print("*****\n{}\n*****".format(new_vcon_json))
    raise e

  assert(len(new_vcon.uuid) == 36)
  assert(new_vcon.vcon == "0.0.1")


@pytest.mark.asyncio
async def test_filter_plugin_register(capsys):
  """ Test cases for the register filter plugin CLI option -r """
  # Importing vcon here so that we catch any junk stdout which will break ths CLI
  import vcon.cli
  command_args = "-n -r foo2 doesnotexist.foo Foo '{}' filter foo2".split()
  # Filter registered, but module not found
  # expect vcon.filter_plugins.FilterPluginModuleNotFound
  assert(len(command_args) == 8)

  try:
    await vcon.cli.main(command_args)
    raise Exception("Expected this to throw vcon.filter_plugins.FilterPluginModuleNotFound as the module name is wrong")

  # TODO: don't know why gets FilterPluginNotRegistered

  except vcon.filter_plugins.FilterPluginModuleNotFound as no_mod_error:
    print("Got {}".format(no_mod_error))

  command_args = "-n -r foo2 tests.foo Foo '{}' filter foo2".split()
  # Filter register and loaded, but not completely implemented
  # expect vcon.filter_plugins.FilterPluginNotImplemented
  assert(len(command_args) == 8)

  try:
    await vcon.cli.main(command_args)
    raise Exception("Expected this to throw vcon.filter_plugins.FilterPluginNotImplemented as the module name is wrong")

  except vcon.filter_plugins.FilterPluginNotImplemented as mod_not_impl_error:
    print("Got {}".format(mod_not_impl_error))


@pytest.mark.asyncio
async def test_filter(capsys):
  """ Test cases for the filter command to run filer plugins """
  # Importing vcon here so that we catch any junk stdout which will break ths CLI
  import vcon.cli
  command_args = "-i {} filter transcribe -fo '{{\"model_size\":\"base\"}}'".format(VCON_WITH_DIALOG_FILE_NAME).split()
  assert(len(command_args) == 6)

  await vcon.cli.main(command_args)

  # Get stdout and stderr
  out_vcon_json, error = capsys.readouterr()

  # As we captured the stderr, we need to re-emmit it for unit test feedback
  print("stderr: {}".format(error), file=sys.stderr)

  # stdout should be a Vcon with analysis added
  out_vcon = vcon.Vcon()
  try:
    out_vcon.loads(out_vcon_json)
  except Exception as e:
    print("output Vcon JSON: {}".format(out_vcon_json[0:300]))
    raise e


  assert(len(out_vcon.dialog) == 1)
  assert(len(out_vcon.analysis) == 3)


@pytest.mark.asyncio
async def test_ext_recording(capsys):
  """test vcon add ex-recording"""
  # Importing vcon here so that we catch any junk stdout which will break ths CLI
  import vcon.cli
  date = "2022-06-21T17:53:26.000+00:00"
  parties = "[0,1]"

  # Setup stdin for vcon CLI to read
  sys.stdin = io.StringIO(IN_VCON_JSON)

  # Run the vcon command to ad externally reference recording
  await vcon.cli.main(["add", "ex-recording", WAVE_FILE_NAME, date, parties, WAVE_FILE_URL])

  out_vcon_json, error = capsys.readouterr()
  # As we captured the stderr, we need to re-emmit it for unit test feedback
  print("stderr: {}".format(error), file=sys.stderr)

  out_vcon = vcon.Vcon()
  out_vcon.loads(out_vcon_json)

  assert(len(out_vcon.dialog) == 1)
  #print(json.dumps(json.loads(out_vcon_json), indent=2))
  assert(out_vcon.dialog[0]["type"] ==  "recording")
  assert(out_vcon.dialog[0]["start"] == date)
  assert(out_vcon.dialog[0]["duration"] == 566.496)
  assert(len(out_vcon.parties) == 2)
  assert(out_vcon.dialog[0]["parties"][0] == 0)
  assert(out_vcon.dialog[0]["parties"][1] == 1)
  assert(out_vcon.dialog[0]["url"] == WAVE_FILE_URL)
  assert(out_vcon.dialog[0]["mimetype"] == "audio/x-wav")
  assert(out_vcon.dialog[0]["filename"] == WAVE_FILE_NAME)
  assert(out_vcon.dialog[0]["signature"] == "MfZG-8n8eU5pbMWN9c_SyTyN6l1zwGWNg43h2n-K1q__XVgdxz1X2H3Wbg4I9VZImQKCRqgYHxJjrdIXDAXO8w")
  assert(out_vcon.dialog[0]["alg"] == "SHA-512")
  assert(out_vcon.vcon == "0.0.1")
  assert(out_vcon.uuid == "0183878b-dacf-8e27-973a-91e26eb8001b")

  assert(out_vcon.dialog[0].get("body") is None )
  assert(out_vcon.dialog[0].get("encoding") is None )


@pytest.mark.asyncio
async def test_int_recording(capsys):
  """test vcon add in-recording"""
  # Importing vcon here so that we catch any junk stdout which will break ths CLI
  import vcon.cli
  date = "2022-06-21T17:53:26.000+00:00"
  parties = "[0,1]"

  # Setup stdin for vcon CLI to read
  sys.stdin = io.StringIO(IN_VCON_JSON)

  # Run the vcon command to ad externally reference recording
  await vcon.cli.main(["add", "in-recording", WAVE_FILE_NAME, date, parties])

  out_vcon_json, error = capsys.readouterr()
  # As we captured the stderr, we need to re-emmit it for unit test feedback
  print("stderr: {}".format(error), file=sys.stderr)

  out_vcon = vcon.Vcon()
  out_vcon.loads(out_vcon_json)

  assert(len(out_vcon.dialog) == 1)
  #print(json.dumps(json.loads(out_vcon_json), indent=2))
  assert(out_vcon.dialog[0]["type"] ==  "recording")
  assert(out_vcon.dialog[0]["start"] == date)
  assert(out_vcon.dialog[0]["duration"] == 566.496)
  assert(len(out_vcon.parties) == 2)
  assert(out_vcon.dialog[0]["parties"][0] == 0)
  assert(out_vcon.dialog[0]["parties"][1] == 1)
  assert(out_vcon.dialog[0]["mimetype"] == "audio/x-wav")
  assert(out_vcon.dialog[0]["filename"] == WAVE_FILE_NAME)
  assert(out_vcon.vcon == "0.0.1")
  assert(out_vcon.uuid == "0183878b-dacf-8e27-973a-91e26eb8001b")
# File is base64url encodes so size will be 4/3 larger
  assert(len(out_vcon.dialog[0]["body"]) == WAVE_FILE_SIZE / 3 * 4)
  assert(out_vcon.dialog[0]["encoding"] == "base64url")

  assert(out_vcon.dialog[0].get("url") is None)
  assert(out_vcon.dialog[0].get("signature") is None)
  assert(out_vcon.dialog[0].get("alg") is None)


# vcon add in-email
@pytest.mark.asyncio
async def test_add_email(capsys):
  # Importing vcon here so that we catch any junk stdout which will break ths CLI
  import vcon.cli

  # Run the vcon command to ad externally reference recording
  await vcon.cli.main(["-n", "add", "in-email", SMTP_MESSAGE_W_IMAGE_FILE_NAME])

  out_vcon_json, error = capsys.readouterr()
  # As we captured the stderr, we need to re-emmit it for unit test feedback
  print("stderr: {}".format(error), file=sys.stderr)

  out_vcon = vcon.Vcon()
  out_vcon.loads(out_vcon_json)

  text_body = """
Alice:Please find the image attached.

Regards,Bob

"""
  assert(len(out_vcon.parties) == 2)
  assert(len(out_vcon.parties[0].keys()) == 2)
  assert(len(out_vcon.parties[1].keys()) == 2)
  assert(out_vcon.subject == "Account problem")
  assert(out_vcon.parties[0]["name"] == "Bob")
  assert(out_vcon.parties[1]["name"] == "Alice")
  assert(out_vcon.parties[0]["mailto"] == "b@example.com")
  assert(out_vcon.parties[1]["mailto"] == "a@example.com")
  assert(len(out_vcon.dialog) == 1)
  assert(out_vcon.dialog[0]["type"] == "text")
  assert(out_vcon.dialog[0]["parties"] == [0, 1])
  assert(out_vcon.dialog[0]["mimetype"][:len(vcon.Vcon.MIMETYPE_MULTIPART)] == vcon.Vcon.MIMETYPE_MULTIPART)
  assert(out_vcon.dialog[0]["start"] == "2022-09-23T21:44:25.000+00:00")
  assert(out_vcon.dialog[0]["duration"] == 0)
  assert(len(out_vcon.dialog[0]["body"]) == 2048)
  assert(out_vcon.dialog[0]["encoding"] is None or
    out_vcon.dialog[0]["encoding"].lower() == "none")
  # TODO: fix:
  #assert(len(out_vcon.attachments) == 1)
  #assert(out_vcon.attachments[0]["mimetype"] == vcon.Vcon.MIMETYPE_IMAGE_PNG)
  # TODO: fix:
  # fix:
  #assert(out_vcon.attachments[0]["encoding"] is "base64")
  #assert(len(out_vcon.attachments[0]["body"]) == 402)


@pytest.mark.asyncio
async def test_in_meet(capsys):
  """ Test add of Google Meet recording as recording and text dialogs """
  # Importing vcon here so that we catch any junk stdout which will break ths CLI
  import vcon.cli

  # Run the vcon command to ad externally reference recording
  await vcon.cli.main(["-n", "add", "in-meet", GOOGLE_MEET_RECORDING])

  out_vcon_json, error = capsys.readouterr()
  # As we captured the stderr, we need to re-emmit it for unit test feedback
  print("stderr: {}".format(error), file=sys.stderr)

  out_vcon = vcon.Vcon()
  out_vcon.loads(out_vcon_json)

  assert(len(out_vcon.parties) == 1)
  assert(len(out_vcon.parties[0].keys()) == 1)
  assert(out_vcon.subject == "test meeting")
  assert(out_vcon.parties[0]["name"] == "Daniel Petrie")
  assert(len(out_vcon.dialog) == 4)
  assert(out_vcon.dialog[0]["type"] == "recording")
  assert(out_vcon.dialog[0]["start"] == "2023-09-07T00:27:00.000+00:00")
  assert(out_vcon.dialog[0]["duration"] == 74.791667 )
  assert(out_vcon.dialog[0]["encoding"] == "base64url")
  assert(out_vcon.dialog[0]["mimetype"] == vcon.Vcon.MIMETYPE_VIDEO_MP4)
  assert(out_vcon.dialog[0]["filename"] == os.path.basename(GOOGLE_MEET_RECORDING))
  assert("parties" not in out_vcon.dialog[0])
  assert(out_vcon.dialog[1]["type"] == "text")
  assert(out_vcon.dialog[1]["parties"] == 0)
  assert(out_vcon.dialog[1]["start"] == "2023-09-07T00:27:21.199+00:00")
  assert(out_vcon.dialog[1]["duration"] == 3 )
  assert(out_vcon.dialog[1]["encoding"] == "none")
  assert(out_vcon.dialog[1]["mimetype"] == vcon.Vcon.MIMETYPE_TEXT_PLAIN)
  assert(out_vcon.dialog[1]["body"] == "test message 1")
  assert(out_vcon.dialog[2]["type"] == "text")
  assert(out_vcon.dialog[2]["parties"] == 0)
  assert(out_vcon.dialog[2]["start"] == "2023-09-07T00:27:39.362+00:00")
  assert(out_vcon.dialog[2]["duration"] == 3 )
  assert(out_vcon.dialog[2]["encoding"] == "none")
  assert(out_vcon.dialog[2]["mimetype"] == vcon.Vcon.MIMETYPE_TEXT_PLAIN)
  assert(out_vcon.dialog[2]["body"] == "https://docs.google.com/document/d/1RN6xuZaqz6bpltbc-t-jRMdQ8AyoMsVoskybU/edit")
  assert(out_vcon.dialog[3]["type"] == "text")
  assert(out_vcon.dialog[3]["parties"] == 0)
  assert(out_vcon.dialog[3]["start"] == "2023-09-07T00:27:57.735+00:00")
  assert(out_vcon.dialog[3]["duration"] == 3 )
  assert(out_vcon.dialog[3]["encoding"] == "none")
  assert(out_vcon.dialog[3]["mimetype"] == vcon.Vcon.MIMETYPE_TEXT_PLAIN)
  assert(out_vcon.dialog[3]["body"] == "test message 2")


@pytest.mark.asyncio
async def test_zoom(capsys):
  """ Test add of Google Meet recording as recording and text dialogs """
  # Importing vcon here so that we catch any junk stdout which will break ths CLI
  import vcon.cli

  # Run the vcon command to ad externally reference recording
  await vcon.cli.main(["-n", "add", "in-zoom", ZOOM_MEETING_RECORDING])

  out_vcon_json, error = capsys.readouterr()
  # As we captured the stderr, we need to re-emmit it for unit test feedback
  print("stderr: {}".format(error), file=sys.stderr)

  out_vcon = vcon.Vcon()
  out_vcon.loads(out_vcon_json)

  assert(len(out_vcon.parties) == 2)
  assert(len(out_vcon.parties[0].keys()) == 1)
  assert(out_vcon.parties[0]["name"] == "Daniel Petrie")
  assert(len(out_vcon.dialog) == 7)
  assert(out_vcon.dialog[0]["type"] == "recording")
  assert(out_vcon.dialog[0]["start"] == "2023-09-19T02:37:55.000+00:00")
  assert(out_vcon.dialog[0]["duration"] == 294.56 )
  assert(out_vcon.dialog[0]["encoding"] == "base64url")
  assert(out_vcon.dialog[0]["mimetype"] == vcon.Vcon.MIMETYPE_VIDEO_MP4)
  assert(out_vcon.dialog[0]["filename"] == "video1635030520.mp4")
  #assert(out_vcon.dialog[0]["parties"] == -1)
  assert(out_vcon.dialog[1]["type"] == "text")
  assert(out_vcon.dialog[1]["parties"] == 0)
  assert(out_vcon.dialog[1]["start"] == "2023-09-19T02:35:18.000+00:00")
  assert(out_vcon.dialog[1]["duration"] == 0 )
  assert(out_vcon.dialog[1]["encoding"] == "none")
  assert(out_vcon.dialog[1]["mimetype"] == vcon.Vcon.MIMETYPE_TEXT_PLAIN)
  assert(out_vcon.dialog[1]["body"] == "What is your fvorite color?")
  assert(out_vcon.dialog[2]["type"] == "text")
  assert(out_vcon.dialog[2]["parties"] == 1)
  assert(out_vcon.dialog[2]["start"] == "2023-09-19T02:35:32.000+00:00")
  assert(out_vcon.dialog[2]["duration"] == 0 )
  assert(out_vcon.dialog[2]["encoding"] == "none")
  assert(out_vcon.dialog[2]["mimetype"] == vcon.Vcon.MIMETYPE_TEXT_PLAIN)
  assert(out_vcon.dialog[2]["body"] == "I don’t have one!  I like them all.")
  assert(out_vcon.dialog[3]["type"] == "text")
  assert(out_vcon.dialog[3]["parties"] == 1)
  assert(out_vcon.dialog[3]["start"] == "2023-09-19T02:36:06.000+00:00")
  assert(out_vcon.dialog[3]["duration"] == 0 )
  assert(out_vcon.dialog[3]["encoding"] == "none")
  assert(out_vcon.dialog[3]["mimetype"] == vcon.Vcon.MIMETYPE_TEXT_PLAIN)
  assert(out_vcon.dialog[3]["body"] == "What is your favorite drink to make and to imbibe?")
  assert(out_vcon.dialog[4]["parties"] == 0)
  assert(out_vcon.dialog[4]["start"] == "2023-09-19T02:36:33.000+00:00")
  assert(out_vcon.dialog[4]["body"] == "Switzerland?")
  assert(out_vcon.dialog[5]["parties"] == 0)
  assert(out_vcon.dialog[5]["start"] == "2023-09-19T02:37:01.000+00:00")
  assert(out_vcon.dialog[5]["body"] == "What ever fruit I have on hand.")
  assert(out_vcon.dialog[6]["parties"] == 1)
  assert(out_vcon.dialog[6]["start"] == "2023-09-19T02:37:25.000+00:00")
  assert(out_vcon.dialog[6]["body"] == 'Reacted to "What ever fruit I ha..." with 😃')


@pytest.mark.asyncio
#@httpretty.activate(verbose = True, allow_net_connect = False)
async def test_get(two_party_tel_vcon, capsys, httpserver: pytest_httpserver.HTTPServer):
  """ Test cli get (-g, --get) HTTP get of Vcon """
  # Importing vcon here so that we catch any junk stdout which will break ths CLI
  import vcon.cli

  # host = "example.com"
  host = httpserver.host
  # port = 8000
  port = httpserver.port
  uuid = "test_fake_uuid"

  # Hack UUID for testing
  two_party_tel_vcon._vcon_dict[vcon.Vcon.UUID] = uuid

  headers = {"accept": vcon.Vcon.MIMETYPE_JSON}
  httpserver.expect_request(
      "/vcon/{}".format(uuid),
      method = "GET",
      headers = headers
    ).respond_with_json(two_party_tel_vcon.dumpd())
  # httpretty.register_uri(
  #   httpretty.GET,
  #   "http://{host}:{port}{path}".format(
  #     host = host,
  #     port = port,
  #     path = "/vcon/{}".format(uuid)
  #     ),
  #   body = two_party_tel_vcon.dumps()
  #   )

  # Run the vcon command to get Vcon from HTTP host
  await vcon.cli.main(["-g", host, str(port), uuid])

  out_vcon_json, error = capsys.readouterr()
  # As we captured the stderr, we need to re-emmit it for unit test feedback
  print("stderr: {}".format(error), file=sys.stderr)

  got_vcon = vcon.Vcon()
  got_vcon.loads(out_vcon_json)

  #assert(httpretty.latest_requests()[0].headers["accept"] == vcon.Vcon.MIMETYPE_JSON)
  assert(len(got_vcon.parties) == 2)
  assert(got_vcon.parties[0]['tel'] == call_data['source'])
  assert(got_vcon.parties[1]['tel'] == call_data['destination'])
  assert(got_vcon.uuid == uuid)


@pytest.mark.asyncio
#@httpretty.activate(verbose = True, allow_net_connect = False)
async def test_post(two_party_tel_vcon, capsys, httpserver: pytest_httpserver.HTTPServer):
  """ Test cli post (-p, --post) HTTP post of Vcon """
  # Importing vcon here so that we catch any junk stdout which will break ths CLI
  import vcon.cli

  #host = "example.com"
  host = httpserver.host
  #port = 8000
  port = httpserver.port
  uuid = "test_fake_uuid"

  # Hack UUID for testing
  two_party_tel_vcon._vcon_dict[vcon.Vcon.UUID] = uuid

  headers = {"Content-Type": vcon.Vcon.MIMETYPE_JSON}
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
  #     host = host,
  #     port = port
  #     ),
  #     status = 200
  #     )

  # Setup stdin for vcon CLI to read
  sys.stdin = io.StringIO(two_party_tel_vcon.dumps())

  # Run the vcon command to post Vcon to HTTP host
  try:
    await vcon.cli.main(["-p", host, str(port)])
  except Exception as e:
    print(httpserver.check_assertions())
    raise e

  out_vcon_json, error = capsys.readouterr()
  # As we captured the stderr, we need to re-emmit it for unit test feedback
  print("stderr: {}".format(error), file=sys.stderr)

  # posted_vcon = vcon.Vcon()
  # The following should all be tested by httpserver
  # assert(httpretty.latest_requests()[0].headers["Content-Type"] == vcon.Vcon.MIMETYPE_JSON)
  #print("type: " + str(type(httpretty.latest_requests()[0].body)))
  #print(httpretty.latest_requests()[0].body)
  # posted_vcon.loads(httpretty.latest_requests()[0].body)

  # assert(len(posted_vcon.parties) == 2)
  # assert(posted_vcon.parties[0]['tel'] == call_data['source'])
  # assert(posted_vcon.parties[1]['tel'] == call_data['destination'])
  # assert(posted_vcon.uuid == uuid)

  out_vcon = vcon.Vcon()
  out_vcon.loads(out_vcon_json)
  assert(len(out_vcon.parties) == 2)
  assert(out_vcon.parties[0]['tel'] == call_data['source'])
  assert(out_vcon.parties[1]['tel'] == call_data['destination'])
  assert(out_vcon.uuid == uuid)


# TODO:
# vcon sign
# vcon verify
# vcon encrypt
# vcon decrypt
# vcon extract dialog
# vcon -i
# vcon -o

