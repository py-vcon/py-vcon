""" Common Vcon unit test fixtures, data and funcitons """
import os
import re
import json
import typing
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

# The draft-ietf-vcon-vcon-core-05 text, for its IANA tables.
VCON_DRAFT_PATH = "draft-ietf-vcon-vcon-core.md"
VCON_DRAFT_SHA256 = "f088a16efd6a72851549229ebaef935e9d1d4a80206253363b845a108c85f779"

# vCon 0.4.0 examples, created by py-vcon before 0.5.0 support (the signed
# and encrypted ones with the certificates in certs/).  None has a vcon parameter.
DRAFT_0_4_0_COMMIT = "fdcf2f5f420b726f7e70d16683ba0977d4610a1f"
DRAFT_0_4_0_EXAMPLES = {
    "examples/ab_call_ext_rec_signed.vcon": "562c391e189e1772d7bb3b591beff7c1e5197a37e09cec0d44611b0a8021e39b",
    "examples/ab_call_ext_rec_encrypted.vcon": "9e0a85404e7cfad359e811f7af4b841774c5143871d77e54202fdadecf92ffcb",
    "examples/ab_call_ext_rec.vcon": "d24202681dca8219c37e91bc62968b21656e77dedf76e680d3e73b5583e6505d",
    "examples/ab_call_ext_rec_amended.vcon": "f0c787c2a8ab04a2064bdc1a4012c3b895f37cf1acf0fc03c90c3fd4954df36f",
    "examples/ab_call_ext_rec_analysis.vcon": "afc0c221e5462cea1d717137cb7db13d3e601d5274c0ab8332da960ba1da6a61",
    "examples/ab_call_ext_rec_redacted.vcon": "c1766bb7bd9d758c3744dae0d8864536208db573d2cd9d270f7eec7476e2fb4b",
    "examples/ab_call_ext_rec_with_redact.vcon": "7df46c8eee0f152a1f710567c5bb2204f589f4efaa4e59b7acaeecf9520b9b8a",
    "examples/ab_call_int_rec.vcon": "126652aefde93e64a2346ce305d435e672d281536cc6bb6ad3b3dd83fa9bceca",
    "examples/ab_email_acct_prob_thread.vcon": "370fe0a1bae2dd63d3df4c2bd55079e6fe2f88f545fb0d5fabac8e8598520e53",
    "examples/ab_email_prob_followup_text_thread.vcon": "85c78e60ca784cf80ca12356089e67bff4d3da5297403bf9f6fababd9b6d7136",
    "examples/b_email_acct_prob_image.vcon": "bb3823d91a0d89310342b0bde00f7fdf08ccd61ea41d836edaaacdb0a55766ce"
  }

# The unsigned ones
DRAFT_0_4_0_UNSIGNED_EXAMPLES = [path for path in DRAFT_0_4_0_EXAMPLES
  if(not path.endswith("_signed.vcon") and not path.endswith("_encrypted.vcon"))]


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


def load_iana_tables() -> typing.Dict[str, typing.List[str]]:
  """
  The names in each IANA table of draft-ietf-vcon-vcon-core-05 (see
  load_draft_file), keyed by the registry Object name, for example "Party",
  or for a value registry, Object name "->" parameter name, for example
  "Event->type".  The vCon Object is "-".
  """
  text = load_draft_file(VCON_SCHEMA_COMMIT, VCON_DRAFT_PATH, VCON_DRAFT_SHA256).decode("utf-8")
  tables: typing.Dict[str, typing.List[str]] = {}
  table_name = None
  for line in text.splitlines():
    parameter_heading = re.match(r"^### (\S+) Object Parameter Names Registry$", line)
    value_heading = re.match(r"^##### (\S+) Type Name Registration Initial Values$", line)
    if(parameter_heading):
      table_name = "-" if parameter_heading.group(1) == "vCon" else parameter_heading.group(1)
      tables[table_name] = []
    elif(value_heading):
      table_name = "{}->type".format(value_heading.group(1))
      tables[table_name] = []
    elif(line.startswith("#")):
      table_name = None
    elif(table_name is not None and line.startswith("| ") and not line.startswith("| ---")):
      name = line.split("|")[1].strip()
      if(not name.endswith(" Name")):
        tables[table_name].append(name)

  return(tables)


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
