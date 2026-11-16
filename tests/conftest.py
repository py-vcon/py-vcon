# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
pytest conftest.py for the python_vcon tests.

Provides the requires_api_key marker for tests which call live services
(e.g. Deepgram, OpenAI) and so need an API key in the environment:

  @pytest.mark.requires_api_key("DEEPGRAM_KEY")

A test with the marker fails if any of the named keys is not set, saying how
to set it, or how to skip the tests which need it by setting the key's skip
variable (see API_KEY_SKIP_VARIABLES) to 1.  The tests are never silently
skipped: they are skipped only when the skip variable is set.

The GitHub workflows set the skip variables only for pull requests from
forks, as GitHub does not pass repository secrets to those runs.
"""
import os
import typing
import pytest

# The variable for each API key which, set to 1, skips the tests needing the key
API_KEY_SKIP_VARIABLES = {
  "DEEPGRAM_KEY": "VCON_SKIP_DEEPGRAM",
  "OPENAI_API_KEY": "VCON_SKIP_OPENAI"
  }


def check_api_keys(
    key_names: typing.Iterable[str],
    environ: typing.Mapping[str, str] = os.environ
  ) -> None:
  """
  Check the API keys needed by a test which calls live services.

  Skips the test (pytest.skip) if the skip variable of any of the keys is 1.
  Otherwise fails the test (pytest.fail) if any of the keys is not set or is
  empty, saying how to set the key or skip the tests which need it.
  """
  skipped = []
  missing = []
  for key_name in key_names:
    skip_variable = API_KEY_SKIP_VARIABLES.get(key_name, None)
    if(skip_variable is None):
      pytest.fail("requires_api_key: {} has no skip variable in API_KEY_SKIP_VARIABLES".format(
        key_name), pytrace = False)
    if(environ.get(skip_variable, "") == "1"):
      skipped.append("{}=1".format(skip_variable))
    elif(environ.get(key_name, "") == ""):
      missing.append(("{} is not set.  This test calls a live service which needs it."
        "  Set {}, or set {}=1 to skip the tests which need it.").format(
        key_name, key_name, skip_variable))

  if(len(skipped) > 0):
    pytest.skip(", ".join(skipped))
  if(len(missing) > 0):
    pytest.fail("\n".join(missing), pytrace = False)


def pytest_configure(config):
  config.addinivalue_line(
    "markers",
    "requires_api_key(*names): the test calls live services and needs the named API keys"
    " set, see tests/conftest.py"
    )


def pytest_runtest_setup(item):
  for marker in item.iter_markers(name = "requires_api_key"):
    check_api_keys(marker.args)
