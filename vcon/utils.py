# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" Utilities and helper functions for the vcon package """

import datetime
import re
import os
import tempfile
import email.utils
import typing
import ffmpeg
import sox

def epoch_to_rfc2822(time : typing.Union[int, float]) -> str:
  """ Returns RFC2822 date for given epoch time """
  date_string = email.utils.formatdate(float(time))
  return(date_string)

def epoch_to_rfc3339(time : typing.Union[int, float]) -> str:
  """ Returns RFC3339 date for given epoch time """
  # This does the epoch conversion to local time zone.
  date_time = datetime.datetime.utcfromtimestamp(float(time))
  # Assume UTC
  #print("datatime: {} tz: {}".format(date_time, date_time.tzinfo))
  date_time = date_time.replace(tzinfo = datetime.timezone.utc)
  #print("datatime utc: {} tz: {}".format(date_time, date_time.tzinfo))
  date_string = date_time.isoformat('T', timespec='milliseconds')
  return(date_string)

def cannonize_date(date : typing.Union[int, float, str, datetime.datetime]) -> str:
  """
  Convert date to cannonical RFC3339 date format string

  Parameters:
    date Union[int, float, str, datetime.datetime]: date to be cannonized.
    int or float are seconds since epoch.  String form can be RFC2822 or RFC3339 date string
  """
  if(isinstance(date, (int, float))):
    #RFC 3339
    date_string = epoch_to_rfc3339(date)
    #RFC 2822
    #date_string = epoch_to_rfc2822(date)

  elif(isinstance(date, str)):
    # Is it already RFC3339
    try:
      #epoch_time = (datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%fZ") - datetime.datetime(1970, 1, 1)).total_seconds()
      #epoch_time = (datetime.datetime.fromisoformat(date) - datetime.datetime(1970, 1, 1)).total_seconds()
      epoch = datetime.datetime(1970, 1, 1)
      epoch = epoch.replace(tzinfo = datetime.timezone.utc)
      epoch = epoch.astimezone(datetime.timezone.utc)

      date = date.strip()
      # the SIO parsing does not seem to like Zulu time
      if(date[-1].lower() == "z"):
        date = date[:-1] + "-00:00"

      epoch_time = (datetime.datetime.fromisoformat(date) - epoch).total_seconds()
      #print("epoch: {}".format(epoch_time))

    except ValueError as rfc3339_error:
      #raise rfc3339_error
      # Nope, not RFC3339

      # Is it an RFC2822 date?
      try:
        date_time_seconds = email.utils.parsedate_to_datetime(date)
        epoch_time = (date_time_seconds - datetime.datetime(1970, 1, 1)).total_seconds()
        #print("epoch: {}".format(epoch_time))

      except Exception as rfc2822_error:
        raise AttributeError("Date string: '{}' not recognized as RFC3339 or RFC2822 formatted date.".format(
          date))

    date_string = epoch_to_rfc3339(epoch_time)

  elif(isinstance(date, datetime.datetime)):
    epoch = datetime.datetime(1970, 1, 1)
    epoch = epoch.replace(tzinfo = datetime.timezone.utc)
    epoch = epoch.astimezone(datetime.timezone.utc)

    #print("date tc: {}".format(date.tzinfo))
    # No time zone, assume UTC
    if(date.tzinfo is None):
      date = date.replace(tzinfo = datetime.timezone.utc)
      #print("date tc: {}".format(date.tzinfo))

    epoch_time = (date - epoch).total_seconds()
    date_string = epoch_to_rfc3339(epoch_time)
  else:
    raise AttributeError("unsupported type: {} value: {} for date".format(type(date), date))

  return(date_string)


def date_to_datetime(date : typing.Union[int, float, str, datetime.datetime]) -> datetime.datetime:
  """
  Convert date to a time zone aware datetime in UTC.

  Parameters:
    date Union[int, float, str, datetime.datetime]: date to be converted.
    int or float are seconds since epoch.  String form can be RFC2822 or RFC3339 date string

  Returns:
    datetime.datetime in UTC
  """
  return(datetime.datetime.fromisoformat(cannonize_date(date)))


def unfold_header(header_value : typing.Union[str, None]) -> typing.Union[str, None]:
  """
  Unfold a folded SMTP header value (RFC5322 section 2.2.3).

  Each line break and the white space which follows it, along with any white
  space which precedes it, are replaced with a single space.

  Parameters:
    header_value (str): the header value, which may be folded over several lines

  Returns:
    the unfolded header value, or None if header_value is None
  """
  if(header_value is None):
    return(None)

  return(re.sub(r"[ \t]*\r?\n[ \t]+", " ", str(header_value)))


def flatten_party_indices(
  parties : typing.Union[int, typing.List[typing.Union[int, typing.List[int], None]], None]
  ) -> typing.List[int]:
  """
  Flatten a Dialog Object parties value into a list of party indices.

  The Dialog Object parties value may be an int, a list of ints, or for
  multi-channel recordings, a list with an int, a list of ints or a null
  for each channel.  The party indices are returned in order without
  duplicates and with nulls removed.

  Parameters:
    parties: Dialog Object parties value

  Returns:
    list of party indices
  """
  flat_parties: typing.List[int] = []
  if(parties is None):
    return(flat_parties)

  if(not isinstance(parties, list)):
    parties = [parties]

  for channel_parties in parties:
    if(channel_parties is None):
      continue

    if(not isinstance(channel_parties, list)):
      channel_parties = [channel_parties]

    for party in channel_parties:
      if(party is not None and party not in flat_parties):
        flat_parties.append(party)

  return(flat_parties)


def get_recording_duration(
  recording_file: typing.Union[typing.BinaryIO, str, bytes]
  ) -> typing.Union[float, None]:

    tmp_path = None

    if(isinstance(recording_file, bytes)):
      # Could not get stream based solutions to work reliably
      # So create temp file
      with tempfile.NamedTemporaryFile(
          delete=False,
          # suffix=ext
        ) as tmp:
        tmp.write(recording_file)
        tmp_path = tmp.name
        recording_file = tmp_path

    try:
      recording_meta = ffmpeg.probe(recording_file)
      duration = float(recording_meta["streams"][0]['duration'])
    except Exception as e:
      #logger.debug("could not get duration of {} using ffmpeg, trying sox\n{}".format(recording_file, e))
      sox_info = sox.file_info.info(str(recording_file))
      duration = sox_info["duration"]

    finally:
      try:
        if(tmp_path and os.path.exists(tmp_path)):
          os.unlink(tmp_path)
      except Exception:
        pass

    return(duration)

