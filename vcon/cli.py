# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
"""
Module for vcon command line interface script functions.  Pulled out of vcon CLI
script file so that it coould more easily be tested with pytest.
"""

import os
import sys
import re
import pathlib
import typing
import datetime
import dateutil
import time
import json
import argparse
import socket
import sox
import pytz
import ffmpeg
import vcon

VERBOSE = False

def do_in_email(
  args,
  in_vcon: vcon.Vcon
  ) -> vcon.Vcon:
  if(not args.emailfile[0].exists()):
    raise Exception("Email file: {} does not exist".format(args.emailfile[0]))

  # Read in the email SMTP message file
  with open(args.emailfile[0], "r") as smtp_message_file:
    smtp_message_string = smtp_message_file.read()

  # add the email message as a dialog along with its paties if not
  # already in the vcon
  in_vcon.add_dialog_inline_email_message(
    smtp_message_string,
    os.path.basename(args.emailfile[0])
    )

  return(in_vcon)

def zoom_chat_to_utc(local_time: str, zoom_start_utc: str, zoom_end_utc: str) -> str:
  if(time.daylight):
    timezone_guess = time.tzname[1]
    tz_info = datetime.timezone(datetime.timedelta(seconds = -time.altzone), time.tzname[1])
  else:
    timezone_guess = time.tzname[0]
    tz_info = datetime.timezone(datetime.timedelta(seconds = -time.altzone), time.tzname[0])

  hour_string, minute_string, second_string = local_time.strip().split(":")
  hour = int(hour_string)
  minute = int(minute_string)
  second = int(second_string)

  start_datetime = datetime.datetime.fromisoformat(zoom_start_utc)
  end_datetime = datetime.datetime.fromisoformat(zoom_end_utc)
  start_date = start_datetime.date()
  end_date = end_datetime.date()

  # The time zone is unclear so we guess at local time zone
  # and test that it is between the start and end times
  # convert the start_date to local time before 
  # taking year, month and day
  start_datetime_local = start_datetime.astimezone(tz_info)
  start_date_local = start_datetime_local.date()
  if(VERBOSE):
    print("local start date: {}".format(start_date_local), file = sys.stderr)
  dt = datetime.datetime(
    year = start_date.year,
    month = start_date.month,
    day = start_date.day,
    hour = hour,
    minute = minute,
    second = second,
    tzinfo = tz_info
    )

  # make it into UTC
  dt = dt.astimezone(pytz.UTC)
  #tz = tzlocal.get_localzone()
  #local_dt = tz.localize(dt, is_dst=None)
  #local_dt = dt.replace(tzinfo = tz_info)

  # Allow difference of 15 minutes
  date_tolerance = datetime.timedelta(0, 15 * 60)
  # The start time is from the recording file which
  # may be off a few minutes from the actual meeting time

  if(start_datetime <= dt <= end_datetime or
    dt - start_datetime < date_tolerance):
    return(dt.isoformat())

  # Hack the timezone as it was not the local one
  if(VERBOSE):
    print("start hour: {} dt hour: {}".format(
      start_datetime.hour,
      dt.hour
      ), file = sys.stderr)
  if(start_datetime.hour != dt.hour):
    dt = dt.replace(hour = start_datetime.hour)
    if(VERBOSE):
      print("reset hour: {}".format(dt.hour), file = sys.stderr)
  elif(end_datetime.hour != dt.hour):
    dt = dt.replace(hour = end_datetime.hour)
    if(VERBOSE):
      print("reset hour: {}".format(dt.hour), file = sys.stderr)

  if(start_datetime <= dt <= end_datetime or
    dt - start_datetime < date_tolerance):
    return(dt.isoformat())

  # Try the end date with local time
  # convert the end_date to local time before
  # taking year, month and day
  end_datetime_local = end_datetime.astimezone(tz_info)
  end_date_local = end_datetime_local.date()
  if(VERBOSE):
    print("local end date: {}".format(end_date_local), file = sys.stderr)
  dt = datetime.datetime(
    year = end_date_local.year,
    month = end_date_local.month,
    day = end_date_local.day,
    hour = hour,
    minute = minute,
    second = second,
    tzinfo = tz_info
    )

  # make it into UTC
  dt = dt.astimezone(pytz.UTC)
  #local_dt = tz.localize(dt, is_dst=None)

  if(start_datetime <= dt <= end_datetime or
    dt - start_datetime < date_tolerance):
    return(dt.isoformat())

  raise Exception("cannot figure out timezone for date: {} local tz is: {} start: {} dt: {} end: {} delta from start: {}".format(
    local_time,
    timezone_guess,
    start_datetime.isoformat(),
    dt.isoformat(),
    end_datetime.isoformat(),
    (dt - start_datetime)
    ))


