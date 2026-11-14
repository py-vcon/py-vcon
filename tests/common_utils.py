""" Common Vcon unit test fixtures, data and funcitons """
import os
import json
import hashlib
import urllib.request
import jsonschema
import pytest
import vcon


# The vCon JSON Schema from draft-ietf-vcon-vcon-core-05.  It is fetched from
# the draft repository at this commit and cached in tests/.cache (not committed).
VCON_SCHEMA_COMMIT = "61edfa1de595b62ca73d8f55f595f18f7fe1de80"
VCON_SCHEMA_SHA256 = "87285e19c3df2520f9c5bf370f7a31aaad1a2f8e882559ef63d6fb1249948f44"
VCON_SCHEMA_URL = "https://raw.githubusercontent.com/ietf-wg-vcon/draft-ietf-vcon-vcon-core/{}/vcon_json_schema.json"
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")


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


def download_file(url: str) -> bytes:
  """ HTTP GET the file at url (separate function so that tests can replace it) """
  with urllib.request.urlopen(url, timeout = 30) as response:
    return(response.read())


def load_vcon_schema() -> dict:
  """
  The vCon JSON Schema, from the cache or downloaded into it.

  Raises AssertionError if the schema can not be fetched or its sha256
  does not match.  The test is never skipped.
  """
  url = VCON_SCHEMA_URL.format(VCON_SCHEMA_COMMIT)
  cache_file = os.path.join(CACHE_DIR, "vcon_json_schema_{}.json".format(VCON_SCHEMA_COMMIT))
  if(os.path.exists(cache_file)):
    with open(cache_file, "rb") as schema_file:
      schema_bytes = schema_file.read()
  else:
    try:
      schema_bytes = download_file(url)
    except Exception as fetch_error:
      raise AssertionError("vCon JSON Schema is not cached and could not be downloaded."
        "  Fetch {} into {}: {}".format(url, cache_file, fetch_error))
    os.makedirs(CACHE_DIR, exist_ok = True)
    with open(cache_file, "wb") as schema_file:
      schema_file.write(schema_bytes)

  sha256 = hashlib.sha256(schema_bytes).hexdigest()
  if(sha256 != VCON_SCHEMA_SHA256):
    raise AssertionError("vCon JSON Schema {} has sha256 {}, expected {}.  Delete it to fetch it again.".format(
      cache_file, sha256, VCON_SCHEMA_SHA256))

  return(json.loads(schema_bytes))


def assert_valid_vcon(vcon_dict: dict) -> None:
  """
  Assert that the given unsigned vCon dict is valid against the vCon JSON Schema.

  Raises AssertionError listing each schema error and its JSON path.
  """
  validator = jsonschema.Draft7Validator(load_vcon_schema())
  errors = sorted(validator.iter_errors(vcon_dict), key = lambda error: error.json_path)
  if(len(errors) > 0):
    raise AssertionError("vCon is not valid against the vCon JSON Schema:\n" +
      "\n".join(["  {}: {}".format(error.json_path, error.message) for error in errors]))
