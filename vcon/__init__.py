# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
# Copyright (C) 2026 SIP Spectrum, Inc.  All rights reserved.
"""
Module for creating and modifying vCon conversation containers.
see https:/vcon.dev
"""
# need future to reference Vcon type in Vcon methods
from __future__ import annotations
import importlib
import pkgutil
import typing
import re
import sys
import os
import copy
import logging
import enum
import cbor2
import time
import hashlib
import inspect
import functools
import warnings
import datetime
import email
import pathlib
import jq
import jsonpath_rfc9535
import uuid6
import cryptography.x509
import jwcrypto.jwe
import jwcrypto.jwk
import jwcrypto.jws
import vcon.logging_utils
# TODO:  remove this and reference vcon.build_logger directly in vcon.* modules
build_logger = vcon.logging_utils.build_logger

# This must occur before importing any other vcon modules that setup logging
logger = build_logger(__name__)


import vcon.utils
import vcon.security
import vcon.filter_plugins
import vcon.accessors
import vcon.parameter_registry
import vcon.http_lb

__version__ = "0.6.14"

# seconds to wait to connect to and read from an x5u URL in Vcon.verify
X5U_FETCH_TIMEOUT = 10.0


try:
  import simplejson as json
  dumps_options = {"ignore_nan" : True}
  logger.info("using simplejson")
except Exception as import_error:
  import json
  dumps_options = {}
  logger.info("using json")


_LAST_V8_TIMESTAMP = None

# Register builtin filter_plugins
for finder, module_name, is_package in pkgutil.iter_modules(vcon.filter_plugins.__path__, vcon.filter_plugins.__name__ + "."):
  logger.info("plugin registration: {}".format(module_name))
  importlib.import_module(module_name)

# Register seperately installed addon filter_plugins
for finder, module_name, is_package in pkgutil.iter_modules(
    ["{}_addons".format(vcon.filter_plugins.__path__[0])],
    "{}_addons.".format(vcon.filter_plugins.__name__)
  ):
  logger.info("addon plugin registration: {}".format(module_name))
  importlib.import_module(module_name)

class ExperimentalWarning(Warning):
  """
  Warning for methods which modify or construct vCons with experimental or non-vCon standards
  complient forms or parameters.  Note: these may be depricated.
  """

class UnconvertedVconVersionWarning(Warning):
  """
  Warning for import of a vCon with a syntax version that is accepted,
  but for which no migration or conversion is implemented.
  """

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


def experimental(reason : str):
  """
  Decorator for marking and emmiting warnings on experimental or non-vCon standard following methods and classes.
  Note: these may be depricated.
  """

  def decorator(func):
    if inspect.isclass(func):
      msg = "Call to experimental class {{}} ({}).".format(reason)
    else:
      msg = "Call to experimental function {{}} ({}).".format(reason)

    @functools.wraps(func)
    def new_func(*args, **kwargs):
      warnings.simplefilter('always', ExperimentalWarning)
      warnings.warn(
        msg.format(func.__name__),
        category = ExperimentalWarning,
        stacklevel=2)
      warnings.simplefilter('default', ExperimentalWarning)
      logger.warning(msg.format(func.__name__))
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

def tag_session(func):
  """ decorator to tag with session category """
  func._tag = "session"
  return(func)

def tag_event(func):
  """ decorator to tag with event category """
  func._tag = "event"
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


def tag_vcon_references(func):
  """ decorator to tag with vCon references category """
  func._tag = "vcon_references"
  return(func)


# Note: __iadd__ and __imul__ are deliberately excluded.  VconAttribute.__set__
# raises, so an in place operator can never complete, and including them would
# leave the mutation applied to the vCon before the assignment raises.
_LIST_MUTATOR_NAMES = (
  "append",
  "extend",
  "insert",
  "remove",
  "pop",
  "clear",
  "sort",
  "reverse",
  "__setitem__",
  "__delitem__"
  )


def _make_write_back_method(base_type, method_name):
  """ build a mutator which writes a plain container back into the vCon dict """
  def write_back_method(self, *args, **kwargs):
    result = getattr(base_type, method_name)(self, *args, **kwargs)
    self._vcon_dict[self._key] = base_type(self)
    return(result)

  write_back_method.__name__ = method_name
  return(write_back_method)


def _make_write_back_type(type_name, base_type, mutator_names):
  """
  Build a container type which adds itself to the vCon dict when it is
  first modified.  This allows an attribute to return an empty container
  without adding an empty container to the vCon.
  """
  def write_back_init(self, vcon_dict, key, initial = ()):
    base_type.__init__(self, initial)
    self._vcon_dict = vcon_dict
    self._key = key

  namespace = {"__init__": write_back_init}
  for mutator_name in mutator_names:
    namespace[mutator_name] = _make_write_back_method(base_type, mutator_name)

  return(type(type_name, (base_type,), namespace))


_WriteBackList = _make_write_back_type("_WriteBackList", list, _LIST_MUTATOR_NAMES)


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


class VconUuid(VconAttribute):
  """ descriptor for UUID attribute in vcon """
  def __init__(self, doc : typing.Union[str, None] = None):
    super().__init__(doc = doc)
    self._type_name = "UUID"


  def __get__(self, instance_object, class_type = None):

    # UNSIGNED, SIGNED or VERIFIED
    if(instance_object._state in [VconStates.UNSIGNED, VconStates.SIGNED, VconStates.VERIFIED]):
      return(Vcon.get_dict_uuid(instance_object._vcon_dict))

    # DECRIPTED or UNVERIFIED
    if(instance_object._state in [VconStates.UNVERIFIED, VconStates.DECRYPTED]):
      return(Vcon.get_dict_uuid(instance_object._jws_dict))

    # ENCRYPTED
    if(instance_object._state in [VconStates.ENCRYPTED]):
      return(Vcon.get_dict_uuid(instance_object._jwe_dict))

    raise Exception("Unexpected state: {}".format(instance_object._state ))


class VconDict(VconAttribute):
  """ descriptor for Lists of dicts in vcon """

  def __init__(self, doc : typing.Union[str, None] = None):
    super().__init__(doc = doc)
    self._type_name = "Dict"

class VconDeprecatedDict(VconDict):
  """ descriptor for a deprecated Dict attribute, which names its replacement """

  def __init__(self, replacement : str, doc : typing.Union[str, None] = None):
    super().__init__(doc = doc)
    self._replacement = replacement

  def __get__(self, instance_object, class_type = None):
    if(instance_object is None):
      return(self)

    warnings.simplefilter('always', DeprecationWarning)
    warnings.warn(
      "the {} attribute is deprecated, use {}".format(self.name, self._replacement),
      category = DeprecationWarning,
      stacklevel = 2)
    warnings.simplefilter('default', DeprecationWarning)
    return(super().__get__(instance_object, class_type))


class VconDictList(VconAttribute):
  """ descriptor for Lists of dicts in vcon """

  def __init__(self, doc : typing.Union[str, None] = None):
    super().__init__(doc = doc)
    self._type_name = "DictList"

  def __get__(self, instance_object, class_type = None):
    got_value = super().__get__(instance_object, class_type)

    # Always return a list to avoid having to test for null and empty
    if(got_value is None):
      got_value = []
      instance_object._vcon_dict[self.name] = got_value

    return(got_value)


class VconLazyDictList(VconAttribute):
  """
  descriptor for Lists of dicts in vcon which are only added to the vCon
  when they are first modified
  """

  def __init__(self, doc : typing.Union[str, None] = None):
    super().__init__(doc = doc)
    self._type_name = "DictList"

  def __get__(self, instance_object, class_type = None):
    got_value = super().__get__(instance_object, class_type)

    # Always return a list to avoid having to test for null and empty.
    # The returned list adds itself to the vCon only if it is modified.
    if(got_value is None):
      got_value = _WriteBackList(instance_object._vcon_dict, self.name)

    return(got_value)


