"""
Module for creating and modifying vCon conversation containers.
see https:/vcon.dev
"""
# need future to reference Vcon type in Vcon methods
from __future__ import annotations
import importlib
import pkgutil
import typing
import sys
import os
import copy
import logging
import logging.config
import enum
import time
import hashlib
import inspect
import functools
import warnings
import datetime
import email
import pathlib
import pyjq
import uuid6
import requests
import jose.utils
import jose.jws
import jose.jwe
import pythonjsonlogger.jsonlogger
import vcon.utils
import vcon.security
import vcon.filter_plugins
import vcon.accessors

__version__ = "0.3.1"

def build_logger(name : str) -> logging.Logger:
  logger = logging.getLogger(name)

  log_config_filename = "./logging.conf"
  if(os.path.isfile(log_config_filename)):
    logging.config.fileConfig(log_config_filename)
    #print("got logging config", file=sys.stderr)
  else:
    logger.setLevel(logging.DEBUG)

    # Output to stdout WILL BREAK the Vcon CLI.
    # MUST use stderr.
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.DEBUG)
    formatter = pythonjsonlogger.jsonlogger.JsonFormatter( "%(timestamp)s %(levelname)s %(message)s ", timestamp=True)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

  return(logger)

logger = build_logger(__name__)

try:
  import simplejson as json
  dumps_options = {"ignore_nan" : True}
  logger.info("using simplejson")
except Exception as import_error:
  import json
  dumps_options = {}
  logger.info("using json")


_LAST_V8_TIMESTAMP = None

for finder, module_name, is_package in pkgutil.iter_modules(vcon.filter_plugins.__path__, vcon.filter_plugins.__name__ + "."):
  logger.info("plugin registration: {}".format(module_name))
  importlib.import_module(module_name)

def deprecated(reason : str):
  """
  Decorator for marking and emmiting warnings on deprecated methods and classes
  """

  def decorator(func):
    if inspect.isclass(func):
      msg = "Call to deprecated class {{}} ({}).".format(reason)
    else:
      msg = "Call to deprecated function {{}} ({}).".format(reason)

    @functools.wraps(func)
    def new_func(*args, **kwargs):
      warnings.simplefilter('always', DeprecationWarning)
      warnings.warn(
        msg.format(func.__name__),
        category=DeprecationWarning,
        stacklevel=2)
      warnings.simplefilter('default', DeprecationWarning)
      return func(*args, **kwargs)

    return new_func

  return decorator

class VconStates(enum.Enum):
  """ Vcon states WRT signing and verification """
  UNKNOWN = 0
  UNSIGNED = 1
  SIGNED = 2
  UNVERIFIED = 3
  VERIFIED = 4
  ENCRYPTED = 5
  DECRYPTED = 6


class UnsupportedVconVersion(Exception):
  """ Thrown if vcon version string is not of set of versions supported by this package"""

class UnverifiedVcon(Exception):
  """ Payload is signed, but not verified.  Must be verified before reading data """

class InvalidVconState(Exception):
  """ Vcon is in an invalid state for a given operation """

class InvalidVconJson(Exception):
  """ JSON not valid for Vcon """

class InvalidVconHash(Exception):
  """ Hash does not match the content/body """

class InvalidVconSignature(Exception):
  """ Signature does not match the content"""



def tag_meta(func):
  """ decorator to tag with meta category """
  func._tag = "meta"
  return(func)

def tag_party(func):
  """ decorator to tag with party category """
  func._tag = "party"
  return(func)

def tag_dialog(func):
  """ decorator to tag with dialog category """
  func._tag = "dialog"
  return(func)

def tag_analysis(func):
  """ decorator to tag with analysis category """
  func._tag = "analysis"
  return(func)

def tag_attachment(func):
  """ decorator to tag with attachment category """
  func._tag = "attachment"
  return(func)

def tag_signing(func):
  """ decorator to tag with signing category """
  func._tag = "signing"
  return(func)

def tag_encrypting(func):
  """ decorator to tag with encrypting category """
  func._tag = "encrypting"
  return(func)

def tag_serialize(func):
  """ decorator to tag with serialize category """
  func._tag = "serialize"
  return(func)

def tag_operation(func):
  """ decorator to tag with operation category """
  func._tag = "operation"
  return(func)


class VconAttribute:
  """ descriptor base class for attributes in vcon """
  def __init__(self, doc : typing.Union[str, None] = None):
    self._type_name = ""
    self.name = None
    if(doc is not None):
      self.__doc__ = doc

  def __set_name__(self, owner_class, name):
    #print("defining new Vcon{}: {}".format(self._type_name, name))
    self.name = name

  def __get__(self, instance_object, class_type = None):
    #print("getting: {} inst type: {} class type: {}".format(self.name, type(instance_object), type(class_type)))
    # TODO: once signed, this should return a read only attribute
    # This may be done by overloading the __get__ method in derived classes

    if(instance_object._state in [VconStates.UNVERIFIED, VconStates.DECRYPTED]):
      raise UnverifiedVcon("vCon is signed, but not verified. Call verify before reading data.")

    if(instance_object._state in [VconStates.ENCRYPTED]):
      raise UnverifiedVcon("vCon is encrypted. Call decrypt and verify before reading data.")

    return(instance_object._vcon_dict.get(self.name, None))

  def __set__(self, instance_object, value : str) -> None:
    raise AttributeError("not allowed to replace {} {}".format(self.name, self._type_name))

class VconString(VconAttribute):
  """ descriptor for String attributes in vcon """
  def __init__(self, doc : typing.Union[str, None] = None):
    super().__init__(doc = doc)
    self._type_name = "String"

class VconDict(VconAttribute):
  """ descriptor for Lists of dicts in vcon """

  def __init__(self, doc : typing.Union[str, None] = None):
    super().__init__(doc = doc)
    self._type_name = "Dict"

class VconDictList(VconAttribute):
  """ descriptor for Lists of dicts in vcon """

  def __init__(self, doc : typing.Union[str, None] = None):
    super().__init__(doc = doc)
    self._type_name = "DictList"

class VconPluginMethodType():
  """ Class defining descriptor used to instantiate methods for the named filter plugins """
  def __init__(self, filter_name, vcon_instance):
    self.__function_name__ = filter_name
    self.__self__ = vcon_instance
    if(not isinstance(vcon_instance, vcon.Vcon)):
      raise AttributeError("vcon_instance should be a Vcon not {}".format(type(vcon_instance)))

    #print("added func: {} for obj: {} type{}".format(filter_name, vcon_instance, type(vcon_instance)))

  async def __call__(self, *args, **kwargs):
    obj = self.__self__
    if(len(args) != 1):
      raise AttributeError("FilterPlugin method: {} missing argument: FilterPluginOptions".format(
        self.__function_name__
        ))
    # print("__call__ args: {}".format(args))
    # print("__call__ args[0]: {}".format(args[0])) # should be FilterPluginOptions
    # print("__call__ kwargs: {}".format(kwargs))
    # print("calling filter for {} create: {} num dialogs: {}".format(self.__function_name__, obj.created_at, len(obj.dialog)))
    return(await vcon.Vcon.filter(obj, self.__function_name__, args[0]))

class VconPluginMethodProperty:
  def __init__(self, plugin_name : str):
    #print("VconPluginMethodProperty.__init__ {}".format(plugin_name))
    self.plugin_name = plugin_name

  def __get__(self, instance_object, class_type = None):
    #print("__get__ on {}".format(self.plugin_name))
    if(instance_object is None):
      return(self)

    return(VconPluginMethodType(self.plugin_name, instance_object))


