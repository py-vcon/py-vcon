# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
"""
Registry of vCon core and extension parameter names and values.

Each registry row is a dict with the fields of the IANA vCon registries:

  parent             the Object name, for example "Party", or for a value of
                     a parameter, the Object name and parameter name joined by
                     "->", for example "Event->type".  The vCon Object itself
                     is "-".
  name               the parameter name, or the value for a value row
  description        brief description
  change_controller  for example "IESG"
  specification      the document which defines it

and two fields which are not IANA columns:

  iana               False for a row with no IANA registry behind it (for
                     example the Civicaddress Object parameters), so that a
                     tool maintaining the IANA tables skips it
  legacy             True for a name of an earlier vCon version which is no
                     longer defined, recognized as core so that vCons of that
                     version do not appear to use unknown parameters.  There
                     are none: 0.4.0 vCons are converted to 0.5.0 on load.

Object names are those used in draft-ietf-vcon-vcon-core: "-" (the vCon
Object), "Party", "Civicaddress", "Dialog", "SessionId",
"Redacted_segments", "Session", "Session_Reference", "Event",
"Attachment", "Analysis", "Redacted_from", "Amended_from" and
"Redacted_string".

An extension is a dict with the fields of the vCon Extensions Names Registry
(name, description, change_controller, specification) plus critical: True if
the extension name is to be listed in the vCon critical parameter whenever
the extension is used.  An extension which is incompatible only under some
conditions is not modeled.
"""

import typing


# Definer token returned for parameters and values defined by the core vCon schema.
PARAMETER_CORE = "core"

# The Object name of the top level vCon Object.
VCON_OBJECT = "-"

# Separates the Object name and parameter name in the parent of a value row.
VALUE_SEPARATOR = "->"

CORE_CHANGE_CONTROLLER = "IESG"
CORE_SPECIFICATION = "RFC XXXX (draft-ietf-vcon-vcon-core)"


def _make_rows(
  parent : str,
  entries : typing.List[typing.Tuple[str, str]],
  iana : bool = True,
  legacy : bool = False
  ) -> typing.List[typing.Dict[str, typing.Any]]:
  """ build core rows for the given parent from (name, description) pairs """
  return([{
      "parent": parent,
      "name": name,
      "description": description,
      "change_controller": CORE_CHANGE_CONTROLLER,
      "specification": CORE_SPECIFICATION,
      "iana": iana,
      "legacy": legacy
    } for name, description in entries])


ENCODING_VALUES = [
    ("base64url", "body is Base64Url encoded"),
    ("json", "body is a JSON value"),
    ("none", "body is a JSON string included without modification")
  ]


# Parameters which py-vcon writes, proposed to the vCon working group but
# not defined in draft-ietf-vcon-vcon-core-05 (vcon-core draft issues 9, 13
# and 14).  They are core rows below, with iana False, as they are expected
# to become core rather than an extension.  As -05 does not define them, a
# vCon which uses them does not pass a strict -05 CDDL validator; the unit
# tests add them to the -05 CDDL with tests/vcon_proposed.cddl.
PROPOSED_PARAMETERS: typing.List[typing.Tuple[str, str]] = [
  ("Dialog", "in_reply_to"),
  ("Dialog", "references"),
  ("Redacted_string", "marker"),
  ("Redacted_segments", "channel")
  ]


