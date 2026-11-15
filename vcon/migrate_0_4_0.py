# Copyright (C) 2026 SIPez LLC.  All rights reserved.
"""
Conversion of 0.4.0 vCons to the vCon 0.5.0 syntax (draft-ietf-vcon-vcon-core-05).

The rules are those of section 9 of the 0.4.0 to 0.5.0 change log:
Session Objects are built from the Dialog Objects, party_history becomes
Event Objects, transfer Dialog Objects become transfer Event Objects and
empty Dialog Objects, the parties of text and incomplete Dialog Objects are
reduced to the sender, email threads whose receivers change get child
Session Objects, originator moves to the Session Objects, and redacted and
amended are renamed redacted_from and amended_from.

A recording-set Dialog Object is not converted: VconConversionError is
raised.  Each case where the result is knowingly invalid or loses
information is converted and reported with a VconConversionWarning naming
the Object.
"""

import copy
import datetime
import logging
import typing
import warnings
import vcon.parameter_registry
import vcon.utils

logger = logging.getLogger(__name__)


class VconConversionError(Exception):
  """ A 0.4.0 vCon which the converter does not convert, e.g. one with a recording-set Dialog Object """


class VconConversionWarning(UserWarning):
  """ A converted vCon which is knowingly invalid or has lost information """


SESSION_PARAMETER_ORDER = ["start", "duration", "parties", "originator", "session_id", "sessions", "dialog"]

TRANSFER_PARTY_ROLES = ["transferor", "transferee", "transfer_target"]

TRANSFER_DIALOG_ROLES = ["original", "consultation", "target_dialog"]


def migrate_0_4_0_vcon(vcon_dict : typing.Dict[str, typing.Any]) -> typing.Dict[str, typing.Any]:
  """
  Convert an unsigned 0.4.0 vCon dict to the vCon 0.5.0 syntax.

  The given dict is not changed; a converted copy is returned.  The uuid
  is kept, vcon is set to "0.5.0" and updated_at is set to now.

  Parameters:
    **vcon_dict** (dict) - unsigned form 0.4.0 vCon

  Returns:
    the converted vCon dict

  Raises VconConversionError, leaving the given dict unchanged, for a
  recording-set Dialog Object or a Dialog Object with a recordings or
  recording_set parameter.  Emits a VconConversionWarning for each case
  where the result is knowingly invalid or has lost information.
  """
  result = copy.deepcopy(vcon_dict)
  dialogs = result.get("dialog", None) or []

  for dialog_index, dialog in enumerate(dialogs):
    if(dialog.get("type", None) == "recording-set" or "recordings" in dialog or "recording_set" in dialog):
      raise VconConversionError("dialog[{}] is or references a recording-set Dialog Object,"
        " which is not converted".format(dialog_index))

  # The 0.4.0 parties and originator, before they are reduced and removed
  original_parties = {dialog_index: vcon.utils.flatten_party_indices(dialog.get("parties", None))
    for dialog_index, dialog in enumerate(dialogs)}
  originators = {dialog_index: dialog.get("originator", None)
    for dialog_index, dialog in enumerate(dialogs)}

  converter = _Converter(result, original_parties, originators)
  converter.build_sessions()
  converter.group_text_dialogs()
  converter.convert_party_history()
  converter.convert_transfers()
  converter.reduce_text_parties()
  converter.fill_sessions()
  converter.remove_references()
  converter.rename_and_label()
  return(result)