class VconStringList(VconAttribute):
  """ descriptor for Lists of strings in vcon """

  def __init__(self, doc : typing.Union[str, None] = None):
    super().__init__(doc = doc)
    self._type_name = "StringList"

  def __get__(self, instance_object, class_type = None):
    got_value = super().__get__(instance_object, class_type)

    # Always return a list to avoid having to test for null and empty.
    # The returned list adds itself to the vCon only if it is modified.
    if(got_value is None):
      got_value = _WriteBackList(instance_object._vcon_dict, self.name)

    return(got_value)


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

  # Some commonly used media types for convenience
  MEDIATYPE_TEXT_PLAIN = "text/plain"
  MEDIATYPE_JSON = "application/json"
  MEDIATYPE_VCON = "application/vcon"
  MEDIATYPE_VCON_JSON = "application/vcon+json"
  MEDIATYPE_IMAGE_PNG = "image/png"
  MEDIATYPE_AUDIO_WAV = "audio/x-wav"
  MEDIATYPE_AUDIO_MP3 = "audio/x-mp3"
  MEDIATYPE_AUDIO_MP4 = "audio/x-mp4"
  MEDIATYPE_VIDEO_MP4 = "video/x-mp4"
  MEDIATYPE_AUDIO_OGG = "audio/ogg"
  MEDIATYPE_AUDIO_FLAC = "audio/flac"
  MEDIATYPE_VIDEO_OGG = "video/ogg"
  MEDIATYPE_MULTIPART = "multipart/mixed"

  FILE_EXTENSIONS = {
    ".txt": MEDIATYPE_TEXT_PLAIN,
    ".text": MEDIATYPE_TEXT_PLAIN,
    ".png": MEDIATYPE_IMAGE_PNG,
    ".wav": MEDIATYPE_AUDIO_WAV,
    ".mp3": MEDIATYPE_AUDIO_MP3,
    ".m4a": MEDIATYPE_AUDIO_MP4,
    ".ogg": MEDIATYPE_AUDIO_OGG,
    ".flac": MEDIATYPE_AUDIO_FLAC,
    ".mp4": MEDIATYPE_VIDEO_MP4,
    ".ogv": MEDIATYPE_VIDEO_OGG
  }

  MEDIATYPE_EXTENSIONS = {
    MEDIATYPE_TEXT_PLAIN: ".txt",
    MEDIATYPE_IMAGE_PNG: ".png",
    MEDIATYPE_AUDIO_WAV: ".wav",
    MEDIATYPE_AUDIO_MP3: ".mp3",
    MEDIATYPE_AUDIO_MP4: ".m4a",
    MEDIATYPE_AUDIO_OGG: ".ogg",
    MEDIATYPE_AUDIO_FLAC: ".flac",
    MEDIATYPE_VIDEO_MP4: ".mp4",
    MEDIATYPE_VIDEO_OGG: ".ogv",
    # Common IANA spellings of the above.  Recognized for lookup only;
    # get_media_type returns the vCon spec media types.
    "audio/wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a"
  }

  CURRENT_VCON_VERSION = "0.5.0"
  # vCon syntax versions accepted on import for which a migration to the
  # current syntax is implemented.
  MIGRATABLE_VCON_VERSIONS = ["0.0.1", "0.0.2"]
  # vCon syntax versions accepted on import as is.  No migration is
  # performed and the vcon parameter is left unmodified.
  UNCONVERTED_VCON_VERSIONS = ["0.3.0", "0.4.0"]

  # Dict keys
  VCON_VERSION = "vcon"
  EXTENSIONS = "extensions"
  CRITICAL = "critical"
  UUID = "uuid"
  SUBJECT = "subject"
  REDACTED_FROM = "redacted_from"
  AMENDED_FROM = "amended_from"
  # vCon 0.4.0 names of redacted_from and amended_from
  REDACTED = "redacted"
  AMENDED = "amended"
  GROUP = "group"
  PARTIES = "parties"
  DIALOG = "dialog"
  ANALYSIS = "analysis"
  ATTACHMENTS = "attachments"
  SESSIONS = "sessions"
  EVENTS = "events"
  REDACTED_STRINGS = "redacted_strings"
  # A Redacted_string marker is the prefix, the ref and the suffix, e.g. __REDACTED_REF_1__.
  # The non-digit suffix ends the number.
  REDACTED_REF_PREFIX = "__REDACTED_REF_"
  REDACTED_REF_SUFFIX = "__"
  CREATED_AT = "created_at"

  # Session_Reference Object type tokens defined by the core vCon schema
  SESSION_REFERENCE_TYPES = ["child", "peer", "precursor", "breakout"]

  # disposition values of an incomplete Dialog Object defined by the core vCon schema
  DIALOG_DISPOSITIONS = ["no-answer", "congestion", "failed", "busy", "hung-up", "voicemail-no-message"]

  # Event Object type tokens defined by the core vCon schema
  EVENT_PARTY_TYPES = ["join", "drop", "hold", "unhold", "mute", "unmute"]
  EVENT_KEY_TYPES = ["keydown", "keyup"]
  EVENT_TRANSFER_TYPES = ["consultation-start", "blind-transfer", "consultative-transfer", "transfer-abandoned"]

  EVENT_CHANNEL_CONTRIBUTORS_TYPE = "channel-contributors"
  EVENT_CORE_TYPES = EVENT_PARTY_TYPES + EVENT_KEY_TYPES + EVENT_TRANSFER_TYPES + [EVENT_CHANNEL_CONTRIBUTORS_TYPE]

  PARAMETER_CORE = vcon.parameter_registry.PARAMETER_CORE

  PARTIES_OBJECT_STRING_PARAMETERS = vcon.parameter_registry.get_object_parameter_names("Party")

  vcon = VconString(doc = "vCon version string attribute")

  extensions = VconStringList(doc = "List of names of the vCon extensions used by this vCon")

  critical = VconStringList(doc = "List of names of the vCon extensions which a consumer must support to process this vCon")

  uuid = VconUuid(doc = "vCon UUID string attribute")
  created_at = VconString(doc = "vCon creation date string attribute")
  subject = VconString(doc = "vCon subject string attribute")

  redacted_from = VconDict(doc = "Redacted_from Object Dict referencing the less redacted version of this vCon")
  amended_from = VconDict(doc = "Amended_from Object Dict referencing the prior version of this vCon, to which this vCon adds data")

  redacted = VconDeprecatedDict("redacted_from",
    doc = "deprecated vCon 0.4.0 redacted Dict of a loaded vCon, use redacted_from")
  amended = VconDeprecatedDict("amended_from",
    doc = "deprecated vCon 0.4.0 amended Dict of a loaded vCon, use amended_from")

  group = VconDictList(doc = "List of Dicts referencing or including other vCons to be aggregated by this vCon")
  parties = VconDictList(doc = "List of Dicts, one for each party to this conversation")
  dialog = VconDictList(doc = "List of Dicts referencing or including the capture of text," +
    " audio or video (original form of communication) segments for this conversation")
  analysis = VconDictList(doc = "List of Dicts referencing or includeing analysis data for this conversation")
  attachments = VconDictList(doc = "List of Dicts referencing or including ancillary documents to this conversation")
  sessions = VconLazyDictList(doc = "List of Session Object Dicts, one for each session or sub-conversation" +
    " of this conversation.  A Session Object references its Dialog Objects by index")
  redacted_strings = VconLazyDictList(doc = "List of Redacted_string Object Dicts, one for each"
    " redacted string, referenced from the redacted text by its marker")
  events = VconLazyDictList(doc = "List of Event Object Dicts, for the events which occurred in this conversation." +
    "  An Event Object references the Session Objects in which it occurred by index")

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
    # Label vCons created by this package with the syntax version.
    # Loaded vCons keep the vcon parameter, if any, which they were loaded with.
    self._vcon_dict[Vcon.VCON_VERSION] = Vcon.CURRENT_VCON_VERSION
    self._vcon_dict[Vcon.PARTIES] = []
    self._vcon_dict[Vcon.DIALOG] = []
    self._vcon_dict[Vcon.ANALYSIS] = []
    self._vcon_dict[Vcon.ATTACHMENTS] = []
    self._vcon_dict[Vcon.CREATED_AT] = vcon.utils.cannonize_date(datetime.datetime.utcnow())


  # TODO: use mediatypes package instead
  @staticmethod
  def get_media_type(file_name):
    """ derive mediatype from file extension """
    path = pathlib.PurePath(file_name)
    extension = path.suffix.lower()

    #print("extension: {}".format(extension), file=sys.stderr)

    if(extension in vcon.Vcon.FILE_EXTENSIONS):
      mediatype = vcon.Vcon.FILE_EXTENSIONS[extension]
  
    # TODO: add: aac
    else:
      raise Exception("Media type not defined for extension: {}".format(extension))
  
    return(mediatype)


  # TODO: use mediatypes package instead
  @staticmethod
  def get_media_extension(media_type):
    """ get file extension for mediatype """
    if(media_type in vcon.Vcon.MEDIATYPE_EXTENSIONS):
      extension = vcon.Vcon.MEDIATYPE_EXTENSIONS[media_type]

    else:
      raise Exception("extension not defined for media type: {}".format(media_type))
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


  def __add_new_dialog(self, index : int) -> int:
    """
    check if a new dialog needs to be added to the list

    Parameters:
    index (int): -1 indicates adding a new dialog, positive numbers
          throw AttributeError if the dialog with that index does not already exist

    Returns:
      dialog index in the list
    """
    self._attempting_modify()

    dialog = index
    if(dialog == -1):
      self._vcon_dict[Vcon.DIALOG].append({})
      dialog = len(self._vcon_dict[Vcon.DIALOG]) - 1

    else:
      if(not len(self._vcon_dict[Vcon.DIALOG]) > index):
        raise AttributeError(
          "index: {} > then dialog List length: {}.  Use index of -1 to add one to the end.".format(
          index, len(self._vcon_dict[Vcon.DIALOG])))

    return(dialog)


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
                  Unregistered parameter names are allowed and log a warning.
      **parameter_value** (String) - new value to set for the named parameter  
      **party_index** (int) - index of party to set tel url on
                  (-1 indicates a new party should be added)  

    Returns:  
    int: if success, positive int index of party in list
    """

    self._attempting_modify()

    self.add_parameter_extension("Party", parameter_name)

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
                  Unregistered parameter names are allowed and log a warning.

    Returns:  
    int: if success, positive int index of party in list
    """
    self._attempting_modify()
    for key in party_dict.keys():
      self.add_parameter_extension("Party", key)

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


  def _check_object_index(self, array_name : str, index : int) -> None:
    """
    Raise AttributeError if the Object at the given index of the named
    Object array does not exist.
    """
    array_length = len(self._vcon_dict.get(array_name, None) or [])
    if(not isinstance(index, int) or
      isinstance(index, bool) or
      index < 0 or
      index >= array_length
      ):
      raise AttributeError(
        "{} index: {} does not exist.  The vCon {} array has {} Object(s).".format(
        array_name, index, array_name, array_length))


  @tag_session
  def add_session(
    self,
    dialog : typing.Union[typing.List[int], None] = None,
    parties : typing.Union[typing.List[int], None] = None,
    start : typing.Union[str, int, float, datetime.datetime, None] = None,
    duration : typing.Union[int, float, None] = None,
    originator : typing.Union[int, None] = None,
    session_id : typing.Union[typing.Dict[str, str], None] = None,
    sessions : typing.Union[typing.List[typing.Dict[str, typing.Any]], None] = None
    ) -> int:
    """
    Add a new Session Object to the vCon sessions Object array.

    This is the only method which creates a Session Object.  Methods which
    implicitly create a Session Object (e.g. the add_dialog_* methods) call
    this method.  The given parameters are stored as given.  Parameters which
    are None are omitted from the Session Object.  Nothing is derived from the
    referenced Dialog Objects.  Use **add_dialog_to_session** to add references
    to Dialog Objects and derive the Session Object parties, start and duration
    from the referenced Dialog Objects.

    Parameters:  
      **dialog** (List[int]) - indices of the Dialog Objects which this session references  
      **parties** (List[int]) - indices of the parties which are the receivers of the
               dialog in this session.  The first party is the implied originator.  
      **start** (str, int, float, datetime.datetime) - Date, time of the start of the session.
               String containing RFC 2822 or RFC3339 date time stamp or int/float
               containing epoch time (since 1970) in seconds.  
      **duration** (int or float) - duration of the session in seconds  
      **originator** (int) - index of the party which originated the session.  Only
               needed if the first party in parties is not the originator.  
      **session_id** (Dict[str, str]) - SessionId Object for the session  
      **sessions** (List[Dict]) - Session_Reference Objects, each of which references another
               Session Object and gives its relationship to this one.  See **add_session_reference**.

    Returns:  
      Index of the new Session Object in the sessions Object array.
    """
    self._attempting_modify()

    for dialog_index in (dialog or []):
      self._check_object_index(Vcon.DIALOG, dialog_index)
    for party_index in (parties or []):
      self._check_object_index(Vcon.PARTIES, party_index)
    if(originator is not None):
      self._check_object_index(Vcon.PARTIES, originator)

    new_session: typing.Dict[str, typing.Any] = {}
    if(start is not None):
      new_session["start"] = vcon.utils.cannonize_date(start)
    if(duration is not None):
      new_session["duration"] = duration
    if(parties is not None):
      new_session["parties"] = list(parties)
    if(originator is not None):
      new_session["originator"] = originator
    if(session_id is not None):
      new_session["session_id"] = session_id
    if(sessions is not None):
      new_session["sessions"] = list(sessions)
    if(dialog is not None):
      new_session["dialog"] = list(dialog)

    if(self._vcon_dict.get(Vcon.SESSIONS, None) is None):
      self._vcon_dict[Vcon.SESSIONS] = []

    self._vcon_dict[Vcon.SESSIONS].append(new_session)

    return(len(self._vcon_dict[Vcon.SESSIONS]) - 1)


  @tag_session
  def add_dialog_to_session(
    self,
    session_index : int,
    dialog_index : int,
    receivers : typing.Union[typing.List[int], None] = None,
    extend_time : bool = True
    ) -> None:
    """
    Add a reference to the Dialog Object to the Session Object dialog parameter
    and add references to the receivers of the dialog to the Session Object
    parties parameter.  The Session Object references the Dialog Object by its
    index in the dialog Object array.  It does not contain the Dialog Object.

    Parameters:  
      **session_index** (int) - index of the Session Object which is to reference the Dialog Object  
      **dialog_index** (int) - index of the Dialog Object to be referenced by the session.  The
               reference is not added again if the session already references the Dialog Object.  
      **receivers** (List[int]) - indices of the parties which are receivers of the dialog.
               The indices are added to the Session Object parties in order, if not already present.
               If None, the parties of the Dialog Object are used, which is correct for
               a normal call recording.  
      **extend_time** (bool) - if True, the Session Object start is set or moved earlier and
               the Session Object duration is set or made longer as needed to span the
               referenced Dialog Object start and duration.  The session start is never moved later and
               the session duration is never made shorter.  If False, the Session Object
               start and duration are not changed.  A session may be shorter than the
               dialog which it references.  In that case, set extend_time to False and
               set the session start and duration with **set_session_parameter**.

    Returns: none
    """
    self._attempting_modify()
    self._check_object_index(Vcon.SESSIONS, session_index)
    self._check_object_index(Vcon.DIALOG, dialog_index)

    session = self._vcon_dict[Vcon.SESSIONS][session_index]
    dialog = self._vcon_dict[Vcon.DIALOG][dialog_index]

    # Parties may be added after the dialog which references them.  So only
    # explicitly given receivers are checked.  Receivers taken from the
    # Dialog Object parties are used as is.
    if(receivers is None):
      receivers = vcon.utils.flatten_party_indices(dialog.get("parties", None))
    else:
      for party_index in receivers:
        self._check_object_index(Vcon.PARTIES, party_index)

    session_dialog = session.get("dialog", None)
    if(session_dialog is None):
      session_dialog = []
      session["dialog"] = session_dialog
    if(dialog_index not in session_dialog):
      session_dialog.append(dialog_index)

    if(len(receivers) > 0):
      session_parties = session.get("parties", None)
      if(session_parties is None):
        session_parties = []
        session["parties"] = session_parties
      for party_index in receivers:
        if(party_index not in session_parties):
          session_parties.append(party_index)

    if(extend_time):
      Vcon._extend_session_time(session, dialog)

    Vcon._order_session_parameters(session)


  @staticmethod
  def _order_session_parameters(session : typing.Dict[str, typing.Any]) -> None:
    """
    Order the core parameters of the Session Object as they are defined in
    the vCon core schema, followed by any other parameters, for readability.
    """
    core_names = vcon.parameter_registry.get_object_parameter_names("Session")
    ordered_names = [name for name in core_names if name in session]
    ordered_names += [name for name in session if name not in core_names]
    for name in ordered_names:
      session[name] = session.pop(name)


  @staticmethod
  def _extend_session_time(
    session : typing.Dict[str, typing.Any],
    dialog : typing.Dict[str, typing.Any]
    ) -> None:
    """
    Set or widen the start and duration of the given Session Object to
    include the start and duration of the given Dialog Object.
    """
    dialog_start_string = dialog.get("start", None)
    if(dialog_start_string is None):
      return

    dialog_start = vcon.utils.date_to_datetime(dialog_start_string)
    dialog_duration = dialog.get("duration", None)
    dialog_end = dialog_start
    if(dialog_duration is not None):
      dialog_end = dialog_start + datetime.timedelta(seconds = dialog_duration)

    session_start_string = session.get("start", None)
    if(session_start_string is None):
      session["start"] = vcon.utils.cannonize_date(dialog_start_string)
      if(dialog_duration is not None and session.get("duration", None) is None):
        session["duration"] = dialog_duration
      return

    session_start = vcon.utils.date_to_datetime(session_start_string)
    session_duration = session.get("duration", None)

    new_start = session_start
    if(dialog_start < session_start):
      new_start = dialog_start
      session["start"] = vcon.utils.cannonize_date(dialog_start_string)

    # With no session duration, the end of the session is not known
    if(session_duration is None):
      return

    session_end = session_start + datetime.timedelta(seconds = session_duration)
    new_end = max(session_end, dialog_end)
    if(new_start != session_start or new_end != session_end):
      new_duration = (new_end - new_start).total_seconds()
      if(float(new_duration).is_integer()):
        new_duration = int(new_duration)
      session["duration"] = new_duration


  @tag_session
  def set_session_parameter(
    self,
    parameter_name : str,
    parameter_value : typing.Any,
    session_index : int
    ) -> int:
    """
    Set the named parameter for the given Session Object.

    Unlike **set_dialog_parameter**, this does not create a new Object.
    Use **add_session** to create a Session Object.  Parameters which
    reference other Objects (e.g. dialog, parties, sessions) take indices.

    Parameters:  
      **parameter_name** (String) - name of the Session Object parameter to be set.  
      **parameter_value** (Any) - new value to set for the named parameter  
      **session_index** (int) - index of the Session Object on which to set the parameter

    Returns:  
      index of the Session Object
    """
    self._attempting_modify()
    self._check_object_index(Vcon.SESSIONS, session_index)
    self.add_parameter_extension("Session", parameter_name)

    self._vcon_dict[Vcon.SESSIONS][session_index][parameter_name] = parameter_value

    return(session_index)


  @tag_session
  def add_session_reference(
    self,
    session_index : int,
    referenced_session : int,
    ref_type : str,
    description : typing.Union[str, None] = None
    ) -> None:
    """
    Add a Session_Reference Object to the sessions parameter of the given
    Session Object.  The Session_Reference Object references another Session
    Object by its index in the sessions Object array and gives the type of
    its relationship to the given Session Object.  It does not contain the
    referenced Session Object.

    Parameters:  
      **session_index** (int) - index of the Session Object to which the Session_Reference Object is added  
      **referenced_session** (int) - index of the Session Object which is referenced  
      **ref_type** (str) - type of relationship to the referenced session.  One of:
               "child", "peer", "precursor", "breakout" or a type defined in a vCon extension.
               A warning is logged if the type is not one of the above and this vCon
               does not list any extensions.  
      **description** (str) - free form text description of the relationship (optional)

    Returns: none
    """
    self._attempting_modify()
    self._check_object_index(Vcon.SESSIONS, session_index)
    self._check_object_index(Vcon.SESSIONS, referenced_session)

    if(ref_type not in Vcon.SESSION_REFERENCE_TYPES and
      len(self._vcon_dict.get(Vcon.EXTENSIONS, None) or []) == 0
      ):
      logger.warning(
        "Session_Reference type: \"%s\" is not a core type and the vCon lists no extensions",
        ref_type)

    reference: typing.Dict[str, typing.Any] = {}
    reference["session"] = referenced_session
    reference["type"] = ref_type
    if(description is not None):
      reference["description"] = description

    session = self._vcon_dict[Vcon.SESSIONS][session_index]
    if(session.get("sessions", None) is None):
      session["sessions"] = []
    session["sessions"].append(reference)


  @tag_session
  def find_sessions_for_dialog(self, dialog_index : int) -> typing.List[int]:
    """
    Find the Session Objects which reference the given Dialog Object.

    Parameters:  
      **dialog_index** (int) - index of the Dialog Object

    Returns:  
      list of the indices of the Session Objects whose dialog parameter contains dialog_index
    """
    found: typing.List[int] = []
    for session_index, session in enumerate(self._vcon_dict.get(Vcon.SESSIONS, None) or []):
      if(dialog_index in (session.get("dialog", None) or [])):
        found.append(session_index)

    return(found)


  @tag_event
  def add_join_event(
    self,
    time : typing.Union[str, int, float, datetime.datetime],
    sessions : typing.Union[int, typing.List[int]],
    party : int
    ) -> int:
    """
    Add a "join" type Event Object: the party joins the session.

    Parameters:
      **time** (str, int, float, datetime.datetime) - Date, time at which the event occurred.
               String containing RFC 2822 or RFC3339 date time stamp or int/float
               containing epoch time (since 1970) in seconds.
      **sessions** (int, List[int]) - index or indices of the Session Objects in which the event
               occurred.  It is stored in the form given.
      **party** (int) - index of the party

    Returns:
      Index of the new Event Object in the events Object array.
    """
    return(self._add_core_event("join", time, sessions = sessions, party = party))


  @tag_event
  def add_drop_event(
    self,
    time : typing.Union[str, int, float, datetime.datetime],
    sessions : typing.Union[int, typing.List[int]],
    party : int
    ) -> int:
    """
    Add a "drop" type Event Object: the party drops out of the session.

    Parameters:
      **time** (str, int, float, datetime.datetime) - Date, time at which the event occurred.
               String containing RFC 2822 or RFC3339 date time stamp or int/float
               containing epoch time (since 1970) in seconds.
      **sessions** (int, List[int]) - index or indices of the Session Objects in which the event
               occurred.  It is stored in the form given.
      **party** (int) - index of the party

    Returns:
      Index of the new Event Object in the events Object array.
    """
    return(self._add_core_event("drop", time, sessions = sessions, party = party))


  @tag_event
  def add_hold_event(
    self,
    time : typing.Union[str, int, float, datetime.datetime],
    sessions : typing.Union[int, typing.List[int]],
    party : int
    ) -> int:
    """
    Add a "hold" type Event Object: the party is put on hold.

    Parameters:
      **time** (str, int, float, datetime.datetime) - Date, time at which the event occurred.
               String containing RFC 2822 or RFC3339 date time stamp or int/float
               containing epoch time (since 1970) in seconds.
      **sessions** (int, List[int]) - index or indices of the Session Objects in which the event
               occurred.  It is stored in the form given.
      **party** (int) - index of the party

    Returns:
      Index of the new Event Object in the events Object array.
    """
    return(self._add_core_event("hold", time, sessions = sessions, party = party))


  @tag_event
  def add_unhold_event(
    self,
    time : typing.Union[str, int, float, datetime.datetime],
    sessions : typing.Union[int, typing.List[int]],
    party : int
    ) -> int:
    """
    Add a "unhold" type Event Object: the party is taken off hold.

    Parameters:
      **time** (str, int, float, datetime.datetime) - Date, time at which the event occurred.
               String containing RFC 2822 or RFC3339 date time stamp or int/float
               containing epoch time (since 1970) in seconds.
      **sessions** (int, List[int]) - index or indices of the Session Objects in which the event
               occurred.  It is stored in the form given.
      **party** (int) - index of the party

    Returns:
      Index of the new Event Object in the events Object array.
    """
    return(self._add_core_event("unhold", time, sessions = sessions, party = party))


  @tag_event
  def add_mute_event(
    self,
    time : typing.Union[str, int, float, datetime.datetime],
    sessions : typing.Union[int, typing.List[int]],
    party : int
    ) -> int:
    """
    Add a "mute" type Event Object: the party is muted.

    Parameters:
      **time** (str, int, float, datetime.datetime) - Date, time at which the event occurred.
               String containing RFC 2822 or RFC3339 date time stamp or int/float
               containing epoch time (since 1970) in seconds.
      **sessions** (int, List[int]) - index or indices of the Session Objects in which the event
               occurred.  It is stored in the form given.
      **party** (int) - index of the party

    Returns:
      Index of the new Event Object in the events Object array.
    """
    return(self._add_core_event("mute", time, sessions = sessions, party = party))


  @tag_event
  def add_unmute_event(
    self,
    time : typing.Union[str, int, float, datetime.datetime],
    sessions : typing.Union[int, typing.List[int]],
    party : int
    ) -> int:
    """
    Add a "unmute" type Event Object: the party is taken off mute.

    Parameters:
      **time** (str, int, float, datetime.datetime) - Date, time at which the event occurred.
               String containing RFC 2822 or RFC3339 date time stamp or int/float
               containing epoch time (since 1970) in seconds.
      **sessions** (int, List[int]) - index or indices of the Session Objects in which the event
               occurred.  It is stored in the form given.
      **party** (int) - index of the party

    Returns:
      Index of the new Event Object in the events Object array.
    """
    return(self._add_core_event("unmute", time, sessions = sessions, party = party))


  @tag_event
  def add_keydown_event(
    self,
    time : typing.Union[str, int, float, datetime.datetime],
    sessions : typing.Union[int, typing.List[int]],
    party : int,
    button : str
    ) -> int:
    """
    Add a "keydown" type Event Object: a DTMF or application key or button was pressed.

    Parameters:
      **time** (str, int, float, datetime.datetime) - Date, time at which the event occurred.
               String containing RFC 2822 or RFC3339 date time stamp or int/float
               containing epoch time (since 1970) in seconds.
      **sessions** (int, List[int]) - index or indices of the Session Objects in which the event
               occurred.  It is stored in the form given.
      **party** (int) - index of the party which pressed or released the key or button
      **button** (str) - the key or button label character or string

    Returns:
      Index of the new Event Object in the events Object array.
    """
    return(self._add_core_event("keydown", time, sessions = sessions, party = party, button = button))


  @tag_event
  def add_keyup_event(
    self,
    time : typing.Union[str, int, float, datetime.datetime],
    sessions : typing.Union[int, typing.List[int]],
    party : int,
    button : str
    ) -> int:
    """
    Add a "keyup" type Event Object: a DTMF or application key or button was released.

    Parameters:
      **time** (str, int, float, datetime.datetime) - Date, time at which the event occurred.
               String containing RFC 2822 or RFC3339 date time stamp or int/float
               containing epoch time (since 1970) in seconds.
      **sessions** (int, List[int]) - index or indices of the Session Objects in which the event
               occurred.  It is stored in the form given.
      **party** (int) - index of the party which pressed or released the key or button
      **button** (str) - the key or button label character or string

    Returns:
      Index of the new Event Object in the events Object array.
    """
    return(self._add_core_event("keyup", time, sessions = sessions, party = party, button = button))


  @tag_event
  def add_consultation_start_event(
    self,
    time : typing.Union[str, int, float, datetime.datetime],
    sessions : int,
    transferor : int,
    transferee : int,
    transfer_target : int,
    consultation : int
    ) -> int:
    """
    Add a "consultation-start" type Event Object: the Transferor starts a
    consultative call with the Transfer Target.

    Parameters:
      **time** (str, int, float, datetime.datetime) - Date, time at which the event occurred.
               String containing RFC 2822 or RFC3339 date time stamp or int/float
               containing epoch time (since 1970) in seconds.
      **sessions** (int) - index of the Session Object for the original call between the
               Transferee and the Transferor
      **transferor** (int) - index of the Transferor party, written as the party parameter
      **transferee** (int) - index of the Transferee party
      **transfer_target** (int) - index of the Transfer Target party
      **consultation** (int) - index of the Session Object for the consultative call

    Returns:
      Index of the new Event Object in the events Object array.
    """
    return(self._add_core_event("consultation-start", time, sessions = sessions, party = transferor,
      transferee = transferee, transfer_target = transfer_target, consultation = consultation))


  @tag_event
  def add_blind_transfer_event(
    self,
    time : typing.Union[str, int, float, datetime.datetime],
    sessions : int,
    transferor : int,
    transferee : int,
    transfer_target : int,
    target_session : int
    ) -> int:
    """
    Add a "blind-transfer" type Event Object: the Transferor transfers the
    Transferee to the Transfer Target without a consultative call.

    Parameters:
      **time** (str, int, float, datetime.datetime) - Date, time at which the event occurred.
               String containing RFC 2822 or RFC3339 date time stamp or int/float
               containing epoch time (since 1970) in seconds.
      **sessions** (int) - index of the Session Object for the original call between the
               Transferee and the Transferor
      **transferor** (int) - index of the Transferor party, written as the party parameter
      **transferee** (int) - index of the Transferee party
      **transfer_target** (int) - index of the Transfer Target party
      **target_session** (int) - index of the Session Object for the target call

    Returns:
      Index of the new Event Object in the events Object array.
    """
    return(self._add_core_event("blind-transfer", time, sessions = sessions, party = transferor,
      transferee = transferee, transfer_target = transfer_target, target_session = target_session))


  @tag_event
  def add_consultative_transfer_event(
    self,
    time : typing.Union[str, int, float, datetime.datetime],
    sessions : int,
    transferor : int,
    transferee : int,
    transfer_target : int,
    consultation : int,
    target_session : int
    ) -> int:
    """
    Add a "consultative-transfer" type Event Object: the Transferor transfers
    the Transferee to the Transfer Target following a consultative call.

    Parameters:
      **time** (str, int, float, datetime.datetime) - Date, time at which the event occurred.
               String containing RFC 2822 or RFC3339 date time stamp or int/float
               containing epoch time (since 1970) in seconds.
      **sessions** (int) - index of the Session Object for the original call between the
               Transferee and the Transferor
      **transferor** (int) - index of the Transferor party, written as the party parameter
      **transferee** (int) - index of the Transferee party
      **transfer_target** (int) - index of the Transfer Target party
      **consultation** (int) - index of the Session Object for the consultative call
      **target_session** (int) - index of the Session Object for the target call

    Returns:
      Index of the new Event Object in the events Object array.
    """
    return(self._add_core_event("consultative-transfer", time, sessions = sessions, party = transferor,
      transferee = transferee, transfer_target = transfer_target, consultation = consultation,
      target_session = target_session))


  @tag_event
  def add_transfer_abandoned_event(
    self,
    time : typing.Union[str, int, float, datetime.datetime],
    sessions : int,
    transferor : int,
    transferee : int,
    transfer_target : typing.Union[int, None] = None,
    consultation : typing.Union[int, None] = None
    ) -> int:
    """
    Add a "transfer-abandoned" type Event Object: the Transferor abandons an
    attempt to transfer the Transferee without completing the transfer.

    Parameters:
      **time** (str, int, float, datetime.datetime) - Date, time at which the event occurred.
               String containing RFC 2822 or RFC3339 date time stamp or int/float
               containing epoch time (since 1970) in seconds.
      **sessions** (int) - index of the Session Object for the original call between the
               Transferee and the Transferor
      **transferor** (int) - index of the Transferor party, written as the party parameter
      **transferee** (int) - index of the Transferee party
      **transfer_target** (int) - index of the Transfer Target party (optional)
      **consultation** (int) - index of the Session Object for the consultative call (optional)

    Returns:
      Index of the new Event Object in the events Object array.
    """
    return(self._add_core_event("transfer-abandoned", time, sessions = sessions, party = transferor,
      transferee = transferee, transfer_target = transfer_target, consultation = consultation))


  @tag_event
  def add_channel_contributors_event(
    self,
    time : typing.Union[str, int, float, datetime.datetime],
    dialog : int,
    channel : int,
    contributors : typing.Union[int, typing.List[int], None] = None
    ) -> int:
    """
    Add a "channel-contributors" type Event Object: the party(s) contributing
    to a channel of a recording change at the given time.  The contributors at
    the start of the recording are given by the parties of the Dialog Object.

    Parameters:
      **time** (str, int, float, datetime.datetime) - Date, time at which the event occurred.
               String containing RFC 2822 or RFC3339 date time stamp or int/float
               containing epoch time (since 1970) in seconds.
      **dialog** (int) - index of the recording Dialog Object
      **channel** (int) - index of the channel in the recording, 0 is the first.  It must
               be less than the number of channels, when the Dialog Object parties tell
               the number: an int is one channel, an array containing an array or null
               has one element per channel.  A flat array of ints may be one mixed
               channel or one channel per party, so then only a negative channel fails.
      **contributors** (int, List[int]) - index or indices of the parties contributing to
               the channel from this time.  None (the default) means no party contributes,
               and writes no contributors parameter.

    Returns:
      Index of the new Event Object in the events Object array.
    """
    return(self._add_core_event(Vcon.EVENT_CHANNEL_CONTRIBUTORS_TYPE, time, dialog = dialog,
      channel = channel, contributors = contributors))


  @tag_event
  def add_event(
    self,
    event_type : str,
    time : typing.Union[str, int, float, datetime.datetime],
    **parameters : typing.Any
    ) -> int:
    """
    Add an Event Object of a type defined in a vCon extension.

    The core Event types have their own methods, for example **add_join_event**.
    The type is looked up in the parameter registry.  If a registered extension
    defines it, the extension is added to the vCon extensions parameter, and to
    critical if the extension is critical.  An unregistered type is added with a
    warning.  The parameters are added as given, after checking that any of
    sessions, party, dialog, transferee, transfer_target, consultation and
    target_session reference existing Objects.  dialog may be an index or a list
    of indices.

    Parameters:
      **event_type** (str) - the Event type defined in a vCon extension
      **time** (str, int, float, datetime.datetime) - Date, time at which the event occurred.
               String containing RFC 2822 or RFC3339 date time stamp or int/float
               containing epoch time (since 1970) in seconds.
      **parameters** - the other Event Object parameters

    Returns:
      Index of the new Event Object in the events Object array.

    Raises AttributeError for a core Event type, naming the method to use.
    """
    definer = vcon.parameter_registry.get_value_extension("Event", "type", event_type)
    if(definer == Vcon.PARAMETER_CORE):
      raise AttributeError(
        "Event type: \"{}\" is a core type.  Use add_{}_event.".format(
        event_type, event_type.replace("-", "_")))

    self._attempting_modify()
    self._check_event_indices(parameters)

    if(definer is None):
      logger.warning(
        "Event type: \"%s\" is not defined by the core vCon schema or any known vCon extension",
        event_type)
    else:
      self._add_extension_name(definer)

    for name in parameters.keys():
      self.add_parameter_extension("Event", name)

    return(self._append_event(event_type, time, parameters))


  def _check_event_indices(self, parameters : typing.Dict[str, typing.Any]) -> None:
    """
    Raise AttributeError if an index parameter of an Event Object references
    an Object which does not exist.  sessions and dialog may be an index or a
    non-empty list of indices.
    """
    for name, array_name in [("sessions", Vcon.SESSIONS), ("dialog", Vcon.DIALOG)]:
      value = parameters.get(name, None)
      if(value is not None):
        index_list = value if isinstance(value, list) else [value]
        if(len(index_list) == 0):
          raise AttributeError("{} must reference at least one Object".format(name))
        for index in index_list:
          self._check_object_index(array_name, index)

    for name in ["party", "transferee", "transfer_target"]:
      if(parameters.get(name, None) is not None):
        self._check_object_index(Vcon.PARTIES, parameters[name])

    for name in ["consultation", "target_session"]:
      if(parameters.get(name, None) is not None):
        self._check_object_index(Vcon.SESSIONS, parameters[name])


  def _add_core_event(
    self,
    event_type : str,
    time : typing.Union[str, int, float, datetime.datetime],
    **parameters : typing.Any
    ) -> int:
    """
    Check and add an Event Object of a core type.  The parameters are written
    in the order given, those which are None are not written.
    """
    self._attempting_modify()
    parameters = {name: value for name, value in parameters.items() if(value is not None)}

    if(event_type in Vcon.EVENT_TRANSFER_TYPES and not isinstance(parameters["sessions"], int)):
      raise AttributeError(
        "sessions for event type: \"{}\" must be the single index of the Session Object"
        " for the original call, not: {}".format(event_type, parameters["sessions"]))

    if(event_type in Vcon.EVENT_KEY_TYPES and
      (not isinstance(parameters.get("button", None), str) or parameters["button"] == "")):
      raise AttributeError("button is required for event type: \"{}\"".format(event_type))

    self._check_event_indices(parameters)

    if(event_type == Vcon.EVENT_CHANNEL_CONTRIBUTORS_TYPE):
      self._check_channel(parameters["dialog"], parameters["channel"])
      contributors = parameters.get("contributors", None)
      if(contributors is not None):
        for party_index in (contributors if isinstance(contributors, list) else [contributors]):
          self._check_object_index(Vcon.PARTIES, party_index)

    return(self._append_event(event_type, time, parameters))


  def _check_channel(self, dialog_index : int, channel : int) -> None:
    """
    Raise AttributeError if the Dialog Object is not a recording or the
    channel is not in it (see **add_channel_contributors_event**).
    """
    dialog = self._vcon_dict[Vcon.DIALOG][dialog_index]
    if(dialog.get("type", None) != "recording"):
      raise AttributeError(
        "dialog[{}] is not a recording Dialog Object, its type is: {}".format(
        dialog_index, dialog.get("type", None)))

    if(not isinstance(channel, int) or isinstance(channel, bool) or channel < 0):
      raise AttributeError("channel: {} must be a non-negative int".format(channel))

    dialog_parties = dialog.get("parties", None)
    if(isinstance(dialog_parties, int)):
      num_channels = 1
    elif(isinstance(dialog_parties, list) and
      any([isinstance(element, list) or element is None for element in dialog_parties])):
      num_channels = len(dialog_parties)
    else:
      # unknown: a flat list of ints may be one mixed channel or a channel per party
      num_channels = None

    if(num_channels is not None and channel >= num_channels):
      raise AttributeError(
        "channel: {} is not in dialog[{}], which has {} channel(s)".format(
        channel, dialog_index, num_channels))


  def _append_event(
    self,
    event_type : str,
    time : typing.Union[str, int, float, datetime.datetime],
    parameters : typing.Dict[str, typing.Any]
    ) -> int:
    """ Append an Event Object with type, time and the given parameters, return its index """
    new_event: typing.Dict[str, typing.Any] = {}
    new_event["type"] = event_type
    new_event["time"] = vcon.utils.cannonize_date(time)
    new_event.update(parameters)

    if(self._vcon_dict.get(Vcon.EVENTS, None) is None):
      self._vcon_dict[Vcon.EVENTS] = []

    self._vcon_dict[Vcon.EVENTS].append(new_event)

    return(len(self._vcon_dict[Vcon.EVENTS]) - 1)


  def _add_extension_name(self, extension_name : str) -> None:
    """
    Add the extension name to the vCon extensions parameter, and to critical
    if the extension is registered as critical.
    """
    names = [Vcon.EXTENSIONS]
    if(vcon.parameter_registry.is_critical(extension_name)):
      names.append(Vcon.CRITICAL)

    for name in names:
      name_list = self._vcon_dict.get(name, None)
      if(name_list is None):
        name_list = []
        self._vcon_dict[name] = name_list

      if(extension_name not in name_list):
        name_list.append(extension_name)


  @tag_event
  def set_event_parameter(
    self,
    parameter_name : str,
    parameter_value : typing.Any,
    event_index : int
    ) -> int:
    """
    Set the named parameter for the given Event Object.

    This does not create a new Object.  Use the add_*_event methods to create
    an Event Object.  The value is not validated.

    Parameters:
      **parameter_name** (String) - name of the Event Object parameter to be set.
      **parameter_value** (Any) - new value to set for the named parameter
      **event_index** (int) - index of the Event Object on which to set the parameter

    Returns:
      index of the Event Object
    """
    self._attempting_modify()
    self._check_object_index(Vcon.EVENTS, event_index)
    self.add_parameter_extension("Event", parameter_name)

    self._vcon_dict[Vcon.EVENTS][event_index][parameter_name] = parameter_value

    return(event_index)


  def _apply_dialog_originator(self, dialog_index : int, originator : int) -> None:
    """
    Apply the originator of a Dialog Object to the Session Object which
    references the Dialog Object.  The originator is never set on the
    Dialog Object.

    Raises AttributeError if the Dialog Object is not referenced by exactly
    one Session Object, or if the Session Object has a different originator
    and also references other Dialog Objects.
    """
    self._check_object_index(Vcon.PARTIES, originator)

    session_indices = self.find_sessions_for_dialog(dialog_index)
    if(len(session_indices) != 1):
      raise AttributeError(
        "cannot apply originator: {} for dialog: {}.  The dialog is referenced by {}"
        " Session Objects: {}.  It must be referenced by exactly one.".format(
        originator, dialog_index, len(session_indices), session_indices))

    session = self._vcon_dict[Vcon.SESSIONS][session_indices[0]]
    session_parties = session.get("parties", None)
    if(session_parties is None or len(session_parties) == 0):
      session["parties"] = [originator]
      return

    current_originator = session.get("originator", session_parties[0])
    if(current_originator == originator):
      return

    other_dialog = [index for index in (session.get("dialog", None) or []) if index != dialog_index]
    if(len(other_dialog) > 0):
      raise AttributeError(
        "cannot apply originator: {} for dialog: {}.  Session: {} has originator: {}"
        " and also references dialog: {}".format(
        originator, dialog_index, session_indices[0], current_originator, other_dialog))

    if(originator not in session_parties):
      session_parties.append(originator)
    if(session_parties[0] == originator):
      session.pop("originator", None)
    else:
      session["originator"] = originator
      Vcon._order_session_parameters(session)


  def _check_new_dialog_session(
    self,
    session : typing.Union[int, None],
    originator : typing.Union[int, None] = None
    ) -> None:
    """
    Check, before a new Dialog Object is created, that a reference to it
    can be added to the given Session Object with the given originator, so
    that the vCon is not left partially modified.

    Raises AttributeError if the session or originator index does not exist
    or if the originator conflicts with that of the Session Object.
    """
    has_originator = originator is not None and originator >= 0
    if(has_originator):
      self._check_object_index(Vcon.PARTIES, originator)

    if(session is None):
      return

    self._check_object_index(Vcon.SESSIONS, session)

    if(not has_originator):
      return

    session_object = self._vcon_dict[Vcon.SESSIONS][session]
    session_parties = session_object.get("parties", None) or []
    if(len(session_parties) == 0):
      return

    current_originator = session_object.get("originator", session_parties[0])
    session_dialog = session_object.get("dialog", None) or []
    if(current_originator != originator and len(session_dialog) > 0):
      raise AttributeError(
        "cannot reference new dialog with originator: {} from session: {}.  The session has"
        " originator: {} and references dialog: {}".format(
        originator, session, current_originator, session_dialog))


  def _add_new_dialog_to_session(
    self,
    dialog_index : int,
    session : typing.Union[int, None],
    originator : typing.Union[int, None] = None,
    receivers : typing.Union[typing.List[int], None] = None
    ) -> int:
    """
    Add a reference to a newly created Dialog Object to the given Session
    Object, or to a new Session Object if session is None, and apply the
    originator if given.  receivers are added to the Session parties; if
    None, the Dialog parties are (see add_dialog_to_session).

    Returns:
      index of the Session Object
    """
    if(session is None):
      session = self.add_session()

    self.add_dialog_to_session(session, dialog_index, receivers)

    if(originator is not None and originator >= 0):
      self._apply_dialog_originator(dialog_index, originator)

    return(session)


  @tag_dialog
  def add_text_dialog_inline(self,
    body : str,
    start_time : typing.Union[str, int, float, datetime.datetime],
    duration : typing.Union[int, float],
    party : typing.Union[int, list[int]],
    media_type : str,
    file_name : typing.Union[str, None] = None,
    session : typing.Union[int, None] = None) -> int:
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
      **media_type** (str) - media type of the body (usually MEDIATYPE_TEXT_PLAIN or MEDIATYPE_MULTIPART)  
      **file_name** (str) - file name of the body if applicable (optional)  
      **session** (int) - index of the Session Object which is to reference the new dialog.  If None,
               a new Session Object is created to reference it.  See **add_dialog_to_session**.

    Returns:  
      Index of the new dialog in the Dialog Object array parameter.
    """

    self._attempting_modify()
    self._check_new_dialog_session(session)

    new_dialog: typing.Dict[str, typing.Any] = {}
    new_dialog['type'] = "text"
    new_dialog['start'] = vcon.utils.cannonize_date(start_time)
    new_dialog['duration'] = duration
    new_dialog['parties'] = party
    new_dialog['mediatype'] = media_type
    if(file_name is not None and len(file_name) > 0):
      new_dialog['filename'] = file_name

    new_dialog['encoding'] = "none"
    new_dialog['body'] = body

    if(self.dialog is None):
      self._vcon_dict[Vcon.DIALOG] = []

    self._vcon_dict[Vcon.DIALOG].append(new_dialog)
    dialog_index = len(self.dialog) - 1

    self._add_new_dialog_to_session(dialog_index, session)

    return(dialog_index)


  @tag_dialog
  def add_incomplete_dialog(
    self,
    disposition : str,
    start_time : typing.Union[str, int, float, datetime.datetime, None] = None,
    duration : typing.Union[int, float, None] = None,
    caller : typing.Union[int, None] = None,
    receivers : typing.Union[typing.List[int], None] = None,
    session : typing.Union[int, None] = None
    ) -> int:
    """
    Add an incomplete Dialog Object, for a call or conversation which failed
    to be set up.  It has no Dialog Content.

    Parameters:  
      **disposition** (str) - why the call failed.  One of Vcon.DIALOG_DISPOSITIONS
               ("no-answer", "congestion", "failed", "busy", "hung-up",
               "voicemail-no-message") or a value defined in a vCon extension.
               "failed" is used when the reason is not known, e.g. in a placeholder.  
      **start_time** (str, int, float, datetime.datetime) - Date, time of the call attempt
               (optional, e.g. not known for a placeholder)  
      **duration** (int, float) - duration of the attempt in seconds (optional)  
      **caller** (int) - index of the party which attempted the call, written as the Dialog
               parties and applied as the Session originator (optional)  
      **receivers** (List[int]) - indices of the parties which were called, added to the
               Session parties (optional)  
      **session** (int) - index of the Session Object which is to reference the new dialog.
               If None, a new Session Object is created.

    Returns:  
      index of the new Dialog Object

    Raises AttributeError if the caller, a receiver or the session does not exist,
    the duration is negative, or the caller cannot become the originator of the
    given session because it has a different originator and other dialogs.  A disposition defined by a registered extension
    adds the extension to the vCon; an unregistered disposition is written with a
    warning.
    """
    self._attempting_modify()

    if(caller is not None):
      self._check_object_index(Vcon.PARTIES, caller)
    for party_index in receivers or []:
      self._check_object_index(Vcon.PARTIES, party_index)
    if(session is not None):
      self._check_object_index(Vcon.SESSIONS, session)
      # the caller must be able to become the Session originator (see _apply_dialog_originator)
      session_object = self._vcon_dict[Vcon.SESSIONS][session]
      session_parties = session_object.get("parties", None) or []
      if(caller is not None and len(session_parties) > 0):
        current_originator = session_object.get("originator", session_parties[0])
        if(current_originator != caller and len(session_object.get("dialog", None) or []) > 0):
          raise AttributeError(
            "cannot add incomplete dialog with caller: {}.  Session: {} has originator: {}"
            " and also references dialog: {}".format(
            caller, session, current_originator, session_object["dialog"]))
    if(duration is not None and
      (not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration < 0)):
      raise AttributeError("duration: {} must be a non-negative number of seconds".format(duration))

    definer = vcon.parameter_registry.get_value_extension("Dialog", "disposition", disposition)
    if(definer is None):
      logger.warning(
        "Dialog disposition: \"%s\" is not defined by the core vCon schema or any known vCon extension",
        disposition)
    elif(definer != Vcon.PARAMETER_CORE):
      self._add_extension_name(definer)

    new_dialog: typing.Dict[str, typing.Any] = {"type": "incomplete"}
    if(start_time is not None):
      new_dialog["start"] = vcon.utils.cannonize_date(start_time)
    if(duration is not None):
      new_dialog["duration"] = duration
    if(caller is not None):
      new_dialog["parties"] = caller
    new_dialog["disposition"] = disposition

    if(self._vcon_dict.get(Vcon.DIALOG, None) is None):
      self._vcon_dict[Vcon.DIALOG] = []
    self._vcon_dict[Vcon.DIALOG].append(new_dialog)
    dialog_index = len(self._vcon_dict[Vcon.DIALOG]) - 1

    session_parties = ([caller] if caller is not None else []) + (receivers or [])
    self._add_new_dialog_to_session(dialog_index, session, caller, session_parties)

    return(dialog_index)


  @tag_dialog
  def add_email_dialog_inline(
    self,
    smtp_message: str,
    file_name : typing.Union[str, None] = None,
    session : typing.Union[int, None] = None,
    include_bcc : bool = False
    ) -> int:
    """
    Add a new text dialog for the given SMTP email message.

    Only an SMTP (RFC 5322) message is accepted: a string with the headers
    and the body.  It should include To, From, Subject, Cc, Date headers and
    may include a simple text or MIME body.  MIME attachments stay in the
    Dialog body; no Attachment Objects are added.

    The parties of the new Dialog Object reference only the sender (From).
    The receivers of the message, the sender and the To and Cc parties (and
    Bcc parties if include_bcc), are referenced by the parties of the Session
    Object.  The Message-ID is written as message_id, and the Message-IDs of
    the In-Reply-To and References headers as in_reply_to and references
    (proposed Dialog parameters), when present.

    Unless session is given, the message joins the email thread of any email
    Dialog with which it shares a Message-ID (its own, In-Reply-To or
    References), in any arrival order.  A message which shares none starts a
    new thread in a new Session Object.  While the receivers of a thread stay
    the same, it is one Session Object.  When they change, the thread Session
    Object becomes the parent of child Session Objects, one for each run of
    messages, in Date order, with the same receivers.  A message which matches
    two threads joins the earliest and a warning is logged.

    Parameters:
      **smtp_message** (str) - string containing the contents of a SMTP
      messages including headers and body.
      **session** (int) - index of the Session Object which is to reference the new dialog,
               with no thread logic.  If None, see above.
      **include_bcc** (bool) - make the Bcc addresses parties and receivers (default False)

    Returns:  
      index (int) of the dialog added for the text body of the message

    Raises ValueError, before the vCon is changed, if the message has no
    parseable From address or Date header.
    """

    self._attempting_modify()
    email_message = email.message_from_string(smtp_message)
    sender, date = Vcon._check_smtp_message(email_message)
    self._check_new_dialog_session(session)

    # Set subject if its not already set
    if(self.subject is None or len(self.subject) == 0):
      subject = email_message.get("subject")
      if(subject is not None and subject != ""):
        self.set_subject(subject)

    # Get tuple(s) of (name, email_uri) for sender and recipients
    receiver_headers = ["to", "cc", "recent-to", "recent-cc"]
    if(include_bcc):
      receiver_headers.append("bcc")
    recipients = email.utils.getaddresses(sum([email_message.get_all(name, []) for name in receiver_headers], []))

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

    # The sender is first, followed by the To and Cc parties
    receivers: typing.List[int] = []
    for party_index in party_indices:
      if(party_index not in receivers):
        receivers.append(party_index)

    content_type = vcon.utils.unfold_header(email_message.get("content-type"))
    file_name = email_message.get_filename()

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

    # get and save the message-id header as that helps us avoid duplicating
    # a message and gives us a key to refer back to the SMTP message.
    message_id = (email_message.get("message-id") or "").strip()
    in_reply_to = Vcon._header_message_ids(email_message.get("in-reply-to"))
    references = Vcon._header_message_ids(email_message.get("references"))

    thread = None
    thread_items = []
    if(session is None):
      thread = self._find_email_thread(set(([message_id] if message_id != "" else []) + in_reply_to + references))
      if(thread is not None):
        thread_items = self._email_thread_items(thread)

    dialog_index = self.add_text_dialog_inline(email_body, date, 0, [sender_index], content_type, file_name,
      session if session is not None else thread)

    if(message_id != ""):
      self.set_dialog_parameter("message_id", message_id, dialog_index)
    if(len(in_reply_to) > 0):
      self.set_dialog_parameter("in_reply_to", in_reply_to, dialog_index)
    if(len(references) > 0):
      self.set_dialog_parameter("references", references, dialog_index)

    if(session is None and thread is not None):
      self._regroup_email_thread(thread, thread_items + [(dialog_index, receivers)])
    else:
      self.add_dialog_to_session(self.find_sessions_for_dialog(dialog_index)[0], dialog_index, receivers = receivers)

    return(dialog_index)


  @tag_dialog
  def add_email_dialogs_inline(
    self,
    smtp_messages : typing.List[str],
    include_bcc : bool = False
    ) -> typing.List[int]:
    """
    Add the given SMTP email messages, in Date order, with **add_email_dialog_inline**.

    Parameters:
      **smtp_messages** (List[str]) - the SMTP messages, in any order
      **include_bcc** (bool) - make the Bcc addresses parties and receivers (default False)

    Returns:
      the index of the dialog added for each message, in the order given

    Raises ValueError, before the vCon is changed, if a message has no
    parseable From address or Date header.
    """
    dates = [Vcon._check_smtp_message(email.message_from_string(smtp_message))[1]
      for smtp_message in smtp_messages]
    dialog_indices: typing.List[typing.Union[int, None]] = [None] * len(smtp_messages)
    for message_index in sorted(range(len(smtp_messages)), key = lambda index: dates[index]):
      dialog_indices[message_index] = self.add_email_dialog_inline(smtp_messages[message_index],
        include_bcc = include_bcc)

    return(typing.cast(typing.List[int], dialog_indices))


  @staticmethod
  def _check_smtp_message(email_message : email.message.Message) -> typing.Tuple[typing.Tuple[str, str], datetime.datetime]:
    """
    The sender (name, address) and Date of an SMTP message.

    Raises ValueError if it has no parseable From address or Date header.
    """
    sender = email.utils.parseaddr(email_message.get("from") or "")
    if(sender[1] == "" or "@" not in sender[1]):
      raise ValueError("email message has no parseable From address: {}".format(email_message.get("from")))

    date_header = email_message.get("date")
    try:
      date = email.utils.parsedate_to_datetime(date_header)
    except (TypeError, ValueError, IndexError):
      date = None
    if(date is None):
      raise ValueError("email message has no parseable Date header: {}".format(date_header))
    if(date.tzinfo is None):
      date = date.replace(tzinfo = datetime.timezone.utc)

    return(sender, date)


  @staticmethod
  def _header_message_ids(header_value : typing.Union[str, None]) -> typing.List[str]:
    """ The Message-IDs (with angle brackets) in an In-Reply-To or References header value """
    if(header_value is None):
      return([])
    return(re.findall(r"<[^<>\s]+>", vcon.utils.unfold_header(str(header_value))))


  def _email_thread_root(self, session_index : int) -> int:
    """ The thread Session: the parent of the given Session if it is a child, else itself """
    for parent_index, parent in enumerate(self._vcon_dict.get(Vcon.SESSIONS, None) or []):
      for reference in parent.get("sessions", None) or []:
        if(reference.get("type", None) == "child" and reference.get("session", None) == session_index):
          return(parent_index)

    return(session_index)


  def _email_thread_children(self, thread : int) -> typing.List[int]:
    """ The child Session indices of the thread Session, in its order """
    return([reference["session"] for reference in self._vcon_dict[Vcon.SESSIONS][thread].get("sessions", None) or []
      if(reference.get("type", None) == "child")])


  def _find_email_thread(self, message_ids : typing.Set[str]) -> typing.Union[int, None]:
    """
    The thread Session of the email Dialogs which share a Message-ID with the
    given set, None if none does.  If they are in more than one thread, the
    earliest (lowest index) is returned and a warning is logged.
    """
    if(len(message_ids) == 0):
      return(None)

    threads: typing.List[int] = []
    for dialog_index, dialog in enumerate(self._vcon_dict.get(Vcon.DIALOG, None) or []):
      if(dialog.get("type", None) != "text" or dialog.get("message_id", None) in (None, "")):
        continue
      dialog_ids = set([dialog["message_id"]] + (dialog.get("in_reply_to", None) or []) +
        (dialog.get("references", None) or []))
      if(len(dialog_ids & message_ids) > 0):
        for session_index in self.find_sessions_for_dialog(dialog_index):
          thread = self._email_thread_root(session_index)
          if(thread not in threads):
            threads.append(thread)

    if(len(threads) == 0):
      return(None)

    threads.sort()
    if(len(threads) > 1):
      logger.warning("email message matches the threads of Sessions: %s.  It joins Session: %s",
        threads, threads[0])

    return(threads[0])


  def _email_thread_items(self, thread : int) -> typing.List[typing.Tuple[int, typing.List[int]]]:
    """ (dialog index, receivers) of each Dialog in the thread """
    sessions = self._vcon_dict[Vcon.SESSIONS]
    holders = self._email_thread_children(thread) or [thread]
    return([(dialog_index, list(sessions[holder].get("parties", None) or []))
      for holder in holders for dialog_index in (sessions[holder].get("dialog", None) or [])])


  def _regroup_email_thread(
    self,
    thread : int,
    items : typing.List[typing.Tuple[int, typing.List[int]]]
    ) -> None:
    """
    Group the Dialogs of an email thread into runs, in Date order, of the
    same receivers.  One run: the thread is one Session.  More: the thread
    Session is the parent of a child Session for each run.  A child keeps
    its index for the run holding its earliest Dialog; new children are
    added as needed.  The parent and child start and duration are recomputed.
    """
    sessions = self._vcon_dict[Vcon.SESSIONS]
    dialogs = self._vcon_dict[Vcon.DIALOG]
    parent = sessions[thread]
    children = self._email_thread_children(thread)

    ordered = sorted(items, key = lambda item: (vcon.utils.date_to_datetime(dialogs[item[0]]["start"]), item[0]))
    runs: typing.List[typing.List[typing.Tuple[int, typing.List[int]]]] = []
    for item in ordered:
      if(len(runs) > 0 and set(runs[-1][0][1]) == set(item[1])):
        runs[-1].append(item)
      else:
        runs.append([item])

    if(len(runs) == 1 and len(children) == 0):
      self.add_dialog_to_session(thread, items[-1][0], receivers = items[-1][1])
      return

    child_of_dialog = {dialog_index: child for child in children
      for dialog_index in (sessions[child].get("dialog", None) or [])}
    assigned: typing.List[int] = []
    for run in runs:
      held = [child_of_dialog[dialog_index] for dialog_index, receivers in run if(dialog_index in child_of_dialog)]
      child = held[0] if(len(held) > 0 and held[0] not in assigned) else None
      if(child is None):
        child = self.add_session()
      assigned.append(child)

      child_session = sessions[child]
      for name in ["dialog", "parties", "start", "duration"]:
        child_session.pop(name, None)
      for dialog_index, receivers in run:
        self.add_dialog_to_session(child, dialog_index, receivers = receivers)

    # the parent: all receivers, the children in Date order and the time they span
    parent.pop("dialog", None)
    for name in ["start", "duration"]:
      parent.pop(name, None)
    parent_parties = parent.get("parties", None) or []
    for dialog_index, receivers in ordered:
      for party_index in receivers:
        if(party_index not in parent_parties):
          parent_parties.append(party_index)
    parent["parties"] = parent_parties
    other_references = [reference for reference in parent.get("sessions", None) or []
      if(reference.get("type", None) != "child")]
    parent["sessions"] = other_references + [{"session": child, "type": "child"} for child in assigned]
    for dialog_index, receivers in ordered:
      Vcon._extend_session_time(parent, dialogs[dialog_index])
    Vcon._order_session_parameters(parent)


  @tag_dialog
  def add_recording_dialog_inline(
    self,
    body : bytes,
    start_time : typing.Union[str, int, float, datetime.datetime],
    duration : typing.Union[int, float],
    parties : typing.Union[int, typing.List[int], typing.List[typing.List[int]]],
    media_type : str,
    file_name : typing.Union[str, None] = None,
    originator : typing.Union[int, None] = None,
    session : typing.Union[int, None] = None) -> int:
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
    **media_type** (str): media type of the recording  
    **file_name** (str): file name of the recording (optional)  
    **originator** (int): by default the originator is the first party listed in the parites array.
               However , in some cases, it is difficult to arrange the recording channels with the originator
               as the first party/channel.  In these cases, the originator can be explicitly provided.  The
               value of the originator is the index into the Vcon.parties array of the party that originated
               this dialog.  The originator is applied to the Session Object, not the Dialog Object.  
    **session** (int): index of the Session Object which is to reference the new dialog.  If None,
               a new Session Object is created to reference it.  See **add_dialog_to_session**.

    Returns:  
            Index to the added dialog
    """

    # TODO: do we want to know the number of channels?  e.g. to verify party list length

    # TODO: should we validate the start time?

    self._attempting_modify()
    self._check_new_dialog_session(session, originator)

    new_dialog: typing.Dict[str, typing.Any] = {}
    new_dialog['type'] = "recording"
    new_dialog['start'] = vcon.utils.cannonize_date(start_time)
    new_dialog['duration'] = duration

    if(parties is not None and
      parties != ""
      ):
      new_dialog['parties'] = parties

    new_dialog['mediatype'] = media_type

    if(file_name is not None and len(file_name) > 0):
      new_dialog['filename'] = file_name

    new_dialog['encoding'] = "base64url"
    encoded_body = vcon.utils.base64url_encode(body)
    #print("encoded body type: {}".format(type(encoded_body)))
    new_dialog['body'] = encoded_body

    if(self.dialog is None):
      self._vcon_dict[Vcon.DIALOG] = []

    self._vcon_dict[Vcon.DIALOG].append(new_dialog)
    dialog_index = len(self.dialog) - 1

    self._add_new_dialog_to_session(dialog_index, session, originator)

    return(dialog_index)

  @deprecated("use Vcon.decode_dialog_inline_body")
  def decode_dialog_inline_recording(self, dialog_index : int) -> bytes:
    """ depricated use decode_dialog_inline_body """
    body = self.decode_dialog_inline_body(dialog_index)
    # this should never happen, its to silence the linters
    if(isinstance(body, str)):
      body = bytes(body, "utf-8")

    return(body)


  @tag_dialog
  def get_channel_contributors(
    self,
    dialog_index : int,
    channel : int,
    num_channels : int,
    start : typing.Union[str, int, float, datetime.datetime],
    duration : typing.Union[int, float, None] = None
    ) -> typing.Union[int, typing.List[int], None]:
    """
    Get the party(s) heard on a channel of a recording Dialog Object from
    the given time, for the given duration.

    The contributors at the start of the recording are given by the Dialog
    Object parties: the whole parties value for a single channel recording,
    else the element of the parties array for the channel.  A channel-contributors
    Event Object for the Dialog and channel replaces the contributors from its
    time.  The latest such Event at or before start gives the contributors
    at start.  The contributors of the Events after start and before the end
    of the duration are added.  A null or absent contributors parameter
    means no party contributes.

    Parameters:  
      **dialog_index** (int) - index of the recording Dialog Object  
      **channel** (int) - index of the channel in the recording, 0 is the first  
      **num_channels** (int) - number of channels in the recording  
      **start** (str, int, float, datetime.datetime) - Date, time from which the party(s)
               are wanted.  String containing RFC 2822 or RFC3339 date time stamp or
               int/float containing epoch time (since 1970) in seconds.  
      **duration** (int, float) - seconds from start over which the party(s) are wanted.
               None (the default) gives the party(s) at start.

    Returns:  
      the party index (int) if one party, list of party indices if more than one,
      None if no party contributes.  With no change over the period, the Dialog
      parties element or Event contributors value is returned as found.

    Raises AttributeError if the dialog_index is out of range, the Dialog Object
    is not a recording, the channel is not less than num_channels or the
    duration is negative.
    """
    dialogs = self._vcon_dict.get(Vcon.DIALOG, None) or []
    if(not isinstance(dialog_index, int) or isinstance(dialog_index, bool) or
      dialog_index < 0 or dialog_index >= len(dialogs)):
      raise AttributeError("dialog index: {} out of range, there are {} Dialog Objects".format(
        dialog_index, len(dialogs)))

    dialog = dialogs[dialog_index]
    if(dialog.get("type", None) != "recording"):
      raise AttributeError(
        "dialog[{}] is not a recording Dialog Object, its type is: {}".format(
        dialog_index, dialog.get("type", None)))

    if(not isinstance(num_channels, int) or isinstance(num_channels, bool) or num_channels < 1):
      raise AttributeError("num_channels: {} must be a positive int".format(num_channels))

    if(not isinstance(channel, int) or isinstance(channel, bool) or
      channel < 0 or channel >= num_channels):
      raise AttributeError("channel: {} is not in dialog[{}], which has {} channel(s)".format(
        channel, dialog_index, num_channels))

    if(duration is not None and duration < 0):
      raise AttributeError("duration: {} must not be negative".format(duration))

    parties = dialog.get("parties", None)
    if(num_channels == 1):
      contributors = parties
    elif(isinstance(parties, list) and channel < len(parties)):
      contributors = parties[channel]
    else:
      contributors = None

    start_time = vcon.utils.date_to_datetime(start)
    end_time = start_time + datetime.timedelta(seconds = duration or 0)

    changes = []
    for event in self._vcon_dict.get(Vcon.EVENTS, None) or []:
      if(event.get("type", None) == Vcon.EVENT_CHANNEL_CONTRIBUTORS_TYPE and
        event.get("dialog", None) == dialog_index and event.get("channel", None) == channel and
        event.get("time", None) is not None):
        changes.append((vcon.utils.date_to_datetime(event["time"]), event.get("contributors", None)))
    changes.sort(key = lambda change: change[0])

    added = []
    for change_time, change_contributors in changes:
      if(change_time <= start_time):
        contributors = change_contributors
      elif(change_time < end_time):
        added.append(change_contributors)

    if(len(added) == 0):
      return(contributors)

    party_indices = vcon.utils.flatten_party_indices(contributors)
    for change_contributors in added:
      for party_index in vcon.utils.flatten_party_indices(change_contributors):
        if(party_index not in party_indices):
          party_indices.append(party_index)

    if(len(party_indices) == 0):
      return(None)
    if(len(party_indices) == 1):
      return(party_indices[0])
    return(party_indices)


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
      An empty Dialog Object returns an empty list.
    """

    #dialog type    mediatype  action
    #================================
    # text          TEXT_PLAIN return text body
    # text          MULTIPART  find first plain/text in multipart body
    # recording     N/A        find transcript in analysis

    dialog = self.dialog[dialog_index]
    # an empty Dialog Object has no type and no text
    dialog_type = dialog.get("type", None)
    if(dialog_type == "text"):
      #logger.debug("get_dialog_text media type:{}".format(dialog["mediatype"]))
      text_dict = {}
      if("parties" in dialog):
        if(isinstance(dialog["parties"], list)):
          text_dict["party"] = dialog["parties"][0]
        elif(isinstance(dialog["parties"], int)):
          text_dict["party"] = dialog["parties"]
        # transcript accessors and their consumers use "parties"
        if("party" in text_dict):
          text_dict["parties"] = text_dict["party"]
      text_dict["start"] = dialog["start"]
      # duration is optional (e.g. typing time is often not known)
      text_dict["duration"] = dialog.get("duration", None)

      if(dialog["mediatype"].lower() == vcon.Vcon.MEDIATYPE_TEXT_PLAIN):
        text_dict["text"] = dialog["body"]
        return([text_dict])

      if(vcon.Vcon.MEDIATYPE_MULTIPART in dialog["mediatype"].lower() ):
        # Need the content type with the boundry and body separator
        email_message = email.message_from_string("Content-Type: " + dialog["mediatype"] + "\r\n\r\n" + dialog["body"])

        if(not email_message.is_multipart()):
          logger.warning("Text body in dialog[{}] incorrectly labeled as multipart".format(dialog_index))

        for subpart in email_message.walk():
          if(subpart.get_content_type() == vcon.Vcon.MEDIATYPE_TEXT_PLAIN):
            logger.debug("subpart payload type: {} part is multipart: {}".format(type(subpart.get_payload()), subpart.is_multipart()))
            text_dict["text"] = subpart.get_payload()
            return([text_dict])

          # else:
          #   logger.debug("skipping part mediatype: {}".format(subpart.get_content_type()))

    elif(dialog_type == "recording"):
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
        # the contributors of a channel come from the Dialog parties and
        # the channel-contributors Events of this vCon
        accessor.channel_contributors = (lambda channel, num_channels, start, duration = None:
          self.get_channel_contributors(dialog_index, channel, num_channels, start, duration))
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

    for analysis_index, analysis in enumerate(self.analysis or []):
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

    Raises AttributeError if the Dialog Object is empty.
    """
    dialog = self._get_non_empty_dialog(dialog_index)
    if(dialog["type"] not in ["text", "recording"]):
      raise AttributeError("dialog[{}] type: {} is not supported".format(dialog_index, dialog["type"]))
    if(dialog.get("body") is None):
      raise AttributeError("dialog[{}] does not contain an inline body/file".format(dialog_index))

    encoding = Vcon.get_object_encoding(dialog, "dialog[{}]".format(dialog_index))

    if(encoding == "base64url"):
      decoded_body = vcon.utils.base64url_decode(dialog["body"])

    # No encoding
    elif(encoding == "none"):
      decoded_body = dialog["body"]

    else:
      raise UnsupportedVconVersion("dialog[{}] body encoding: {} not supported".format(dialog_index, dialog["encoding"]))

    return(decoded_body)


  @tag_dialog
  def add_recording_dialog_external(self, body : bytes,
    start_time : typing.Union[str, int, float, datetime.datetime],
    duration : typing.Union[int, float],
    parties : typing.Union[int, typing.List[int], typing.List[typing.List[int]]],
    external_url: str,
    media_type : typing.Union[str, None] = None,
    file_name : typing.Union[str, None] = None,
    sign_type : typing.Union[str, None] = "SHA-512",
    originator : typing.Union[int, None] = None,
    session : typing.Union[int, None] = None) -> int:
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
    **media_type** (str): media type of the recording (optional)  
    **file_name** (str): file name of the recording (optional)  
    **sign_type** (str): signature type to create for external signature
                     default= "SHA-512" use SHA 512 bit hash (RFC6234)
                     "LM-OTS" use Leighton-Micali One Time Signature (RFC8554)  
    **originator** (int): by default the originator of the dialog is the first party listed in the parites array.
               However , in some cases, it is difficult to arrange the recording channels with the originator
               as the first party/channel.  In these cases, the originator can be explicitly provided.  The
               value of the originator is the index into the Vcon.parties array of the party that originated
               this dialog.  The originator is applied to the Session Object, not the Dialog Object.  
    **session** (int): index of the Session Object which is to reference the new dialog.  If None,
               a new Session Object is created to reference it.  See **add_dialog_to_session**.

    Returns:  
            Index to the added dialog
    """

    # TODO: need a streaming/chunk version of this so that we don't have to have the whole file in memory.

    self._attempting_modify()
    self._check_new_dialog_session(session, originator)

    new_dialog: typing.Dict[str, typing.Any] = {}
    new_dialog['type'] = "recording"
    new_dialog['start'] = vcon.utils.cannonize_date(start_time)
    new_dialog['duration'] = duration
    new_dialog['parties'] = parties
    new_dialog['url'] = external_url
    if(media_type is not None):
      new_dialog['mediatype'] = media_type
    if(file_name is not None):
      new_dialog['filename'] = file_name


    if (body):
      if(sign_type == "LM-OTS"):
        warnings.simplefilter('always', DeprecationWarning)
        warnings.warn(
          "sign_type \"LM-OTS\" is deprecated; use \"SHA-512\" instead",
          category = DeprecationWarning,
          stacklevel = 2)
        warnings.simplefilter('default', DeprecationWarning)
        logger.warning("sign_type \"LM-OTS\" is deprecated; use \"SHA-512\" instead")

        key, signature = vcon.security.lm_one_time_signature(body)
        new_dialog['key'] = key
        new_dialog['signature'] = signature
        new_dialog['alg'] = "LMOTS_SHA256_N32_W8"

      elif(sign_type == "SHA-512"):
        sig_hash = vcon.security.sha_512_hash(body)
        new_dialog["content_hash"] = vcon.security.build_content_hash_token(sign_type, sig_hash)

      else:
        raise AttributeError("Unsupported signature type: {}.  Please use \"SHA-512\" or \"LM-OTS\"".format(sign_type))

    if(self.dialog is None):
      self._vcon_dict[Vcon.DIALOG] = []

    dialog_index = len(self.dialog)
    self._vcon_dict[Vcon.DIALOG].append(new_dialog)

    self._add_new_dialog_to_session(dialog_index, session, originator)

    return(dialog_index)


  @tag_dialog
  @deprecated("transfer Dialog Objects were removed in vCon 0.5.0; transfer Event Objects are added instead")
  def add_transfer_dialog(
      self,
      transferee: int,
      transferor: int,
      transfer_target: int,
      original_dialog: int,
      target_dialog: typing.Union[int, None],
      consultative_dialog: typing.Union[int, None] = None
    ) -> typing.List[int]:
    """
    Deprecated: vCon 0.5.0 has no transfer Dialog Object.  The transfer is
    captured in transfer Event Objects, which this adds (see
    **add_blind_transfer_event**, **add_consultation_start_event**,
    **add_consultative_transfer_event** and **add_transfer_abandoned_event**).

    The Events reference the Sessions of the given Dialogs:

      * target, no consultation: blind-transfer at the target Dialog start
      * consultation and target: consultation-start at the consultation Dialog
        start, consultative-transfer at the target Dialog start
      * consultation, no target: consultation-start, then transfer-abandoned
        at the end of the consultation Dialog
      * neither: transfer-abandoned at the end of the original Dialog

    Parameters:
      **transferee** (int): party index for the party from the original call that gets
                transfered to the target call
      **transferor** (int): party index for the party from the original call that performs
                or actuates the transfer.
      **transfer_target** (int): party index to the new party introduced in the target call
      **original_dialog** (int): the index to the original call dialog
      **target_dialog** (int, None): the index to the target or resulting outcome call, None
                if the transfer was not completed
      **consultative_dialog** (int, None): the index to the consultative dialog if one
                occurred.

    Returns:
      list of the indices of the Event Objects added

    Raises AttributeError, before anything is added, if a Dialog does not exist, is
    not referenced by exactly one Session Object, shares its Session Object with
    another of the Dialogs, a party does not exist, or a needed start or duration
    is missing.
    """
    self._attempting_modify()

    planned_events = Vcon._plan_transfer_events(
      self._vcon_dict,
      transferee,
      transferor,
      transfer_target,
      original_dialog,
      target_dialog,
      consultative_dialog
      )

    methods = {
        "blind-transfer": self.add_blind_transfer_event,
        "consultation-start": self.add_consultation_start_event,
        "consultative-transfer": self.add_consultative_transfer_event,
        "transfer-abandoned": self.add_transfer_abandoned_event
      }
    event_indices = []
    for event in planned_events:
      arguments = {name: value for name, value in event.items() if(name not in ("type", "party"))}
      event_indices.append(methods[event["type"]](transferor = event["party"], **arguments))

    return(event_indices)


  @staticmethod
  def _plan_transfer_events(
    vcon_dict : typing.Dict[str, typing.Any],
    transferee : int,
    transferor : int,
    transfer_target : int,
    original_dialog : int,
    target_dialog : typing.Union[int, None],
    consultative_dialog : typing.Union[int, None]
    ) -> typing.List[typing.Dict[str, typing.Any]]:
    """
    The transfer Event Objects which capture a 0.4.0 transfer Dialog Object
    (see **add_transfer_dialog**), as dicts of the Event parameters with the
    time canonized, in the order they occurred.  Works on a plain vCon dict
    (also used to convert 0.4.0 vCons).

    Raises AttributeError if a Dialog does not exist, is not referenced by
    exactly one Session Object, shares its Session Object with another of the
    Dialogs, a party does not exist, or a needed start or duration is missing.
    """
    dialogs = vcon_dict.get(Vcon.DIALOG, None) or []
    sessions = vcon_dict.get(Vcon.SESSIONS, None) or []
    num_parties = len(vcon_dict.get(Vcon.PARTIES, None) or [])

    for role, party_index in [("transferee", transferee), ("transferor", transferor),
      ("transfer_target", transfer_target)]:
      if(not isinstance(party_index, int) or isinstance(party_index, bool) or
        party_index < 0 or party_index >= num_parties):
        raise AttributeError("{} party: {} does not exist.  The vCon has {} parties.".format(
          role, party_index, num_parties))

    session_of = {}
    for role, dialog_index in [("original", original_dialog), ("target", target_dialog),
      ("consultation", consultative_dialog)]:
      if(dialog_index is None):
        continue
      if(not isinstance(dialog_index, int) or isinstance(dialog_index, bool) or
        dialog_index < 0 or dialog_index >= len(dialogs)):
        raise AttributeError("{} dialog: {} does not exist.  The vCon has {} dialogs.".format(
          role, dialog_index, len(dialogs)))
      session_indices = [session_index for session_index, session in enumerate(sessions)
        if(dialog_index in (session.get("dialog", None) or []))]
      if(len(session_indices) != 1):
        raise AttributeError("{} dialog: {} is referenced by {} Session Objects: {}.  It must be"
          " referenced by exactly one.".format(role, dialog_index, len(session_indices), session_indices))
      if(session_indices[0] in session_of.values()):
        raise AttributeError("{} dialog: {} is in Session: {}, which another of the transfer dialogs"
          " is also in.  Each role needs its own Session.".format(role, dialog_index, session_indices[0]))
      session_of[role] = session_indices[0]

    def dialog_time(role : str, dialog_index : int, at_end : bool) -> str:
      dialog = dialogs[dialog_index]
      if(dialog.get("start", None) is None or (at_end and dialog.get("duration", None) is None)):
        raise AttributeError("{} dialog: {} needs a start{} for the transfer event time".format(
          role, dialog_index, " and duration" if at_end else ""))
      if(not at_end):
        return(vcon.utils.cannonize_date(dialog["start"]))
      return(vcon.utils.cannonize_date(vcon.utils.date_to_datetime(dialog["start"]) +
        datetime.timedelta(seconds = dialog["duration"])))

    common = {"sessions": session_of["original"], "party": transferor, "transferee": transferee}
    events = []
    if(consultative_dialog is None and target_dialog is not None):
      events.append(dict(common, type = "blind-transfer", time = dialog_time("target", target_dialog, False),
        transfer_target = transfer_target, target_session = session_of["target"]))

    elif(consultative_dialog is not None):
      consultation_start = dialog_time("consultation", consultative_dialog, False)
      if(target_dialog is not None):
        target_start = dialog_time("target", target_dialog, False)
        events.append(dict(common, type = "consultation-start", time = consultation_start,
          transfer_target = transfer_target, consultation = session_of["consultation"]))
        events.append(dict(common, type = "consultative-transfer", time = target_start,
          transfer_target = transfer_target, consultation = session_of["consultation"],
          target_session = session_of["target"]))
      else:
        consultation_end = dialog_time("consultation", consultative_dialog, True)
        events.append(dict(common, type = "consultation-start", time = consultation_start,
          transfer_target = transfer_target, consultation = session_of["consultation"]))
        events.append(dict(common, type = "transfer-abandoned", time = consultation_end,
          transfer_target = transfer_target, consultation = session_of["consultation"]))

    else:
      events.append(dict(common, type = "transfer-abandoned",
        time = dialog_time("original", original_dialog, True), transfer_target = transfer_target))

    return(events)


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
      **get_kwargs** (dict, optional) - optional keyword arguments:
          ``connect_timeout`` (float) - TCP/TLS connection timeout
              (default: 5 s).
          ``read_timeout`` (float) - time to wait for response data
              (default: 20 s).
          ``timeout`` (float) - **deprecated**, use ``read_timeout``
              instead.  If provided, its value is used as
              ``read_timeout`` and a DeprecationWarning is issued.

    Returns:  
      verified content/bytes for the recording
    """
    from vcon.http_lb import HttpLb

    if(get_kwargs is None):
      get_kwargs = {}

    # Support legacy "timeout" key with a deprecation warning
    if("timeout" in get_kwargs):
      warnings.warn(
        "get_kwargs key 'timeout' is deprecated; use 'read_timeout' instead",
        DeprecationWarning,
        stacklevel=2
        )
      get_kwargs.setdefault("read_timeout", get_kwargs.pop("timeout"))

    url = self.dialog[dialog_index]["url"]
    resp = await HttpLb.get(
      url,
      connect_timeout=get_kwargs.get("connect_timeout", None),
      read_timeout=get_kwargs.get("read_timeout", 20.0),
      )
    if(not(200 <= resp.status_code < 300)):
      raise Exception("get of {} resulted in error: {}".format(
        url,
        resp.status_code
        ))
    body = resp.content

    # verify the body
    self.verify_dialog_external_recording(dialog_index, body)

    return(body)


  @tag_dialog
  def set_dialog_parameter(self,
    parameter_name : str,
    parameter_value : str,
    dialog_index : int = -1
    ) -> int:
    """
    Set the named parameter for the given dialog index.  If the index is not provided,
    add a new dialog to the vCon Dialog Object array.

    Parameters:
      **parameter_name** (String) - name of the Dialog Object parameter to be set.
      **parameter_value** (String) - new value to set for the named parameter
      **dialog_index** (int) - index of dialog to set tel url on
                  (-1 indicates a new dialog should be added, in a new Session Object)

    The originator parameter is no longer a Dialog Object parameter.  Setting
    it is applied to the Session Object which references the dialog.  An
    AttributeError is raised if that is ambiguous: the dialog is not
    referenced by exactly one Session Object, or the Session Object has a
    different originator and also references other dialogs.

    Returns:
    int: if success, positive int index of dialog in list
    """

    self._attempting_modify()

    if(parameter_name == "originator"):
      self._check_object_index(Vcon.DIALOG, dialog_index)
      self._apply_dialog_originator(dialog_index, parameter_value)
      return(dialog_index)

    new_dialog = (dialog_index == -1)
    dialog_index = self.__add_new_dialog(dialog_index)
    if(new_dialog):
      self._add_new_dialog_to_session(dialog_index, None)
    self.add_parameter_extension("Dialog", parameter_name)

    # TODO parameter specific validation
    self._vcon_dict[Vcon.DIALOG][dialog_index][parameter_name] = parameter_value

    return(dialog_index)


  @tag_dialog
  def add_dialog_redacted_segment(
    self,
    dialog_index : int,
    start : typing.Union[str, int, float, datetime.datetime],
    duration : typing.Union[int, float],
    parties : typing.Union[typing.List[int], None] = None,
    channel : typing.Union[int, None] = None
    ) -> int:
    """
    Add a Redacted_segments Object to a recording Dialog Object, for a period
    of the recording in which the audio or video was redacted.

    The Redacted_segments Object has start and end; end is computed as start
    plus duration.

    Parameters:  
      **dialog_index** (int) - index of the recording Dialog Object  
      **start** (str, int, float, datetime.datetime) - Date, time at which the redacted
               period starts.  String containing RFC 2822 or RFC3339 date time stamp
               or int/float containing epoch time (since 1970) in seconds.  
      **duration** (int, float) - length of the redacted period in seconds  
      **parties** (List[int]) - indices of the parties whose media was redacted (optional)  
      **channel** (int) - index of the redacted channel of the recording, 0 is the first
               (optional, proposed for the draft).  It must be less than the number of
               channels when the Dialog Object parties tell the number (see
               **add_channel_contributors_event**).

    Returns:  
      index of the new Redacted_segments Object in the Dialog's redacted_segments list

    Raises AttributeError if the Dialog Object is not a recording, the duration
    is negative, or a party or the channel does not exist.
    """
    self._attempting_modify()
    self._check_object_index(Vcon.DIALOG, dialog_index)
    dialog = self._vcon_dict[Vcon.DIALOG][dialog_index]
    if(dialog.get("type", None) != "recording"):
      raise AttributeError(
        "dialog[{}] is not a recording Dialog Object, its type is: {}".format(
        dialog_index, dialog.get("type", None)))

    if(not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration < 0):
      raise AttributeError("duration: {} must be a non-negative number of seconds".format(duration))

    if(parties is not None):
      if(not isinstance(parties, list)):
        raise AttributeError("parties: {} must be a list of party indices".format(parties))
      for party_index in parties:
        self._check_object_index(Vcon.PARTIES, party_index)

    if(channel is not None):
      self._check_channel(dialog_index, channel)

    start_time = vcon.utils.cannonize_date(start)
    end_time = vcon.utils.cannonize_date(
      vcon.utils.date_to_datetime(start_time) + datetime.timedelta(seconds = duration))

    segment: typing.Dict[str, typing.Any] = {"start": start_time, "end": end_time}
    if(parties is not None):
      segment["parties"] = parties
    if(channel is not None):
      segment["channel"] = channel

    if(dialog.get("redacted_segments", None) is None):
      dialog["redacted_segments"] = []
    dialog["redacted_segments"].append(segment)

    return(len(dialog["redacted_segments"]) - 1)


  @tag_dialog
  @deprecated("use add_text_dialog_inline")
  def add_dialog_inline_text(self, *args, **kwargs) -> int:
    """
    Deprecated, use **add_text_dialog_inline**, which this calls with the same arguments.
    """
    return(self.add_text_dialog_inline(*args, **kwargs))


  @tag_dialog
  @deprecated("use add_recording_dialog_inline")
  def add_dialog_inline_recording(self, *args, **kwargs) -> int:
    """
    Deprecated, use **add_recording_dialog_inline**, which this calls with the same arguments.
    """
    return(self.add_recording_dialog_inline(*args, **kwargs))


  @tag_dialog
  @deprecated("use add_recording_dialog_external")
  def add_dialog_external_recording(self, *args, **kwargs) -> int:
    """
    Deprecated, use **add_recording_dialog_external**, which this calls with the same arguments.
    """
    return(self.add_recording_dialog_external(*args, **kwargs))


  @tag_dialog
  @deprecated("use add_email_dialog_inline")
  def add_dialog_inline_email_message(self, *args, **kwargs) -> int:
    """
    Deprecated, use **add_email_dialog_inline**, which this calls with the same arguments.
    """
    return(self.add_email_dialog_inline(*args, **kwargs))


  @tag_dialog
  def clear_dialog(
    self,
    dialog_index : int,
    remove_from_sessions : bool = False
    ) -> None:
    """
    Replace the Dialog Object at the given index with an empty Dialog Object
    ({}), so that the indices of the other Dialog Objects do not change.

    References to the Dialog Object from Analysis and Attachment Objects are
    left to the caller.  The start and duration of Session Objects are not
    recomputed.

    Parameters:  
      **dialog_index** (int) - index of the Dialog Object to clear  
      **remove_from_sessions** (bool) - also remove the index from the dialog
               parameter of every Session Object which lists it (default False)

    Returns: none

    Raises AttributeError if there is no Dialog Object at the index.
    """
    self._attempting_modify()
    self._check_object_index(Vcon.DIALOG, dialog_index)

    self._vcon_dict[Vcon.DIALOG][dialog_index] = {}

    if(remove_from_sessions):
      for session in self._vcon_dict.get(Vcon.SESSIONS, None) or []:
        session_dialog = session.get("dialog", None)
        if(isinstance(session_dialog, list) and dialog_index in session_dialog):
          session["dialog"] = [index for index in session_dialog if index != dialog_index]


  def _get_non_empty_dialog(self, dialog_index : int) -> typing.Dict[str, typing.Any]:
    """ The Dialog Object at the index; raises AttributeError if it is an empty Dialog Object """
    dialog = self.dialog[dialog_index]
    if(len(dialog) == 0):
      raise AttributeError("dialog[{}] is an empty Dialog Object".format(dialog_index))

    return(dialog)


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
    AttributeError if the Dialog Object is empty.
    """

    dialog = self._get_non_empty_dialog(dialog_index)

    if(dialog['type'] != "recording"):
      raise AttributeError("dialog[{}] is of type: {} not recording".format(dialog_index, dialog['type']))

    if("content_hash" not in dialog):
      logger.warning("No content_hash in dialog: {}".format(dialog.keys()))
    if(len(dialog['content_hash']) < 1 ):
      raise AttributeError("dialog[{}] content_hash: {} not set.  Must be for LMOTS_SHA256_N32_W8".format(dialog_index, dialog['signature']))

    # TODO support array of content_hash tokens
    alg, hash_string = vcon.security.split_content_hash_token(dialog["content_hash"])

    if(alg == 'sha512'):
      sig_hash = vcon.security.sha_512_hash(body)
      if( hash_string != sig_hash):
        print("dialog[\"signature\"]: {} hash: {} size: {}".format(hash_string, sig_hash, len(body)))
        print("dialog: {}".format(json.dumps(dialog, indent=2)))
        raise InvalidVconHash("SHA-512 hash in signature does not match the given body for dialog[{}]".format(dialog_index))

    else:
      raise AttributeError("dialog[{}] alg: {} not supported.  Must be SHA-512".format(dialog_index, alg))


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
      self.add_parameter_extension("Analysis", param)
      analysis_element[param] = value

    if(self.analysis is None):
      self._vcon_dict[Vcon.ANALYSIS] = []

    self._vcon_dict[Vcon.ANALYSIS].append(analysis_element)

  @tag_analysis
  def add_analysis(self,
    dialog_index : typing.Union[int, typing.List[int], None],
    analysis_type: str,
    body : typing.Union[str, None] = None,
    vendor : typing.Union[str, None] = None,
    schema : typing.Union[str, None] = None,
    encoding : str= "json",
    sessions : typing.Union[int, typing.List[int], None] = None,
    attachment : typing.Union[int, typing.List[int], None] = None,
    analysis : typing.Union[int, typing.List[int], None] = None,
    **optional_parameters
    ) -> int:
    """
    Add a generic analysis for the indicated dialog(s), session(s), attachment(s)
    or other analysis.

    Parameters:  
    **dialog_index** (Union[int, list[int], None]): index or list of indices to the dialog in the vCon dialog
      list that this analysis was generated from, None if it was not generated from dialogs.  
    **vendor** (str): string token for the vendor of the audio to text transcription service  
    **schema** (str): schema label for the transcription data.  Used to identify data format of the transcription
                  for vendors that have more than one format or version.  
    **sessions** (Union[int, list[int]]): index or indices of the Session Objects analysed (optional)  
    **attachment** (Union[int, list[int]]): index or indices of the Attachment Objects analysed (optional)  
    **analysis** (Union[int, list[int]]): index or indices of the existing Analysis Objects analysed
      (optional).  An Analysis Object may not reference itself.  
    **optional_parameters** (dict[str, Any]) - additional parameters to add to the analysis object.

    A warning is logged if none of dialog_index, sessions, attachment and analysis
    is given, as an Analysis Object SHOULD reference what it was generated from.

    Return: index of the new Analysis Object

    Raises AttributeError if an index does not exist.
    """

    self._attempting_modify()

    references = [("dialog", dialog_index, Vcon.DIALOG), ("sessions", sessions, Vcon.SESSIONS),
      ("attachment", attachment, Vcon.ATTACHMENTS), ("analysis", analysis, Vcon.ANALYSIS)]
    for name, value, array_name in references:
      if(value is not None):
        index_list = value if isinstance(value, list) else [value]
        if(len(index_list) == 0):
          raise AttributeError("{} must reference at least one Object".format(name))
        for index in index_list:
          self._check_object_index(array_name, index)

    if(all([value is None for name, value, array_name in references])):
      logger.warning(
        "analysis type: \"%s\" references no dialog, sessions, attachment or analysis",
        analysis_type)

    analysis_element = {}
    analysis_element["type"] = analysis_type
    for name, value, array_name in references:
      if(value is not None):
        analysis_element[name] = value
    if(body is not None and body != ""):
      analysis_element["body"] = body
    analysis_element["encoding"] = encoding
    if(vendor is not None and vendor != ""):
      analysis_element["vendor"] = vendor
    if(schema is not None and schema != ""):
      analysis_element["schema"] = schema

    for parameter_name, value in optional_parameters.items():
      self.add_parameter_extension("Analysis", parameter_name)
      analysis_element[parameter_name] = value

    if(self.analysis is None):
      self._vcon_dict[Vcon.ANALYSIS] = []

    self._vcon_dict[Vcon.ANALYSIS].append(analysis_element)

    return(len(self._vcon_dict[Vcon.ANALYSIS]) - 1)


  @tag_attachment
  def add_attachment_inline(
    self,
    body : bytes,
    sent_time : typing.Union[str, int, float, datetime.datetime],
    party : int,
    media_type : typing.Union[str, None] = None,
    file_name : typing.Union[str, None] = None,
    dialog : typing.Union[int, None] = None,
    session : typing.Union[int, typing.List[int], None] = None,
    purpose : typing.Union[str, None] = None
    ) -> int:
    """
    Add an attachment object for the given file body.  The attachment must
    reference a Dialog Object, Session Object(s) or both.

    Parameters:  
    **body** (bytes): bytes for the audio or video recording (e.g. wave or MP3 file).  
    **send_time** (str, int, float, datetime.datetime): Date, time the attachment was sent.
               string containing RFC 2822 or RFC3339 date time stamp or int/float
               containing epoch time (since 1970) in seconds.  
    **party** (int): party index of the sender  
    **media_type** (str): media type of the recording  
    **file_name** (str): file name of the recording (optional)  
    **dialog** (int): index of the Dialog Object the attachment is part of (optional)  
    **session** (int, List[int]): index or indices of the Session Object(s) the attachment
               is related to (optional, written as given)  
    **purpose** (str): text describing what the attachment is for (optional)

    Returns:  
    (int) index of the added attachment

    Raises AttributeError if neither dialog nor session is given, or if the
    party, dialog or a session does not exist.
    """

    self._attempting_modify()

    if(dialog is None and session is None):
      raise AttributeError("an attachment must reference a dialog, a session or both")
    self._check_object_index(Vcon.PARTIES, party)
    if(dialog is not None):
      self._check_object_index(Vcon.DIALOG, dialog)
    if(session is not None):
      session_list = session if isinstance(session, list) else [session]
      if(len(session_list) == 0):
        raise AttributeError("session must reference at least one Session Object")
      for session_index in session_list:
        self._check_object_index(Vcon.SESSIONS, session_index)

    new_attachment: typing.Dict[str, typing.Any] = {}
    if(purpose is not None):
      new_attachment['purpose'] = purpose
    new_attachment['start'] = vcon.utils.cannonize_date(sent_time)
    new_attachment['party'] = party
    if(dialog is not None):
      new_attachment['dialog'] = dialog
    if(session is not None):
      new_attachment['session'] = session
    if(media_type is not None and
      media_type != ""):
      new_attachment['mediatype'] = media_type
      if(media_type in [
        vcon.Vcon.MEDIATYPE_TEXT_PLAIN,
        vcon.Vcon.MEDIATYPE_JSON
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
      encoded_body = vcon.utils.base64url_encode(body)
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
    Dump the vCon as a JSON format string.

    Parameters:  
    **signed** (Boolean): If the vCon is signed locally or verfied,  
        True: serialize the signed version  
        False: serialize the unsigned version

    Returns:  
             String containing JSON representation of the vCon.
    """
    return(json.dumps(self.dumpd(signed, False), indent = indent, default=lambda o: o.__dict__, **dumps_options))


  class VconBase64Bytes():
    """
    Class to handle encoding and conversion of base64url strings to/from bytes for JSON and CBOR
    """
    def __init__(self, encoded_base64url):
      self._base64url = encoded_base64url

    def base64url(self) -> str:
      return(self._base64url)

    def bytes(self) -> bytes:
      return(vcon.utils.base64url_decode(self._base64url))

    @staticmethod
    def isBase64Object(dict_object: dict) -> bool:
      if({"encoding", "body"} <= dict_object.keys()):
        if(dict_object["encoding"] == "base64url"):
          return(True)
      return(False)

    @staticmethod
    def objectizeBase64Object(dict_object: dict) -> None:
      dict_object["encoding"] = "binary"
      dict_object["body"] = Vcon.VconBase64Bytes(dict_object["body"])

  @staticmethod
  def get_object_encoding(dict_object: dict, object_label: str) -> str:
    """
    Get the encoding parameter form the given object.
    It is expected that this is a Dialog, Attachment, Analysis or Group Object
    """
    encoding = dict_object.get("encoding", None)
    if(encoding is None):
      # Strictly speaking this is not allowed.
      # encoding is a MUST set parameter in the spec.
      # Try to infer the coding from the mediatype:
      mediatype = dict_object.get("mediatype", None)
      if(mediatype):
        if(mediatype in [
            Vcon.MEDIATYPE_IMAGE_PNG,
            Vcon.MEDIATYPE_AUDIO_WAV,
            Vcon.MEDIATYPE_AUDIO_MP3,
            Vcon.MEDIATYPE_AUDIO_MP4,
            Vcon.MEDIATYPE_AUDIO_OGG,
            Vcon.MEDIATYPE_AUDIO_FLAC,
            Vcon.MEDIATYPE_VIDEO_MP4,
            Vcon.MEDIATYPE_VIDEO_OGG,
          ]):
          encoding = 'base64url'
        else:
          encoding = 'none'
        logger.warning("{}: missing MUST have 'encoding' parameter. Guessing from mediatype: {}"
          "  Assuming '{}' encoding.".format(object_label, mediatype, encoding))
      else:
        logger.warning("{}: missing MUST have 'encoding' and recommended 'mediatype' parameters."
          "  Assuming 'none' encoding.".format(object_label))
    else:
      encoding.lower()

    return(encoding)


  @staticmethod
  def vcon_object_cbor_encoder(cbor_encoder, value):
    if(isinstance(value, Vcon.VconBase64Bytes)):
       cbor_encoder.encode(cbor2.CBORTag(21, value.bytes()))
    else:
      raise(Exception("Unsupported type: {} for CBOR encoding"))


  @experimental("CBOR format is non-standard for vCon")
  @tag_serialize
  def dumpc(
      self
    ) -> bytes:
    """
    Dump the vCon as CBOR format bytes.

    Parameters:

    Returns:  
             String containing JSON representation of the vCon.
    """

    # TODO: would be better not to deep copy the dict
    vcon_dict = self.dumpd(False, True) # deep copy as we modify the copy and do not want this to be permient

    # Iterate body parameters in redacted_from and amended_from (and their 0.4.0 names)
    for reference in [Vcon.REDACTED_FROM, Vcon.AMENDED_FROM, Vcon.REDACTED, Vcon.AMENDED]:
      # change the base64 encoded bodies to an object so that it will be tagged and change the encoding label to "binary"
      if(reference in vcon_dict and
          Vcon.VconBase64Bytes.isBase64Object(vcon_dict[reference])
        ):
        Vcon.VconBase64Bytes.objectizeBase64Object(vcon_dict[reference])

    # Iterate body parameters in objects in group, parties, dialog, attachments and analysis arrays
    for object_array_name in [Vcon.GROUP, Vcon.DIALOG, Vcon.ATTACHMENTS, Vcon.ANALYSIS]:
      object_array = vcon_dict.get(object_array_name, None)
      if(object_array):
        for reference_object in object_array:
          # change the base64 encoded bodies to an object so that it will be tagged and change the encoding label to "binary"
          if(reference_object is not None and
              Vcon.VconBase64Bytes.isBase64Object(reference_object)
            ):
            Vcon.VconBase64Bytes.objectizeBase64Object(reference_object)

    return(cbor2.dumps(vcon_dict, default = Vcon.vcon_object_cbor_encoder))


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
    post_kwargs: typing.Optional[typing.Dict[str, typing.Any]] = None,
    ) -> None:
    """
    HTTP Post this Vcon to the given URL.
 
    Supports two URL styles:
 
    1. **Template style** (original, backward-compatible)::
 
         base_uri="http://{host}:{port}/vcon", host="localhost", port=8000
 
    2. **Multi-host URL with load balancing and failover**::
 
         base_uri="http://:password@host1:port1,host2:port2/path?db=0"
 
       When the URL contains comma-separated host:port pairs, DNS names
       are resolved to all A/AAAA records, the addresses are shuffled for
       load balancing, and failover is attempted on connection errors or
       502/503/504 responses.
 
    Parameters:
      **base_uri** (str) - template URL or multi-host URL for HTTP post
      **host** (str) - host IP or DNS name (used only with template URLs)
      **port** (int) - HTTP port (used only with template URLs)
      **post_kwargs** (dict, optional) - extra args:
          ``connect_timeout`` (float) - TCP/TLS connection timeout.
              Keep short for fast failover (default: 5 s).
          ``read_timeout`` (float) - time to wait for response data.
              Set high for LLM/transcription backends
              (default: 300 s).
          ``write_timeout`` (float) - time to send request body
              (default: 20 s).
          ``pool_timeout`` (float) - time to wait for a connection
              from the pool (default: 10 s).
          ``max_retries`` (int) - max addresses to attempt before
              giving up (default: try all resolved).
 
    Return: none
    """
    from vcon.http_lb import HttpLb
 
    if post_kwargs is None:
      post_kwargs = {}
 
    # Resolve template placeholders.
    if "{host}" in base_uri or "{port}" in base_uri:
      uri = base_uri.format(host=host, port=port)
    else:
      uri = base_uri
 
    resp = await HttpLb.post(
      url=uri,
      body=self.dumpd(),
      content_type=vcon.Vcon.MEDIATYPE_JSON,
      connect_timeout=post_kwargs.get("connect_timeout", None),
      read_timeout=post_kwargs.get("read_timeout", None),
      write_timeout=post_kwargs.get("write_timeout", None),
      pool_timeout=post_kwargs.get("pool_timeout", None),
      max_retries=post_kwargs.get("max_retries", None),
    )
 
    if not (200 <= resp.status_code < 300):
      raise Exception(
        "post of {} resulted in error code: {} text: {} content: {}".format(
          uri, resp.status_code, resp.text, resp.content
        )
      )


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
    1) unsigned vcon must have one or more of the following elements: parties, dialog, analysis, attachments, sessions, events
    2) JWS vCon must have a payload and signatures
    3) JWE vCon must have a ciphertext and recipients

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
    1) unsigned vcon must have one or more of the following elements: parties, dialog, analysis, attachments, sessions, events
    2) JWS vCon must have a payload and signatures
    3) JWE vCon must have a ciphertext and recipients

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
    elif(("ciphertext" in vcon_dict) and
      ("recipients" in vcon_dict)
      ):
      self._vcon_dict = {}

      self._state = VconStates.ENCRYPTED
      self._jwe_dict = vcon_dict

    # Unsigned vCon may have vcon version and
    elif(
      # one of the following arrays
      ('parties' in vcon_dict) or
      ('dialog' in vcon_dict) or
      ('analysis' in vcon_dict) or
      ('attachments' in vcon_dict) or
      ('sessions' in vcon_dict) or
      ('events' in vcon_dict)
      ):

      # validate version and migrate if needed
      self._vcon_dict = Vcon.check_and_migrate_version(vcon_dict)

    # Unknown
    else:
      raise InvalidVconJson("Not recognized as a unsigned , signed or encrypted form of JSON vCon." +
        "  Unsigned vcon must have at least one of: parties, dialog, analysis, attachments, sessions or events object arrays." +
        "  Signed vcon must have payload and signatures fields." +
        "  Encrypted vcon must have ciphertext and recipients fields."
        )


  @experimental("CBOR format is non-standard for vCon")
  @tag_serialize
  def loadc(self, vcon_cbor : bytes) -> None:
    """
    Load the vCon from a CBOR bytes array.
    Assumes that this vCon is an empty vCon as it is not cleared.

    Decision as to what json form to be deserialized is:
    1) unsigned vcon must have one or more of the following elements: parties, dialog, analysis, attachments, sessions, events
    2) JWS vCon must have a payload and signatures
    3) JWE vCon must have a ciphertext and recipients

    Parameters:  
      **vcon_json** (str): string containing JSON representation of a vCon

    Returns: none
    """

    self._attempting_modify()

    #TODO: Should check unsafe stuff is not loaded

    # TODO should use self._attempting_modify() ???
    if(self._state != VconStates.UNSIGNED):
      raise InvalidVconState("Cannot load Vcon unless current state is UNSIGNED.  Current state: {}".format(self._state))

    vcon_dict = cbor2.loads(vcon_cbor)

    # TODO: iterate object and replace CBORTag 21 with base64url encoded string and set encoding to "base64url"

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
    elif(("ciphertext" in vcon_dict) and
      ("recipients" in vcon_dict)
      ):
      self._vcon_dict = {}

      self._state = VconStates.ENCRYPTED
      self._jwe_dict = vcon_dict

    # Unsigned vCon may have vcon version and
    elif((
      # one of the following arrays
      ('parties' in vcon_dict) or
      ('dialog' in vcon_dict) or
      ('analysis' in vcon_dict) or
      ('attachments' in vcon_dict) or
      ('sessions' in vcon_dict) or
      ('events' in vcon_dict)
      )):

      # Check for CBOR tags that need to be replaced
      # This is not easily done with hooks int the CBOR parser as we need to change the body and the encoding parameters.

      # Iterate body parameters in redacted_from and amended_from (and their 0.4.0 names)
      for reference in [Vcon.REDACTED_FROM, Vcon.AMENDED_FROM, Vcon.REDACTED, Vcon.AMENDED]:
        # change the base64 encoded bodies to an object so that it will be tagged and change the encoding label to "binary"
        if(reference in vcon_dict and
           "body" in vcon_dict[reference] and
           isinstance(vcon_dict[reference]["body"], cbor2.CBORTag)):
          raise Exception("unimplemented CBORTag for: {}".format(reference))

      for object_array_name in [Vcon.GROUP, Vcon.DIALOG, Vcon.ATTACHMENTS, Vcon.ANALYSIS]:
        object_array = vcon_dict.get(object_array_name, None)
        if(object_array):
          for reference_object in object_array:
            # change the base64 encoded bodies to an object so that it will be tagged and change the encoding label to "binary"
            if(reference_object is not None and
               "body" in reference_object and
               isinstance(reference_object["body"], cbor2.CBORTag)
              ):
              if(reference_object["body"].tag != 21):
                raise Exception("CBOR tag: {} not support in: {}".format(
                    reference_object["body"].tag,
                    object_array_name
                  ))

              reference_object["body"] = vcon.utils.base64url_encode(reference_object["body"].value)
              reference_object["encoding"] = "base64url"

      # validate version and migrate if needed
      self._vcon_dict = Vcon.check_and_migrate_version(vcon_dict)

    # Unknown
    else:
      raise InvalidVconJson("Not recognized as a unsigned , signed or encrypted form of JSON vCon." +
        "  Unsigned vcon must have at least one of: parties, dialog, analysis, attachments, sessions or events object arrays." +
        "  Signed vcon must have payload and signatures fields." +
        "  Encrypted vcon must have ciphertext and recipients fields."
        )


  @tag_serialize
  async def get(
    self,
    uuid: str,
    base_uri: str = "http://{host}:{port}{path}",
    host: str = "localhost",
    port: int = 8000,
    path: str = "/vcon/{uuid}",
    get_kwargs: typing.Optional[typing.Dict[str, typing.Any]] = None,
    ) -> None:
    """
    HTTP GET the Vcon from the given base_uri and path.

    Supports two URL styles:

    1. **Template style** (original, backward-compatible)::

         base_uri="http://{host}:{port}{path}", host="localhost",
         port=8000, path="/vcon/{uuid}"

    2. **Multi-host URL with load balancing and failover**::

         base_uri="http://:password@host1:port1,host2:port2/vcon/{uuid}"

       The ``{uuid}`` placeholder in the URL is replaced with the
       *uuid* parameter.

    Parameters:
      **uuid** (str) - UUID of the vCon to retrieve
      **base_uri** (str) - template URL or multi-host URL
      **host** (str) - host IP or DNS name (used only with template URLs)
      **port** (int) - HTTP port (used only with template URLs)
      **path** (str) - template path (used only with template URLs)
      **get_kwargs** (dict, optional) - extra args:
          ``connect_timeout`` (float) - TCP/TLS connection timeout
              (default: 5 s).
          ``read_timeout`` (float) - time to wait for response data
              (default: 300 s).
          ``write_timeout`` (float) - time to send request body
              (default: 20 s).
          ``pool_timeout`` (float) - time to wait for a connection
              from the pool (default: 10 s).
          ``max_retries`` (int) - max addresses to attempt before
              giving up (default: try all resolved).

    Return: none
    """
    from vcon.http_lb import HttpLb

    if get_kwargs is None:
      get_kwargs = {}

    # Resolve template placeholders.
    if "{host}" in base_uri or "{port}" in base_uri:
      uri = base_uri.format(
        host=host,
        port=port,
        path=path.format(uuid=uuid)
      )
    elif "{uuid}" in base_uri:
      uri = base_uri.format(uuid=uuid)
    else:
      uri = base_uri

    resp = await HttpLb.get(
      url=uri,
      headers={"accept": vcon.Vcon.MEDIATYPE_JSON},
      connect_timeout=get_kwargs.get("connect_timeout", None),
      read_timeout=get_kwargs.get("read_timeout", None),
      write_timeout=get_kwargs.get("write_timeout", None),
      pool_timeout=get_kwargs.get("pool_timeout", None),
      max_retries=get_kwargs.get("max_retries", None),
    )

    if not (200 <= resp.status_code < 300):
      raise Exception("get of {} resulted in error: {}".format(
        uri,
        resp.status_code
      ))

    vcon_json = resp.content
    self.loads(vcon_json)


  @tag_signing
  def sign(
    self,
    private_key_pem_file: str,
    cert_chain_pem_files : typing.List[str],
    x5u : typing.Union[str, None] = None,
    include_x5c : bool = True
    ) -> None:
    """
    Sign the vcon using the given private key from the give certificate chain.

    Parameters:  
    **private_key_pem_file** (str): file name or string containing PEM format private key to use for signing the vcon.  
    **cert_chain_pem_files** (List[str]): file names or PEM strings, for the pem format certicate chain for the
        private key to use for signing.  The cert/public key corresponding to the private key should be the
        first cert.  THe certificate authority root should be the last cert.  
    **x5u** (str): URL of the PEM format certificate chain (RFC7515 section 4.1.5), added
        to the signature header if given (optional)  
    **include_x5c** (bool): add the certificate chain to the signature header as x5c
        (default True).  If False, x5u must be given.

    Returns: none

    Logs a warning if the vCon uses extensions which it does not list in its
    extensions or critical parameters (see **Vcon.check_extensions**).  The
    vCon is signed unchanged.

    Raises ValueError if include_x5c is False and no x5u is given, as the
    signature would then have no certificate chain.
    """

    if(self._state == VconStates.SIGNED):
      raise InvalidVconState("Vcon was already signed.")

    if(self._state != VconStates.UNSIGNED):
      raise InvalidVconState("Vcon not in valid state to be signed: {}.".format(self._state))

    if(self.uuid is None or len(self.uuid) < 1):
      raise InvalidVconState("vCon has no UUID set.  Use set_uuid method before signing.")

    if(not include_x5c and (x5u is None or x5u == "")):
      raise ValueError("include_x5c is False and no x5u is given.  A signature needs x5c or x5u.")

    self._warn_unlisted_extensions("sign")

    chain_header, signing_jwk = vcon.security.build_signing_jwk_from_pem_files(private_key_pem_file, cert_chain_pem_files)

    header = {}
    if(include_x5c):
      header["x5c"] = chain_header["x5c"]
    if(x5u is not None and x5u != ""):
      header["x5u"] = x5u
    # For convenience add the uuid to the header
    header[Vcon.UUID] = self.uuid

    # No header parameter may be in both the protected and unprotected
    # headers.  alg is integrity protected.  x5c, x5u and uuid are in the
    # unprotected header.
    jws = jwcrypto.jws.JWS(json.dumps(self._vcon_dict, separators = (",", ":")).encode("utf-8"))
    jws.add_signature(
      signing_jwk,
      None,
      json.dumps({"alg": chain_header["alg"]}, separators = (",", ":")),
      header
      )
    # jwcrypto creates the flattened JSON serialization for a single
    # signature.  vCon uses the general JSON serialization.
    flattened = json.loads(jws.serialize())

    jws_serialization = {}
    jws_serialization['payload'] = flattened["payload"]
    jws_serialization['signatures'] = []
    first_sig = {}
    first_sig['header'] = header
    first_sig['signature'] = flattened["signature"]
    first_sig['protected'] = flattened["protected"]
    jws_serialization['signatures'].append(first_sig)

    self._jws_dict = jws_serialization
    self._state = VconStates.SIGNED


  @tag_signing
  async def verify(
    self,
    ca_cert_pem_files : typing.List[str],
    fetch_x5u : bool = False,
    cert_chain_pem_files : typing.Union[typing.List[str], None] = None
    ) -> None:
    """
    Verify the signed vCon and its certificate chain which should be issued by one of the given CAs

    verify is a coroutine and must be awaited.  Calling it without await
    verifies nothing; Python only warns that the coroutine was never awaited.

    Parameters:  
      **ca_cert_pem_files** (List[str]): file name or PEM string list containing Certificate Authority certificates 
        to verify the vCon's certificate chain.  
      **fetch_x5u** (bool): for a signature with x5u and no x5c header parameter, fetch the
        certificate chain from the x5u URL (default False)  
      **cert_chain_pem_files** (List[str]): file names or PEM strings for the certificate chain,
        signing certificate first, to use for a signature with no x5c header parameter
        (optional).  Used in place of fetching x5u.

    Returns: none

    Raises exceptions for invalid cert chaind, invalid cert dates or chain not issued by one
    of the given CAs.  InvalidVconSignature if a signature has no alg, has alg
    "none" (an unsecured JWS, which a vCon must not use) or its certificate
    chain is not available.

    The header parameters may be in the protected header, the unprotected
    header or both.  A header parameter may not be in both the protected and
    unprotected headers of a signature.  Signed vCons created by earlier
    versions of this package repeat alg and x5c in both headers with identical
    values.  These are still accepted.  A signature with a header parameter in
    both headers with different values is rejected.

    The certificate chain is taken from x5c, else cert_chain_pem_files, else
    x5u if fetch_x5u is True.  A supplied or fetched chain must still be issued
    by one of the given CAs.

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
    for ca in ca_cert_pem_files:
      ca_cert_object_list.append(vcon.security.load_pem_cert(ca)[0])

    # TODO: what does it mean if ca_cert_pem_files is empty?  Should we verify and
    # assume that the cert chain is trusted?
    last_exception = Exception("Internal error in Vcon.verify this exception should never be thrown")
    for signature_index, signature in enumerate(self._jws_dict['signatures']):
      label = "signature[{}]".format(signature_index)

      # TODO: need to do something a little smarter on the exception raise to
      # give a clue of the best/closest chain and CA that failed.  Perhaps
      # even all of the failures.

      try:
        try:
          signature_header = vcon.security.merge_jose_headers(
            vcon.security.decode_jws_protected_header(signature.get('protected', None) or ""),
            signature.get('header', None) or {},
            label
            )
        except ValueError as header_error:
          raise InvalidVconSignature(str(header_error)) from header_error

        if(signature_header.get('alg', None) is None):
          raise InvalidVconSignature("{} has no alg header parameter".format(label))

        # checked before any certificate chain is fetched
        if(signature_header['alg'] == "none"):
          raise InvalidVconSignature("{} has alg \"none\", which a vCon must not use".format(label))

        cert_chain_objects = await Vcon._signature_cert_chain(
          signature_header,
          label,
          fetch_x5u,
          cert_chain_pem_files
          )

        vcon.security.verify_cert_chain(cert_chain_objects)

        # We have a valid chain, check if its from one of the accepted CAs
        for ca_object in ca_cert_object_list:
          try:
            vcon.security.verify_cert(cert_chain_objects[len(cert_chain_objects) - 1], ca_object)

            # IF we get here, we have a valid chain: cert_chain_objects issued from one of our accepted
            # CAs: ca_object.
            # The assumtion is that it is safe to trust this cert chain.  So we
            # can use it to build a JWK and verify the signature.
            verification_jwk = jwcrypto.jwk.JWK.from_pyca(cert_chain_objects[0].public_key())

            # Verify this signature alone, in the flattened JSON
            # serialization, without the identical header parameters
            # repeated by earlier versions of this package.
            flattened = vcon.security.remove_jws_repeated_headers(signature)
            flattened["payload"] = self._jws_dict['payload']
            jws = jwcrypto.jws.JWS()
            jws.deserialize(json.dumps(flattened), verification_jwk, signature_header['alg'])
            verified_payload = jws.payload

            # If we get here, the payload was verified
            vcon_dict = json.loads(verified_payload.decode('utf-8'))
            self._vcon_dict = Vcon.check_and_migrate_version(vcon_dict)
            self._state = VconStates.VERIFIED

            return(None)

          # This valid chain, is not issued from the CA for this ca_objjwk
          except Exception as e:
            last_exception = e
            # Keep trying other CAs until we run out or succeed

      # Invalid chain or headers
      except Exception as e:
        last_exception = e
        # Keep trying other signatures until we run out or succeed

    raise last_exception


  @staticmethod
  async def _signature_cert_chain(
    signature_header : dict,
    label : str,
    fetch_x5u : bool,
    cert_chain_pem_files : typing.Union[typing.List[str], None]
    ) -> typing.List[cryptography.x509.Certificate]:
    """
    The certificate chain for a signature: from x5c, else the supplied chain,
    else fetched from x5u if fetch_x5u is True.

    Raises InvalidVconSignature if no chain is available.
    """
    if("x5c" in signature_header):
      return(vcon.security.der_to_certs(signature_header["x5c"]))

    if(cert_chain_pem_files is not None and len(cert_chain_pem_files) > 0):
      return([vcon.security.load_pem_cert(pem)[0] for pem in cert_chain_pem_files])

    x5u = signature_header.get("x5u", None)
    if(x5u is None):
      raise InvalidVconSignature("{} has no x5c or x5u header parameter and no"
        " cert_chain_pem_files were given".format(label))

    if(not fetch_x5u):
      raise InvalidVconSignature("{} certificate chain is only available by x5u: {}."
        "  Set fetch_x5u to fetch it or give cert_chain_pem_files.".format(label, x5u))

    try:
      response = await vcon.http_lb.HttpLb.get(
        x5u,
        connect_timeout = X5U_FETCH_TIMEOUT,
        read_timeout = X5U_FETCH_TIMEOUT
        )
      response.raise_for_status()
      return(vcon.security.pem_chain_to_certs(response.content))
    except Exception as fetch_error:
      raise InvalidVconSignature("{} certificate chain could not be fetched from x5u: {}: {}: {}".format(
        label, x5u, type(fetch_error).__name__, fetch_error)) from fetch_error


  @tag_encrypting
  def encrypt(self, cert_pem_file: str) -> None:
    """
    encrypt a Signed vcon using the given public key from the give certificate.

    vcon must be signed first.

    Parameters:  
    **cert_pem_file** (str): file name or PEM string for the public key/cert to use for encrypting the vcon.

    Returns: none

    Logs a warning if the vCon uses extensions which it does not list in its
    extensions or critical parameters (see **Vcon.check_extensions**).  The
    vCon is encrypted unchanged.
    """

    if(self._state not in [VconStates.SIGNED, VconStates.UNVERIFIED]):
      raise InvalidVconState("Vcon must be signed before it can be encrypted")

    if(len(self._jws_dict) < 2):
      raise InvalidVconState("Vcon signature does not seem valid: {}".format(self._jws_dict))

    self._warn_unlisted_extensions("encrypt")

    # both of these work
    #encryption = "A256GCM"
    encryption = "A256CBC-HS512"

    encryption_key = vcon.security.build_encryption_jwk_from_pem_file(cert_pem_file)

    plaintext = json.dumps(self._jws_dict, **dumps_options)

    unprotected = {}
    # Add UUID to unprotected for easy reference
    unprotected["uuid"] = self.uuid
    unprotected["cty"] = Vcon.MEDIATYPE_VCON

    # enc and alg are in the protected header.  No header parameter may be
    # repeated in the unprotected or recipient headers.
    jwe = jwcrypto.jwe.JWE(
      plaintext.encode("utf-8"),
      protected = json.dumps({"alg": "RSA-OAEP", "enc": encryption}, separators = (",", ":")),
      unprotected = json.dumps(unprotected)
      )
    jwe.add_recipient(encryption_key)
    # jwcrypto creates the flattened JSON serialization for a single
    # recipient.  vCon uses the general JSON serialization.
    flattened = json.loads(jwe.serialize())

    jwe_complete_serialization = {}
    jwe_complete_serialization["protected"] = flattened["protected"]
    jwe_complete_serialization["iv"] = flattened["iv"]
    jwe_complete_serialization["ciphertext"] = flattened["ciphertext"]
    jwe_complete_serialization["tag"] = flattened["tag"]
    jwe_complete_serialization["recipients"] = [{"encrypted_key": flattened["encrypted_key"]}]
    jwe_complete_serialization["unprotected"] = unprotected

    self._jwe_dict = jwe_complete_serialization
    self._state = VconStates.ENCRYPTED


  @tag_encrypting
  def decrypt(self, private_key_pem_file: str, cert_pem_file: str) -> None:
    """
    Decrypt a vCon using private and public key file.

    vCon must be in encrypted state and will be in signed state after decryption.

    A header parameter may not be in more than one of the protected, unprotected
    and recipient headers.  Encrypted vCons created by earlier versions of this
    package repeat enc in all three with identical values.  These are still
    accepted.  A JWE with a header parameter repeated with different values is
    rejected with InvalidVconJson.

    Parameters:
    **private_key_pem_file** (str): file name or PEM string for the private key to use for decrypting the vcon.  
    **cert_pem_file** (str): file name or PEM string for the public key/cert to use for decrypting the vcon.

    Returns: none
    """

    if(self._state != VconStates.ENCRYPTED):
      raise InvalidVconState("Vcon is not encrypted")

    if(len(self._jwe_dict) < 2):
      raise InvalidVconState("Vcon JWE does not seem valid: {}".format(self._jws_dict))

    try:
      vcon.security.check_jwe_headers(self._jwe_dict)
    except ValueError as header_error:
      raise InvalidVconJson(str(header_error)) from header_error

    (header, decryption_key) = vcon.security.build_signing_jwk_from_pem_files(private_key_pem_file, [cert_pem_file])

    jwe = jwcrypto.jwe.JWE()
    jwe.deserialize(json.dumps(vcon.security.remove_jwe_repeated_headers(self._jwe_dict)), decryption_key)
    plaintext_decrypted = jwe.payload.decode('utf-8')
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
  def jsonpath(
    self,
    query: typing.Union[str, dict[str, str]]
    ) -> typing.Union[list[typing.Any], dict[str, list[typing.Any]]]:
    """
    Perform JSONPath queries (RFC 9535) on the Vcon JSON

    The query runs on the vCon content, whether the vCon is unsigned, signed or
    verified.  A signed vCon read back from storage must be verified first, and an
    encrypted one decrypted and verified.

    Parameters:  
    **query** (Union[str, dict[str, str]]) - query(s) to be performed on this Vcon
      **query** can be a single JSONPath query string or a dict containing a named set
      where the values are query strings.

    Returns:  
      if query is a str, a list of the values of the nodes the query selects  
      if query is a dict, a dict with keys corresponding to the input query where
      the values are the lists of selected values.

    Raises jsonpath_rfc9535.JSONPathError (JSONPathSyntaxError for a malformed query).
    """
    if(self._state in [VconStates.UNVERIFIED, VconStates.DECRYPTED, VconStates.ENCRYPTED]):
      raise InvalidVconState("Vcon state: {} cannot read parameters".format(self._state))

    # The vCon content, as attribute access returns it.  A signed or verified vCon
    # also has a JWS form, but the content there is inside the payload.
    vcon_dict = self.dumpd(signed = False)

    if(isinstance(query, str)):
      return(jsonpath_rfc9535.find(query, vcon_dict).values())

    results = {}
    for query_name, query_string in query.items():
      results[query_name] = jsonpath_rfc9535.find(query_string, vcon_dict).values()

    return(results)


  @property
  def state(self) -> VconStates:
    """
    The form this Vcon is currently in: UNSIGNED, SIGNED, UNVERIFIED (signed,
    read from storage or the wire and not yet verified), VERIFIED, ENCRYPTED or
    DECRYPTED.  Which operations and attributes are allowed depends upon it.
    """
    return(self._state)


  @tag_operation
  def jq(
    self,
    query: typing.Union[str, dict[str, str]]
    ) -> typing.Union[list[str], dict[str, any]]:
    """
    Perform jq syle queries on the Vcon JSON

    The query runs on the vCon content, whether the vCon is unsigned, signed or
    verified.  A signed vCon read back from storage must be verified first, and an
    encrypted one decrypted and verified.

    Parameters:  
    **query** (Union[str, dict[str, str]]) - query(s) to be performed on this Vcon
      **query** can be a single query string or a dict containing a names set where
      the values are query strings.

  Returns:  
    if query is a str, a list containing the query result is returned  
    if query is a dict, a dict with keys corresponding to the input query where
    the values are the query result.
    """
    if(self._state in [VconStates.UNVERIFIED, VconStates.DECRYPTED, VconStates.ENCRYPTED]):
      raise InvalidVconState("Vcon state: {} cannot read parameters".format(self._state))

    # The vCon content, as attribute access returns it.  A signed or verified vCon
    # also has a JWS form, but the content there is inside the payload.
    vcon_dict = self.dumpd(signed = False)

    if(isinstance(query, str)):
      compiled_query = jq.compile(query)

      return(compiled_query.input_value(vcon_dict).all())

    else:
      results = {}
      for query_name, query_string in query.items():
        compiled_query = jq.compile(query_string)
        results[query_name] = compiled_query.input_value(vcon_dict).all()[0]

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

    plugin_reg = vcon.filter_plugins.FilterPluginRegistry.get(filter_name, True)

    plugin = plugin_reg.plugin()
    if(plugin is None):
      message = "plugin: {} not loaded as module: {} was not found".format(plugin_reg.name, plugin_reg._module_name)
      raise vcon.filter_plugins.FilterPluginModuleNotFound(message)

    plugin.check_valid_state(self)

    # Force defaulting and typing for plugin specific options
    if(isinstance(options, dict)):
      options = plugin.options_type(**options)

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


  @tag_meta
  @staticmethod
  def get_dict_uuid(vcon_dict: dict) -> str:
    """
    Get the vCon UUID from the given dict.

    The dict may be the unsigned, signed (JWS) or encrypted (JWE) forms.
    """

    if(not isinstance(vcon_dict, dict)):
      raise Exception("get_dict_uuid expected dict, got: {} {}".format(type(vcon_dict), vcon_dict))

    # signed (JWS) form of vCon
    if({"payload", "signatures"} <= vcon_dict.keys() and
       len(vcon_dict["signatures"]) > 0
      ):
      # the unprotected header is optional
      uuid = (vcon_dict["signatures"][0].get("header", None) or {}).get("uuid", None)
      if(uuid is None):
        # decode the payload and parse JSON to get UUID
        vcon_json_string = vcon.utils.base64url_decode(vcon_dict["payload"])
        payload_vcon_dict = json.loads(vcon_json_string)
        uuid = payload_vcon_dict.get("uuid", None)

    # encrypted (JWE) form of vCon, the protected and unprotected headers are optional
    elif({"ciphertext", "recipients"} <= vcon_dict.keys()):
      uuid = (vcon_dict.get("unprotected", None) or {}).get("uuid", None)

    # Unsigned form
    else:
      uuid = vcon_dict.get("uuid", None)

    return(uuid)


  @tag_vcon_references
  def set_redacted_from(
    self,
    uuid : typing.Union[str, None],
    redaction_type : str,
    url : typing.Union[str, None] = None,
    content_hash : typing.Union[str, typing.List[str], None] = None
    ) -> None:
    """
    Set/replace the Redacted_from Object, which references the less redacted
    version of this vCon.

    Parameters:  
      **uuid** (str) - the UUID of the less redacted vCon.  None if it is not
               available.  
      **redaction_type** (str) - text describing the redaction, for example the type of
               information that was redacted  
      **url** (str) - URL from which the less redacted vCon may be retrieved (optional)  
      **content_hash** (str, List[str]) - content hash(es) of the vCon at url (required with url)

    Returns:  None

    Raises AttributeError if url is given without content_hash, or if this
    vCon has an amended_from (or 0.4.0 amended) parameter, which is mutually
    exclusive with redacted_from.
    """
    self._attempting_modify()
    self._check_vcon_reference(Vcon.REDACTED_FROM, url, content_hash, [Vcon.AMENDED_FROM, Vcon.AMENDED])

    new_redacted_from: typing.Dict[str, typing.Any] = {}
    if(uuid is not None):
      new_redacted_from["uuid"] = uuid
    new_redacted_from["type"] = redaction_type
    self._set_vcon_reference(Vcon.REDACTED_FROM, Vcon.REDACTED, new_redacted_from, url, content_hash)


  @tag_vcon_references
  def set_amended_from(
    self,
    uuid : typing.Union[str, None],
    url : typing.Union[str, None] = None,
    content_hash : typing.Union[str, typing.List[str], None] = None
    ) -> None:
    """
    Set/replace the Amended_from Object, which references the prior version
    of this vCon, to which this vCon adds data.

    Parameters:  
      **uuid** (str) - the UUID of the prior vCon version (may be None if url is given)  
      **url** (str) - URL from which the prior vCon version may be retrieved (optional)  
      **content_hash** (str, List[str]) - content hash(es) of the vCon at url (required with url)

    Returns:  None

    Raises AttributeError if neither uuid nor url is given, if url is given
    without content_hash, or if this vCon has a redacted_from (or 0.4.0
    redacted) parameter, which is mutually exclusive with amended_from.
    """
    self._attempting_modify()
    if(uuid is None and url is None):
      raise AttributeError("amended_from needs a uuid or a url")
    self._check_vcon_reference(Vcon.AMENDED_FROM, url, content_hash, [Vcon.REDACTED_FROM, Vcon.REDACTED])

    new_amended_from: typing.Dict[str, typing.Any] = {}
    if(uuid is not None):
      new_amended_from["uuid"] = uuid
    self._set_vcon_reference(Vcon.AMENDED_FROM, Vcon.AMENDED, new_amended_from, url, content_hash)


  def _check_vcon_reference(
    self,
    name : str,
    url : typing.Union[str, None],
    content_hash : typing.Union[str, typing.List[str], None],
    exclusive_names : typing.List[str]
    ) -> None:
    """ Raise AttributeError if url has no content_hash or a mutually exclusive parameter is present """
    if(url is not None and (content_hash is None or len(content_hash) == 0)):
      raise AttributeError("{} url: {} needs a content_hash".format(name, url))

    for exclusive_name in exclusive_names:
      if(exclusive_name in self._vcon_dict):
        raise AttributeError("{} cannot be set, the vCon has {}, which is mutually exclusive with it".format(
          name, exclusive_name))


  def _set_vcon_reference(
    self,
    name : str,
    old_name : str,
    reference : typing.Dict[str, typing.Any],
    url : typing.Union[str, None],
    content_hash : typing.Union[str, typing.List[str], None]
    ) -> None:
    """ Set the reference Object, replacing it and any member with its 0.4.0 name """
    if(url is not None):
      reference["url"] = url
      reference["content_hash"] = content_hash

    self._vcon_dict.pop(old_name, None)
    self._vcon_dict[name] = reference


  @tag_vcon_references
  def add_redacted_string(
    self,
    redaction_type : typing.Union[str, None] = None,
    orig : typing.Union[str, None] = None,
    avoid_text : str = ""
    ) -> int:
    """
    Add a Redacted_string Object for a string which is to be redacted, or find
    the one already added for the same original string.

    The Redacted_string gets the next ref after the highest existing ref, and
    the marker parameter: the string which replaces the redacted string, e.g.
    "__REDACTED_REF_1__".  The marker parameter is proposed for the draft; the
    non-digit suffix ends the number, so refs have no upper limit (the -05
    JSON Schema caps ref at 99999).

    Parameters:  
      **redaction_type** (str) - the type of information redacted, e.g. "PHONE_NUMBER" (optional)  
      **orig** (str) - the original string (optional).  If a Redacted_string with
               the same orig exists, its ref is returned and nothing is added.  
      **avoid_text** (str) - text in which the new marker must not already appear
               literally; a ref whose marker appears in it is skipped.

    Returns:  
      the ref of the Redacted_string
    """
    self._attempting_modify()
    redacted_strings = self._vcon_dict.get(Vcon.REDACTED_STRINGS, None) or []

    if(orig is not None):
      for redacted_string in redacted_strings:
        if(redacted_string.get("orig", None) == orig):
          return(redacted_string["ref"])

    ref = max([redacted_string.get("ref", 0) for redacted_string in redacted_strings] + [0]) + 1
    while(Vcon.redacted_string_marker(ref) in avoid_text):
      ref += 1

    new_redacted_string: typing.Dict[str, typing.Any] = {"ref": ref}
    if(redaction_type is not None):
      new_redacted_string["type"] = redaction_type
    if(orig is not None):
      new_redacted_string["orig"] = orig
    new_redacted_string["marker"] = Vcon.redacted_string_marker(ref)

    if(self._vcon_dict.get(Vcon.REDACTED_STRINGS, None) is None):
      self._vcon_dict[Vcon.REDACTED_STRINGS] = []
    self._vcon_dict[Vcon.REDACTED_STRINGS].append(new_redacted_string)

    return(ref)


  @staticmethod
  @tag_vcon_references
  def redacted_string_marker(ref : int) -> str:
    """ The marker string for the given Redacted_string ref, e.g. "__REDACTED_REF_1__" """
    return("{}{}{}".format(Vcon.REDACTED_REF_PREFIX, ref, Vcon.REDACTED_REF_SUFFIX))


  @tag_vcon_references
  def redact_text(
    self,
    text : str,
    spans : typing.List[typing.Tuple[int, int, str]]
    ) -> str:
    """
    Replace each labeled span of the text with the marker of its Redacted_string
    (see **add_redacted_string**), adding the Redacted_string Objects with the
    label as type and the replaced string as orig.  The same string gets the
    same ref wherever it appears in this vCon, with the type of its first label.
    A new ref is not used if its marker already appears in the text.

    Parameters:  
      **text** (str) - the text to redact  
      **spans** (List[Tuple[int, int, str]]) - start index, end index (exclusive) and
               label of each string to redact.  A span which overlaps an earlier
               span is ignored.

    Returns:  
      the redacted text
    """
    pieces = []
    position = 0
    for start, end, label in sorted(spans, key = lambda span: span[0]):
      end = min(end, len(text))
      if(start < position or start >= end):
        continue
      ref = self.add_redacted_string(label, text[start:end], avoid_text = text)
      pieces.append(text[position:start])
      pieces.append(Vcon.redacted_string_marker(ref))
      position = end

    pieces.append(text[position:])
    return("".join(pieces))


  @tag_vcon_references
  def find_redacted_strings(self, text : str) -> typing.List[typing.Dict[str, typing.Any]]:
    """
    Find the Redacted_string Objects referenced by the markers in a string.

    A Redacted_string with a marker parameter is matched by its exact marker
    string.  One without a marker (from another -05 producer) is matched by
    "__REDACTED_REF_" followed by up to 5 digits anywhere in the string, taking
    the longest leading run of those digits which is the ref of such a
    Redacted_string.  Text which matches none is literal text.

    Parameters:  
      **text** (str) - the string to search

    Returns:  
      the Redacted_string for each marker found, in the order found
    """
    redacted_strings = self.redacted_strings
    found = []
    covered = []
    for redacted_string in redacted_strings:
      marker = redacted_string.get("marker", None)
      if(marker is None or marker == ""):
        continue
      position = text.find(marker)
      while(position >= 0):
        found.append((position, redacted_string))
        covered.append((position, position + len(marker)))
        position = text.find(marker, position + len(marker))

    by_ref = {redacted_string.get("ref", None): redacted_string
      for redacted_string in redacted_strings if(redacted_string.get("marker", None) in (None, ""))}
    for match in re.finditer(re.escape(Vcon.REDACTED_REF_PREFIX) + r"(\d{1,5})", text):
      if(any([start <= match.start() < end for start, end in covered])):
        continue
      digits = match.group(1)
      for length in range(len(digits), 0, -1):
        redacted_string = by_ref.get(int(digits[:length]), None)
        if(redacted_string is not None):
          found.append((match.start(), redacted_string))
          break

    return([redacted_string for position, redacted_string in sorted(found, key = lambda item: item[0])])


  @tag_vcon_references
  @deprecated("use set_redacted_from")
  def set_redacted(self, uuid: str, redacted_type: str) -> None:
    """
    Deprecated, use **set_redacted_from**, which this calls.

    Parameters:  
      **uuid** - the UUID of the less redacted form of this vCon
      **redacted_type** - the reason or content that was redacted from the referenced vCon

    Returns:  None
    """
    self.set_redacted_from(uuid, redacted_type)


  @tag_vcon_references
  @deprecated("use set_amended_from")
  def set_amended(self, uuid: str) -> None:
    """
    Deprecated, use **set_amended_from**, which this calls.

    Parameters:  
      **uuid** - the UUID of the vCon that this vCon amends content to

    Returns:  None
    """
    self.set_amended_from(uuid)


  @tag_vcon_references
  def add_group_object(self, uuid: str) -> int:
    """
    Append a new Group Object to the group list.
    The Group Object references a vCon by UUID.
    The group list references vCons which are sub-conversations, part of a larger conversation,
    defined in this vCon which containes the group list.

    Parameters:  
      **uuid** - the UUID of the vCon that is to be part of this group of vCons

    Returns:  None
    """

    self._attempting_modify()

    new_child = {}
    new_child["uuid"] = uuid

    group_list = self._vcon_dict.setdefault(Vcon.GROUP, [])
    group_len = len(group_list)
    group_list.append(new_child)

    return(group_len)


  @staticmethod
  def get_parameter_extension(
    object_name : str,
    parameter_name : str
    ) -> typing.Union[str, None]:
    """
    Get the vCon extension which defines the given parameter name in the
    given Object.

    Parameters:  
      **object_name** (String) - name of the Object containing the parameter,
                  as in draft-ietf-vcon-vcon-core.  "-" is the top level vCon
                  Object.  For example: "-", "Party", "Dialog", "Session",
                  "Session_Reference", "Event", "Attachment", "Analysis",
                  "Civicaddress", "SessionId".
                  See **vcon.parameter_registry**.  
      **parameter_name** (String) - name of the parameter in the Object.

    Returns:  
      **Vcon.PARAMETER_CORE** if defined by the core vCon schema, the extension
      name token as it is to appear in the vCon extensions parameter if defined
      by an extension, or None if the name is not registered in the Object.

    Raises ValueError if the Object name is not registered.
    """
    return(vcon.parameter_registry.get_parameter_extension(object_name, parameter_name))


  @tag_meta
  def add_parameter_extension(
    self,
    object_name : str,
    parameter_name : str
    ) -> typing.Union[str, None]:
    """
    Add the name of the vCon extension which defines the given parameter to
    this vCon's extensions parameter, and also to its critical parameter if
    the extension is registered as critical.

    Has no effect if the parameter is defined by the core vCon schema.  Logs a
    warning and has no effect if the parameter name is not registered.

    Parameters:  
      **object_name** (String) - name of the Object containing the
                  parameter.  See **Vcon.get_parameter_extension**.  
      **parameter_name** (String) - name of the parameter in the Object.

    Returns:  
      the same value as **Vcon.get_parameter_extension**

    Raises ValueError if the Object name is not registered.
    """
    definer = Vcon.get_parameter_extension(object_name, parameter_name)

    if(definer is None):
      logger.warning(
        "parameter name: \"%s\" in Object: \"%s\" is not defined by the"
        " core vCon schema or any known vCon extension",
        parameter_name,
        object_name
        )
      return(None)

    if(definer == Vcon.PARAMETER_CORE):
      return(definer)

    self._attempting_modify()
    self._add_extension_name(definer)

    return(definer)


  @tag_meta
  def check_extensions(self) -> typing.Dict[str, typing.List[str]]:
    """
    Find the extensions this vCon uses, and those it uses but does not list
    in its extensions and critical parameters.

    The setters add the extension name when they write an extension
    parameter.  This checks the whole vCon, which catches what bypasses
    them: vCons that were loaded, edited with jq or changed through
    _vcon_dict.  Nothing is changed.  See **Vcon.update_extensions**.

    Returns:  
      see **vcon.parameter_registry.find_extensions**: the lists used,
      unlisted, critical_unlisted and unregistered
    """
    return(vcon.parameter_registry.find_extensions(self._vcon_dict))


  @tag_meta
  def update_extensions(self) -> typing.Dict[str, typing.List[str]]:
    """
    Add the extensions this vCon uses but does not list to its extensions
    parameter, and those registered as critical also to its critical
    parameter.  Unregistered parameters and values are reported, not
    assigned to an extension.

    Returns:  
      the result of **Vcon.check_extensions** before the update
    """
    self._attempting_modify()
    report = self.check_extensions()

    for name, missing in [(Vcon.EXTENSIONS, report["unlisted"]), (Vcon.CRITICAL, report["critical_unlisted"])]:
      if(len(missing) > 0):
        name_list = self._vcon_dict.get(name, None)
        if(name_list is None):
          name_list = []
          self._vcon_dict[name] = name_list
        name_list.extend(missing)

    return(report)


  def _warn_unlisted_extensions(self, operation : str) -> None:
    """ Log a warning naming any extension used but not listed (see check_extensions) """
    report = self.check_extensions()
    if(len(report["unlisted"]) > 0 or len(report["critical_unlisted"]) > 0):
      logger.warning(
        "%s vCon UUID: %s uses extensions not listed in extensions: %s, critical: %s."
        "  Use update_extensions to add them.",
        operation,
        self.uuid,
        report["unlisted"],
        report["critical_unlisted"]
        )


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
      instance_attributes = ['_jwe_dict', '_jws_dict', '_state', '_vcon_dict', 'vcon', "Vcon", "accessors", "bin", "cli", "docker_dev", "filter_plugins", "filter_plugins_addons", "pydantic_utils", "security", "utils"]
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
  def check_and_migrate_version(vcon_dict : dict) -> dict:
    """
    Validate the vCon syntax version parameter and migrate the vCon to the
    current syntax if a migration is implemented for that version.

    The vcon parameter is deprecated.  A vCon with no vcon parameter is
    assumed to be of the current syntax and is passed through unmodified.
    A vCon of the CURRENT_VCON_VERSION is passed through unmodified.
    A vCon of a version in UNCONVERTED_VCON_VERSIONS is passed through
    unmodified, with its vcon parameter left as is, and a
    UnconvertedVconVersionWarning is emitted.  A vCon of a version in
    MIGRATABLE_VCON_VERSIONS is migrated, the migrations stack and the
    last one removes the vcon parameter.

    Parameters:
      vcon_dict - unsigned form vCon dict to validate and migrate

    Returns:
      the vCon dict, migrated if a migration was implemented and needed
    """

    version_string = vcon_dict.get(Vcon.VCON_VERSION, None)

    # vcon parameter is deprecated.  Assume current syntax.
    if(version_string is None):
      return(vcon_dict)

    # Current syntax
    if(version_string == Vcon.CURRENT_VCON_VERSION):
      return(vcon_dict)

    # Accepted as is.  No migration implemented, vcon parameter left alone.
    if(version_string in Vcon.UNCONVERTED_VCON_VERSIONS):
      warnings.simplefilter('always', UnconvertedVconVersionWarning)
      warnings.warn(
        "vCon syntax version: \"{}\" accepted without conversion."
        "  No migration is implemented for this version."
        "  Parameter names and semantics may differ from the current vCon syntax.".format(
          version_string),
        category = UnconvertedVconVersionWarning,
        stacklevel = 3)
      warnings.simplefilter('default', UnconvertedVconVersionWarning)
      logger.warning("vCon syntax version: \"%s\" accepted without conversion", version_string)
      return(vcon_dict)

    if(version_string not in Vcon.MIGRATABLE_VCON_VERSIONS):
      raise UnsupportedVconVersion("load of JSON vcon version: \"{}\" not supported".format(
        version_string))

    # Migrations stack.  Each sets the vcon parameter to the next version.
    if(version_string == "0.0.1"):
      vcon_dict = Vcon.migrate_0_0_1_vcon(vcon_dict)
    if(vcon_dict.get(Vcon.VCON_VERSION, None) == "0.0.2"):
      vcon_dict = Vcon.migrate_0_0_2_vcon(vcon_dict)

    return(vcon_dict)


  @staticmethod
  def migrate_0_0_2_vcon(old_vcon : dict) -> dict:
    """
    Migrate/translate an an older deprecated vCon to the current version.

    Parameters:
      old_vcon old format 0.0.2 vCon

    Returns:
      the modified old_vcon in the new format
    """

    # This is the last migration in the chain.  The vcon parameter is
    # deprecated, so remove it rather than set it to a newer version.
    old_vcon.pop(Vcon.VCON_VERSION, None)
    return(old_vcon)


  @staticmethod
  def migrate_0_0_1_vcon(old_vcon : dict) -> dict:
    """
    Migrate/translate an an older deprecated vCon to the 0.0.1 version.

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

        # Convert to content_hash
        if("signature" in dialog):
          hash_string = dialog["signature"]
          alg = dialog["alg"]
          dialog["content_hash"] = vcon.security.build_content_hash_token(alg, hash_string)
          del dialog["alg"]
          del dialog["signature"]

      # Change mimetype to mediatype
      if("mimetype" in dialog):
        dialog["mediatype"] = dialog["mimetype"]
        del dialog["mimetype"]

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

      # Convert to content_hash
      if("alg" in analysis and "signature" in analysis):
        hash_string = analysis["signature"]
        alg = analysis["alg"]
        analysis["content_hash"] = vcon.security.build_content_hash_token(alg, hash_string)
        del analysis["alg"]
        del analysis["signature"]

      # Change mimetype to mediatype
      if("mimetype" in analysis):
        analysis["mediatype"] = analysis["mimetype"]
        del analysis["mimetype"]


    for index, attachment in enumerate(old_vcon.get("attachment", [])):
      # Change mimetype to mediatype
      if("mimetype" in attachment):
        attachment["mediatype"] = attachment["mimetype"]
        del attachment["mimetype"]

      # Convert to content_hash
      if("alg" in attachment and "signature" in attachment):
        hash_string = attachment["signature"]
        alg = attachment["alg"]
        attachment["content_hash"] = vcon.security.build_content_hash_token(alg, hash_string)
        del attachment["alg"]
        del attachment["signature"]

    # Now converted to 0.0.2
    old_vcon["vcon"] = "0.0.2"

    return(old_vcon)

