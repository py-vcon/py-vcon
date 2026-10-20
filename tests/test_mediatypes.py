# Copyright (C) 2026 SIPez LLC.  All rights reserved.
""" Unit tests for Vcon media type / file extension lookups """
import pytest
import vcon


def test_existing_extension_mappings_unchanged():
  """ Mappings that existed before the media type additions are unchanged """
  assert(vcon.Vcon.get_media_type("a.txt") == vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  assert(vcon.Vcon.get_media_type("a.text") == vcon.Vcon.MEDIATYPE_TEXT_PLAIN)
  assert(vcon.Vcon.get_media_type("a.png") == vcon.Vcon.MEDIATYPE_IMAGE_PNG)
  assert(vcon.Vcon.get_media_type("a.wav") == "audio/x-wav")
  assert(vcon.Vcon.get_media_type("a.mp3") == "audio/x-mp3")
  assert(vcon.Vcon.get_media_type("a.mp4") == "video/x-mp4")

  assert(vcon.Vcon.get_media_extension(vcon.Vcon.MEDIATYPE_TEXT_PLAIN) == ".txt")
  assert(vcon.Vcon.get_media_extension(vcon.Vcon.MEDIATYPE_IMAGE_PNG) == ".png")
  assert(vcon.Vcon.get_media_extension("audio/x-wav") == ".wav")
  assert(vcon.Vcon.get_media_extension("audio/x-mp3") == ".mp3")
  assert(vcon.Vcon.get_media_extension("video/x-mp4") == ".mp4")


@pytest.mark.parametrize("media_type,extension", [
    ("audio/x-mp4", ".m4a"),
    ("audio/ogg", ".ogg"),
    ("audio/flac", ".flac"),
    ("video/ogg", ".ogv"),
  ])
def test_new_media_types_both_directions(media_type, extension):
  """ New media types map to an extension and back """
  assert(vcon.Vcon.get_media_extension(media_type) == extension)
  assert(vcon.Vcon.get_media_type("recording" + extension) == media_type)


def test_new_media_type_constants():
  """ Constants for the vCon spec audio types """
  assert(vcon.Vcon.MEDIATYPE_AUDIO_MP4 == "audio/x-mp4")
  assert(vcon.Vcon.MEDIATYPE_AUDIO_OGG == "audio/ogg")
  assert(vcon.Vcon.MEDIATYPE_AUDIO_FLAC == "audio/flac")
  assert(vcon.Vcon.MEDIATYPE_VIDEO_OGG == "video/ogg")


@pytest.mark.parametrize("media_type,extension,spec_media_type", [
    ("audio/wav", ".wav", "audio/x-wav"),
    ("audio/mpeg", ".mp3", "audio/x-mp3"),
    ("audio/mp4", ".m4a", "audio/x-mp4"),
  ])
def test_iana_aliases_lookup_only(media_type, extension, spec_media_type):
  """
  Common IANA spellings map to an extension, but the extension maps back
  to the vCon spec media type.
  """
  assert(vcon.Vcon.get_media_extension(media_type) == extension)
  assert(vcon.Vcon.get_media_type("recording" + extension) == spec_media_type)


def test_extension_case_insensitive():
  """ File extension lookup ignores case """
  assert(vcon.Vcon.get_media_type("RECORDING.OGG") == "audio/ogg")
  assert(vcon.Vcon.get_media_type("Recording.Flac") == "audio/flac")


def test_unknown_media_type_raises():
  """ Unknown media types and extensions still raise """
  with pytest.raises(Exception, match = "extension not defined"):
    vcon.Vcon.get_media_extension("audio/x-unknown")
  with pytest.raises(Exception, match = "Media type not defined"):
    vcon.Vcon.get_media_type("recording.xyz")


@pytest.mark.parametrize("media_type", [
    "audio/ogg",
    "audio/flac",
    "audio/x-mp4",
    "video/ogg",
  ])
def test_object_encoding_guess_for_binary_types(media_type):
  """ Missing encoding is guessed as base64url for binary media types """
  assert(vcon.Vcon.get_object_encoding({"mediatype": media_type}, "dialog[0]") == "base64url")


def test_object_encoding_guess_for_text():
  """ Missing encoding is guessed as none for text """
  assert(vcon.Vcon.get_object_encoding({"mediatype": "text/plain"}, "dialog[0]") == "none")