def parse_zoom_chat(
  file_handle,
  recording_start: str,
  duration: typing.Union[int, float]
  ) -> typing.List[typing.Tuple[str, str, str]]:
  result = []
  start_datetime = datetime.datetime.fromisoformat(recording_start)
  recording_end = (start_datetime + datetime.timedelta(0, duration)).isoformat()
  for line in file_handle:
    message_time, sender_message = line.split("From", 1)
    message_time = message_time.strip()
    sender, message = sender_message.split(":", 1)
    sender = sender.strip()
    message = message.strip()
    # Try to extrapolate a UTD date and time from a local time
    datetime_string = zoom_chat_to_utc(message_time, recording_start, recording_end)
    result.append((datetime_string, sender, message))

  return(result)


def do_in_zoom(
  args,
  in_vcon: vcon.Vcon
  ) -> vcon.Vcon:
  if(not args.zoomdir[0].exists()):
    raise Exception("Zoom directory: {} does not exist".format(args.zoomdir[0]))

  ignore_extensions = [ "..", ".", ".conf"]
  conf_file = next(args.zoomdir[0].glob("*.conf"))
  if(conf_file is not None and conf_file != ""):
    with open(conf_file, "r") as zoom_conf_file:
      conf_json = json.load(zoom_conf_file)
      audio_file = conf_json["items"][0]["audio"]
      video_file = conf_json["items"][0]["video"]

  start = None
  duration = None
  chatfile = None
  for rec_file in args.zoomdir[0].glob("*"):
    filebase = os.path.basename(rec_file)
    file_ext = rec_file.suffix
    if(filebase == audio_file and
      video_file is not None and
      video_file != ""
      ):
      if(VERBOSE):
        print("ignoring audio file: {} in favor of video file: {}".format(
        audio_file,
        video_file
        ), file = sys.stderr)
      continue

    if(file_ext in ignore_extensions):
      if(VERBOSE):
        print("ignore extension: {}".format(rec_file), file = sys.stderr)
      continue

    if(VERBOSE):
      print("found: {} ".format(rec_file), file = sys.stderr)
      print("file name: {}".format(filebase), file = sys.stderr)
      print("extension: {} ".format(file_ext), file = sys.stderr)

    if(file_ext == ".mp4"):
      video_meta = ffmpeg.probe(rec_file)
      # tweak the date to make it RFC3339
      start = video_meta["streams"][0]['tags']["creation_time"].replace("Z", "+00:00")
      duration = float(video_meta["streams"][0]['duration'])
      with open(rec_file, "rb") as video_file_handle:
        body_bytes = video_file_handle.read()
        in_vcon .add_dialog_inline_recording(
          body_bytes,
          start,
          duration,
          -1, # TODO: can we get parties?
          vcon.Vcon.MIMETYPE_VIDEO_MP4,
          filebase
          )

    elif(filebase == "chat.txt"):
      # need to skip until we have start and end to the recording
      chatfile = rec_file

    # All other files are attachments
    else:
      with open(rec_file, "rb") as attachment_handle:
        body_bytes = attachment_handle.read()
        in_vcon.add_attachment_inline(
          body_bytes,
          start,
          -1,
          vcon.Vcon.get_mime_type(filebase),
          filebase
          )

  if(chatfile is not None):
    with open(chatfile, "r") as chatfile_handle:
      messages = parse_zoom_chat(
        chatfile_handle,
        start,
        duration
        )

      for message in messages:
        msg_time, msg_sender, msg_text = message

        # Get the party index for the sendor or add them if they don't exist
        sender_indices = in_vcon.find_parties_by_parameter("name", msg_sender)
        if(len(sender_indices) < 1):
          sender_indices.append(in_vcon.set_party_parameter("name", msg_sender))

        # Add the text dialog
        in_vcon.add_dialog_inline_text(
          msg_text,
          msg_time,
          0,
          sender_indices[0],
          vcon.Vcon.MIMETYPE_TEXT_PLAIN
          )

  return(in_vcon)


