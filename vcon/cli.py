"""
Module for vcon command line interface script functions.  Pulled out of vcon CLI
script file so that it coould more easily be tested with pytest.
"""

import sys
import pathlib
import typing

def get_mime_type(file_name):
  path = pathlib.PurePath(file_name)
  extension = path.suffix.lower()

  print("extension: {}".format(extension), file=sys.stderr)

  if(extension == ".wav"):
    mimetype = vcon.Vcon.MIMETYPE_AUDIO_WAV

  else:
    raise UnrecognizedMimeType("MIME type not defined for extension: {}".format(extension))

  return(mimetype)

def main(argv : typing.Optional[typing.Sequence[str]] = None) -> int:
  import argparse
  import vcon
  import json
  import sox
  import email
  import email.utils
  import time
  import socket
 
  parser = argparse.ArgumentParser("vCon operations such as construction, signing, encryption, verification, decrytpion")
  input_group = parser.add_mutually_exclusive_group()
  input_group.add_argument("-i", "--infile", metavar='infile', nargs='?', type=argparse.FileType('r'), default=sys.stdin)
  input_group.add_argument("-n", "--newvcon", action="store_true")
  
  parser.add_argument("-o", "--outfile", metavar='outfile', nargs='?', type=argparse.FileType('w'), default=sys.stdout)
 
  subparsers_command = parser.add_subparsers(dest="command")

  addparser = subparsers_command.add_parser("add")
  subparsers_add = addparser.add_subparsers(dest="add_command")
  add_in_recording_subparsers = subparsers_add.add_parser("in-recording")
  add_in_recording_subparsers.add_argument("recfile", metavar='recording_file', nargs=1, type=pathlib.Path, default=None)
  add_in_recording_subparsers.add_argument("start", metavar='start_time', nargs=1, type=str, default=None)
  add_in_recording_subparsers.add_argument("parties", metavar='parties', nargs=1, type=str, default=None)

  add_ex_recording_subparsers = subparsers_add.add_parser("ex-recording")
  add_ex_recording_subparsers.add_argument("recfile", metavar='recording_file', nargs=1, type=pathlib.Path, default=None)
  add_ex_recording_subparsers.add_argument("start", metavar='start_time', nargs=1, type=str, default=None)
  add_ex_recording_subparsers.add_argument("parties", metavar='parties', nargs=1, type=str, default=None)
  add_ex_recording_subparsers.add_argument("url", metavar='url', nargs=1, type=str, default=None)

  add_in_email_subparsers = subparsers_add.add_parser("in-email")
  add_in_email_subparsers.add_argument("emailfile", metavar='email_file', nargs=1, type=pathlib.Path, default=None)
  add_in_email_subparsers.add_argument("start", metavar='start_time', nargs="?", type=str, default=None)
  add_in_email_subparsers.add_argument("parties", metavar='parties', nargs="?", type=str, default=None)

  extractparser = subparsers_command.add_parser("extract")
  subparsers_extract = extractparser.add_subparsers(dest="extract_command")
  extract_dialog_subparsers = subparsers_extract.add_parser("dialog")
  extract_dialog_subparsers.add_argument("index", metavar='dialog_index', nargs=1, type=int, default=None)

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
    -i <file_name>
  
    -o <file_name>
 
  Commands:
    add in-recording <file_name> <start_date> <parties>
    add ex-recording <file_name> <start_date> <parties> <url>
  
    sign private_key x5c1[, x5c2]... 
  
    verify ca_cert
  
    encrypt x5c1[, x5c2]... signing_private_key
  
    decrypt private_key, ca_cert
  
  """

  print("reading", file=sys.stderr)

  print("out: {}".format(type(args.outfile)), file=sys.stderr)
  print("in: {}".format(type(args.infile)), file=sys.stderr)
  print("new in {}".format(args.newvcon), file=sys.stderr)
  in_vcon = vcon.Vcon()
  if(args.newvcon == False):
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

  elif(args.command == "encrypt"):
    print("state: {}".format(in_vcon._state), file=sys.stderr)
    in_vcon.encrypt(args.pubkey[0])

  elif(args.command == "decrypt"):
    print("state: {}".format(in_vcon._state), file=sys.stderr)
    in_vcon.decrypt(args.privkey[0], args.pubkey[0])
  
  elif(args.command == "add"):
    if(args.add_command == "in-recording" or args.add_command == "ex-recording"):
      if(not args.recfile[0].exists()):
        raise Exception("Recording file: {} does not exist".format(args.recfile[0]))

      sox_info = sox.file_info.info(str(args.recfile[0]))
      duration = sox_info["duration"]
      mimetype = get_mime_type(args.recfile[0])

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
      if(not args.emailfile[0].exists()):
        raise Exception("Email file: {} does not exist".format(args.emailfile[0]))

      email_message = email.message_from_file(args.emailfile[0].open("r"))

      # Set subject if its not already set
      if(in_vcon.subject is None or len(in_vcon.subject) == 0):
        subject = email_message.get("subject")
        in_vcon.set_subject(subject)

      # Get tuple(s) of (name, email_uri) for sender and recipients
      sender = email.utils.parseaddr(email_message.get("from"))
      recipients = email.utils.getaddresses(email_message.get_all("to", []) +
        email_message.get_all("cc", []) +
        email_message.get_all("recent-to", []) +
        email_message.get_all("recent-cc", []))

      party_indices = []
      for email_address in [sender] + recipients:
        print("email name: {} mailto: {}".format(email_address[0], email_address[1]), file=sys.stderr)
        parties_found = in_vcon.find_parties_by_parameter("mailto", email_address[1])
        if(len(parties_found) == 0):
          parties_found = in_vcon.find_parties_by_parameter("name", email_address[0])

        if(len(parties_found) == 0):
          party_index = in_vcon.set_party_parameter("mailto", email_address[1])
          in_vcon.set_party_parameter("name", email_address[0], party_index)
          parties_found = [party_index]

        party_indices.extend(parties_found)

        if(len(parties_found) > 1):
          print("Warning: multiple parties found matching {}: at indices: {}".format(email_address, parties_found), file=sys.stderr)

      content_type = email_message.get("content-type")
      file_name = email_message.get_filename()
      #date = time.mktime(email.utils.parsedate(email_message.get("date")))
      date = email.utils.parsedate_to_datetime(email_message.get("date"))

      email_body = ""

      if(email_message.is_multipart()):
        body_start = False
        for line in str(email_message).splitlines():
          if(body_start):
            email_body = email_body + line + "\n\r"

          elif(len(line) == 0):
            body_start = True

      else:
        email_body = email_message.get_payload()

      in_vcon.add_dialog_inline_text(email_body, date, 0, party_indices, content_type, file_name)

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
    if(in_vcon.uuid is None or len(in_vcon.uuid) < 1):
      in_vcon.set_uuid(socket.gethostname() + ".vcon.dev")
    out_vcon_json = in_vcon.dumps(signed=signed_json)
    args.outfile.write(out_vcon_json)

  return(0)