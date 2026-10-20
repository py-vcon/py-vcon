# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
Registry of vCon core and extension parameter names.

Parameter names are registered per Object path.  A path is a dot
separated string in which each segment is the parameter name of the
Object within its parent Object.  The empty string is the top level
vCon Object.  For example:

  ""                      the vCon Object
  "parties"               a Party Object
  "parties.civicaddress"  the Civicaddress Object of a Party Object
  "dialog"                a Dialog Object
  "dialog.party_history"  an element of a Dialog Object party_history array

Core parameter names are taken from the IANA registries defined in
draft-ietf-vcon-vcon-core.  Where the IANA section of that document
lags its normative text, the text is used: the Party Object did
parameter and the party_history Object button parameter are both
defined in the text but absent from their registry tables, and the
Civicaddress and SessionId Objects have no registry tables at all.

The group parameter is registered on the vCon Object as it appears in
the vCon Object Parameter Names Registry, however "group" is not a
registered path as no Group Object registry is defined.
"""

import typing


# Definer token returned for parameters defined by the core vCon schema.
PARAMETER_CORE = "core"


CORE_PARAMETERS: typing.Dict[str, typing.List[str]] = {
  "": [
    "vcon",
    "uuid",
    "extensions",
    "critical",
    "created_at",
    "updated_at",
    "subject",
    "redacted",
    "amended",
    "group",
    "parties",
    "dialog",
    "analysis",
    "attachments"
    ],

  "redacted": [
    "uuid",
    "type",
    "url",
    "content_hash"
    ],

  "amended": [
    "uuid",
    "url",
    "content_hash"
    ],

  "parties": [
    "tel",
    "sip",
    "stir",
    "mailto",
    "name",
    "did",
    "validation",
    "gmlpos",
    "civicaddress",
    "uuid",
    "type",
    "org",
    "dept"
    ],

  "parties.civicaddress": [
    "country",
    "a1",
    "a2",
    "a3",
    "a4",
    "a5",
    "a6",
    "prd",
    "pod",
    "sts",
    "hno",
    "hns",
    "lmk",
    "loc",
    "flr",
    "nam",
    "pc"
    ],

  "dialog": [
    "type",
    "start",
    "duration",
    "parties",
    "originator",
    "mediatype",
    "filename",
    "body",
    "encoding",
    "url",
    "content_hash",
    "disposition",
    "session_id",
    "party_history",
    "transferee",
    "transferor",
    "transfer_target",
    "original",
    "consultation",
    "target_dialog",
    "application",
    "message_id",
    "recordings",
    "recording_set"
    ],

  "dialog.session_id": [
    "local",
    "remote"
    ],

  "dialog.party_history": [
    "party",
    "time",
    "event",
    "button"
    ],

  "analysis": [
    "type",
    "dialog",
    "attachment",
    "mediatype",
    "filename",
    "vendor",
    "product",
    "schema",
    "body",
    "encoding",
    "url",
    "content_hash"
    ],

  "attachments": [
    "purpose",
    "start",
    "party",
    "dialog",
    "mediatype",
    "filename",
    "body",
    "encoding",
    "url",
    "content_hash"
    ]
  }


EXTENSION_PARAMETERS: typing.Dict[str, typing.Dict[str, typing.List[str]]] = {
  "CC": {
    "parties": [
      "role",
      "contact_list"
      ],

    "dialog": [
      "campaign",
      "interaction_type",
      "interaction_id",
      "skill"
      ]
    }
  }


# Built by build_index at import.
_PARAMETER_INDEX: typing.Dict[str, typing.Dict[str, str]] = {}
PARAMETER_PATHS: typing.FrozenSet[str] = frozenset()


def build_index() -> None:
  """
  Build the parameter index and the set of registered paths from
  CORE_PARAMETERS and EXTENSION_PARAMETERS.

  Called at import.  Call again after modifying either table.

  Raises ValueError if:
    * a parameter name is duplicated within a single core path
    * an extension parameter name collides with a core parameter name
      at the same path
    * two extensions define the same parameter name at the same path
  """
  global _PARAMETER_INDEX
  global PARAMETER_PATHS

  index: typing.Dict[str, typing.Dict[str, str]] = {}

  for path, parameter_names in CORE_PARAMETERS.items():
    path_index: typing.Dict[str, str] = {}
    for parameter_name in parameter_names:
      if(parameter_name in path_index):
        raise ValueError(
          "duplicate core parameter name: \"{}\" at path: \"{}\"".format(
          parameter_name, path))
      path_index[parameter_name] = PARAMETER_CORE
    index[path] = path_index

  # sorted for deterministic collision reporting
  for extension_name in sorted(EXTENSION_PARAMETERS.keys()):
    for path, parameter_names in EXTENSION_PARAMETERS[extension_name].items():
      path_index = index.setdefault(path, {})
      for parameter_name in parameter_names:
        if(parameter_name in path_index):
          raise ValueError(
            "extension: \"{}\" parameter name: \"{}\" at path: \"{}\""
            " collides with parameter already defined by: \"{}\"".format(
            extension_name, parameter_name, path, path_index[parameter_name]))
        path_index[parameter_name] = extension_name

  _PARAMETER_INDEX = index
  PARAMETER_PATHS = frozenset(index.keys())


def normalize_path(path : str) -> str:
  """
  Normalize an Object path string.

  Parameters:
    **path** (String) - the Object path to normalize

  Returns:
    the normalized path string

  Raises ValueError if the path has a leading or trailing separator.
  """
  normalized_path = path.strip()

  if(normalized_path.startswith(".") or
    normalized_path.endswith(".")
    ):
    raise ValueError(
      "invalid Object path: \"{}\".  Path must not begin or end with \".\"".format(
      path))

  return(normalized_path)


def get_parameter_extension(
  path : str,
  parameter_name : str
  ) -> typing.Union[str, None]:
  """
  Get the definer of the given parameter name at the given Object path.

  Parameters:
    **path** (String) - the Object path containing the parameter
    **parameter_name** (String) - the parameter name to look up

  Returns:
    PARAMETER_CORE, the defining extension name or None if the parameter
    name is not registered at the given path.

  Raises ValueError if the path is not a registered Object path.
  """
  normalized_path = normalize_path(path)

  if(normalized_path not in PARAMETER_PATHS):
    raise ValueError(
      "\"{}\" is not a registered vCon Object path.  Must be one of: {}".format(
      normalized_path, sorted(PARAMETER_PATHS)))

  return(_PARAMETER_INDEX[normalized_path].get(parameter_name, None))


def get_path_parameter_names(path : str) -> typing.List[str]:
  """
  Get all registered parameter names, core and extension defined, for the
  given Object path.

  Parameters:
    **path** (String) - the Object path

  Returns:
    list of registered parameter names

  Raises ValueError if the path is not a registered Object path.
  """
  normalized_path = normalize_path(path)

  if(normalized_path not in PARAMETER_PATHS):
    raise ValueError(
      "\"{}\" is not a registered vCon Object path.  Must be one of: {}".format(
      normalized_path, sorted(PARAMETER_PATHS)))

  return(list(_PARAMETER_INDEX[normalized_path].keys()))


build_index()