def meet_chat_time_to_seconds(relative_time: str) -> float:
  hours, minutes, seconds = relative_time.split(":")
  total_time = int(hours) * 3600 + \
    int(minutes) * 60 + \
    float(seconds)

  return(total_time)


def parse_meet_chat(
  file_handle,
  meeting_start: str
  ) -> typing.List[typing.Tuple[str, float, str, str]]:

  meeting_start_datetime = datetime.datetime.fromisoformat(meeting_start)
  messages = []
  while(1):
    times = file_handle.readline()
    if(times is None or
      times == ""
      ):
      break
    # times are relative to start of meeting
    time_start, time_end = times.split(",", 1)
    # convert to seconds to calculate duration
    # calculate start time from meeting start time
    seconds_start = meet_chat_time_to_seconds(time_start)
    seconds_end = meet_chat_time_to_seconds(time_end)
    duration = seconds_end - seconds_start
    start_date = (meeting_start_datetime + datetime.timedelta(0, seconds_start)).isoformat()

    sender_message = file_handle.readline()
    sender, message = sender_message.split(":", 1)
    messages.append((start_date, duration, sender.strip(), message.strip()))
    file_handle.readline() # blank line separator

  return(messages)


def do_in_meet(args, in_vcon: vcon.Vcon) -> vcon.Vcon:
  if(not args.meetrec[0].exists()):
    print("Google Meet recording file: {} does not exist".format(
      args.meetrec[0]
      ),
      file = sys.stderr
      )
    sys.exit(7)
  if(not args.meetrec[0].is_file()):
    print("{} is not a file".format(
      args.meetrec[0]
      ),
      file = sys.stderr
      )
    sys.exit(7)
  #print(magic.from_file(args.meetrec, mime = True))
  with open(args.meetrec[0], "rb") as rec_file_handle:
    image_data = rec_file_handle.read(8)
    if(len(image_data) < 8):
      print("recording file: {} too small)".format(
        args.meetrec[0]
        ),
        file = sys.stderr
        )
      sys.exit(7)

    # magic header bytes
    header = ''.join('{:02x}'.format(x) for x in image_data[4:])
    if(header != "66747970"):
      print("expected file: {} to be an MP4 recording (magic: {} expected: 66747970)".format(
        args.meetrec[0],
        header
        ),
        file = sys.stderr
        )
      sys.exit(7)

  # Check metadata on recording
  video_meta = ffmpeg.probe(args.meetrec[0])
  meta_filename = os.path.basename(video_meta["format"]["filename"])
  duration = float(video_meta["streams"][0]['duration'])
  # print("Metadata: {}".format(video_meta))
  # print("meta file name: {}".format(meta_filename))
  # print("duration: {}".format(duration))
  re_results = re.match(r'(?P<meeting>[a-zA-Z0-9 ]+) [^\(]*\((?P<date>[^\(]+)\) [^\(]*\((?P<hash>[^\(]+)\)',
    meta_filename)
  if(re_results is not None):
    name_parts_dict = re_results.groupdict()
    meeting_name = name_parts_dict["meeting"]
    meeting_date = name_parts_dict["date"]
    # Massage the date into RFC3339 format
    # hour offset must be 2 digits
    if(meeting_date[-2:-1] == "-"):
      meeting_date = meeting_date[:-1] + "0" + meeting_date[-1:]
    # insert T between date and time, remove space and GMT, add minutes to offset
    meeting_date = meeting_date.replace(" ", "T", 1).replace(" GMT", "") + ":00"
    meeting_hash = name_parts_dict["hash"]
    # print("meeting name: {}\ndate: {}\nhash: {}".format(
    #   meeting_name,
    #   meeting_date,
    #   meeting_hash
    #   ),
    #   file = sys.stderr
    #   )
  else:
    meeting_name = None
    meeting_hash = None
    # infer meeting date from recording file creation date
    meeting_date = vcon.utils.cannonize_date(os.path.getctime(args.meetrec[0]))
    print("Meeting date: {}".format(meeting_date), file = sys.stderr)

  # Set the subject, if not alaready set, to the meeting name
  if(meeting_name is not None and
    (in_vcon.subject is None or
    in_vcon.subject == "")
    ):
    in_vcon.set_subject(meeting_name)

  # parties unknown
  parties = None
  with open(args.meetrec[0], "rb") as recording_handle:
    body_bytes = recording_handle.read()
    in_vcon.add_dialog_inline_recording(
      body_bytes,
      meeting_date,
      duration,
      parties,
      vcon.Vcon.MIMETYPE_VIDEO_MP4,
      os.path.basename(str(args.meetrec[0]))
      )

  # Try to find the chat file
  if(meeting_hash is not None and
    (" (" + meeting_hash + ")") in str(args.meetrec[0])
    ):
    chatfile = str(args.meetrec[0]).replace(" (" + meeting_hash + ")", "")

    with open(chatfile, "r") as chat_handle:
      messages = parse_meet_chat(
        chat_handle,
        meeting_date
        )
      #print("chat: {} chat messages".format(messages))
      for timestamp, duration, sender, message in messages:
        # Get party index or add them if not in the Vcon
        sender_indices = in_vcon.find_parties_by_parameter("name", sender)
        if(len(sender_indices) < 1):
          sender_indices.append(in_vcon.set_party_parameter("name", sender))

        # add a text dialog
        in_vcon.add_dialog_inline_text(
          message,
          timestamp,
          duration,
          sender_indices[0],
          vcon.Vcon.MIMETYPE_TEXT_PLAIN
          )

  return(in_vcon)