CORE_ROWS: typing.List[typing.Dict[str, typing.Any]] = (
  # vCon Object Parameter Names Registry
  _make_rows(VCON_OBJECT, [
    ("vcon", "Schema version number"),
    ("uuid", "vCon instance UUID"),
    ("extensions", "list of extensions used"),
    ("critical", "list of incompatible extensions used"),
    ("created_at", "creation date"),
    ("updated_at", "modification date"),
    ("subject", "conversation subject"),
    ("redacted_from", "Redacted Object"),
    ("amended_from", "Amended Object"),
    ("group", "reserved for future extension"),
    ("sessions", "Session Objects array"),
    ("events", "Event Objects array"),
    ("parties", "Party Objects array"),
    ("dialog", "Dialog Objects array"),
    ("analysis", "Analysis Objects array"),
    ("attachments", "Attachment Objects array"),
    ("redacted_strings", "Redacted Strings array")
    ]) +

  # Party Object Parameter Names Registry
  _make_rows("Party", [
    ("tel", "tel URL"),
    ("sip", "SIP URL"),
    ("stir", "STIR token"),
    ("mailto", "mailto URL"),
    ("name", "participant name"),
    ("validation", "validation method"),
    ("gmlpos", "participant geolocation"),
    ("civicaddress", "civic address"),
    ("uuid", "participant unique identifier"),
    ("type", "participant type"),
    ("org", "participant organization"),
    ("dept", "participant department"),
    ("did", "decentralized identifier")
    ]) +

  # Civicaddress Object, no IANA registry (GEOPRIV section 2.2.1 names)
  _make_rows("Civicaddress", [
    ("country", "country"),
    ("a1", "national subdivision"),
    ("a2", "county, parish"),
    ("a3", "city, township"),
    ("a4", "city division"),
    ("a5", "neighborhood"),
    ("a6", "street"),
    ("prd", "leading street direction"),
    ("pod", "trailing street suffix"),
    ("sts", "street suffix"),
    ("hno", "house number"),
    ("hns", "house number suffix"),
    ("lmk", "landmark"),
    ("loc", "additional location information"),
    ("flr", "floor"),
    ("nam", "name"),
    ("pc", "postal code")
    ], iana = False) +

  # Dialog Object Parameter Names Registry
  _make_rows("Dialog", [
    ("type", "dialog type name"),
    ("start", "dialog start time"),
    ("duration", "dialog duration period"),
    ("parties", "dialog parties list"),
    ("mediatype", "dialog content media type"),
    ("filename", "dialog content filename"),
    ("body", "dialog inline content"),
    ("encoding", "dialog inline content encoding"),
    ("url", "dialog referenced content URL"),
    ("content_hash", "dialog content hash"),
    ("disposition", "dialog disposition"),
    ("session_id", "RFC7989 session ID"),
    ("application", "dialog source application"),
    ("message_id", "dialog message id"),
    ("redacted_segments", "redacted segments")
    ]) +
  _make_rows("Dialog", [
    ("in_reply_to", "Message-IDs of the In-Reply-To email header (proposed, not in -05)"),
    ("references", "Message-IDs of the References email header (proposed, not in -05)")
    ], iana = False) +

  # Dialog Type Name Registry
  _make_rows("Dialog->type", [
    ("text", "text dialog"),
    ("recording", "recording dialog"),
    ("incomplete", "incomplete dialog")
    ]) +

  # Dialog disposition values, no IANA registry
  _make_rows("Dialog->disposition", [
    ("no-answer", "no one answered or accepted the connection"),
    ("congestion", "unable to be completed due to system load"),
    ("failed", "the call or connection failed"),
    ("busy", "the party was busy with another conversation"),
    ("hung-up", "the party hung-up before any conversation occurred"),
    ("voicemail-no-message", "voicemail answered, but no message was left")
    ], iana = False) +

  # encoding values, no IANA registry
  _make_rows("Dialog->encoding", ENCODING_VALUES, iana = False) +

  # SessionId Object, no IANA registry
  _make_rows("SessionId", [
    ("local", "local UUID of the RFC7989 session ID"),
    ("remote", "remote UUID of the RFC7989 session ID")
    ], iana = False) +

  # Redacted_segments Object, no IANA registry
  _make_rows("Redacted_segments", [
    ("start", "redaction start time"),
    ("end", "redaction end time"),
    ("parties", "parties whose media was redacted"),
    ("channel", "index of the redacted recording channel (proposed, not in -05)")
    ], iana = False) +

  # Session Object Parameter Names Registry
  _make_rows("Session", [
    ("start", "session start time"),
    ("duration", "session duration period"),
    ("parties", "session parties list"),
    ("originator", "session originator party"),
    ("session_id", "RFC7989 session ID"),
    ("sessions", "Session_Reference Objects array"),
    ("dialog", "session dialog index list")
    ]) +

  # Session_Reference Object Parameter Names Registry
  _make_rows("Session_Reference", [
    ("session", "referenced session index"),
    ("type", "session relationship type"),
    ("description", "session relationship description")
    ]) +

  # Session_Reference Type Name Registry
  _make_rows("Session_Reference->type", [
    ("child", "contained session"),
    ("peer", "parallel or overlapping session"),
    ("precursor", "preceding session"),
    ("breakout", "breakout session with a subset of the parties")
    ]) +

  # Event Object Parameter Names Registry
  _make_rows("Event", [
    ("type", "event type name"),
    ("time", "time event occurred"),
    ("sessions", "event session indices"),
    ("party", "event party index"),
    ("dialog", "event dialog index"),
    ("channel", "recording channel index"),
    ("contributors", "recording channel contributor party indices"),
    ("button", "button label character or string"),
    ("transferee", "transferee party index"),
    ("transfer_target", "transfer target party index"),
    ("consultation", "consultation session index"),
    ("target_session", "target session index")
    ]) +

  # Event Type Name Registry
  _make_rows("Event->type", [
    ("join", "party join event"),
    ("drop", "party drop event"),
    ("hold", "party on hold event"),
    ("unhold", "party off hold event"),
    ("mute", "party on mute event"),
    ("unmute", "party off mute event"),
    ("keydown", "DTMF/app key/button press event"),
    ("keyup", "DTMF/app key/button release event"),
    ("consultation-start", "transfer consultation start event"),
    ("blind-transfer", "blind transfer event"),
    ("consultative-transfer", "consultative transfer event"),
    ("transfer-abandoned", "transfer abandoned event"),
    ("channel-contributors", "recording channel contributors change event")
    ]) +

  # Attachment Object Parameter Names Registry
  _make_rows("Attachment", [
    ("purpose", "attachment object purpose description"),
    ("start", "attachment start time"),
    ("party", "sending party index"),
    ("dialog", "associated dialog index"),
    ("session", "associated session index"),
    ("mediatype", "attachment body media type"),
    ("filename", "attachment content filename"),
    ("body", "attachment inline content"),
    ("encoding", "attachment inline content encoding"),
    ("url", "attachment referenced content URL"),
    ("content_hash", "attachment content hash")
    ]) +
  _make_rows("Attachment->encoding", ENCODING_VALUES, iana = False) +

  # Analysis Object Parameter Names Registry
  _make_rows("Analysis", [
    ("type", "analysis type"),
    ("dialog", "associated dialog index"),
    ("sessions", "associated session indices"),
    ("attachment", "associated attachment index"),
    ("analysis", "associated analysis index"),
    ("mediatype", "analysis body media type"),
    ("filename", "analysis content filename"),
    ("vendor", "vendor producing content"),
    ("product", "vendor product producing content"),
    ("schema", "product schema of content"),
    ("body", "analysis inline content"),
    ("encoding", "analysis inline content encoding"),
    ("url", "analysis referenced content URL"),
    ("content_hash", "analysis content hash")
    ]) +
  _make_rows("Analysis->encoding", ENCODING_VALUES, iana = False) +

  # Redacted_from Object Parameter Names Registry
  _make_rows("Redacted_from", [
    ("uuid", "less redacted vCon UUID"),
    ("type", "redaction type or reason"),
    ("url", "referenced less redacted vCon URL"),
    ("content_hash", "less redacted vCon hash")
    ]) +

  # Amended_from Object Parameter Names Registry
  _make_rows("Amended_from", [
    ("uuid", "prior vCon version UUID"),
    ("url", "referenced prior version vCon URL"),
    ("content_hash", "prior version vCon hash")
    ]) +

  # Redacted_string Object, no IANA registry
  _make_rows("Redacted_string", [
    ("ref", "reference number of the redacted string"),
    ("type", "type of information redacted"),
    ("orig", "the original string before redaction"),
    ("marker", "the marker string which replaced the redacted string (proposed, not in -05)")
    ], iana = False)
  )


