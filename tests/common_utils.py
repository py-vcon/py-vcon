""" Common Vcon unit test fixtures, data and funcitons """
import os
import json
import hashlib
import urllib.request
import jsonschema
import pytest
import vcon


# Files from the draft-ietf-vcon-vcon-core repository are fetched at a pinned
# commit, checked against their sha256 and cached in tests/.cache (not committed).
DRAFT_URL = "https://raw.githubusercontent.com/ietf-wg-vcon/draft-ietf-vcon-vcon-core/{}/{}"
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")

# The vCon JSON Schema from draft-ietf-vcon-vcon-core-05.
VCON_SCHEMA_COMMIT = "61edfa1de595b62ca73d8f55f595f18f7fe1de80"
VCON_SCHEMA_PATH = "vcon_json_schema.json"
VCON_SCHEMA_SHA256 = "87285e19c3df2520f9c5bf370f7a31aaad1a2f8e882559ef63d6fb1249948f44"

# vCon 0.4.0 examples, signed and encrypted by py-vcon before 0.5.0 support,
# with the certificates in certs/.
DRAFT_0_4_0_COMMIT = "fdcf2f5f420b726f7e70d16683ba0977d4610a1f"
DRAFT_0_4_0_EXAMPLES = {
    "examples/ab_call_ext_rec_signed.vcon": "562c391e189e1772d7bb3b591beff7c1e5197a37e09cec0d44611b0a8021e39b",
    "examples/ab_call_ext_rec_encrypted.vcon": "9e0a85404e7cfad359e811f7af4b841774c5143871d77e54202fdadecf92ffcb"
  }


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


def load_draft_file(commit: str, path: str, sha256: str) -> bytes:
  """
  A file from the draft repository at the given commit, from the cache or
  downloaded into it.

  Raises AssertionError if the file can not be fetched or its sha256 does
  not match.  The test is never skipped.
  """
  url = DRAFT_URL.format(commit, path)
  base_name, extension = os.path.splitext(os.path.basename(path))
  cache_file = os.path.join(CACHE_DIR, "{}_{}{}".format(base_name, commit, extension))
  if(os.path.exists(cache_file)):
    with open(cache_file, "rb") as cached_file:
      file_bytes = cached_file.read()
  else:
    try:
      file_bytes = download_file(url)
    except Exception as fetch_error:
      raise AssertionError("{} is not cached and could not be downloaded."
        "  Fetch {} into {}: {}".format(path, url, cache_file, fetch_error))
    os.makedirs(CACHE_DIR, exist_ok = True)
    with open(cache_file, "wb") as cached_file:
      cached_file.write(file_bytes)

  file_sha256 = hashlib.sha256(file_bytes).hexdigest()
  if(file_sha256 != sha256):
    raise AssertionError("{} has sha256 {}, expected {}.  Delete it to fetch it again.".format(
      cache_file, file_sha256, sha256))

  return(file_bytes)


def load_vcon_schema() -> dict:
  """ The vCon JSON Schema (see load_draft_file) """
  return(json.loads(load_draft_file(VCON_SCHEMA_COMMIT, VCON_SCHEMA_PATH, VCON_SCHEMA_SHA256)))


def load_draft_0_4_0_example(path: str) -> dict:
  """ One of the DRAFT_0_4_0_EXAMPLES (see load_draft_file) """
  return(json.loads(load_draft_file(DRAFT_0_4_0_COMMIT, path, DRAFT_0_4_0_EXAMPLES[path])))


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
