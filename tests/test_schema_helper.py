# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" Unit tests for the vCon JSON Schema test helper in tests/common_utils.py """

import os
import pytest
import vcon
import tests.common_utils


START = "2022-06-21T13:53:26-04:00"


def make_valid_vcon_dict() -> dict:
  """ minimal valid 0.5.0 vCon: uuid, one party, one text Dialog in one Session """
  a_vcon = vcon.Vcon()
  a_vcon.set_uuid("example.com")
  a_vcon.set_party_parameter("tel", "+15551110000")
  a_vcon.add_text_dialog_inline("Hello", START, 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  return(a_vcon.dumpd())


def test_valid_vcon_passes():
  tests.common_utils.assert_valid_vcon(make_valid_vcon_dict())


def test_missing_uuid_fails():
  vcon_dict = make_valid_vcon_dict()
  del vcon_dict["uuid"]
  with pytest.raises(AssertionError, match = "uuid"):
    tests.common_utils.assert_valid_vcon(vcon_dict)


def test_attachment_without_reference_fails():
  vcon_dict = make_valid_vcon_dict()
  vcon_dict["attachments"] = [{
      "start": "2022-06-21T17:53:26.000+00:00",
      "party": 0,
      "mediatype": "text/plain",
      "encoding": "none",
      "body": "notes"
    }]
  with pytest.raises(AssertionError, match = r"\$\.attachments\[0\]"):
    tests.common_utils.assert_valid_vcon(vcon_dict)


def test_schema_cached(monkeypatch, tmp_path):
  downloads = []
  real_download = tests.common_utils.download_file
  def counting_download(url):
    downloads.append(url)
    return(real_download(url))

  monkeypatch.setattr(tests.common_utils, "CACHE_DIR", str(tmp_path))
  monkeypatch.setattr(tests.common_utils, "download_file", counting_download)
  tests.common_utils.load_vcon_schema()
  assert(len(downloads) == 1)
  assert(tests.common_utils.VCON_SCHEMA_COMMIT in downloads[0])
  assert(len(os.listdir(str(tmp_path))) == 1)

  tests.common_utils.load_vcon_schema()
  assert(len(downloads) == 1)


def test_schema_hash_mismatch_fails(monkeypatch, tmp_path):
  monkeypatch.setattr(tests.common_utils, "CACHE_DIR", str(tmp_path))
  cache_file = os.path.join(str(tmp_path),
    "vcon_json_schema_{}.json".format(tests.common_utils.VCON_SCHEMA_COMMIT))
  with open(cache_file, "w") as schema_file:
    schema_file.write("{}")
  with pytest.raises(AssertionError, match = tests.common_utils.VCON_SCHEMA_SHA256):
    tests.common_utils.load_vcon_schema()


def test_schema_download_failure_fails(monkeypatch, tmp_path):
  def failing_download(url):
    raise OSError("network unreachable")

  monkeypatch.setattr(tests.common_utils, "CACHE_DIR", str(tmp_path))
  monkeypatch.setattr(tests.common_utils, "download_file", failing_download)
  with pytest.raises(AssertionError, match = "could not be downloaded.*Fetch https://"):
    tests.common_utils.load_vcon_schema()