CC_EXTENSION = {
    "name": "CC",
    "description": "Contact Center",
    "change_controller": "IESG",
    "specification": "RFC XXXX (draft-ietf-vcon-cc-extension)",
    # CC is Compatible: it adds only optional parameters
    "critical": False
  }

CC_ROWS = [
    {"parent": "Party", "name": "role", "description": "Agent party role"},
    {"parent": "Party", "name": "contact_list", "description": "Contact list including this party"},
    {"parent": "Dialog", "name": "campaign", "description": "Campaign the dialog is part of"},
    {"parent": "Dialog", "name": "interaction_type", "description": "Dialog interaction type"},
    {"parent": "Dialog", "name": "interaction_id", "description": "Dialog interaction ID"},
    {"parent": "Dialog", "name": "skill", "description": "Required skill"}
  ]


EXTENSION_FIELDS = ["name", "description", "change_controller", "specification", "critical"]

# Registered extensions by name: the extension fields plus "rows".
EXTENSIONS: typing.Dict[str, typing.Dict[str, typing.Any]] = {}

# Built by _build_index.
# parent -> name -> PARAMETER_CORE or the defining extension name
_INDEX: typing.Dict[str, typing.Dict[str, str]] = {}
# (parent, name) of each legacy row
_LEGACY: typing.Set[typing.Tuple[str, str]] = set()
# Object names (parents of parameter rows)
OBJECT_NAMES: typing.FrozenSet[str] = frozenset()
# Value set names (parents of value rows, e.g. "Event->type")
VALUE_SETS: typing.FrozenSet[str] = frozenset()