async def main(argv : typing.Optional[typing.Sequence[str]] = None) -> int:
  parser = argparse.ArgumentParser("vCon operations such as construction, signing, encryption, verification, decrytpion, filtering")

  input_group = parser.add_mutually_exclusive_group()
  input_group.add_argument(
    "-i",
    "--infile",
    metavar='infile',
    help = "- read input vCon from file",
    nargs='?',
    type=argparse.FileType('r'),
    default=sys.stdin
    )
  input_group.add_argument(
    "-g",
    "--get",
    metavar=('host', 'port', 'uuid'),
    help = "- HTTP get vCon having the given uuid from host, port",
    nargs = 3,
    type = str
    )
  input_group.add_argument(
    "-n",
    "--newvcon",
    help = "- create a new/empty vCon as the input file",
    action="store_true"
    )

  parser.add_argument(
    "-o",
    "--outfile",
    metavar='outfile',
    nargs='?',
    type=argparse.FileType('w'),
    default=sys.stdout
    )

  parser.add_argument(
    "-p",
    "--post",
    metavar = ('host', 'port'),
    nargs = 2,
    # action = "append",
    help = "- HTTP post the output vCon to the given host and port",
    type = str
    )

  parser.add_argument(
    "-r",
    "--register-filter-plugin",
    nargs = 4,
    action = "append",
    metavar = ("register_name", "module_name", "class_name", "FilterPluginInitOptions"),
    help = "register and load a FilterPlugin as the given name from module and class and initialize using the given FilterPluginInitOptions (JSON dict string)",
    type = str,
    default = [])

  subparsers_command = parser.add_subparsers(dest="command")

  addparser = subparsers_command.add_parser("add")
  subparsers_add = addparser.add_subparsers(dest="add_command")

  add_in_recording_subparsers = subparsers_add.add_parser(
    "in-recording",
    help = "add a audio or video file as a inline recording dialog"
    )
  add_in_recording_subparsers.add_argument("recfile", metavar='recording_file', nargs=1, type=pathlib.Path, default=None)
  add_in_recording_subparsers.add_argument("start", metavar='start_time', nargs=1, type=str, default=None)
  add_in_recording_subparsers.add_argument("parties", metavar='parties', nargs=1, type=str, default=None)

  add_ex_recording_subparsers = subparsers_add.add_parser(
    "ex-recording",
    help = "add a audio or video file as a externally referenced recording dialog"
    )
  add_ex_recording_subparsers.add_argument("recfile", metavar='recording_file', nargs=1, type=pathlib.Path, default=None)
  add_ex_recording_subparsers.add_argument("start", metavar='start_time', nargs=1, type=str, default=None)
  add_ex_recording_subparsers.add_argument("parties", metavar='parties', nargs=1, type=str, default=None)
  add_ex_recording_subparsers.add_argument("url", metavar='url', nargs=1, type=str, default=None)

  add_in_email_subparsers = subparsers_add.add_parser(
    "in-email",
    help = "add SMTP message as a inline text dialog"
    )
  add_in_email_subparsers.add_argument(
    "emailfile",
    metavar='email_file',
    nargs=1,
    type=pathlib.Path,
    help = "path to SMTP email message file to add as text dialog",
    default=None)
  # not needed as they come from the SMTP message:
  # add_in_email_subparsers.add_argument("start", metavar='start_time', nargs="?", type=str, default=None)
  # add_in_email_subparsers.add_argument("parties", metavar='parties', nargs="?", type=str, default=None)

  add_in_zoom_subparsers = subparsers_add.add_parser(
    "in-zoom",
    help = "add zoom recording and capture as inline dialogs and attachments"
    )
  add_in_zoom_subparsers.add_argument(
    "zoomdir",
    metavar='zoom_directory',
    nargs=1,
    type=pathlib.Path,
    help = "directory containing Zoom meeint recording and captured files to add as dialog(s) and attachment(s)",
    default=None)


  add_in_meet_subparsers = subparsers_add.add_parser(
    "in-meet",
    help = "add Google meet recording and chat as inline dialogs"
    )
  add_in_meet_subparsers.add_argument(
    "meetrec",
    metavar='meet_recording',
    nargs=1,
    type=pathlib.Path,
    help = "- path to Google Meet video recording file.  The path to the chat file is implied from this if presnet.",
    default=None)


  extractparser = subparsers_command.add_parser("extract")
  subparsers_extract = extractparser.add_subparsers(dest="extract_command")
  extract_dialog_subparsers = subparsers_extract.add_parser("dialog")
  extract_dialog_subparsers.add_argument("index", metavar='dialog_index', nargs=1, type=int, default=None)

  filter_parser = subparsers_command.add_parser(
    "filter",
    formatter_class = argparse.RawTextHelpFormatter
    )
  plugin_names = vcon.filter_plugins.FilterPluginRegistry.get_names()
  default_types = vcon.filter_plugins.FilterPluginRegistry.get_types()
  fn_help_template = """\
Name of filter plugin (e.g. {}) or default type filter plugin name (e.g. {})
{}
"""
  plugin_descriptions = ""
  for plugin_name in plugin_names:
    descript = vcon.filter_plugins.FilterPluginRegistry.get(plugin_name).description
    plugin_descriptions += "{} - {}\n".format(plugin_name, descript)


  fn_help = fn_help_template.format(
    ", ".join(plugin_names),
    ", ".join(default_types),
    plugin_descriptions
    )
  filter_parser.add_argument(
    "filter_name",
    metavar = "filter_plugin_name",
    nargs = 1,
    type = str,
    help = fn_help,
    default = None,
    action = "append")
  fo_help="JSON dict/object (FilterPluginOptions) with key name values which are options passed to the filter. (e.g. \'{\"a\" : 1, \"b\" : \"two\"}\' )"
  filter_parser.add_argument("-fo", "--filter-options", metavar='filter_options', nargs=1, type=str, help=fo_help, action="append")

  sign_parser = subparsers_command.add_parser("sign")
  sign_parser.add_argument("privkey", metavar='private_key_file', nargs=1, type=pathlib.Path, default=None)
  sign_parser.add_argument("pubkey", metavar='public_key_file', nargs='+', type=pathlib.Path, default=None)

  verify_parser = subparsers_command.add_parser("verify")
  verify_parser.add_argument("pubkey", metavar='public_key_file', nargs='+', type=pathlib.Path, default=None)

  encrypt_parser = subparsers_command.add_parser("encrypt")
  encrypt_parser.add_argument("pubkey", metavar='public_key_file', nargs='+', type=pathlib.Path, default=None)

  decrypt_parser = subparsers_command.add_parser("decrypt")
  decrypt_parser.add_argument("privkey", metavar='private_key_file', nargs=1, type=pathlib.Path, default=None)
  decrypt_parser.add_argument("pubkey", metavar='public_key_file', nargs=1, type=pathlib.Path, default=None)

  args = parser.parse_args(argv)

  print("args: {}".format(args), file=sys.stderr)
  print("args dir: {}".format(dir(args)), file=sys.stderr)

  print("command: {}".format(args.command), file=sys.stderr)

  for filter_plugin_registration in args.register_filter_plugin:
    print("test cli got reg info pluging: {}".format(
      filter_plugin_registration[0]
      ),
      file = sys.stderr
      )
    if(len(filter_plugin_registration) >= 5):
      init_options_json = filter_plugin_registration[4]
    else:
      init_options_json = None
    if(init_options_json is not None and init_options_json != ""):
      init_options_dict = json.loads(init_options_json)
      if(not isinstance(init_options_dict, dict)):
        print("filter init options: {} ignored, must be a valid json dict string".format(
          init_options_json),
          file = sys.stderr
          )
        sys.exit(2)
    else:
      init_options_dict = {}

    vcon.filter_plugins.FilterPluginRegistry.register(
      filter_plugin_registration[0],
      filter_plugin_registration[1],
      filter_plugin_registration[2],
      filter_plugin_registration[0],
      init_options_dict,
      replace=True)

  if(args.command == "sign"):
    print("priv key files: {}".format(len(args.privkey)), file=sys.stderr)
    if(args.privkey[0].exists()):
      print("priv key: {} exists".format(str(args.privkey[0])), file=sys.stderr)
    else:
      print("priv key: {} does NOT exist".format(str(args.privkey[0])), file=sys.stderr)

    print("pub key files: {}".format(len(args.pubkey)), file=sys.stderr)

  if(args.command == "verify"):
    if(args.pubkey[0].exists()):
      print("pub key: {} exists".format(str(args.pubkey[0])), file=sys.stderr)
    else:
      print("pub key: {} does NOT exist".format(str(args.pubkey[0])), file=sys.stderr)

  if(args.command == "encrypt"):
    if(args.pubkey[0].exists()):
      print("pub key: {} exists".format(str(args.pubkey[0])), file=sys.stderr)
    else:
      print("pub key: {} does NOT exist".format(str(args.pubkey[0])), file=sys.stderr)

  if(args.command == "decrypt"):
    if(args.pubkey[0].exists()):
      print("pub key: {} exists".format(str(args.pubkey[0])), file=sys.stderr)
    else:
      print("pub key: {} does NOT exist".format(str(args.pubkey[0])), file=sys.stderr)
    if(args.privkey[0].exists()):
      print("priv key: {} exists".format(str(args.privkey[0])), file=sys.stderr)
    else:
      print("priv key: {} does NOT exist".format(str(args.privkey[0])), file=sys.stderr)

  if(args.command == "add"):
    print("add: {}".format(args.add_command), file=sys.stderr)

  """
  Options: 
    [-n | -i <file_name>][-o <file_name>][-r filter_plugin_name plugin_module plugin_class_name [-r ...]]
 
  Commands:
    add in-recording <file_name> <start_date> <parties>
    add ex-recording <file_name> <start_date> <parties> <url>
 
    filter filter-name [-fo filter-options-dict] 

    sign private_key x5c1[, x5c2]... 
  
    verify ca_cert
  
    encrypt x5c1[, x5c2]... signing_private_key
  
    decrypt private_key, ca_cert
  
  """

  print("reading", file=sys.stderr)

  print("out: {}".format(type(args.outfile)), file=sys.stderr)
  print("in: {}".format(type(args.infile)), file=sys.stderr)
  print("new in {}".format(args.newvcon), file=sys.stderr)
  print("filter plugin registrations in {}".format(args.register_filter_plugin), file=sys.stderr)
  in_vcon = vcon.Vcon()
  if(args.get):
    try:
      port = int(args.get[1])
    except ValueError:
      parser.error("get port must be an integer.  Received: {}".format(args.get[1]))

    await in_vcon.get(
      host = args.get[0],
      port = port,
      uuid = args.get[2]
      )

  elif(not args.newvcon):
    in_vcon_json = args.infile.read()
    if(in_vcon_json is not None and len(in_vcon_json) > 0):
      in_vcon.loads(in_vcon_json)
  else:
    pass

  # Use default serialization for state of vCon
  signed_json = True

  # By default we output the vCon at the end
  stdout_vcon = True

  if(args.command == "sign"):
    in_vcon.sign(args.privkey[0], args.pubkey)

  elif(args.command == "verify"):
    print("state: {}".format(in_vcon._state), file=sys.stderr)
    in_vcon.verify(args.pubkey)

    # Assuming that generally if someone is verifying the vCon, they want the
    # unsigned JSON version as output.
    signed_json = False

  elif(args.command == "filter"):
    plugin_name = args.filter_name[0][0].strip(" '\"")
    print("filter name: \"{}\"".format(plugin_name), file=sys.stderr)
    if(args.filter_options is not None):
      try:
        filter_options_dict = json.loads(args.filter_options[0][0].strip(" '\""))
      except Exception as opt_error:
        print(opt_error, file=sys.stderr)
        print("filter options: {}".format(args.filter_options))
        filter_options_dict = None
      if(not isinstance(filter_options_dict, dict)):
        print("filter_options should be a well formed dict.  Got: {}".format(args.filter_options[0][0]), file=sys.stderr)
        sys.exit(2)
    else:
      filter_options_dict = {}
    print("filter options: \"{}\"".format(filter_options_dict), file=sys.stderr)
    try:
      plugin = vcon.filter_plugins.FilterPluginRegistry.get(plugin_name, True, True)
      print("got plugin for: {}".format(plugin), file=sys.stderr)
      if(plugin is None):
        raise Exception("should not get here, exception should have been raised in get()")
    except Exception as pname_error:
      names = vcon.filter_plugins.FilterPluginRegistry.get_names()
      print("filter name: {} not found, the following filters are registered: {}".format(
        plugin_name,
        names
        ),
        file = sys.stdout
        )

      raise pname_error

    # send print statements that we want to go to stderr
    #
    # Leaving this here commented out for diagnostic purposes.  I kind of
    # like it that the unit test fails if there is any print to stdout
    # noise to force clean up.
    #with contextlib.redirect_stdout(sys.stderr):

    if(plugin is None):
      raise Exception("Should not get here")

    options = plugin.options_type(**filter_options_dict)
    in_vcon = await in_vcon.filter(plugin_name, options)

  elif(args.command == "encrypt"):
    print("state: {}".format(in_vcon._state), file=sys.stderr)
    in_vcon.encrypt(args.pubkey[0])

  elif(args.command == "decrypt"):
    print("state: {}".format(in_vcon._state), file=sys.stderr)
    in_vcon.decrypt(args.privkey[0], args.pubkey[0])

  elif(args.command == "add"):
    if(args.add_command in ["in-recording", "ex-recording"]):
      if(not args.recfile[0].exists()):
        raise Exception("Recording file: {} does not exist".format(args.recfile[0]))

      try:
        recording_meta = ffmpeg.probe(args.recfile[0])
        # tweak the date to make it RFC3339
        #start = recording_meta["streams"][0]['tags']["creation_time"].replace("Z", "+00:00")
        duration = float(recording_meta["streams"][0]['duration'])
      except Exception as e:
        print("could not get duration of {} using ffmpeg, trying sox\n{}".format(args.recfile[0], e), file = sys.stderr)
        sox_info = sox.file_info.info(str(args.recfile[0]))
        duration = sox_info["duration"]

      mimetype = vcon.Vcon.get_mime_type(args.recfile[0])

      with open(args.recfile[0], 'rb') as file_handle:
        body = file_handle.read()

      parties_object = json.loads(args.parties[0])

      if(args.add_command == "in-recording"):
        in_vcon.add_dialog_inline_recording(body, args.start[0], duration, parties_object,
          mimetype, str(args.recfile[0]))

      elif(args.add_command == "ex-recording"):
        in_vcon.add_dialog_external_recording(body, args.start[0], duration, parties_object,
          args.url[0], mimetype, str(args.recfile[0]))

    elif(args.add_command == "in-email"):
      in_vcon = do_in_email(args, in_vcon)

    elif(args.add_command == "in-zoom"):
      in_vcon = do_in_zoom(args, in_vcon)

    elif(args.add_command == "in-meet"):
      in_vcon = do_in_meet(args, in_vcon)


  elif(args.command == "extract"):
    if(args.extract_command == "dialog"):
      if(not isinstance(args.index[0], int)):
        raise AttributeError("Dialog index should be type int, not {}".format(type(args.index[0])))

      dialog_index = args.index[0]
      num_dialogs = len(in_vcon.dialog)
      if(dialog_index > num_dialogs):
        raise AttributeError("Dialog index: {} must be less than the number of dialog in the vCon: {}".format(dialog_index, num_dialogs))

      recording_bytes = in_vcon.decode_dialog_inline_body(dialog_index)
      stdout_vcon = False
      if(isinstance(recording_bytes, bytes)):
        args.outfile.buffer.write(recording_bytes)
      else:
        args.outfile.write(recording_bytes)

  #print("vcon._vcon_dict: {}".format(in_vcon._vcon_dict))
  if(stdout_vcon):
    if(in_vcon._state == vcon.VconStates.UNSIGNED and (in_vcon.uuid is None or len(in_vcon.uuid) < 1)):
      in_vcon.set_uuid(socket.gethostname() + ".vcon.dev")
    out_vcon_json = in_vcon.dumps(signed=signed_json)
    args.outfile.write(out_vcon_json)

  if(args.post):
    print("post args: {}".format(len(args.post)), file = sys.stderr)
    try:
      port = int(args.post[1])
    except ValueError:
      parser.error("post port must be an integer.  Received: {}".format(args.post[1]))

    await in_vcon.post(
      host = args.post[0],
      port = port
      )
  return(0)

