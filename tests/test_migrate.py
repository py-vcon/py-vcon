# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
Unit test for migration of vCon versions
"""

import vcon
import vcon.security
import json
import warnings
import pytest
import logging

def test_migrate_0_0_1():
  vcon_json = vcon.security.load_string_from_file("tests/pre_0.0.1_vcon_trans.vcon")

  migrated_vcon = vcon.Vcon()
  migrated_vcon.loads(vcon_json)

  assert("body" in migrated_vcon.analysis[0])
  assert("transcript" not in migrated_vcon.analysis[0])
  assert("encoding" in migrated_vcon.analysis[0])
  assert(migrated_vcon.analysis[0]["encoding"] == "json")
  assert(migrated_vcon.analysis[0]["body"]['a'] == "b")
  assert(migrated_vcon.analysis[0]["body"]['c'] == 3)

  # Should be converted to RFC3339 format date
  assert(migrated_vcon.dialog[0]['start'] == "2022-05-18T23:05:05.000+00:00")

  # Migrations stack.  0.0.1 migrates to 0.0.2, then the 0.0.2 migration
  # removes the deprecated vcon parameter.
  assert(migrated_vcon.vcon is None)


def test_migrate_0_0_2():
  vcon_json = vcon.security.load_string_from_file("tests/ab_call_ext_rec_0.0.1.vcon")

  migrated_vcon = vcon.Vcon()
  migrated_vcon.loads(vcon_json)

  assert("mimetype" not in migrated_vcon.dialog[0])
  assert(migrated_vcon.dialog[0]["mediatype"] == "audio/x-wav")

  assert("signature" not in migrated_vcon.dialog[0])
  assert("alg" not in migrated_vcon.dialog[0])
  assert(migrated_vcon.dialog[0]["content_hash"] == "sha512-Re9R7UWKaD7yN9kxoYLbFFNSKU8XfH18NFbTc3AgT4_aBubMtvGUEtRmP6XUxSS3Nl4LU-1mOCtezoTHQ67cVQ")

  assert("mimetype" not in migrated_vcon.analysis[0])
  assert(migrated_vcon.analysis[0]["mediatype"] == "application/foo")
  assert(migrated_vcon.analysis[0]["product"] == "bob")
  assert(migrated_vcon.analysis[0]["schema"] == "bobject")
  assert(migrated_vcon.analysis[0]["encoding"] == "none")

  assert(migrated_vcon.analysis[1]["mediatype"] == "application/foo")
  assert(migrated_vcon.analysis[1]["product"] == "whisper")
  assert(migrated_vcon.analysis[1]["vendor"] == "openai")
  assert(migrated_vcon.analysis[1]["encoding"] == "none")

  # Last migration in the chain removes the deprecated vcon parameter.
  assert(migrated_vcon.vcon is None)


def make_version_dict(version_string = None) -> dict:
  """ Build a minimal vCon dict, setting the vcon parameter only if given """
  vcon_dict = {
      "uuid": "01855517-ac4e-8edf-84fd-77776666acbe",
      "parties": [{"tel": "+12345678901"}],
      "dialog": [],
      "analysis": [],
      "attachments": []
    }
  if(version_string is not None):
    vcon_dict[vcon.Vcon.VCON_VERSION] = version_string

  return(vcon_dict)


def test_version_absent():
  """ vcon parameter is deprecated.  Absent means current syntax. """
  checked = vcon.Vcon.check_and_migrate_version(make_version_dict())

  assert(vcon.Vcon.VCON_VERSION not in checked)
  assert(checked["uuid"] == "01855517-ac4e-8edf-84fd-77776666acbe")
  assert(len(checked["parties"]) == 1)


@pytest.mark.parametrize("version_string", ["0.0.1", "0.0.2"])
def test_version_migrated_removes_parameter(version_string):
  """ The last migration in the chain removes the deprecated vcon parameter """
  checked = vcon.Vcon.check_and_migrate_version(make_version_dict(version_string))

  assert(vcon.Vcon.VCON_VERSION not in checked)
  assert(checked["uuid"] == "01855517-ac4e-8edf-84fd-77776666acbe")


@pytest.mark.parametrize("version_string", ["0.3.0", "0.4.0"])
def test_version_unconverted(version_string):
  """ Accepted as is, warning emitted, vcon parameter left unmodified """
  with pytest.warns(vcon.UnconvertedVconVersionWarning) as warning_list:
    checked = vcon.Vcon.check_and_migrate_version(make_version_dict(version_string))

  # vcon parameter left exactly as found, not updated and not removed
  assert(checked[vcon.Vcon.VCON_VERSION] == version_string)

  # Guard against vCon contents being dropped when no migration is run
  assert(checked["uuid"] == "01855517-ac4e-8edf-84fd-77776666acbe")
  assert(len(checked["parties"]) == 1)

  assert(len(warning_list) == 1)
  assert(version_string in str(warning_list[0].message))


@pytest.mark.parametrize("version_string",
    ["0.0.3", "0.2.0", "0.4.1", "1.0.0", "0.4", ""])
def test_version_unsupported(version_string):
  """ Versions with no migration and not explicitly accepted are rejected """
  with pytest.raises(vcon.UnsupportedVconVersion):
    vcon.Vcon.check_and_migrate_version(make_version_dict(version_string))


@pytest.mark.parametrize("version_string", [None, "0.0.1", "0.0.2"])
def test_version_no_warning(version_string):
  """ No unconverted version warning for absent or migratable versions """
  with warnings.catch_warnings(record = True) as warning_list:
    warnings.simplefilter("always")
    vcon.Vcon.check_and_migrate_version(make_version_dict(version_string))

  unconverted = [warning for warning in warning_list
      if(issubclass(warning.category, vcon.UnconvertedVconVersionWarning))]
  assert(len(unconverted) == 0)


def test_version_unconverted_logged(caplog):
  """ Unconverted version warning is also logged, for server visibility """
  with caplog.at_level(logging.WARNING, logger = "vcon"):
    with pytest.warns(vcon.UnconvertedVconVersionWarning):
      vcon.Vcon.check_and_migrate_version(make_version_dict("0.4.0"))

  warning_records = [record for record in caplog.records
      if(record.levelname == "WARNING" and "0.4.0" in record.getMessage())]
  assert(len(warning_records) == 1)


def test_version_unconverted_round_trip():
  """ Unconverted vcon parameter survives load and serialization unmodified """
  round_trip_vcon = vcon.Vcon()
  with pytest.warns(vcon.UnconvertedVconVersionWarning):
    round_trip_vcon.loads(json.dumps(make_version_dict("0.4.0")))

  assert(round_trip_vcon.vcon == "0.4.0")
  assert('"vcon": "0.4.0"' in round_trip_vcon.dumps())

