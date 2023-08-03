
import enum
import typing
import py_vcon_server.db
import vcon
from py_vcon_server.logging_utils import init_logger

logger = init_logger(__name__)


class VconTypes(enum.Enum):
  """ Enum for the various forms that a Vcon can exist in """
  UNKNOWN = 0
  UUID = 1
  JSON = 2
  DICT = 3
  OBJECT = 4

class MultifariousVcon():
  """ Container object for various forms of vCon and cashing of the different forms """
  def __init__(self):
    self._vcon_forms = {}

  def update_vcon(self, new_vcon: typing.Union[str, vcon.Vcon],
    vcon_uuid: str = None,
    vcon_json: str = None,
    vcon_dict: dict = None,
    vcon_object: vcon.Vcon = None) -> None:

    vcon_type = self.get_vcon_type(new_vcon)
    if(vcon_type == VconTypes.UNKNOWN):
      raise Exception("Unknown/unsupported vcon type: {} for new_vcon".format(type(new_vcon)))

    # Clear the cache of all forms of the Vcon
    self._vcon_forms = {}
    self._vcon_forms[vcon_type] = new_vcon

    # The following check if multiple forms of the Vcon were provided to cache
    if(vcon_json is not None and vcon_type != VconTypes.JSON):
      self._vcon_forms[VconTypes.JSON] = vcon_json
    if(vcon_dict is not None and vcon_type != VconTypes.DICT):
      self._vcon_forms[VconTypes.DICT] = vcon_dict
    if(vcon_object is not None and vcon_type != VconTypes.OBJECT):
      self._vcon_forms[VconTypes.OBJECT] = vcon_object
 
    # Try to get the UUID if the given type is not a UUID
    if(vcon_type != VconTypes.UUID):
      if(vcon_uuid is not None):
        self._vcon_forms[VconTypes.UUID] = vcon_uuid

      elif(vcon_type == VconTypes.OBJECT):
        self._vcon_forms[VconTypes.UUID] = new_vcon.uuid

      elif(vcon_type == VconTypes.DICT):
        self._vcon_forms[VconTypes.UUID] = new_vcon["uuid"]

      # String JSON, don't parse to get UUID, wait until we need to

  async def get_vcon(self, 
    vcon_type: VconTypes
    ) -> typing.Union[str, dict, vcon.Vcon, None]:

    # First check if we have it in the form we want
    got_vcon = self._vcon_forms.get(vcon_type, None)
    if(got_vcon is not None):
      return(got_vcon)

    # Clean out any Nones
    #logger.debug("keys: {}".format(self._vcon_forms.keys()))
    for form in self._vcon_forms:
      if(self._vcon_forms[form] is None):
        logger.debug("removing null: {}".format(form))
        del self._vcon_forms[form]
    #logger.debug("keys after cleanup: {}".format(self._vcon_forms.keys()))

    forms = list(self._vcon_forms.keys())
    if(len(forms) == 1 and forms[0] == VconTypes.UUID):
      # No choice have to hit the DB
      vcon_object = await py_vcon_server.db.VconStorage.get(self._vcon_forms[VconTypes.UUID])
      if(vcon_object is None):
        logger.warning("Unable to get Vcon for UUID: {} from storage".format(self._vcon_forms[VconTypes.UUID]))

      else:
        forms.append(VconTypes.OBJECT)
        self._vcon_forms[VconTypes.OBJECT] = vcon_object

      if(vcon_type == VconTypes.OBJECT):
        return(vcon_object)

    if(vcon_type == VconTypes.UUID):
      uuid = None
      if(VconTypes.OBJECT in forms):
        uuid = self._vcon_forms[VconTypes.OBJECT].uuid

      elif(VconTypes.DICT in forms):
        uuid = self._vcon_forms[VconTypes.DICT]["uuid"]

      elif(VconTypes.JSON in forms):
        # Have to parse the JSON string, build a Vcon
        vcon_object = None
        if(self._vcon_forms[VconTypes.JSON] is not None):
          vcon_object = vcon.Vcon()
          vcon_object.loads(self._vcon_forms[VconTypes.JSON])

        # Cache the object
        if(vcon_object is not None):
          self._vcon_forms[VconTypes.OBJECT] = vcon_object

        uuid = self._vcon_forms[VconTypes.OBJECT].uuid

      # Cache the UUID
      if(uuid is not None):
        self._vcon_forms[VconTypes.UUID] = uuid
      return(uuid)

    elif(vcon_type == VconTypes.OBJECT):
      vcon_object = None
      if(VconTypes.DICT in forms):
        vcon_object = vcon.Vcon()
        vcon_object.loadd(self._vcon_forms[VconTypes.DICT])

      elif(VconTypes.JSON in forms):
        vcon_object = None
        if(self._vcon_forms[VconTypes.JSON] is not None):
          vcon_object = vcon.Vcon()
          vcon_object.loads(self._vcon_forms[VconTypes.JSON])

      # Cache the object
      if(vcon_object is not None):
        self._vcon_forms[VconTypes.OBJECT] = vcon_object
  
      return(vcon_object)

    elif(vcon_type == VconTypes.DICT):
      vcon_dict = None
      if(VconTypes.OBJECT in forms):
        vcon_dict = self._vcon_forms[VconTypes.OBJECT].dumpd()

      elif(VconTypes.JSON in forms):
        vcon_dict = None
        vcon_object = None
        vcon_json = self._vcon_forms[VconTypes.JSON]
        if(vcon_json is not None):
          vcon_object = vcon.Vcon()
          vcon_object.loads(vcon_json)

        # Cache the object
        if(vcon_object is not None):
          self._vcon_forms[VconTypes.OBJECT] = vcon_object

          vcon_dict = vcon_object.dumpd()

      # Cache the dict
      if(vcon_dict is not None):
        self._vcon_forms[VconTypes.DICT] = vcon_dict

      return(vcon_dict)

    elif(vcon_type == VconTypes.JSON):
      vcon_json = None
      if(VconTypes.OBJECT in forms and self._vcon_forms[VconTypes.OBJECT] is not None):
        vcon_json = self._vcon_forms[VconTypes.OBJECT].dumps()

      elif(VconTypes.DICT in forms):
        vcon_object = None
        vcon_dict = self._vcon_forms[VconTypes.DICT]
        if(vcon_dict is not None):
          vcon_object = vcon.Vcon()
          vcon_object.loadd(vcon_dict)

        # Cache the object
        if(vcon_object is not None):
          self._vcon_forms[VconTypes.OBJECT] = vcon_object

        vcon_json = vcon_object.dumps()

      # Cache the JSON
      if(vcon_json is not None):
        self._vcon_forms[VconTypes.JSON] = vcon_json

      return(vcon_json)

    else:
      return(None)


  @staticmethod
  def get_vcon_type(a_vcon: typing.Union[str, dict, vcon.Vcon]):
    if(isinstance(a_vcon, str)):
      # Determine if its a UUID or a JSON string
      if("{" in a_vcon):
        vcon_type = VconTypes.JSON
      else:
        # Assume its a UUID
        vcon_type = VconTypes.UUID

    elif(isinstance(a_vcon, dict)):
        vcon_type = VconTypes.DICT

    elif(isinstance(a_vcon, vcon.Vcon)):
        vcon_type = VconTypes.OBJECT

    else:
        vcon_type = VconTypes.UNKNOWN

    return(vcon_type)

class PipelineIO():
  """ Abstract input for a pipeline processor """
  def __init__(self):
    self._vcons = []

  def get_vcon(self,
    index: int = 0,
    vcon_type: VconTypes = VconTypes.OBJECT
    ) -> typing.Union[str, dict, vcon.Vcon, None]:
    """ Get the indicated Vcon in the form indicated by vcon_type """

    return(self._vcons[index].get_vcon(vcon_type))

  def update_vcon(self,
    modified_vcon: typing.Union[str, dict, vcon.Vcon],
    index: int = 0) -> None:
    """
    Update the indecated Vcon in this PipelineIO object, does NOT update stored Vcon.
    The update of the Vcon occurs at the end of the pipeline if the Vcon was updated.
    """

    raise Exception("Not iplemented")

class PipelineProcessor():
  def __init__(self):
    raise Exception("Not iplemented")

  async def process(self, process_input: PipelineIO):
    raise Exception("Not iplemented")