def _check_rows(
  definer : str,
  rows : typing.List[typing.Dict[str, typing.Any]],
  index : typing.Dict[str, typing.Dict[str, str]]
  ) -> None:
  """
  Check that no row name matches, case insensitively, a name already in the
  index or another of the rows under the same parent.

  Raises ValueError naming the collision.
  """
  lower_index = {
      parent: {name.lower(): (name, owner) for name, owner in names.items()}
      for parent, names in index.items()
    }
  for row in rows:
    parent_names = lower_index.setdefault(row["parent"], {})
    existing = parent_names.get(row["name"].lower(), None)
    if(existing is not None):
      raise ValueError(
        "\"{}\" name: \"{}\" under: \"{}\" collides with: \"{}\" defined by: \"{}\"".format(
        definer, row["name"], row["parent"], existing[0], existing[1]))
    parent_names[row["name"].lower()] = (row["name"], definer)


def _build_index() -> None:
  """
  Build the lookup index from CORE_ROWS and EXTENSIONS.

  Raises ValueError if names collide (see _check_rows).
  """
  global _INDEX
  global _LEGACY
  global OBJECT_NAMES
  global VALUE_SETS

  index: typing.Dict[str, typing.Dict[str, str]] = {}
  legacy: typing.Set[typing.Tuple[str, str]] = set()

  _check_rows(PARAMETER_CORE, CORE_ROWS, index)
  for row in CORE_ROWS:
    index.setdefault(row["parent"], {})[row["name"]] = PARAMETER_CORE
    if(row["legacy"]):
      legacy.add((row["parent"], row["name"]))

  for extension_name, extension in EXTENSIONS.items():
    _check_rows(extension_name, extension["rows"], index)
    for row in extension["rows"]:
      index.setdefault(row["parent"], {})[row["name"]] = extension_name

  _INDEX = index
  _LEGACY = legacy
  OBJECT_NAMES = frozenset([parent for parent in index if VALUE_SEPARATOR not in parent])
  VALUE_SETS = frozenset([parent for parent in index if VALUE_SEPARATOR in parent])


def register_extension(
  extension : typing.Dict[str, typing.Any],
  rows : typing.List[typing.Dict[str, typing.Any]]
  ) -> None:
  """
  Register a vCon extension and the parameter names and values it defines.

  Parameters:
    **extension** (dict) - name, description, change_controller,
      specification and critical (bool) of the extension
    **rows** (List[dict]) - parent, name and description of each parameter
      name or value it defines.  change_controller and specification default
      to those of the extension.  An extension may define rows under a parent
      which core does not define, for an Object or value set of its own.

  Raises ValueError if a field is missing, if a name collides with a core or
  other extension name under the same parent, including names which differ
  only in case, if the extension name differs only in case from a registered
  extension name, or if the extension is already registered with different
  content.  Registering the same extension again with identical content is
  allowed and has no effect.
  """
  for field in EXTENSION_FIELDS:
    if(field not in extension):
      raise ValueError("extension is missing: \"{}\"".format(field))

  name = extension["name"]
  new_extension = {field: extension[field] for field in EXTENSION_FIELDS}
  new_rows = []
  for row in rows:
    for field in ["parent", "name", "description"]:
      if(field not in row):
        raise ValueError("extension: \"{}\" row: {} is missing: \"{}\"".format(name, row, field))
    new_rows.append({
        "parent": row["parent"],
        "name": row["name"],
        "description": row["description"],
        "change_controller": row.get("change_controller", extension["change_controller"]),
        "specification": row.get("specification", extension["specification"]),
        "iana": True,
        "legacy": False
      })
  new_extension["rows"] = new_rows

  for registered_name, registered in EXTENSIONS.items():
    if(registered_name == name):
      if(registered == new_extension):
        return
      raise ValueError("extension: \"{}\" is already registered with different content".format(name))
    if(registered_name.lower() == name.lower()):
      raise ValueError("extension name: \"{}\" differs only in case from registered extension: \"{}\"".format(
        name, registered_name))

  EXTENSIONS[name] = new_extension
  try:
    _build_index()
  except ValueError:
    del EXTENSIONS[name]
    _build_index()
    raise