class Vcon():
  """
  Constructor, Serializer and Deserializer for vCon conversation data container.

  Attributes:
    See Data descriptors under help(vcon.Vcon)

  """

  # Some commonly used MIME types for convenience
  MIMETYPE_TEXT_PLAIN = "text/plain"
  MIMETYPE_JSON = "application/json"
  MIMETYPE_IMAGE_PNG = "image/png"
  MIMETYPE_AUDIO_WAV = "audio/x-wav"
  MIMETYPE_AUDIO_MP3 = "audio/x-mp3"
  MIMETYPE_AUDIO_MP4 = "audio/x-mp4"
  MIMETYPE_VIDEO_MP4 = "video/x-mp4"
  MIMETYPE_VIDEO_OGG = "video/ogg"
  MIMETYPE_MULTIPART = "multipart/mixed"

  FILE_EXTENSIONS = {
    ".txt": MIMETYPE_TEXT_PLAIN,
    ".text": MIMETYPE_TEXT_PLAIN,
    ".png": MIMETYPE_IMAGE_PNG,
    ".wav": MIMETYPE_AUDIO_WAV,
    ".mp3": MIMETYPE_AUDIO_MP3,
    ".mp4": MIMETYPE_VIDEO_MP4
  }

  MIME_EXTENSIONS = {
    MIMETYPE_TEXT_PLAIN: ".txt",
    MIMETYPE_IMAGE_PNG: ".png",
    MIMETYPE_AUDIO_WAV: ".wav",
    MIMETYPE_AUDIO_MP3: ".mp3",
    MIMETYPE_VIDEO_MP4: ".mp4"
  }

  CURRENT_VCON_VERSION = "0.0.1"

  # Dict keys
  VCON_VERSION = "vcon"
  UUID = "uuid"
  SUBJECT = "subject"
  REDACTED = "redacted"
  APPENDED = "appended"
  GROUP = "group"
  PARTIES = "parties"
  DIALOG = "dialog"
  ANALYSIS = "analysis"
  ATTACHMENTS = "attachments"
  CREATED_AT = "created_at"

  PARTIES_OBJECT_STRING_PARAMETERS = ["tel", "stir", "mailto", "name", "validation", "gmlpos", "timezone", "role", "extension"]

  vcon = VconString(doc = "vCon version string attribute")
  uuid = VconString(doc = "vCon UUID string attribute")
  created_at = VconString(doc = "vCon creation date string attribute")
  subject = VconString(doc = "vCon subject string attribute")

  redacted = VconDict(doc = "redacted Dict for reference or inclusion of less redacted signed or encrypted version of this vCon")
  appended = VconDict(doc = "appended Dict for reference or includsion of signed or encrypted vCon to which this vCon appends data")

  group = VconDictList(doc = "List of Dicts referencing or including other vCons to be aggregated by this vCon")
  parties = VconDictList(doc = "List of Dicts, one for each party to this conversation")
  dialog = VconDictList(doc = "List of Dicts referencing or including the capture of text," +
    " audio or video (original form of communication) segments for this conversation")
  analysis = VconDictList(doc = "List of Dicts referencing or includeing analysis data for this conversation")
  attachments = VconDictList(doc = "List of Dicts referencing or including ancillary documents to this conversation")

  # TODO:  work out states the vcon can be in.  For example:
  """
    unsigned
    signed
    signed_unverified
    signed_verified
    encrypted
    encrypted_unverified
    decryppted_verified

  Also are there failure cases for the above?

  JSW (RFC7515) signing stored in:
  _jsw_dict
  {
    payload
    signatures
    [
      {
        protected
        header
        signature
      } [, ...]
    ]
  }


  """

  def __init__(self):
    """ Constructor """
    # Note: if you add new instance members/attributes, be sure to add its
    # name to instance_attibutes in Vcon.attribute_exists.
    # Register filter plugins as named instance methods
    for plugin_name in vcon.filter_plugins.FilterPluginRegistry.get_names():
      if(Vcon.attribute_exists(plugin_name) is not True):
        setattr(vcon.Vcon, plugin_name, VconPluginMethodProperty(plugin_name))
        logger.info("added Vcon.{}".format(plugin_name))
      else:
        existing_attr = getattr(vcon.Vcon, plugin_name)
        if(issubclass(type(existing_attr), vcon.VconPluginMethodProperty)):
          #print("Warning: Filter Plugin name: {} previsously added.".format(plugin_name))
          pass
        else:
          logger.warning("Warning: Filter Plugin name: {} conflicts".format(plugin_name) +
            " with existing instance or class attributes and is not directly callable." +
            "  Use Vcon.filter method to invoke it." +
            "  Better yet, change the name so that it does not conflict")

    for plugin_type_name in vcon.filter_plugins.FilterPluginRegistry.get_types():
      if(Vcon.attribute_exists(plugin_type_name) is not True):
        setattr(vcon.Vcon, plugin_type_name, VconPluginMethodProperty(plugin_type_name))
        logger.info("added Vcon.{}".format(plugin_type_name))
      else:
        existing_attr = getattr(vcon.Vcon, plugin_type_name)
        if(issubclass(type(existing_attr), vcon.VconPluginMethodProperty)):
          #print("Warning: Filter Plugin name: {} previsously added.".format(plugin_type_name))
          pass
        else:
           logger.warning("Warning: Filter Plugin Type name: {} conflicts with existing".format(plugin_type_name) +
           "instance or class attributes and is not directly callable." +
           "  Use Vcon.filter method to invoke it." +
           "  Better yet, change the name so that it does not conflict")

    self._state = VconStates.UNSIGNED
    self._jws_dict = None
    self._jwe_dict = None

    self._vcon_dict = {}
    self._vcon_dict[Vcon.VCON_VERSION] = Vcon.CURRENT_VCON_VERSION
    self._vcon_dict[Vcon.GROUP] = []
    self._vcon_dict[Vcon.PARTIES] = []
    self._vcon_dict[Vcon.DIALOG] = []
    self._vcon_dict[Vcon.ANALYSIS] = []
    self._vcon_dict[Vcon.ATTACHMENTS] = []
    self._vcon_dict[Vcon.CREATED_AT] = vcon.utils.cannonize_date(datetime.datetime.utcnow())
    self._vcon_dict[Vcon.REDACTED] = {}


  # TODO: use mimetypes package instead
  @staticmethod
  def get_mime_type(file_name):
    """ derive mimetype from fle extension """
    path = pathlib.PurePath(file_name)
    extension = path.suffix.lower()

    #print("extension: {}".format(extension), file=sys.stderr)

    if(extension in vcon.Vcon.FILE_EXTENSIONS):
      mimetype = vcon.Vcon.FILE_EXTENSIONS[extension]
  
    # TODO: add: aac, ogg, 
    else:
      raise Exception("MIME type not defined for extension: {}".format(extension))
  
    return(mimetype)


  # TODO: use mimetypes package instead
  @staticmethod
  def get_mime_extension(mime_type):
    """ get file extension for MIMETYPE """
    if(mime_type in vcon.Vcon.MIME_EXTENSIONS):
      extension = vcon.Vcon.MIME_EXTENSIONS[mime_type]

    else:
      raise Exception("extension not defined for mime type: {}".format(mime_type))
    return(extension)


  def _attempting_modify(self) -> None:
    if(self._state != VconStates.UNSIGNED):
      raise InvalidVconState("Cannot modify Vcon unless current state is UNSIGNED.  Current state: {}".format(self._state))

  def __add_new_party(self, index : int) -> int:
    """
    check if a new party needs to be added to the list

    Parameters:
    index (int): -1 indicates adding a new party, positive numbers
          throw AttributeError if the party with that index does not already exist

    Returns:
      party index in the list
    """
    self._attempting_modify()

    party = index
    if(party == -1):
      self._vcon_dict[Vcon.PARTIES].append({})
      party = len(self._vcon_dict[Vcon.PARTIES]) - 1

    else:
      if(not len(self._vcon_dict[Vcon.PARTIES]) > index):
        raise AttributeError(
          "index: {} > then party List length: {}.  Use index of -1 to add one to the end.".format(
          index, len(self._vcon_dict[Vcon.PARTIES])))

    return(party)


  def get_conversation_time(self) -> typing.Tuple[str, float]:
    """
    Get the start time and duration of the vcon

    Parameters: none

    Returns:
      Tuple(str, float): RFC2822 format string start time and float duration in seconds
    """
    # TODO: loop through dialogs and find the oldest start time, calculate end time from
    # duration, find the most recent end time and return the results

    # TODO: Dialog recordings for mutiple parties will not show the start/join time for
    # all of the parties, only the first to join.  Requires analysis of recording to show
    # when party speaks, but this may not be a good indicator of join time.  Where as signalling
    # has defininte joine time for each party, but is not captured in the vcon.
    raise Exception("not implemented")


  @tag_party
  def set_party_parameter(self,
    parameter_name : str,
    parameter_value : str,
    party_index : int =-1
    ) -> int:
    """
    Set the named parameter for the given party index.  If the index is not provided,
    add a new party to the vCon Parties Object array.

    Parameters:  
      **parameter_name** (String) - name of the Party Object parameter to be set.
                  Must beone of the following: ["tel", "stir", "mailto", "name", "validation", "gmlpos", "timezone"]  
      **parameter_value** (String) - new value to set for the named parameter  
      **party_index** (int) - index of party to set tel url on
                  (-1 indicates a new party should be added)  

    Returns:  
    int: if success, positive int index of party in list
    """

    self._attempting_modify()

    if(parameter_name not in Vcon.PARTIES_OBJECT_STRING_PARAMETERS):
      raise AttributeError(
        "Not supported: setting of Parties Object parameter: {}.  Must be one of the following:  {}".
        format(parameter_name, Vcon.PARTIES_OBJECT_STRING_PARAMETERS))

    party_index = self.__add_new_party(party_index)

    # TODO parameter specific validation
    self._vcon_dict[Vcon.PARTIES][party_index][parameter_name] = parameter_value

    return(party_index)


  @tag_party
  def add_party(self, party_dict: dict) -> int:
    """
    Add a new party to the vCon Parties Object array.

    Parameters:  
      **party_dict** (dict) - dict representing the parameter name and value pairs
                  Dict key must beone of the following: ["tel", "stir", "mailto", "name", "validation", "gmlpos", "timezone"]

    Returns:  
    int: if success, positive int index of party in list
    """
    self._attempting_modify()
    for key in party_dict.keys():
      if(key not in Vcon.PARTIES_OBJECT_STRING_PARAMETERS):
        raise AttributeError(f"Not supported: setting of Parties Object parameter: {key}." +
          f"  Must be one of the following:  {Vcon.PARTIES_OBJECT_STRING_PARAMETERS}")
    # TODO parameter specific validation
    self._vcon_dict[Vcon.PARTIES].append(party_dict)
    party_index = len(self._vcon_dict[Vcon.PARTIES]) - 1
    return party_index


  @deprecated("use Vcon.set_party_parameter")
  def set_party_tel_url(self, tel_url : str, party_index : int =-1) -> int:
    """
    Set tel URL for a party.

    Parameters:
      tel_url
      party_index (int): index of party to set tel url on
                  (-1 indicates a new party should be added)

    Returns:
      int: if success, opsitive int index of party in list
    """

    return(self.set_party_parameter("tel", tel_url, party_index))


  @tag_party
  def find_parties_by_parameter(self, parameter_name : str, parameter_value_substr : str) -> typing.List[int]:
    """
    Find the list of parties which have string parameters of the given name and value
    which contains the given substring.

    Parameters:  
      **parameter_name** (String) - name of the Party Object parameter to be searched.  
      **paramter_value_substr** (String) - substring to check if it is contained in the value of the given
              parameter name

    Returns:  
      List of indices into the parties object array for which the given parameter name's value
      contains a match for the given substring.
    """
    found = []
    for party_index, party in enumerate(self.parties):
      value = party.get(parameter_name, "")
      if(parameter_value_substr in value):
        found.append(party_index)

    return(found)


  @tag_dialog
  def add_dialog_inline_text(self,
    body : str,
    start_time : typing.Union[str, int, float, datetime.datetime],
    duration : typing.Union[int, float],
    party : typing.Union[int, list[int]],
    mime_type : str,
    file_name : typing.Union[str, None] = None) -> int:
    """
    Add a dialog segment for a text chat or email thread.

    Parameters:  
      **body** (str) - bytes for the text communication (e.g. text or multipart MIME body).  
      **start_time** (str, int, float, datetime.datetime) - Date, time of the start time the
               sender started typing or if unavailable, the time it was sent.
               String containing RFC 2822 or RFC3339 date time stamp or int/float
               containing epoch time (since 1970) in seconds.  
      **duration** (int or float) - duration in time the sender completed typing in seconds.
               Should be zero if unknown.
      **party** (int) - index into parties object array as to which party sent the text communication.  
      **mime_type** (str) - mime type of the body (usually MIMETYPE_TEXT_PLAIN or MIMETYPE_MULTIPART)  
      **file_name** (str) - file name of the body if applicable (optional)

    Returns:  
      Index of the new dialog in the Dialog Object array parameter.
    """

    self._attempting_modify()

    new_dialog: typing.Dict[str, typing.Any] = {}
    new_dialog['type'] = "text"
    new_dialog['start'] = vcon.utils.cannonize_date(start_time)
    new_dialog['duration'] = duration
    new_dialog['parties'] = party
    new_dialog['mimetype'] = mime_type
    if(file_name is not None and len(file_name) > 0):
      new_dialog['filename'] = file_name

    new_dialog['encoding'] = "none"
    new_dialog['body'] = body

    if(self.dialog is None):
      self._vcon_dict[Vcon.DIALOG] = []

    self._vcon_dict[Vcon.DIALOG].append(new_dialog)

    return(len(self.dialog) - 1)


  @tag_dialog
  def add_dialog_inline_email_message(
    self,
    smtp_message: str,
    file_name : typing.Union[str, None] = None
    ) -> int:
    """
    Add a new text dialog and any attachments for the given SMTP email message.

    SMTP message should include To, From, Subject, Cc, Date headers and may
    include a simple text or MIME body.  Attachments are added to Vcon. 

    Parameters:  
      **smtp_message** (str) - string containing the contents of a SMTP
      messages including headers and body.

    Returns:  
      index (int) of the dialog added for the text body of the message
    """

    email_message = email.message_from_string(smtp_message)

    # Set subject if its not already set
    if(self.subject is None or len(self.subject) == 0):
      subject = email_message.get("subject")
      if(subject is not None and subject != ""):
        self.set_subject(subject)

    # Get tuple(s) of (name, email_uri) for sender and recipients
    sender = email.utils.parseaddr(email_message.get("from"))
    recipients = email.utils.getaddresses(email_message.get_all("to", []) +
      email_message.get_all("cc", []) +
      email_message.get_all("recent-to", []) +
      email_message.get_all("recent-cc", []))

    party_indices = []
    sender_index = None
    for email_address in [sender] + recipients:
      logger.debug("email name: {} mailto: {}".format(email_address[0], email_address[1]))
      parties_found = self.find_parties_by_parameter("mailto", email_address[1])
      if(len(parties_found) == 0):
        parties_found = self.find_parties_by_parameter("name", email_address[0])

      if(len(parties_found) == 0):
        party_index = self.set_party_parameter("mailto", email_address[1])
        self.set_party_parameter("name", email_address[0], party_index)
        parties_found = [party_index]

      if(sender_index is None):
        sender_index = parties_found[0]

      party_indices.extend(parties_found)

      if(len(parties_found) > 1):
        logger.warning("Warning: multiple parties found matching {}: at indices: {}".format(email_address, parties_found))

    content_type = email_message.get("content-type")
    file_name = email_message.get_filename()
    #date = time.mktime(email.utils.parsedate(email_message.get("date")))
    date = email.utils.parsedate_to_datetime(email_message.get("date"))

    email_body = ""

    if(email_message.is_multipart()):
      body_start = False
      for line in str(email_message).splitlines():
        if(body_start):
          email_body = email_body + line + "\r\n"

        elif(len(line) == 0):
          body_start = True

    else:
      email_body = email_message.get_payload()

    dialog_index = self.add_dialog_inline_text(email_body, date, 0, party_indices, content_type, file_name)

    return(dialog_index)


  @tag_dialog
  def add_dialog_inline_recording(
    self,
    body : bytes,
    start_time : typing.Union[str, int, float, datetime.datetime],
    duration : typing.Union[int, float],
    parties : typing.Union[int, typing.List[int], typing.List[typing.List[int]]],
    mime_type : str,
    file_name : typing.Union[str, None] = None,
    originator : typing.Union[int, None] = None) -> int:
    """
    Add a recording of a portion of the conversation, inline (base64 encoded) to the dialog.

    Parameters:  
    **body** (bytes): bytes for the audio or video recording (e.g. wave or MP3 file).  
    **start_time** (str, int, float, datetime.datetime): Date, time of the start of
               the recording.
               string containing RFC 2822 or RFC3339 date time stamp or int/float
               containing epoch time (since 1970) in seconds.
    **duration** (int or float): duration of the recording in seconds  
    **parties** (int, List[int], List[List[int]]): party indices speaking in each
               channel of the recording.  
    **mime_type** (str): mime type of the recording  
    **file_name** (str): file name of the recording (optional)  
    **originator** (int): by default the originator of the dialog is the first party listed in the parites array.
               However , in some cases, it is difficult to arrange the recording channels with the originator
               as the first party/channel.  In these cases, the originator can be explicitly provided.  The
               value of the originator is the index into the Vcon.parties array of the party that originated
               this dialog.

    Returns:  
            Number of bytes read from body.
    """
    # TODO should return dialog index not byte count

    # TODO: do we want to know the number of channels?  e.g. to verify party list length

    # TODO: should we validate the start time?

    self._attempting_modify()

    new_dialog: typing.Dict[str, typing.Any] = {}
    new_dialog['type'] = "recording"
    new_dialog['start'] = vcon.utils.cannonize_date(start_time)
    new_dialog['duration'] = duration

    if(parties is not None and
      parties != ""
      ):
      new_dialog['parties'] = parties

    new_dialog['mimetype'] = mime_type

    if(file_name is not None and len(file_name) > 0):
      new_dialog['filename'] = file_name

    if(originator is not None and originator >= 0):
      new_dialog['originator'] = originator

    new_dialog['encoding'] = "base64url"
    encoded_body = jose.utils.base64url_encode(body).decode('utf-8')
    #print("encoded body type: {}".format(type(encoded_body)))
    new_dialog['body'] = encoded_body

    if(self.dialog is None):
      self._vcon_dict[Vcon.DIALOG] = []

    self._vcon_dict[Vcon.DIALOG].append(new_dialog)

    return(len(body))

  @deprecated("use Vcon.decode_dialog_inline_body")
  def decode_dialog_inline_recording(self, dialog_index : int) -> bytes:
    """ depricated use decode_dialog_inline_body """
    body = self.decode_dialog_inline_body(dialog_index)
    # this should never happen, its to silence the linters
    if(isinstance(body, str)):
      body = bytes(body, "utf-8")

    return(body)


  @tag_dialog
  async def get_dialog_text(
    self,
    dialog_index: int,
    find_transcript: bool = True,
    generate_transcript: bool = False
    ) -> typing.List[typing.Dict[str, typing.Any]]:
    """
    Get the text for this dialog.

    If this is a text dialog, return the text.  If this is a recording dialog
    try to find the transcript for this dialog in the analysis objects and 
    return the text from the transcript.

    Parameters:  
      **dialog_index** (int) - index to the dialog in this Vcon's dialog objects list.  
      **find_transcript** (bool) - try to find transcript for this dialog in the
        analysis objects list and get the transcript text.  
      **generate_transcript** (bool) - if the transcript for this dialog is not found
        in the analysis objects, generate the transcript using the default transcript
        type FilterPlugin.

    Returns:  
      list of dicts where each dict contains the following:
        * "party" (int) - index to the party that typed or spoke the given text
        * "text" (str) - the typed or spoken text
        * "start" (str) - the RFC3339 time stamp at which the text started/spoken/transmitted
        * "duration" (int) - optional duration over which the text was typed or spoken

      Text dialogs will return a single dict, recording dialogs may return one or more dicts.
    """

    #dialog type    mimetype   action
    #================================
    # text          TEXT_PLAIN return text body
    # text          MULTIPART  find first plain/text in multipart body
    # recording     N/A        find transcript in analysis

    dialog = self.dialog[dialog_index]
    if(dialog["type"] == "text"):
      #logger.debug("get_dialog_text mime type:{}".format(dialog["mimetype"]))
      text_dict = {}
      text_dict["party"] = dialog["parties"][0]
      text_dict["start"] = dialog["start"]
      text_dict["duration"] = dialog["duration"]

      if(dialog["mimetype"].lower() == vcon.Vcon.MIMETYPE_TEXT_PLAIN):
        text_dict["text"] = dialog["body"]
        return([text_dict])

      if(vcon.Vcon.MIMETYPE_MULTIPART in dialog["mimetype"].lower() ):
        # Need the content type with the boundry and body separator
        email_message = email.message_from_string("Content-Type: " + dialog["mimetype"] + "\r\n\r\n" + dialog["body"])

        if(not email_message.is_multipart()):
          logger.warning("Text body in dialog[{}] incorrectly labeled as multipart".format(dialog_index))

        for subpart in email_message.walk():
          if(subpart.get_content_type() == vcon.Vcon.MIMETYPE_TEXT_PLAIN):
            logger.debug("subpart payload type: {} part is multipart: {}".format(type(subpart.get_payload()), subpart.is_multipart()))
            text_dict["text"] = subpart.get_payload()
            return([text_dict])

          # else:
          #   logger.debug("skipping part mimetype: {}".format(subpart.get_content_type()))

    elif(dialog["type"] == "recording"):
      transcript_index = self.find_transcript_for_dialog(dialog_index)
      if(transcript_index is None):
        await self.transcribe({})
        transcript_index = self.find_transcript_for_dialog(dialog_index)

      if(transcript_index is not None):
        analysis = self.analysis[transcript_index]
        accessor_class = vcon.accessors.transcript_accessors[(
          analysis["vendor"].lower(),
          analysis["product"].lower(),
          analysis["schema"].lower(),
          )]
        accessor = accessor_class(dialog, analysis)
        return(accessor.get_text())

    return([])


  @tag_dialog
  def find_transcript_for_dialog(
    self,
    dialog_index: int,
    transcript_accessor_exists: bool = True,
    transcript_accessors: typing.Union[typing.List[typing.Tuple[str, str, str]], None] = None
    ) -> typing.Union[int, None]:
    """
    Find the index to the transcript analysis for the indicated dialog.

    Parameters:  
      **dialog_index** (int) - index to a recording dialog  
      **transcript_accessor_exists** (bool) - only consider transcript analysis objects
        for which a transcript_accessor exist.

    Returns:  
      (int or None) - index of the transcript type analysis object in this Vcon or
        None if not found.
    """
    if(transcript_accessors is None):
      transcript_accessors = list(vcon.accessors.transcript_accessors.keys())
    logger.debug("accessors: {}".format(transcript_accessors))

    for analysis_index, analysis in enumerate(self.analysis):
      if(analysis["type"] == "transcript" and
        analysis["dialog"] == dialog_index
        ):
        if(not transcript_accessor_exists):
          return(analysis_index)

        generator_tuple = (
          analysis.get("vendor", "").lower(),
          analysis.get("product", "").lower(),
          analysis.get("schema", "").lower()
          )

        logger.debug("generator: {}".format(generator_tuple))
        if(generator_tuple in transcript_accessors):
          return(analysis_index)

    return(None)


  @tag_dialog
  async def get_dialog_body(self, dialog_index: int) -> typing.Union[str, bytes]:
    """
    Get the dialog body whether it is inline or an externally reference URL

    Parameters:  
    **dialog_index** (int) - index of the dialog in the Vcon, from which to retrieve the body

    Returns:  
    (str) or (bytes) for the dialog body
    """
    dialog = self.dialog[dialog_index]

    if(any(key in dialog for key in("body", "url"))):
      if("body" in dialog and dialog["body"] is not None and dialog["body"] != ""):
        # Need to base64url decode recording
        body_bytes = self.decode_dialog_inline_body(dialog_index)
      elif("url" in dialog and dialog["url"] is not None and dialog["url"] != ""):
        # HTTP GET and verify the externally referenced recording
        body_bytes = await self.get_dialog_external_recording(dialog_index)
      else:
        raise Exception("dialog[{}] has no body or url.  Should not have gotten here.".format(dialog_index))

    return(body_bytes)



  @tag_dialog
  def decode_dialog_inline_body(self, dialog_index : int) -> typing.Union[str, bytes]:
    """
    Get the dialog recording at the given index, decoding it and returning the raw bytes.

    Parameters:  
      **dialog_index** (int): index the the dialog in the dialog list, containing the inline recording

    Returns:  
      (bytes): the bytes for the recording file
    """
    dialog = self.dialog[dialog_index]
    if(dialog["type"] not in ["text", "recording"]):
      raise AttributeError("dialog[{}] type: {} is not supported".format(dialog_index, dialog["type"]))
    if(dialog.get("body") is None):
      raise AttributeError("dialog[{}] does not contain an inline body/file".format(dialog_index))

    encoding = dialog.get("encoding", "none").lower()
    if(encoding == "base64url"):
      # This is wrong.  decode should take a string not bytes, but it fails without the bytes conversion
      # this is a bug in jose.baseurl_decode
      decoded_body = jose.utils.base64url_decode(bytes(dialog["body"], 'utf-8'))

    # No encoding
    elif(encoding == "none"):
      decoded_body = dialog["body"]

    else:
      raise UnsupportedVconVersion("dialog[{}] body encoding: {} not supported".format(dialog_index, dialog["encoding"]))

    return(decoded_body)


  @tag_dialog
  def add_dialog_external_recording(self, body : bytes,
    start_time : typing.Union[str, int, float, datetime.datetime],
    duration : typing.Union[int, float],
    parties : typing.Union[int, typing.List[int], typing.List[typing.List[int]]],
    external_url: str,
    mime_type : typing.Union[str, None] = None,
    file_name : typing.Union[str, None] = None,
    sign_type : typing.Union[str, None] = "SHA-512",
    originator : typing.Union[int, None] = None) -> int:
    """
    Add a recording of a portion of the conversation, as a reference via the given
    URL, to the dialog and generate a signature and key for the content.  This
    method has the limitation that the entire recording must be passed in in-memory.

    Parameters:  
    **body** (bytes): bytes for the audio or video recording (e.g. wave or MP3 file).  
    **start_time** (str, int, float, datetime.datetime): Date, time of the start of
               the recording.
               string containing RFC 2822 or RFC 3339 date time stamp or int/float
               containing epoch time (since 1970) in seconds.  
    **duration** (int or float): duration of the recording in seconds  
    **parties** (int, List[int], List[List[int]]): party indices speaking in each
               channel of the recording.  
    **external_url** (string): https URL where the body is stored securely  
    **mime_type** (str): mime type of the recording (optional)  
    **file_name** (str): file name of the recording (optional)  
    **sign_type** (str): signature type to create for external signature
                     default= "SHA-512" use SHA 512 bit hash (RFC6234)
                     "LM-OTS" use Leighton-Micali One Time Signature (RFC8554)  
    **originator** (int): by default the originator of the dialog is the first party listed in the parites array.
               However , in some cases, it is difficult to arrange the recording channels with the originator
               as the first party/channel.  In these cases, the originator can be explicitly provided.  The
               value of the originator is the index into the Vcon.parties array of the party that originated
               this dialog.

    Returns:  
            Index to the added dialog
    """
    # TODO should return dialog index not byte count

    # TODO: need a streaming/chunk version of this so that we don't have to have the whole file in memory.

    self._attempting_modify()

    new_dialog: typing.Dict[str, typing.Any] = {}
    new_dialog['type'] = "recording"
    new_dialog['start'] = vcon.utils.cannonize_date(start_time)
    new_dialog['duration'] = duration
    new_dialog['parties'] = parties
    new_dialog['url'] = external_url
    if(mime_type is not None):
      new_dialog['mimetype'] = mime_type
    if(file_name is not None):
      new_dialog['filename'] = file_name
    if(originator is not None and originator >= 0):
      new_dialog['originator'] = originator


    if (body):
      if(sign_type == "LM-OTS"):
        logger.warning("Warning: \"LM-OTS\" may be depricated")
        key, signature = vcon.security.lm_one_time_signature(body)
        new_dialog['key'] = key
        new_dialog['signature'] = signature
        new_dialog['alg'] = "LMOTS_SHA256_N32_W8"

      elif(sign_type == "SHA-512"):
        sig_hash = vcon.security.sha_512_hash(body)
        new_dialog['signature'] = sig_hash
        new_dialog['alg'] = "SHA-512"

      else:
        raise AttributeError("Unsupported signature type: {}.  Please use \"SHA-512\" or \"LM-OTS\"".format(sign_type))

    if(self.dialog is None):
      self._vcon_dict[Vcon.DIALOG] = []

    dialog_index = len(self.dialog)
    self._vcon_dict[Vcon.DIALOG].append(new_dialog)

    return(dialog_index)


  @tag_dialog
  async def get_dialog_external_recording(self,
    dialog_index : int,
    get_kwargs: typing.Union[dict, None] = None
    ) -> bytes:
    """
    Get the externally referenced dialog recording via the dialog's url
    and verify its integrity using the signature in the dialog object,
    blocking on its return.

    Parameters:  
      **dialog_index** (int) - index into the Vcon.dialog array indicating
        which external recording is to be retrieved and verified.  
      **get_kwargs** (dict) - kwargs passed to **requests.get** method
        defaults to {"timeout": = 20} seconds

    Returns:  
      verified content/bytes for the recording
    """
    # Get body from URL using requests
    url = self.dialog[dialog_index]["url"]
    if(get_kwargs is None):
      get_kwargs = {"timeout": 20}
    req = requests.get(url, **get_kwargs)
    if(not(200 <= req.status_code < 300)):
      raise Exception("get of {} resulted in error: {}".format(
        url,
        req.status_code
        ))
    body = req.content

    # verify the body
    self.verify_dialog_external_recording(dialog_index, body)

    return(body)

  @tag_signing
  def verify_dialog_external_recording(self, dialog_index : int, body : bytes) -> None:
    """
    Verify the given body of the externally stored recording for the indicted dialog.
    Using the signature and public key stored in the dialog, the content of the body
    of the recording is verifyed.

    Parameters:  
      **dialog_index** (int): index of the dialog to be verified  
      **body** (bytes): the contents of the recording which is stored external to this vCon

    Returns: none

    Raises exceptions if the signature and public key fail to verify the body.
    """

    dialog = self.dialog[dialog_index]

    if(dialog['type'] != "recording"):
      raise AttributeError("dialog[{}] is of type: {} not recording".format(dialog_index, dialog['type']))

    if(len(dialog['signature']) < 1 ):
      raise AttributeError("dialog[{}] signature: {} not set.  Must be for LMOTS_SHA256_N32_W8".format(dialog_index, dialog['signature']))

    if(dialog['alg'] == 'LMOTS_SHA256_N32_W8'):
      if(len(dialog['key']) < 1 ):
        raise AttributeError("dialog[{}] key: {} not set.  Must be for LMOTS_SHA256_N32_W8".format(dialog_index, dialog['key']))

      vcon.security.verify_lm_one_time_signature(body,
        dialog['signature'],
        dialog['key'])

    elif(dialog['alg'] == 'SHA-512'):
      sig_hash = vcon.security.sha_512_hash(body)
      if( dialog['signature'] != sig_hash):
        print("dialog[\"signature\"]: {} hash: {} size: {}".format(dialog['signature'], sig_hash, len(body)))
        print("dialog: {}".format(json.dumps(dialog, indent=2)))
        raise InvalidVconHash("SHA-512 hash in signature does not match the given body for dialog[{}]".format(dialog_index))

    else:
      raise AttributeError("dialog[{}] alg: {} not supported.  Must be SHA-512 or LMOTS_SHA256_N32_W8".format(dialog_index, dialog['alg']))


  @tag_analysis
  def add_analysis_transcript(self,
    dialog_index : int,
    transcript : dict,
    vendor : str,
    schema : typing.Union[str, None] = None,
    analysis_type: str = "transcript",
    encoding : str = "json",
    **optional_parameters: typing.Dict[str, typing.Any]
    ) -> None:
    """
    Add a transcript for the indicated dialog.

    Parameters:  
    **dialog_index** (str): index to the dialog in the vCon dialog list that this trascript corresponds to.  
    **vendor** (str): string token for the vendor of the audio to text transcription service.  
    **schema** (str): schema label for the transcription data.  Used to identify data format of the transcription
                  for vendors that have more than one format or version.

    Return: none
    """

    self._attempting_modify()

    analysis_element: typing.Dict[str, typing.Any] = {}
    analysis_element["type"] = analysis_type
    # TODO should validate dialog_index??
    analysis_element["dialog"] = dialog_index
    analysis_element["body"] = transcript
    analysis_element["encoding"] = encoding
    analysis_element["vendor"] = vendor
    if(schema is not None):
      analysis_element["schema"] = schema

    for param, value in optional_parameters.items():
      analysis_element[param] = value

    if(self.analysis is None):
      self._vcon_dict[Vcon.ANALYSIS] = []

    self._vcon_dict[Vcon.ANALYSIS].append(analysis_element)

  @tag_analysis
  def add_analysis(self,
    dialog_index : typing.Union[int, typing.List[int]],
    analysis_type: str,
    body : typing.Union[str, None] = None,
    vendor : typing.Union[str, None] = None,
    schema : typing.Union[str, None] = None,
    encoding : str= "json",
    **optional_parameters
    ) -> None:
    """
    Add a generic analysis for the indicated dialog.

    Parameters:  
    **dialog_index** (Union[int, list[int]]): index or list of indices to the dialog in the vCon dialog
      list that this analysis was generated from.  
    **vendor** (str): string token for the vendor of the audio to text transcription service  
    **schema** (str): schema label for the transcription data.  Used to identify data format of the transcription
                  for vendors that have more than one format or version.  
    **optional_parameters** (dict[str, Any]) - additional parameters to add to the analysis object.

    Return: none
    """

    self._attempting_modify()

    analysis_element = {}
    analysis_element["type"] = analysis_type
    analysis_element["dialog"] = dialog_index
    if(body is not None and body != ""):
      analysis_element["body"] = body
    analysis_element["encoding"] = encoding
    if(vendor is not None and vendor != ""):
      analysis_element["vendor"] = vendor
    if(schema is not None and schema != ""):
      analysis_element["schema"] = schema

    for parameter_name, value in optional_parameters.items():
      analysis_element[parameter_name] = value

    if(self.analysis is None):
      self._vcon_dict[Vcon.ANALYSIS] = []

    self._vcon_dict[Vcon.ANALYSIS].append(analysis_element)


  @tag_attachment
  def add_attachment_inline(
    self,
    body : bytes,
    sent_time : typing.Union[str, int, float, datetime.datetime],
    party : int,
    mime_type : typing.Union[str, None] = None,
    file_name : typing.Union[str, None] = None
    ) -> int:
    """
    Add an attachment object for the given file body

    Parameters:  
    **body** (bytes): bytes for the audio or video recording (e.g. wave or MP3 file).  
    **send_time** (str, int, float, datetime.datetime): Date, time the attachment was sent.
               string containing RFC 2822 or RFC3339 date time stamp or int/float
               containing epoch time (since 1970) in seconds.  
    **party** (int): party index of the sender  
    **mime_type** (str): mime type of the recording  
    **file_name** (str): file name of the recording (optional)

    Returns:  
    (int) index of the added attachment
    """

    self._attempting_modify()

    new_attachment: typing.Dict[str, typing.Any] = {}
    new_attachment['start'] = vcon.utils.cannonize_date(sent_time)
    new_attachment['party'] = party
    if(mime_type is not None and
      mime_type != ""):
      new_attachment['mimetype'] = mime_type
      if(mime_type in [
        vcon.Vcon.MIMETYPE_TEXT_PLAIN,
        vcon.Vcon.MIMETYPE_JSON
        ]):
        encoding = "none"
      else:
        encoding = "base64url"

    if(file_name is not None and
      len(file_name) > 0):
      new_attachment['filename'] = file_name

    new_attachment['encoding'] = encoding
    if(encoding == "none"):
      if(isinstance(body, str)):
        encoded_body = body
      else:
        encoded_body = body.decode('utf-8')
    else:
      encoded_body = jose.utils.base64url_encode(body).decode('utf-8')
    #print("encoded body type: {}".format(type(encoded_body)))
    new_attachment['body'] = encoded_body

    if(self.attachments is None):
      self._vcon_dict[Vcon.ATTACHMENTS] = []

    self._vcon_dict[Vcon.ATTACHMENTS].append(new_attachment)

    return(len(self.attachments) - 1)


  @tag_serialize
  def dump(
      self,
      vconfile: typing.Union[str, typing.TextIO],
      indent: typing.Union[int, None] = None
    ) -> None:
    """
    dump vcon in JSON form to given file

    Parameters:  
    **vconfile** (str, TextIO) - if string, file name else file like object to write Vcon JSON to.  
    **index** (None, int) - apply indenting/pretty printing to JSON

    Return: none
    """
    if(isinstance(vconfile, str)):
      file_handle = open(vconfile, "w")
    else:
      file_handle = vconfile

    file_handle.write(self.dumps(indent = indent))

    if(isinstance(vconfile, str)):
      file_handle.close()


  @tag_serialize
  def dumps(
      self,
      signed: bool = True,
      indent: typing.Union[int, None] = None
    ) -> str:
    """
    Dump the vCon as a JSON string.

    Parameters:  
    **signed** (Boolean): If the vCon is signed locally or verfied,  
        True: serialize the signed version  
        False: serialize the unsigned version

    Returns:  
             String containing JSON representation of the vCon.
    """
    return(json.dumps(self.dumpd(signed, False), indent = indent, default=lambda o: o.__dict__, **dumps_options))


  @tag_serialize
  def dumpd(
      self,
      signed: bool = True,
      deepcopy: bool = True,
    ) -> dict:
    """
    Dump the vCon as a dict representing JSON.

    Parameters:

    signed (Boolean): If the vCon is signed locally or verfied,
        True: serialize the signed version
        False: serialize the unsigned version

    deepcopy (boolean): make a deep copy of the dict so that 
        the Vcon data is not much with.
        True (default): make deep copy of the dict holding Vcon JSON data (highly recommended)
        False: pass reference to Vcon data as dict (dangerous)

    Returns:
             dict containing JSON representation of the vCon.
    """



    # TODO: Should it throw an acception if its not signed?  Could have argument to
    # not throw if it not signed.
    vcon_dict = None

    if(self._state == VconStates.UNSIGNED):
      if(self.uuid is None or len(self.uuid) < 1):
        raise InvalidVconState("vCon has no UUID set.  Use set_uuid method.")
      vcon_dict = self._vcon_dict


    elif(self._state in [VconStates.SIGNED, VconStates.UNVERIFIED, VconStates.VERIFIED]):
      if(signed is False and self._state != VconStates.UNVERIFIED):
        vcon_dict = self._vcon_dict
      else:
        vcon_dict = self._jws_dict

    elif(self._state in [VconStates.ENCRYPTED, VconStates.DECRYPTED]):
      if(signed is False):
        raise AttributeError("not supported: unsigned JSON output for encrypted vCon")
      vcon_dict = self._jwe_dict

    else:
      raise InvalidVconState("vCon state: {} is not valid for dumps".format(self._state))

    if(deepcopy):
      return(copy.deepcopy(vcon_dict))

    return(vcon_dict)


  @tag_serialize
  async def post(
    self,
    base_uri: str = "http://{host}:{port}/vcon",
    host: str = "localhost",
    port: int = 8000,
    # not sure why I cannot use vcon.Vcon.MIMETYPE_JSON here
    post_kwargs: typing.Dict[str, typing.Any] = {"timeout": 20}
    ) -> None:
    """
    HTTP Post this Vcon from the given base_uri and path.

    Parameters:  
    **base_url** (str) - template URL for HTTP post  
    **host** (str) - host IP or DNS name to use in URL  
    **port** (int) - HTTP port to use  
    **post_kwargs** (dict) - extra args to pass to requests.post

    Return: none
    """
    if(post_kwargs is None):
      post_kwargs = {"timeout": 20}

    uri = base_uri.format(
      host = host,
      port = port
      )

    req = requests.post(uri, json = self.dumpd(), **post_kwargs)
    if(not(200 <= req.status_code < 300)):
      raise Exception("post of {} resulted in error: {}".format(
        uri,
        req.status_code
        ))


  @tag_serialize
  def load(self, vconfile: typing.Union[str, typing.TextIO]) -> None:
    """
    Load the Vcon JSON from the given file_handle and deserialize it.
    see Vcon.loads for more details.

    Parameters: 
    **vconfile** (str, TextIO) - if string, file name else file like object to write Vcon JSON to.  

    Returns: none
    """
    self._attempting_modify()

    if(isinstance(vconfile, str)):
      file_handle = open(vconfile, "rb")
    else:
      file_handle = vconfile

    vcon_json_string = file_handle.read()

    if(isinstance(vconfile, str)):
      file_handle.close()

    self.loads(vcon_json_string)


  @tag_serialize
  def loadd(self, vcon_dict : dict) -> None:
    """
    Load the vCon from the JSON style dict.
    Assumes that this vCon is an empty vCon as it is not cleared.

    Decision as to what json form to be deserialized is:
    1) unsigned vcon must have a vcon and one or more of the following elements: parties, dialog, analysis, attachments
    2) JWS vCon must have a payload and signatures
    3) JWE vCon must have a cyphertext and recipients

    Parameters:  
      **vcon_dict** (dict): dict containing JSON representation of a vCon

    Returns: none
    """

    # TODO:  Should refactor this and loads to work with dict.  This is very
    # inefficient as we are serializing and then deserializing.
    vcon_string = json.dumps(vcon_dict)

    return(self.loads(vcon_string))


  @tag_serialize
  def loads(self, vcon_json : str) -> None:
    """
    Load the vCon from a JSON string.
    Assumes that this vCon is an empty vCon as it is not cleared.

    Decision as to what json form to be deserialized is:
    1) unsigned vcon must have a vcon and one or more of the following elements: parties, dialog, analysis, attachments
    2) JWS vCon must have a payload and signatures
    3) JWE vCon must have a cyphertext and recipients

    Parameters:  
      **vcon_json** (str): string containing JSON representation of a vCon

    Returns: none
    """

    self._attempting_modify()

    #TODO: Should check unsafe stuff is not loaded

    # TODO should use self._attempting_modify() ???
    if(self._state != VconStates.UNSIGNED):
      raise InvalidVconState("Cannot load Vcon unless current state is UNSIGNED.  Current state: {}".format(self._state))

    vcon_dict = json.loads(vcon_json)

    # we need to check the format as to whether it is signed or
    # not and deconstruct the loaded object.
    # load differently based upon the contents of the JSON

    # Signed vCon (JWS)
    if(("payload" in vcon_dict) and
      ("signatures" in vcon_dict)
      ):
      self._vcon_dict = {}

      self._state = VconStates.UNVERIFIED
      self._jws_dict = vcon_dict

    # encrypted vCon (JWE)
    elif(("cyphertext" in vcon_dict) and
      ("recipients" in vcon_dict)
      ):
      self._vcon_dict = {}

      self._state = VconStates.ENCRYPTED
      self._jwe_dict = vcon_dict

    # Unsigned vCon has to have vcon version and
    elif((self.VCON_VERSION in vcon_dict) and (
      # one of the following arrays
      ('parties' in vcon_dict) or
      ('dialog' in vcon_dict) or
      ('analysis' in vcon_dict) or
      ('attachments' in vcon_dict)
      )):

      # validate version
      version_string = vcon_dict.get(self.VCON_VERSION, "not set")
      if(version_string != "0.0.1"):
        raise UnsupportedVconVersion("loads of JSON vcon version: \"{}\" not supported".format(version_string))

      self._vcon_dict = self.migrate_0_0_1_vcon(vcon_dict)

    # Unknown
    else:
      raise InvalidVconJson("Not recognized as a unsigned , signed or encrypted form of JSON vCon." +
        "  Unsigned vcon must have vcon version and at least one of: parties, dialog, analyisis or attachment object arrays." +
        "  Signed vcon must have payload and signatures fields." +
        "  Encrypted vcon must have cyphertext and recipients fields."
        )


  @tag_serialize
  async def get(
    self,
    uuid: str,
    base_uri: str = "http://{host}:{port}{path}",
    host: str = "localhost",
    port: int = 8000,
    path: str = "/vcon/{uuid}",
    # not sure why I cannot use vcon.Vcon.MIMETYPE_JSON here
    get_kwargs: typing.Dict[str, typing.Any] = {"timeout": 20, "headers": {"accept": "application/json"}}
    ) -> None:
    """
    HTTP GET the Vcon from the given base_uri and path.

    Parameters:  
    **uuid** (str) - UUID of the vCon to retrieve  
    **base_url** (str) - template URL for HTTP post  
    **host** (str) - host IP or DNS name to use in URL  
    **port** (int) - HTTP port to use  
    **path** (str) - template path for the URL  
    **get_kwargs** (dict) - extra args to pass to requests.get

    Return: none
    """
    if(get_kwargs is None):
      get_kwargs = {"timeout": 20, "headers": {"accept": vcon.Vcon.MIMETYPE_JSON }}

    uri = base_uri.format(
      host = host,
      port = port,
      path = path.format(uuid = uuid)
      )
    req = requests.get(uri, **get_kwargs)
    if(not(200 <= req.status_code < 300)):
      raise Exception("get of {} resulted in error: {}".format(
        uri,
        req.status_code
        ))
    vcon_json = req.content
    self.loads(vcon_json)

  @tag_signing
  def sign(self, private_key_pem_file_name : str, cert_chain_pem_file_names : typing.List[str]) -> None:
    """
    Sign the vcon using the given private key from the give certificate chain.

    Parameters:  
    **private_key_pem_file_name** (str): the private key to use for signing the vcon.  
    **cert_chain_pem_file_names** (List[str]): file names for the pem format certicate chain for the
        private key to use for signing.  The cert/public key corresponding to the private key should be the
        first cert.  THe certificate authority root should be the last cert.

    Returns: none
    """

    if(self._state == VconStates.SIGNED):
      raise InvalidVconState("Vcon was already signed.")

    if(self._state != VconStates.UNSIGNED):
      raise InvalidVconState("Vcon not in valid state to be signed: {}.".format(self._state))

    if(self.uuid is None or len(self.uuid) < 1):
      raise InvalidVconState("vCon has no UUID set.  Use set_uuid method before signing.")

    header, signing_jwk = vcon.security.build_signing_jwk_from_pem_files(private_key_pem_file_name, cert_chain_pem_file_names)

    # dot separated JWS token.  First part is the payload, second part is the signature (both base64url encoded)
    jws_token = jose.jws.sign(self._vcon_dict, signing_jwk, headers=header, algorithm=signing_jwk["alg"])
    #print(jws_token.split('.'))
    protected_header, payload, signature = jws_token.split('.')
    #print("decoded header: {}".format(jose.utils.base64url_decode(bytes(protected_header, 'utf-8'))))

    jws_serialization = {}
    jws_serialization['payload'] = payload
    jws_serialization['signatures'] = []
    first_sig = {}
    first_sig['header'] = header
    first_sig['signature'] = signature
    first_sig['protected'] = protected_header
    jws_serialization['signatures'].append(first_sig)

    self._jws_dict = jws_serialization
    self._state = VconStates.SIGNED


  @tag_signing
  def verify(self, ca_cert_pem_file_names : typing.List[str]) -> None:
    """
    Verify the signed vCon and its certificate chain which should be issued by one of the given CAs

    Parameters:  
      **ca_cert_pem_file_names** (List[str]): list of Certificate Authority certificate PEM file names
        to verify the vCon's certificate chain.

    Returns: none

    Raises exceptions for invalid cert chaind, invalid cert dates or chain not issued by one
    of the given CAs.

    NOTE:  DOES NOT CHECK REVOKATION LISTS!!!
    """
    if(self._state == VconStates.SIGNED):
      raise InvalidVconState("Vcon was locally signed.  No need to verify")

    if(self._state == VconStates.VERIFIED):
      raise InvalidVconState("Vcon was already verified")

    if(self._state != VconStates.UNVERIFIED):
      raise InvalidVconState("Vcon cannot be verified invalid state: {}")

    if(self._jws_dict is None or
      ('signatures' not in self._jws_dict) or
      (len(self._jws_dict['signatures']) < 1) or
      ('signature' not in self._jws_dict['signatures'][0])
      ):
      raise InvalidVconState("Vcon JWS invalid")

    # Load an array of CA certficate objects to use to verify acceptable cert chains
    ca_cert_object_list = []
    for ca in ca_cert_pem_file_names:
      ca_cert_object_list.append(vcon.security.load_pem_cert(ca)[0])

    last_exception = Exception("Internal error in Vcon.verify this exception should never be thrown")
    chain_count = 0
    for signature in self._jws_dict['signatures']:
      if('header' in signature):
        if('x5c' in signature['header']):
          x5c = signature['header']['x5c']
          chain_count += 1

          cert_chain_objects = vcon.security.der_to_certs(x5c)

          # TODO: some of this should be move to the security submodule
          # e.g. the iterating over CAs

          # TODO: need to do something a little smarter on the exception raise to
          # give a clue of the best/closest chain and CA that failed.  Perhaps
          # even all of the failures.

          try:
            vcon.security.verify_cert_chain(cert_chain_objects)

            # We have a valid chain, check if its from one of the accepted CAs
            for ca_object in ca_cert_object_list:
              try:
                vcon.security.verify_cert(cert_chain_objects[len(cert_chain_objects) - 1], ca_object)

                # IF we get here, we have a valid chain: cert_chain_objects issued from one of our accepted
                # CAs: ca_object.
                # The assumtion is that it is safe to trust this cert chain.  So we
                # can use it to build a JWK and verify the signature.
                verification_jwk = {}
                verification_jwk["kty"] = "RSA"
                verification_jwk["use"] = "sig"
                verification_jwk["alg"] = signature['header']['alg']
                verification_jwk["e"] = jose.utils.base64url_encode(jose.utils.
                  long_to_bytes(cert_chain_objects[0].public_key().public_numbers().e)).decode('utf-8')
                verification_jwk["n"] = jose.utils.base64url_encode(jose.utils.
                  long_to_bytes(cert_chain_objects[0].public_key().public_numbers().n)).decode('utf-8')

                jws_token = signature['protected'] + "." + self._jws_dict['payload'] + "." + signature['signature']
                verified_payload = jose.jws.verify(jws_token, verification_jwk, verification_jwk["alg"])

                # If we get here, the payload was verified
                #print("verified payload: {}".format(verified_payload))
                #print("verified payload type: {}".format(type(verified_payload)))
                vcon_dict = json.loads(verified_payload.decode('utf-8'))
                self._vcon_dict = self.migrate_0_0_1_vcon(vcon_dict)

                self._state = VconStates.VERIFIED

                return(None)

              # This valid chain, is not issued from the CA for this ca_objjwk
              except Exception as e:
                last_exception = e
                # Keep trying other CAs until we run out or succeed

          # Invalid chain
          except Exception as e:
            last_exception = e
            # Keep trying other chains until we run out or succeed

    if(chain_count == 0):
      raise InvalidVconSignature("None of the signatures contain the x5c chain, which this implementation currenlty requires.")

    raise last_exception


  @tag_encrypting
  def encrypt(self, cert_pem_file_name : str) -> None:
    """
    encrypt a Signed vcon using the given public key from the give certificate.

    vcon must be signed first.

    Parameters:  
    **cert_pem_file_name** (str): the public key/cert to use for encrypting the vcon.

    Returns: none
    """

    if(self._state not in [VconStates.SIGNED, VconStates.UNVERIFIED]):
      raise InvalidVconState("Vcon must be signed before it can be encrypted")

    if(len(self._jws_dict) < 2):
      raise InvalidVconState("Vcon signature does not seem valid: {}".format(self._jws_dict))

    # both of these work
    #encryption = "A256GCM"
    encryption = "A256CBC-HS512"

    encryption_key = vcon.security.build_encryption_jwk_from_pem_file(cert_pem_file_name)

    plaintext = json.dumps(self._jws_dict, **dumps_options)

    jwe_compact_token = jose.jwe.encrypt(plaintext, encryption_key, encryption, encryption_key['alg']).decode('utf-8')
    jwe_complete_serialization = vcon.security.jwe_compact_token_to_complete_serialization(jwe_compact_token, enc = encryption, x5c = [])
    self._jwe_dict = jwe_complete_serialization
    self._state = VconStates.ENCRYPTED


  @tag_encrypting
  def decrypt(self, private_key_pem_file_name : str, cert_pem_file_name : str) -> None:
    """
    Decrypt a vCon using private and public key file.

    vCon must be in encrypted state and will be in signed state after decryption.

    Parameters:  
    **private_key_pem_file_name** (str): the private key to use for decrypting the vcon.  
    **cert_pem_file_name** (str): the public key/cert to use for decrypting the vcon.

    Returns: none
    """

    if(self._state != VconStates.ENCRYPTED):
      raise InvalidVconState("Vcon is not encerypted")

    if(len(self._jwe_dict) < 2):
      raise InvalidVconState("Vcon JWE does not seem valid: {}".format(self._jws_dict))

    jwe_compact_token_reconstructed = vcon.security.jwe_complete_serialization_to_compact_token(self._jwe_dict)

    (header, signing_key) = vcon.security.build_signing_jwk_from_pem_files(private_key_pem_file_name, [cert_pem_file_name])
    #signing_key['alg'] = encryption_key['alg']

    plaintext_decrypted = jose.jwe.decrypt(jwe_compact_token_reconstructed, signing_key).decode('utf-8')
    # let loads figure out if this is an encrypted JWS vCon or just a vCon
    current_state = self._state
    # Fool loads into thinking this is a raw vCon and its safe to load.  Save state incase we barf.
    self._state = VconStates.UNSIGNED
    try:
      self.loads(plaintext_decrypted)

    except Exception as e:
      # restore state
      self._state = current_state
      raise e


  @tag_meta
  def set_created_at(
    self,
    create_date: typing.Union[int, float, str, None]
    ) -> None:
    """
    Set the Vcon creation date.

    Parameters:  
    **create_date** (typing.Union[int, float, str, None]) - epoch time as int or float,
      date string as RFC3339 or RFC822 format.
      passing a value of None will use the current time.

    Returns: None
    """
    self._attempting_modify()

    if(create_date is None):
      create_date = time.time()

    self._vcon_dict[Vcon.CREATED_AT] = vcon.utils.cannonize_date(create_date)


  @tag_meta
  def set_subject(self, subject: str) -> None:
    """
    Set the subject parameter of the vCon.

    Parameters:  
      **subject** - String value to assign to the vCon subject parameter.

    Returns: None
    """

    self._attempting_modify()

    self._vcon_dict[Vcon.SUBJECT] = subject


  @tag_operation
  def jq(
    self,
    query: typing.Union[str, dict[str, str]]
    ) -> typing.Union[list[str], dict[str, any]]:
    """
    Perform jq syle queries on the Vcon JSON

    Parameters:  
    **query** (Union[str, dict[str, str]]) - query(s) to be performed on this Vcon
      **query** can be a single query string or a dict containing a names set where
      the values are query strings.

  Returns:  
    if query is a str, a list containing the query result is returned  
    if query is a dict, a dict with keys corresponding to the input query where
    the values are the query result.
    """
    if(self._state in [VconStates.UNVERIFIED, VconStates.DECRYPTED]):
      raise InvalidVconState("Vcon state: {} cannot read parameters".format(self._state))

    if(isinstance(query, str)):
      return(pyjq.all(query, self.dumpd()))

    else:
      results = {}
      vcon_dict = self.dumpd()
      for query_name, query_string in query.items():
        results[query_name] = pyjq.all(query_string, vcon_dict)[0]

      return(results)


  @tag_operation
  async def filter(self,
    filter_name: str,
    options: vcon.filter_plugins.FilterPluginOptions
    ) -> Vcon:
    """
    Run this Vcon through the named filter plugin.

    See vcon.filter_plugins.FilterPluginRegistry for the set of registered plugins.

    Parameters:  
      **filter_name** (str) - name of a registered FilterPlugin
      **options** - passed through to plugin.  The fields in options are documented by
        the specified plugin.

    Returns:  
      the filter modified Vcon
    """
    self._attempting_modify()

    plugin = vcon.filter_plugins.FilterPluginRegistry.get(filter_name, True)

    return(await plugin.filter(self, options))


  @tag_meta
  def set_uuid(self, domain_name: str, replace: bool= False) -> str:
    """
    Generate a UUID for this vCon and set the parameter

    Parameters:  
      **domain_name**: a DNS domain name string, should generally be a fully qualified host
          name.

    Returns:  
      UUID version 8 string
      (vCon uuid parameter is also set)

    """

    self._attempting_modify()

    if(self.uuid is not None and replace is False and len(self.uuid) > 0):
      raise AttributeError("uuid parameter already set")

    uuid = self.uuid8_domain_name(domain_name)

    self._vcon_dict[Vcon.UUID] = uuid

    return(uuid)

  @staticmethod
  def attribute_exists(name : str) -> bool:
    """
    Check if the given name is already used as a attribute or method on Vcon.

    Parameters:
      name (str) - name to check if it is used.

    Returns:
      True/False if name is used.
    """
    try:
       existing_attr = getattr(vcon.Vcon, name)
       #logger.warning("found Vcon attribute: {} {}".format(name, existing_attr))
       exists = existing_attr is not None

    except AttributeError as ex_err:
      if(str(ex_err).startswith("type object 'Vcon'")):
        exists = False
      else:
        # These are descriptors, which for some reason cannot
        # be got by getattr.
        logger.error(ex_err)
        exists = True

    if(not exists):
      # The only programatic way to do this is to instantiate a Vcon, but this seemed a bit
      # heavy.  So for now just testing a manually maintained list of attributes and  blacklisted
      # token names.
      instance_attributes = ['_jwe_dict', '_jws_dict', '_state', '_vcon_dict', 'vcon', "Vcon", "filter_plugins", "security", "utils", "cli"]
      if(name in instance_attributes):
        exists = True

    return(exists)

  @staticmethod
  def uuid8_domain_name(domain_name: str) -> str:
    """
    Generate a version 8 (custom) UUID using the upper 62 bits of the SHA-1 hash
    for the given DNS domain name string for custom_c and generating
    custom_a and custom_b the same way as unix_ts_ms and rand_a respectively
    for UUID version 7 (per IETF I-D draft-peabody-dispatch-new-uuid-format-04).

    Parameters:
      domain_name: a DNS domain name string, should generally be a fully qualified host
          name.

    Returns:
      UUID version 8 string
    """

    sha1_hasher = hashlib.sha1()
    sha1_hasher.update(bytes(domain_name, "utf-8"))
    dn_sha1 = sha1_hasher.digest()

    hash_upper_64 = dn_sha1[0:8]
    int64 = int.from_bytes(hash_upper_64, byteorder="big")

    uuid8_domain = Vcon.uuid8_time(int64)

    return(uuid8_domain)

  @staticmethod
  def uuid8_time(custom_c_62_bits: int) -> str:
    """
    Generate a version 8 (custom) UUID using the given custom_c and generating
    custom_a and custom_b the same way as unix_ts_ms and rand_a respectively
    for UUID version 7 (per IETF I-D draft-peabody-dispatch-new-uuid-format-04).

    Parameters:
      custom_c_62_bits: the 62 bit value as an integer to be used for custom_b
           portion of UUID version 8.

    Returns:
      UUID version 8 string
    """
    # This is partially from uuid6.uuid7 implementation:
    global _LAST_V8_TIMESTAMP

    nanoseconds = time.time_ns()
    if _LAST_V8_TIMESTAMP is not None and nanoseconds <= _LAST_V8_TIMESTAMP:
        nanoseconds = _LAST_V8_TIMESTAMP + 1
    _last_v7_timestamp = nanoseconds
    timestamp_ms, timestamp_ns = divmod(nanoseconds, 10**6)
    subsec = uuid6._subsec_encode(timestamp_ns)

    # This is not what is in the vCon I-D.  It says random bits
    # not bits from the time stamp.  May want to change this
    subsec_a = subsec >> 8
    uuid_int = (timestamp_ms & 0xFFFFFFFFFFFF) << 80
    uuid_int |= subsec_a << 64
    uuid_int |= custom_c_62_bits

    # We lie about the version and then correct it afterwards
    uuid_str = str(uuid6.UUID(int=uuid_int, version=7))
    assert(uuid_str[14] == '7')
    uuid_str =  uuid_str[:14] +'8' + uuid_str[15:]

    return(uuid_str)

  @staticmethod
  def migrate_0_0_1_vcon(old_vcon : dict) -> dict:
    """
    Migrate/translate an an older deprecated vCon to the current version.

    Parameters:
      old_vcon old format 0.0.1 vCon

    Returns:
      the modified old_vcon in the new format
    """

    # Fix dates in older dialogs
    for index, dialog in enumerate(old_vcon.get("dialog", [])):
      if("start" in dialog):
        dialog['start'] = vcon.utils.cannonize_date(dialog['start'])

      if("alg" in dialog):
        if( dialog['alg'] == "lm-ots"):
          dialog['alg'] = "LMOTS_SHA256_N32_W8"
        elif( dialog['alg'] in ["SHA-512", "LMOTS_SHA256_N32_W8"]):
          pass
        else:
          raise AttributeError("dialog[{}] alg: {} not supported.  Must be SHA-512 or LMOTS_SHA256_N32_W8".format(index, dialog['alg']))

    # Translate transcriptions to body for consistency with dialog and attachments
    for index, analysis in enumerate(old_vcon.get("analysis", [])):
      analysis_type = analysis.get('type', None)
      if(analysis_type is None):
        raise InvalidVconJson("analysis object: {} has no type field".format(index))

      if(analysis_type == "transcript"):
        # Clean up Vcons where vendor_schema was used instead of schema
        if("vendor_schema" in analysis):
          analysis['schema'] = analysis.pop('vendor_schema')

        # Clean up Vcons where vendor_product was used instead of product
        if("vendor_product" in analysis):
          analysis['product'] = analysis.pop('vendor_product')

        # Clean up Vcons where Whisper was set as vendor instead of product
        if(analysis.get("vendor", "").lower() == "whisper" and
           analysis.get("product", None) is None
          ):
            analysis['vendor'] = "openai"
            analysis['product'] = "whisper"

        if("transcript" in analysis):
          analysis['body'] = analysis.pop('transcript')

          if(isinstance(analysis['body'], dict)):
            analysis['encoding'] = "json"
          elif(isinstance(analysis['body'], str)):
            analysis['encoding'] = "none"

          else:
            raise Exception("body type: {} in analysis[{}] not recognized".format(type(analysis['body']), index))

    return(old_vcon)