class _Converter():
  """ The state of one conversion; the methods are applied in the order of migrate_0_4_0_vcon """

  def __init__(
    self,
    result : typing.Dict[str, typing.Any],
    original_parties : typing.Dict[int, typing.List[int]],
    originators : typing.Dict[int, typing.Any]
    ):
    self.result = result
    self.dialogs = result.get("dialog", None) or []
    self.original_parties = original_parties
    self.originators = originators
    self.sessions: typing.List[typing.Dict[str, typing.Any]] = []
    self.events: typing.List[typing.Dict[str, typing.Any]] = []
    # Session index holding each Dialog Object listed by a Session
    self.holder_of: typing.Dict[int, int] = {}
    self.top: typing.Union[int, None] = None
    self.transfers = [dialog_index for dialog_index, dialog in enumerate(self.dialogs)
      if(dialog.get("type", None) == "transfer")]
    # Session index created for each Dialog index a transfer references
    self.transfer_session_of: typing.Dict[int, int] = {}
    # usable Dialog index, or None, of each (transfer index, role), found once
    self.references: typing.Dict[typing.Tuple[int, str], typing.Union[int, None]] = {}


  def add_session(self, session : typing.Dict[str, typing.Any]) -> int:
    self.sessions.append(session)
    return(len(self.sessions) - 1)


  def dialog_sort_key(self, dialog_index : int) -> typing.Tuple[int, typing.Any, int]:
    """ start order, falling back to array order for a Dialog Object without start """
    start = self.dialogs[dialog_index].get("start", None)
    if(start is None):
      return((1, 0, dialog_index))
    return((0, vcon.utils.date_to_datetime(start), dialog_index))


  def valid_dialog_reference(self, transfer_index : int, role : str) -> typing.Union[int, None]:
    """ the Dialog index a transfer references in the given role, None if absent or not a usable Dialog """
    if((transfer_index, role) not in self.references):
      self.references[(transfer_index, role)] = self.find_dialog_reference(transfer_index, role)
    return(self.references[(transfer_index, role)])


  def find_dialog_reference(self, transfer_index : int, role : str) -> typing.Union[int, None]:
    dialog_index = self.dialogs[transfer_index].get(role, None)
    if(dialog_index is None):
      return(None)

    if(not isinstance(dialog_index, int) or isinstance(dialog_index, bool) or
      dialog_index < 0 or dialog_index >= len(self.dialogs) or
      len(self.dialogs[dialog_index]) == 0 or
      self.dialogs[dialog_index].get("type", None) == "transfer"):
      self.warn("dialog[{}] {}: {} is not a recording, text or incomplete Dialog Object."
        "  It is treated as absent.".format(transfer_index, role, dialog_index))
      return(None)

    return(dialog_index)


  @staticmethod
  def warn(message : str) -> None:
    logger.warning(message)
    warnings.warn(message, VconConversionWarning, stacklevel = 4)


  def build_sessions(self) -> None:
    """
    M4: without transfers, one Session Object listing every Dialog Object.
    M5, M12, P1, M13: with transfers, a child Session Object for each Dialog
    Object a transfer references, and a top level Session Object listing
    the others and referencing the children.
    """
    listed = [dialog_index for dialog_index, dialog in enumerate(self.dialogs)
      if(len(dialog) > 0 and dialog.get("type", None) != "transfer")]
    if(len(listed) == 0 and len(self.transfers) == 0):
      return

    self.top = self.add_session({})
    referenced: typing.List[int] = []
    for transfer_index in self.transfers:
      for role in TRANSFER_DIALOG_ROLES:
        dialog_index = self.valid_dialog_reference(transfer_index, role)
        if(dialog_index is not None and dialog_index not in referenced):
          referenced.append(dialog_index)

    for dialog_index in referenced:
      child = self.add_session({"dialog": [dialog_index]})
      self.transfer_session_of[dialog_index] = child
      self.holder_of[dialog_index] = child
      self.add_child(self.top, child)

    top_dialogs = [dialog_index for dialog_index in listed if(dialog_index not in referenced)]
    if(len(top_dialogs) > 0):
      self.sessions[self.top]["dialog"] = top_dialogs
    for dialog_index in top_dialogs:
      self.holder_of[dialog_index] = self.top


  def add_child(self, parent : int, child : int) -> None:
    self.sessions[parent].setdefault("sessions", []).append({"session": child, "type": "child"})


  def group_text_dialogs(self) -> None:
    """
    M18: the text Dialog Objects of the top level Session Object, in start
    order, stay in it if every message has the same receivers (all of its
    0.4.0 parties).  Otherwise each run of consecutive messages with the same
    receivers moves to a child Session Object whose parties are those receivers.
    """
    if(self.top is None):
      return

    top_session = self.sessions[self.top]
    texts = sorted([dialog_index for dialog_index in top_session.get("dialog", [])
      if(self.dialogs[dialog_index].get("type", None) == "text")], key = self.dialog_sort_key)

    runs: typing.List[typing.List[int]] = []
    for dialog_index in texts:
      if(len(runs) > 0 and
        set(self.original_parties[runs[-1][0]]) == set(self.original_parties[dialog_index])):
        runs[-1].append(dialog_index)
      else:
        runs.append([dialog_index])

    if(len(runs) <= 1):
      return

    top_session["dialog"] = [dialog_index for dialog_index in top_session["dialog"]
      if(dialog_index not in texts)]
    if(len(top_session["dialog"]) == 0):
      del top_session["dialog"]

    for run in runs:
      receivers: typing.List[int] = []
      for dialog_index in run:
        for party_index in self.original_parties[dialog_index]:
          if(party_index not in receivers):
            receivers.append(party_index)
      child = self.add_session({"parties": receivers, "dialog": run})
      self.add_child(self.top, child)
      for dialog_index in run:
        self.holder_of[dialog_index] = child


  def convert_party_history(self) -> None:
    """
    M1, M2, D8: each party_history entry becomes an Event Object of the
    Session Object holding its Dialog Object, else the top level one.
    """
    for dialog_index, dialog in enumerate(self.dialogs):
      history = dialog.pop("party_history", None)
      if(history is None):
        continue

      session_index = self.holder_of.get(dialog_index, self.top)
      for entry in history:
        event: typing.Dict[str, typing.Any] = {}
        event["type"] = entry.get("event", None)
        if("time" in entry):
          event["time"] = entry["time"]
        if(session_index is not None):
          event["sessions"] = session_index
        for name, value in entry.items():
          if(name not in ("event", "time")):
            event[name] = value
        self.events.append(event)


  def transfer_party(self, transfer_index : int, role : str) -> int:
    """ D2, D3: the party of a transfer role, an appended empty Party Object if absent """
    parties = self.result.setdefault("parties", [])
    party_index = self.dialogs[transfer_index].get(role, None)
    if(isinstance(party_index, int) and not isinstance(party_index, bool) and
      0 <= party_index < len(parties)):
      return(party_index)

    if(party_index is not None):
      self.warn("dialog[{}] {}: {} is not a party.  It is treated as absent.".format(
        transfer_index, role, party_index))
    parties.append({})
    return(len(parties) - 1)


  def dialog_time(self, dialog_index : typing.Union[int, None], at_end : bool) -> typing.Union[str, None]:
    """ the start, or start plus duration, of a Dialog Object; None if not known """
    if(dialog_index is None):
      return(None)
    dialog = self.dialogs[dialog_index]
    start = dialog.get("start", None)
    if(start is None):
      return(None)
    if(not at_end):
      return(vcon.utils.cannonize_date(start))
    duration = dialog.get("duration", None)
    if(duration is None):
      return(None)
    return(vcon.utils.cannonize_date(vcon.utils.date_to_datetime(start) + datetime.timedelta(seconds = duration)))


  def convert_transfers(self) -> None:
    """
    M5 to M15, D1 to D4, P2: each transfer Dialog Object becomes transfer
    Event Objects (section 9.4), then an empty Dialog Object (M6, M7).
    """
    for transfer_index in self.transfers:
      transfer = self.dialogs[transfer_index]
      original = self.valid_dialog_reference(transfer_index, "original")
      consultation = self.valid_dialog_reference(transfer_index, "consultation")
      target = self.valid_dialog_reference(transfer_index, "target_dialog")

      if(original is not None):
        original_session = self.transfer_session_of[original]
      else:
        # D3: a placeholder Session Object for the unknown original call
        original_session = self.add_session({})

      # D1: an absent target_dialog is treated as abandoned
      if(consultation is None and target is not None):
        event_types = ["blind-transfer"]
      elif(consultation is not None and target is not None):
        event_types = ["consultation-start", "consultative-transfer"]
      elif(consultation is not None):
        event_types = ["consultation-start", "transfer-abandoned"]
      else:
        event_types = ["transfer-abandoned"]

      transferor = self.transfer_party(transfer_index, "transferor")
      transferee = self.transfer_party(transfer_index, "transferee")
      # transfer_target is optional only for transfer-abandoned
      transfer_target = None
      if(event_types != ["transfer-abandoned"] or transfer.get("transfer_target", None) is not None):
        transfer_target = self.transfer_party(transfer_index, "transfer_target")

      transfer_start = self.dialog_time(transfer_index, False)
      times = {
        # M11
        "blind-transfer": transfer_start,
        "consultation-start": transfer_start,
        # M15
        "consultative-transfer": self.dialog_time(target, False),
        # M14, D4
        "transfer-abandoned": (self.dialog_time(consultation, True) if(consultation is not None)
          else transfer_start)
        }

      for event_type in event_types:
        event: typing.Dict[str, typing.Any] = {"type": event_type}
        if(times[event_type] is not None):
          event["time"] = times[event_type]
        else:
          # P2
          self.warn("dialog[{}] {} Event has no usable time.  It is converted without time,"
            " which is invalid.".format(transfer_index, event_type))
        event["sessions"] = original_session
        event["party"] = transferor
        event["transferee"] = transferee
        if(transfer_target is not None):
          event["transfer_target"] = transfer_target
        if(consultation is not None):
          event["consultation"] = self.transfer_session_of[consultation]
        if(event_type in ("blind-transfer", "consultative-transfer")):
          event["target_session"] = self.transfer_session_of[target]
        self.events.append(event)


  def reduce_text_parties(self) -> None:
    """
    M17: a text or incomplete Dialog Object with more than one party keeps
    only its originator if set, else its first party.
    """
    for dialog_index, dialog in enumerate(self.dialogs):
      if(dialog.get("type", None) not in ("text", "incomplete")):
        continue
      parties = self.original_parties[dialog_index]
      if(len(parties) <= 1):
        continue
      originator = self.originators[dialog_index]
      dialog["parties"] = [originator if(originator is not None) else parties[0]]


  def session_dialogs(self, session_index : int) -> typing.List[int]:
    """ the Dialog indices of a Session Object and of its child Session Objects """
    session = self.sessions[session_index]
    dialog_indices = list(session.get("dialog", None) or [])
    for reference in session.get("sessions", None) or []:
      if(reference.get("type", None) == "child"):
        for dialog_index in self.session_dialogs(reference["session"]):
          if(dialog_index not in dialog_indices):
            dialog_indices.append(dialog_index)
    return(dialog_indices)


  def fill_sessions(self) -> None:
    """
    M10, D6, D5, M16: the start, duration, parties and originator of each
    Session Object, over its Dialog Objects and those of its children.
    """
    for session_index, session in enumerate(self.sessions):
      dialog_indices = sorted(self.session_dialogs(session_index), key = self.dialog_sort_key)
      if(len(dialog_indices) == 0):
        continue

      # M10, D6
      starts = [vcon.utils.date_to_datetime(self.dialogs[dialog_index]["start"])
        for dialog_index in dialog_indices if(self.dialogs[dialog_index].get("start", None) is not None)]
      if(len(starts) > 0):
        start = min(starts)
        session["start"] = vcon.utils.cannonize_date(start)
        durations = [self.dialogs[dialog_index].get("duration", None) for dialog_index in dialog_indices]
        if(len(starts) == len(dialog_indices) and None not in durations):
          end = max([vcon.utils.date_to_datetime(self.dialogs[dialog_index]["start"]) +
            datetime.timedelta(seconds = self.dialogs[dialog_index]["duration"])
            for dialog_index in dialog_indices])
          duration = (end - start).total_seconds()
          session["duration"] = int(duration) if(float(duration).is_integer()) else duration

      # D5: the parties of a text run child are already its receivers
      if("parties" not in session):
        parties: typing.List[int] = []
        for dialog_index in dialog_indices:
          for party_index in self.original_parties[dialog_index]:
            if(party_index not in parties):
              parties.append(party_index)
        for event in self.events:
          if(event.get("sessions", None) == session_index and isinstance(event.get("party", None), int)
            and event["party"] not in parties):
            parties.append(event["party"])
        if(len(parties) > 0):
          session["parties"] = parties

      # M16: the originator of the chronologically first Dialog Object having one
      explicit = [(dialog_index, self.originators[dialog_index]) for dialog_index in dialog_indices
        if(self.originators[dialog_index] is not None)]
      if(len(explicit) > 0):
        originator = explicit[0][1]
        if(originator != (session.get("parties", None) or [None])[0]):
          session["originator"] = originator
        # text and incomplete Dialog Objects keep their originator as their parties (M17)
        lost = [(dialog_index, value) for dialog_index, value in explicit[1:]
          if(value != originator and self.dialogs[dialog_index].get("type", None) not in ("text", "incomplete"))]
        if(len(lost) > 0):
          self.warn("sessions[{}] originator: {} is kept.  The different originator of: {} is lost.".format(
            session_index, originator,
            ", ".join(["dialog[{}]: {}".format(dialog_index, value) for dialog_index, value in lost])))

      ordered = {name: session[name] for name in SESSION_PARAMETER_ORDER if(name in session)}
      session.clear()
      session.update(ordered)

    for dialog in self.dialogs:
      dialog.pop("originator", None)


  def remove_references(self) -> None:
    """
    M6, M20: each transfer Dialog Object is replaced by an empty Dialog
    Object and Analysis and Attachment dialog references to it are removed.
    """
    for transfer_index in self.transfers:
      self.dialogs[transfer_index] = {}

    for analysis in self.result.get("analysis", None) or []:
      self.remove_dialog_reference(analysis)

    for attachment_index, attachment in enumerate(self.result.get("attachments", None) or []):
      self.remove_dialog_reference(attachment)
      if("dialog" not in attachment and "session" not in attachment):
        self.warn("attachments[{}] references neither a Dialog nor a Session Object,"
          " which is invalid.".format(attachment_index))


  def remove_dialog_reference(self, obj : typing.Dict[str, typing.Any]) -> None:
    """ remove the references to transfer Dialog Objects from the dialog parameter of the given Object """
    reference = obj.get("dialog", None)
    if(reference is None):
      return
    if(isinstance(reference, list)):
      kept = [dialog_index for dialog_index in reference if(dialog_index not in self.transfers)]
      if(len(kept) == 0):
        del obj["dialog"]
      elif(len(kept) != len(reference)):
        obj["dialog"] = kept
    elif(reference in self.transfers):
      del obj["dialog"]


  def rename_and_label(self) -> None:
    """ Sessions and Events in place, M22, M24, vcon and updated_at """
    result = self.result
    if(len(self.sessions) > 0):
      result["sessions"] = (result.get("sessions", None) or []) + self.sessions
    if(len(self.events) > 0):
      result["events"] = (result.get("events", None) or []) + self.events

    # M22
    if("redacted" in result and "amended" in result):
      self.warn("redacted and amended are both present.  Both are renamed,"
        " though redacted_from and amended_from are mutually exclusive.")
    if("redacted" in result):
      if(not isinstance(result["redacted"], dict) or result["redacted"].get("type", None) is None):
        self.warn("redacted has no type.  It is renamed redacted_from without type, which is invalid.")
      result["redacted_from"] = result.pop("redacted")
    if("amended" in result):
      result["amended_from"] = result.pop("amended")

    result["vcon"] = "0.5.0"
    result["updated_at"] = vcon.utils.cannonize_date(datetime.datetime.now(datetime.timezone.utc))

    # M24
    found = vcon.parameter_registry.find_extensions(result)
    for list_name, found_name in [("extensions", "unlisted"), ("critical", "critical_unlisted")]:
      for extension_name in found[found_name]:
        names = result.setdefault(list_name, [])
        if(extension_name not in names):
          names.append(extension_name)
