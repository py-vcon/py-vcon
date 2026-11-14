# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" Unit tests for the base64url helpers in vcon.utils """

import base64
import pytest
import vcon
import vcon.utils


def test_base64url_encode_no_padding():
  assert(vcon.utils.base64url_encode(b"") == "")
  assert(vcon.utils.base64url_encode(b"a") == "YQ")
  assert(vcon.utils.base64url_encode(b"ab") == "YWI")
  assert(vcon.utils.base64url_encode(b"abc") == "YWJj")
  assert(vcon.utils.base64url_encode(b'{"alg":"RS256"}') == "eyJhbGciOiJSUzI1NiJ9")


def test_base64url_encode_url_safe_alphabet():
  # standard base64 would give "+/8="
  assert(vcon.utils.base64url_encode(b"\xfb\xff") == "-_8")
  assert(base64.b64encode(b"\xfb\xff") == b"+/8=")


@pytest.mark.parametrize("length", range(0, 8))
def test_base64url_round_trip(length):
  data = bytes((250 + index) % 256 for index in range(length))
  encoded = vcon.utils.base64url_encode(data)
  assert("=" not in encoded)
  assert(vcon.utils.base64url_decode(encoded) == data)
  assert(vcon.utils.base64url_decode(encoded.encode("utf-8")) == data)


def test_base64url_decode_with_or_without_padding():
  assert(vcon.utils.base64url_decode("YQ") == b"a")
  assert(vcon.utils.base64url_decode("YQ==") == b"a")
  assert(vcon.utils.base64url_decode(b"YWI") == b"ab")
  assert(vcon.utils.base64url_decode(b"YWI=") == b"ab")
  assert(vcon.utils.base64url_decode("-_8") == b"\xfb\xff")
  assert(vcon.utils.base64url_decode("") == b"")


def test_inline_attachment_base64url_body():
  body = b"\x89PNG\r\n\x1a\n\xfb\xff"
  v = vcon.Vcon()
  v.set_party_parameter("tel", "+15551110000")
  index = v.add_attachment_inline(body, "2022-06-21T13:53:26-04:00", 0, "image/png", "a.png")
  attachment = v.attachments[index]
  assert(attachment["encoding"] == "base64url")
  assert(attachment["body"] == "iVBORw0KGgr7_w")
  assert(vcon.utils.base64url_decode(attachment["body"]) == body)
