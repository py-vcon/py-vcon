# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" Unit tests for the CDDL validation helper used by the unit tests """

import os
import re
import subprocess
import pytest
import vcon
import vcon.parameter_registry
import tests.common_utils

CA_CERT = "certs/fake_ca_root.crt"
DIVISION_CERT = "certs/fake_div.crt"
GROUP_CERT = "certs/fake_grp.crt"
GROUP_PRIVATE_KEY = "certs/fake_grp.key"
CERT_CHAIN = [GROUP_CERT, DIVISION_CERT, CA_CERT]
UUID = "01a07da8-c2bb-83e5-b9a2-279e0d16bc46"

# CDDL group socket for the Objects which have proposed parameters
OBJECT_SOCKETS = {
  "Dialog": "$$dialog-ext",
  "Redacted_string": "$$redacted-string-ext",
  "Redacted_segments": "$$redacted-segments-ext"
  }


def make_vcon() -> vcon.Vcon:
  v = vcon.Vcon()
  v.set_party_parameter("tel", "+15551110000")
  v.set_party_parameter("tel", "+15552220000")
  v.add_text_dialog_inline("Hello", "2022-06-21T13:53:26-04:00", 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  v.set_uuid("example.com")
  return(v)


def test_valid_vcon_passes():
  tests.common_utils.assert_valid_cddl(make_vcon().dumpd())


def test_invalid_vcon_fails():
  vcon_dict = make_vcon().dumpd()
  vcon_dict["redacted_from"] = {"uuid": UUID, "type": "PII"}
  vcon_dict["amended_from"] = {"uuid": UUID}
  with pytest.raises(AssertionError, match = "not valid against the vCon CDDL"):
    tests.common_utils.assert_valid_cddl(vcon_dict)


def test_missing_tool_fails(monkeypatch):
  monkeypatch.delenv(tests.common_utils.CDDL_SKIP_VARIABLE, raising = False)
  monkeypatch.setattr(tests.common_utils.shutil, "which", lambda name: None)
  with pytest.raises(AssertionError) as error:
    tests.common_utils.assert_valid_cddl(make_vcon().dumpd())
  assert("gem install cddl" in str(error.value))
  assert("VCON_SKIP_CDDL=1" in str(error.value))


def test_skip_variable(monkeypatch):
  def no_run(*args, **kwargs):
    raise Exception("cddl must not be run")
  monkeypatch.setenv(tests.common_utils.CDDL_SKIP_VARIABLE, "1")
  monkeypatch.setattr(tests.common_utils.subprocess, "run", no_run)
  vcon_dict = make_vcon().dumpd()
  vcon_dict["redacted_from"] = {"uuid": UUID, "type": "PII"}
  vcon_dict["amended_from"] = {"uuid": UUID}
  tests.common_utils.assert_valid_cddl(vcon_dict)


def test_cddl_cached(monkeypatch, tmp_path):
  downloads = []
  real_download = tests.common_utils.download_file
  def counting_download(url):
    downloads.append(url)
    return(real_download(url))

  monkeypatch.setattr(tests.common_utils, "CACHE_DIR", str(tmp_path))
  monkeypatch.setattr(tests.common_utils, "download_file", counting_download)
  tests.common_utils.assert_valid_cddl(make_vcon().dumpd())
  tests.common_utils.assert_valid_cddl(make_vcon().dumpd())
  assert(len(downloads) == 1)
  assert(downloads[0].endswith("/" + tests.common_utils.VCON_CDDL_PATH))
  assert(tests.common_utils.VCON_SCHEMA_COMMIT in downloads[0])


def test_signed_and_encrypted_pass():
  v = make_vcon()
  v.sign(GROUP_PRIVATE_KEY, CERT_CHAIN)
  tests.common_utils.assert_valid_cddl(v.dumpd())
  v.encrypt(DIVISION_CERT)
  tests.common_utils.assert_valid_cddl(v.dumpd())


def test_proposed_cddl_matches_registry():
  """ tests/vcon_proposed.cddl defines exactly the registry's proposed parameters """
  with open(tests.common_utils.VCON_PROPOSED_CDDL_FILE) as proposed_file:
    lines = [line for line in proposed_file.read().splitlines() if(not line.lstrip().startswith(";"))]
  defined = []
  for line in lines:
    match = re.match(r"\s*(\$\$[a-z-]+)\s*//=\s*\((.*)\)\s*$", line)
    if(match is None):
      assert(line.strip() == ""), line
      continue
    for name in re.findall(r"\?\s*([a-z_]+)\s*:", match.group(2)):
      defined.append((match.group(1), name))

  expected = [(OBJECT_SOCKETS[object_name], name)
    for object_name, name in vcon.parameter_registry.PROPOSED_PARAMETERS]
  assert(sorted(defined) == sorted(expected))

  rows = {(row["parent"], row["name"]): row for row in vcon.parameter_registry.CORE_ROWS}
  for object_name, name in vcon.parameter_registry.PROPOSED_PARAMETERS:
    assert(rows[(object_name, name)]["iana"] is False), name
    assert("proposed" in rows[(object_name, name)]["description"]), name


def test_proposed_parameters_need_proposed_cddl(tmp_path):
  """ a vCon using the proposed parameters is valid with them, not against -05 alone """
  v = make_vcon()
  v._vcon_dict["dialog"][0]["in_reply_to"] = ["<1@example.com>"]
  v._vcon_dict["dialog"][0]["references"] = ["<1@example.com>"]
  tests.common_utils.assert_valid_cddl(v.dumpd())

  core_cddl = tests.common_utils.draft_cache_file(tests.common_utils.VCON_SCHEMA_COMMIT,
    tests.common_utils.VCON_CDDL_PATH)
  json_file = os.path.join(str(tmp_path), "vcon.json")
  with open(json_file, "w") as out_file:
    out_file.write(v.dumps())
  result = subprocess.run([tests.common_utils.shutil.which("cddl"), core_cddl, "validate", json_file],
    stdout = subprocess.PIPE, stderr = subprocess.STDOUT)
  assert(result.returncode != 0)
