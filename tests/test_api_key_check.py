# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" Unit tests for the requires_api_key marker check in tests/conftest.py """

import pytest
import tests.conftest


def test_key_set_runs():
  tests.conftest.check_api_keys(["DEEPGRAM_KEY"], {"DEEPGRAM_KEY": "abc"})
  tests.conftest.check_api_keys(["DEEPGRAM_KEY", "OPENAI_API_KEY"],
    {"DEEPGRAM_KEY": "abc", "OPENAI_API_KEY": "def"})


@pytest.mark.parametrize("environ", [{}, {"DEEPGRAM_KEY": ""}, {"VCON_SKIP_DEEPGRAM": "0"}])
def test_key_missing_fails(environ):
  with pytest.raises(pytest.fail.Exception) as error:
    tests.conftest.check_api_keys(["DEEPGRAM_KEY"], environ)
  assert("DEEPGRAM_KEY is not set" in str(error.value))
  assert("VCON_SKIP_DEEPGRAM=1" in str(error.value))


def test_one_of_two_keys_missing_fails():
  with pytest.raises(pytest.fail.Exception) as error:
    tests.conftest.check_api_keys(["DEEPGRAM_KEY", "OPENAI_API_KEY"], {"DEEPGRAM_KEY": "abc"})
  assert("OPENAI_API_KEY is not set" in str(error.value))
  assert("VCON_SKIP_OPENAI=1" in str(error.value))
  assert("DEEPGRAM_KEY is not set" not in str(error.value))


def test_skip_variable_skips():
  with pytest.raises(pytest.skip.Exception) as error:
    tests.conftest.check_api_keys(["OPENAI_API_KEY"], {"VCON_SKIP_OPENAI": "1"})
  assert("VCON_SKIP_OPENAI=1" in str(error.value))

  # the skip variable skips even with the key set
  with pytest.raises(pytest.skip.Exception):
    tests.conftest.check_api_keys(["OPENAI_API_KEY"], {"OPENAI_API_KEY": "def", "VCON_SKIP_OPENAI": "1"})


def test_skip_variable_of_either_key_skips():
  # a test needing both keys cannot run if either is skipped
  with pytest.raises(pytest.skip.Exception):
    tests.conftest.check_api_keys(["DEEPGRAM_KEY", "OPENAI_API_KEY"], {"VCON_SKIP_DEEPGRAM": "1"})


def test_unknown_key_fails():
  with pytest.raises(pytest.fail.Exception) as error:
    tests.conftest.check_api_keys(["BOGUS_KEY"], {"BOGUS_KEY": "abc"})
  assert("BOGUS_KEY has no skip variable" in str(error.value))
