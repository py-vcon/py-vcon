# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" Unit tests for Redacted_string Objects and redacting text with markers """

import pytest
import vcon
import vcon.parameter_registry
import tests.common_utils

START = "2022-06-21T13:53:26-04:00"
PHONE = "617 555 1234"


def make_vcon() -> vcon.Vcon:
  v = vcon.Vcon()
  v.set_uuid("example.com")
  v.set_party_parameter("tel", "+15551110000")
  v.set_party_parameter("tel", "+15552220000")
  return(v)


def spans_of(text : str, *values_labels) -> list:
  """ (start, end, label) of the first occurrence of each value in text """
  spans = []
  for value, label in values_labels:
    start = text.index(value)
    spans.append((start, start + len(value), label))
  return(spans)


def test_add_redacted_string():
  v = make_vcon()
  assert(v.add_redacted_string("PHONE_NUMBER", "555-1234") == 1)
  assert(v.redacted_strings == [{"ref": 1, "type": "PHONE_NUMBER", "orig": "555-1234",
    "marker": "__REDACTED_REF_1__"}])

  # the same orig returns its ref and adds nothing
  assert(v.add_redacted_string("PERSON", "555-1234") == 1)
  assert(len(v.redacted_strings) == 1)


def test_refs_continue_from_highest():
  v = make_vcon()
  v._vcon_dict["redacted_strings"] = [{"ref": 3}, {"ref": 7}, {"ref": 2}]
  assert(v.add_redacted_string("PERSON", "Alice") == 8)
  assert(v.redacted_strings[3]["marker"] == "__REDACTED_REF_8__")


def test_no_ref_limit():
  """ -05 caps ref at 99999 for digit parsing, which the marker suffix makes unnecessary (not schema valid) """
  v = make_vcon()
  v._vcon_dict["redacted_strings"] = [{"ref": 99999}]
  assert(v.add_redacted_string("PERSON", "Alice") == 100000)
  assert(v.redacted_strings[1]["marker"] == "__REDACTED_REF_100000__")


def test_marker_registry_row():
  rows = [row for row in vcon.parameter_registry.get_rows("Redacted_string") if(row["name"] == "marker")]
  assert(len(rows) == 1)
  assert(rows[0]["iana"] is False and rows[0]["legacy"] is False)
  assert("proposed" in rows[0]["description"])
  assert(vcon.Vcon.get_parameter_extension("Redacted_string", "marker") == vcon.Vcon.PARAMETER_CORE)


def test_find_by_marker():
  v = make_vcon()
  for ref in range(1, 12):
    v.add_redacted_string("PERSON", "name {}".format(ref))
  found = v.find_redacted_strings("call __REDACTED_REF_1__ and __REDACTED_REF_11__ today, __REDACTED_REF_1__")
  assert([redacted_string["ref"] for redacted_string in found] == [1, 11, 1])


def test_find_without_marker():
  """ -05 Redacted_strings from another producer have no marker """
  v = make_vcon()
  v._vcon_dict["redacted_strings"] = [{"ref": 1, "type": "PERSON"}]
  assert([rs["ref"] for rs in v.find_redacted_strings("I am __REDACTED_REF_1, hello")] == [1])
  # only 1 exists: __REDACTED_REF_15 is ref 1 followed by the text "5"
  assert([rs["ref"] for rs in v.find_redacted_strings("__REDACTED_REF_15")] == [1])

  v._vcon_dict["redacted_strings"].append({"ref": 15, "type": "PERSON"})
  assert([rs["ref"] for rs in v.find_redacted_strings("__REDACTED_REF_15")] == [15])

  # no entry: literal text
  assert(v.find_redacted_strings("__REDACTED_REF_2 and __REDACTED_REF_x") == [])


def test_redact_text():
  v = make_vcon()
  text = "my number is {}, thanks".format(PHONE)
  redacted = v.redact_text(text, spans_of(text, (PHONE, "PHONE_NUMBER")))
  assert(redacted == "my number is __REDACTED_REF_1__, thanks")
  assert(v.redacted_strings == [{"ref": 1, "type": "PHONE_NUMBER", "orig": PHONE,
    "marker": "__REDACTED_REF_1__"}])
  assert(v.find_redacted_strings(redacted) == v.redacted_strings)


def test_same_value_in_two_dialogs():
  v = make_vcon()
  first = "call me at {}".format(PHONE)
  second = "Alice said {} again".format(PHONE)
  assert(v.redact_text(first, spans_of(first, (PHONE, "PHONE_NUMBER"))) == "call me at __REDACTED_REF_1__")
  assert(v.redact_text(second, spans_of(second, ("Alice", "PERSON"), (PHONE, "PHONE_NUMBER"))) ==
    "__REDACTED_REF_2__ said __REDACTED_REF_1__ again")
  assert([(rs["ref"], rs["orig"]) for rs in v.redacted_strings] == [(1, PHONE), (2, "Alice")])


def test_value_labeled_two_ways():
  v = make_vcon()
  text = "{} or {}".format(PHONE, PHONE)
  second_start = text.rindex(PHONE)
  redacted = v.redact_text(text, [(0, len(PHONE), "PHONE_NUMBER"),
    (second_start, second_start + len(PHONE), "INTEGER")])
  assert(redacted == "__REDACTED_REF_1__ or __REDACTED_REF_1__")
  assert(v.redacted_strings == [{"ref": 1, "type": "PHONE_NUMBER", "orig": PHONE,
    "marker": "__REDACTED_REF_1__"}])


def test_literal_marker_in_text_skipped():
  v = make_vcon()
  text = "the text __REDACTED_REF_1__ is literal, Bob"
  redacted = v.redact_text(text, spans_of(text, ("Bob", "PERSON")))
  assert(redacted == "the text __REDACTED_REF_1__ is literal, __REDACTED_REF_2__")
  assert(v.redacted_strings[0]["ref"] == 2)


def test_overlapping_and_empty_spans_ignored():
  v = make_vcon()
  text = "Alice Smith"
  redacted = v.redact_text(text, [(0, 11, "PERSON"), (6, 11, "PERSON"), (3, 3, "X"), (6, 99, "Y")])
  assert(redacted == "__REDACTED_REF_1__")
  assert(len(v.redacted_strings) == 1)


def test_redacted_vcon_schema_valid():
  v = make_vcon()
  text = "my number is {}".format(PHONE)
  redacted = v.redact_text(text, spans_of(text, (PHONE, "PHONE_NUMBER")))
  v.add_text_dialog_inline(redacted, START, 0, 0, vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  tests.common_utils.assert_valid_vcon(v.dumpd())


@pytest.mark.asyncio
@pytest.mark.parametrize("keep", [False, True])
async def test_jq_redaction_orig(keep):
  v = make_vcon()
  text = "my number is {}".format(PHONE)
  v.add_text_dialog_inline(v.redact_text(text, spans_of(text, (PHONE, "PHONE_NUMBER"))), START, 0, 0,
    vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  options = {"jq_redaction_query": ".", "redaction_type_label": "PII", "uuid_domain": "example.com"}
  if(keep):
    options["keep_redacted_string_orig"] = True

  redacted = await v.jq_redaction(options)
  if(keep):
    assert(redacted.redacted_strings[0]["orig"] == PHONE)
  else:
    assert(redacted.redacted_strings == [{"ref": 1, "type": "PHONE_NUMBER", "marker": "__REDACTED_REF_1__"}])
  # the input keeps orig
  assert(v.redacted_strings[0]["orig"] == PHONE)
  tests.common_utils.assert_valid_vcon(redacted.dumpd())