def unregister_extension(name : str) -> None:
  """
  Remove a registered extension and its rows.

  Raises ValueError if the extension is not registered.
  """
  if(name not in EXTENSIONS):
    raise ValueError("extension: \"{}\" is not registered".format(name))

  del EXTENSIONS[name]
  _build_index()


def _check_object_name(object_name : str) -> None:
  """ Raises ValueError if the Object name is not registered """
  if(object_name not in OBJECT_NAMES):
    raise ValueError(
      "\"{}\" is not a registered vCon Object name.  Must be one of: {}".format(
      object_name, sorted(OBJECT_NAMES)))


def get_parameter_extension(
  object_name : str,
  parameter_name : str
  ) -> typing.Union[str, None]:
  """
  Get the definer of the given parameter name in the given Object.

  Parameters:
    **object_name** (String) - the Object name, for example "-" or "Party"
    **parameter_name** (String) - the parameter name to look up

  Returns:
    PARAMETER_CORE (also for legacy 0.4.0 names), the defining extension
    name or None if the parameter name is not registered in the Object.

  Raises ValueError if the Object name is not registered.
  """
  _check_object_name(object_name)
  return(_INDEX[object_name].get(parameter_name, None))


def get_value_extension(
  object_name : str,
  parameter_name : str,
  value : str
  ) -> typing.Union[str, None]:
  """
  Get the definer of the given value of the given parameter in the given
  Object, for example the Event type value "join".

  Returns:
    PARAMETER_CORE (also for legacy 0.4.0 values), the defining extension
    name or None if the value is not registered.

  Raises ValueError if the parameter has no registered values.
  """
  value_set = "{}{}{}".format(object_name, VALUE_SEPARATOR, parameter_name)
  if(value_set not in VALUE_SETS):
    raise ValueError(
      "\"{}\" is not a registered value set.  Must be one of: {}".format(
      value_set, sorted(VALUE_SETS)))

  return(_INDEX[value_set].get(value, None))


def get_object_parameter_names(object_name : str) -> typing.List[str]:
  """
  Get all registered parameter names, core (including legacy) and extension
  defined, of the given Object, core names first in registry order.

  Raises ValueError if the Object name is not registered.
  """
  _check_object_name(object_name)
  return(list(_INDEX[object_name].keys()))


def is_legacy(parent : str, name : str) -> bool:
  """ True if the name under the given parent is a legacy 0.4.0 name """
  return((parent, name) in _LEGACY)


def is_critical(extension_name : str) -> bool:
  """
  True if the named extension is registered as critical, i.e. its name is
  to be listed in critical whenever it is used.  False for an unregistered
  name.
  """
  extension = EXTENSIONS.get(extension_name, None)
  return(extension is not None and extension["critical"] is True)


def get_rows(
  parent : typing.Union[str, None] = None
  ) -> typing.List[typing.Dict[str, typing.Any]]:
  """
  Get copies of the registry rows, core then extension rows, optionally only
  those under the given parent.  Extension rows have an added "extension"
  field with the extension name.
  """
  rows = [dict(row) for row in CORE_ROWS]
  for extension_name, extension in EXTENSIONS.items():
    rows.extend([dict(row, extension = extension_name) for row in extension["rows"]])

  if(parent is not None):
    rows = [row for row in rows if row["parent"] == parent]

  return(rows)


# Where each Object appears in the vCon JSON: Object name -> list of
# (containing Object name, parameter name).  The parameter value is the
# Object, an array of the Objects or, for SessionId, nested arrays of them.
OBJECT_LOCATIONS: typing.Dict[str, typing.List[typing.Tuple[str, str]]] = {
    "Party": [(VCON_OBJECT, "parties")],
    "Civicaddress": [("Party", "civicaddress")],
    "Dialog": [(VCON_OBJECT, "dialog")],
    "SessionId": [("Dialog", "session_id"), ("Session", "session_id")],
    "Redacted_segments": [("Dialog", "redacted_segments")],
    "Session": [(VCON_OBJECT, "sessions")],
    "Session_Reference": [("Session", "sessions")],
    "Event": [(VCON_OBJECT, "events")],
    "Attachment": [(VCON_OBJECT, "attachments")],
    "Analysis": [(VCON_OBJECT, "analysis")],
    "Redacted_from": [(VCON_OBJECT, "redacted_from")],
    "Amended_from": [(VCON_OBJECT, "amended_from")],
    "Redacted_string": [(VCON_OBJECT, "redacted_strings")]
  }


def _contained_objects(
  object_name : str
  ) -> typing.List[typing.Tuple[str, str]]:
  """ (parameter name, Object name) of the Objects contained in the given Object """
  return([(parameter_name, contained_name)
    for contained_name, locations in OBJECT_LOCATIONS.items()
    for container_name, parameter_name in locations
    if(container_name == object_name)])


def find_extensions(vcon_dict : typing.Dict[str, typing.Any]) -> typing.Dict[str, typing.List[str]]:
  """
  Find the extensions used in an unsigned vCon dict, and those it uses but
  does not list in its extensions and critical parameters.

  Every parameter name in each Object, and each value of a parameter with
  registered values (for example the Event type), is looked up in the
  registry.  Names and values in no registry are reported as unregistered
  with their location; they are never assigned to an extension.  The
  parameters of Objects defined by an extension are not looked into.

  Parameters:
    **vcon_dict** (dict) - the unsigned vCon, as a plain dict

  Returns:
    dict with the lists:
      **used** - names of the extensions used, in the order found
      **unlisted** - extensions used but not in the vCon extensions parameter
      **critical_unlisted** - extensions registered as critical which are
        used but not in the vCon critical parameter
      **unregistered** - location and name of each parameter or value in no
        registry, for example: '$.parties[0]: "my_param"' or
        '$.events[2].type: "my-event"'
  """
  used: typing.List[str] = []
  unregistered: typing.List[str] = []

  def add_used(definer : str) -> None:
    if(definer not in used):
      used.append(definer)

  def check_object(object_name : str, an_object : typing.Any, location : str) -> None:
    if(isinstance(an_object, list)):
      # an array of the Objects or, for SessionId, nested arrays
      for index, element in enumerate(an_object):
        check_object(object_name, element, "{}[{}]".format(location, index))
      return

    if(not isinstance(an_object, dict)):
      return

    object_index = _INDEX.get(object_name, {})
    for parameter_name, value in an_object.items():
      definer = object_index.get(parameter_name, None)
      if(definer is None):
        unregistered.append("{}: \"{}\"".format(location, parameter_name))
        continue
      if(definer != PARAMETER_CORE):
        add_used(definer)

      value_set = "{}{}{}".format(object_name, VALUE_SEPARATOR, parameter_name)
      if(value_set in VALUE_SETS and isinstance(value, str)):
        value_definer = _INDEX[value_set].get(value, None)
        if(value_definer is None):
          unregistered.append("{}.{}: \"{}\"".format(location, parameter_name, value))
        elif(value_definer != PARAMETER_CORE):
          add_used(value_definer)

    for parameter_name, contained_name in _contained_objects(object_name):
      if(parameter_name in an_object):
        check_object(contained_name, an_object[parameter_name],
          "{}.{}".format(location, parameter_name))

  check_object(VCON_OBJECT, vcon_dict, "$")

  listed = vcon_dict.get("extensions", None) or []
  listed_critical = vcon_dict.get("critical", None) or []
  return({
      "used": used,
      "unlisted": [name for name in used if(name not in listed)],
      "critical_unlisted": [name for name in used if(is_critical(name) and name not in listed_critical)],
      "unregistered": unregistered
    })


_build_index()
register_extension(CC_EXTENSION, CC_ROWS)
