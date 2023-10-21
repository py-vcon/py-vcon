""" Abstract VconProcessor and registry """

import enum
import typing
import time
import datetime
import asyncio
import importlib
import pydantic
import py_vcon_server.db
import py_vcon_server.logging_utils
import vcon

logger = py_vcon_server.logging_utils.init_logger(__name__)


class VconNotFound(Exception):
  """ Exceptions in accessing or retrieving **Vcon**s """


class InvalidInitClass(Exception):
  """ Rasied if VconProcessorInitOptions is an invalid class """

class InvalidOptionsClass(Exception):
  """ Rasied if VconProcessorOptions is an invalid class """

class MayModifyPolicyNotSet(Exception):
  """
  Raised if the VconProcssor derived class has not set the policy
  as whether it may modify a Vcon in the **VconProcessorIO**
  when it's **processor method is invoked.
  """

class VconProcessorNotRegistered(Exception):
  """
  Raised when requesting VconProcessor instance that
  has not been registered.
  """


class VconProcessorNotInstantiated(Exception):
  """
  Rasied when a registered **VconProcessor** has failed
  to be instantiated due to failures in module loading,
  finding the class or initialization of the instance.
  """

class InvalidVconProcessorClass(Exception):
  """ Attempt to use invalide class as a VconProcessor """


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

  def update_vcon(self,
    new_vcon: typing.Union[str, vcon.Vcon],
    vcon_uuid: typing.Union[str, None] = None,
    vcon_json: typing.Union[str, None] = None,
    vcon_dict: typing.Union[dict, None] = None,
    vcon_object: vcon.Vcon = None
    ) -> None:

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
    for form in list(self._vcon_forms):
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

    if(vcon_type == VconTypes.OBJECT):
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

    if(vcon_type == VconTypes.DICT):
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

    if(vcon_type == VconTypes.JSON):
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

    return(None)


  @staticmethod
  def get_vcon_type(a_vcon: typing.Union[str, dict, vcon.Vcon]):
    """
    Determine the form of the given **Vcon** 

    Returns: enum of **VconTypes**
    """

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


class VconPartiesObject(pydantic.BaseModel, extra=pydantic.Extra.allow):
  tel: str = pydantic.Field(
    title = "tel URI",
    description = "a telephone number",
    example = "+1 123 456 7890"
    )


date_examples = [ int(time.time()),
  time.time(),
  "Wed, 14 May 2022 18:16:19 -0000",
  vcon.utils.cannonize_date(time.time()),
  "2022-05-14T18:16:19.000+00:00"
  ]


# TODO: use the following to avoid getting arrays or parameters set to None???
# bar.dict(exclude_unset=True)
class VconObject(pydantic.BaseModel, extra=pydantic.Extra.allow):
  vcon: str = pydantic.Field(
    title = "vCon format version",
    #description = "vCon format version,
    default = vcon.Vcon.CURRENT_VCON_VERSION
    )
  uuid: str
  created_at: typing.Union[pydantic.PositiveInt, pydantic.PositiveFloat, str, datetime.datetime] = pydantic.Field(
    title = "vCon format version",
    #description = "vCon format version,
    default_factory=lambda: vcon.utils.cannonize_date(time.time()),
    example = date_examples[3],
    examples = date_examples
    )
  # subject: str = None
  # redacted: typing.Optional[typing.Union[typing.List[dict], None]] = None
  # appended: typing.Optional[typing.Union[typing.List[dict], None]] = None
  # group: typing.Optional[typing.Union[typing.List[dict], None]] = None
  parties: typing.Optional[typing.Union[typing.List[VconPartiesObject], None]] = None
  dialog: typing.Optional[typing.Union[typing.List[dict], None]] = None
  analysis: typing.Optional[typing.Union[typing.List[dict], None]] = None
  attachments: typing.Optional[typing.Union[typing.List[dict], None]] = None


class VconProcessorInitOptions(pydantic.BaseModel):
  """
  Base class to options passed to initalize a **VconProcessor**
  derived class in the **VconProcessorRegistry**
  """


class VconProcessorOptions(pydantic.BaseModel, extra = pydantic.Extra.allow):
  """ Base class options for **VconProcessor.processor** method """
  input_vcon_index: int = pydantic.Field(
    title = "VconProcessorIO input vCon index",
    description = "Index to which vCon in the VconProcessorIO is to be used for input",
    default = 0
    )
  #rename_output: dict[str, str]

class VconProcessorOutput(pydantic.BaseModel, extra=pydantic.Extra.allow):
  """ Serializable Output results from a VconProcessor """
  vcons: typing.List[VconObject] = pydantic.Field(
    title = "array of **Vcon** objects",
    default = []
    )
  vcons_modified: typing.List[bool] = pydantic.Field(
    title = "boolean indicated if the **Vcon** in the **vcons** array has been modified from the input version",
    default = []
    )


class VconProcessorIO():
  """ Abstract input and output for a VconProcessor """
  def __init__(self):
    self._vcons = []
    self._vcon_locks = []
    self._vcon_update = []

  def is_vcon_modified(self,
    index: int = 0
    ) -> bool:
    """
    Get modified state of **Vcon** at given **index**.

    Returns: tru/false if the **Vcon** at index is marked
      as modified, meaning needing to be committed.
    """

    if(index >= len(self._vcons)):
      raise Exception("Invalid index to Vcon")

    return(self._vcon_update[index])


  def num_vcons(self) -> int:
    """ Return the number of **Vcons** in this **VconProcessorIO** object """
    return(len(self._vcons))


  async def get_vcon(self,
    index: int = 0,
    vcon_type: VconTypes = VconTypes.OBJECT
    ) -> typing.Union[str, dict, vcon.Vcon, None]:
    """ Get the Vcon at index in the form indicated by vcon_type """

    if(index >= len(self._vcons)):
      raise VconNotFound("index: {} is behond the end of the Vcon array of length: {}".format(
        index,
        len(self._vcons)))

    vCon = await self._vcons[index].get_vcon(vcon_type)
    if(vCon is None):
      raise VconNotFound("Vcon type: {} at index: {} in Vcon array of length: {} not found".format(
        vcon_type,
        index,
        len(self._vcons)))

    return(vCon)


  async def add_vcon(self,
    vcon_to_add: typing.Union[str, dict, vcon.Vcon],
    lock_key: typing.Union[str, None] = None,
    readonly: bool = True
    ) -> int:
    """
    Add the given Vcon to this **VconProcessorIO** object.
    It will NOT add the Vcon to storage as the time this 
    method is invoked.

    If the lock_key is provied, the vCon will be updated in
    VconStorage at the end of the pipeline processing,
    only if the vCon is modified via the update_vcon
    method.

    If no lock_key is provided AND the readonly == False,
    the Vcon will be added to VconStorage after all of the 
    pipeline processing has occurred.  If a vCon with the 
    same UUID exist in the VconStorage, prior to the
    VconStorage add, the VconStorage add will result in an
    error.

    returns: index of the added vCon
    """

    # Storage actions after pipeline processing
    #
    #      | Readonly
    # Lock |    T | F
    # ---------------------------------------------
    #    T |  N/A | Persist if modfied AFTER add
    #    F |  NOP | Persist, this is new to storage
    #
    # N/A - not allowed
    # NOP - no operation/storage

    mVcon = MultifariousVcon()
    mVcon.update_vcon(vcon_to_add)
    if(lock_key == ""):
      lock_key = None
    if(lock_key is not None and readonly):
      raise Exception("Should not lock readonly vCon")

    # Make sure no vCon with same UUID
    new_uuid = await mVcon.get_vcon(VconTypes.UUID)
    for index, vCon in enumerate(self._vcons):
      exists_uuid = await vCon.get_vcon(VconTypes.UUID)
      if(exists_uuid == new_uuid):
        raise Exception("Cannot add duplicate vCon to VconProcessorIO, same uuid: {} at index: {}",
          new_uuid, index)

    self._vcons.append(mVcon)
    self._vcon_locks.append(lock_key)
    self._vcon_update.append(not readonly and lock_key is None)

    return(len(self._vcons) - 1)


  async def update_vcon(self,
    modified_vcon: typing.Union[str, dict, vcon.Vcon],
    ) -> int:
    """
    Update an existing vCon in the VconProcessorIO object.
    Does not update the Vcon in storage.
    The update of the stored Vcon occurs at the end of the pipeline if the Vcon was updated.

    Returns: index of updated vCon or None
    """

    mVcon = MultifariousVcon()
    mVcon.update_vcon(modified_vcon)

    uuid = await mVcon.get_vcon(VconTypes.UUID)

    for index, vCon in enumerate(self._vcons):
      if(await vCon.get_vcon(VconTypes.UUID) == uuid):
        # If there is no lock and this vCon is not marked for update, its readonly
        if(self._vcon_locks[index] is None and not self._vcon_update[index]):
          raise Exception("vCon {} index: {} has no write lock".format(
            uuid,
            index))

        self._vcons[index] = mVcon
        self._vcon_update[index] = True
        return(index)

    raise Exception("vCon {} not found in VconProcessorIO".format(uuid))

  def set_paramenter(self, name: str, value, rename: typing.Dict[str, str]) -> None:
    """
    set and output parameter value, applying the rename to the given name.
    """
    raise Exception("not implemented")


  async def get_output(self) -> VconProcessorOutput:
    """ Get **VconProcessorOutput** serializable output form of **VconProcessorIO** """
    out_vcons = []
    for mVcon in self._vcons:
      out_vcons.append(await mVcon.get_vcon(VconTypes.DICT))

    response_output = VconProcessorOutput(
      vcons = out_vcons,
      vcons_modified = self._vcon_update
      )

    return(response_output)

class VconProcessor():
  """
  Abstract base class to all vCon processors.

  A vCon Processor generally takes zero or more Vcons as input
  and produces some sort of output which may include:

    * A modification of one or more of the input vCons
    * The creation of one or more new Vcons
    * An extraction of data from the input
    * Emmition of a report (e.g. via email or slack)

  **VconProcessor**s may be sequenced together (1 or more)
  in a **Pipeline**.  A **VconProcessorIO** object is provided as
  input to the first **VconProcessor** which outputs a
  **VconProcessorIO** that become the input to the next **VconProcessor**
  in the **Pipeline** and so on.

  The **VconProcessor** contains the method **process** which performs
  the work.  It takes a **VconProcessorIO** object as input which contains
  the zero or vCon.  The ** process** method also takes a
  **VconProcessorOptions** object which is where additional input 
  parameters are provided as defined by the **VconProcessor**.  The
  **processor** method always provides output in the return in
  the form of a **VconProcessorIO** object.  Typically this is the same
  PipelilneIO that was input with some or no modification.  If
  the input **VconProcessorIO** is not provided as ouput (if the
  **VconProcessorIO** was modified by prior **VconProcessor**s in
  the **Pipeline**) any created or modified vCons from the input
  will be lost and not saved to the **VconStorage** database.  Care
  should be made that this is intensional.

  A concrete **VconProcessor** derives from **VconProcessor** and implements
  the abstract methods.  If it requires or has optional additional
  input parameters, it defines a subclass of the **VconProcessorOptions**
  class.  The derived **VconProcessorOptions** class for the derived
  **VconProcessor** serves to document the additional input parameters
  and helps to validate the input.

  A well behaved VconProcessor does not modify the VconStorage
  database at all.  Vcons are modified in the **VconProcessorIO** input
  and pass on as output.  It is up to the invoker of the **process**
  method to decide when to commit the changed to the **VconStorage** database.
  For example after all **VconProcessors** in a **Pipeline** sequence
  have been processed.  The **VconProcessorIO** keeps track of **Vcon**s
  that have been changed to ease the decision of what needs to be commited.

  A **VconProcessor** is typically dynamically loaded at startup and gets
  registered in the **VconProcessorRegistry**.  A when a concrete 
  **VconProcessor* is registered, it is loaded from a given package,
  given a unique name and instantiated from the given class name from
  that package.  The allow serveral instances of a concrete 
  **VconProcessor** to be instantiated, each with a unique name and
  different set of initialization options.  The class MUST also
  implement a static parameter: **initialization_options_class**.
  The **initialization_options_class** value MUST be the derived
  class of **VconProcessorInitializationOptions** that is used to
  validate the options provided to the concrete **VconProcessor**
  __init__ method.
  """

  def __init__(self,
    title: str,
    description: str,
    version: str,
    init_options: VconProcessorInitOptions,
    processor_options_class: typing.Type[VconProcessorOptions],
    may_modify_vcons: bool
    # TODO how do we define output parameters???
    ):
    """
    Initialization method used to construct a **VconProcessor**
    instance for the **VconProcessorRegistry**.

    Parms:
      init_options: VconProcessorInitOptions - options used to
        initialize this instance
      title: str - title or short description of what this
        registered instance of VconProcessor will do in the
        process method.  Should be specific to the options provided.
      description: str - long description of what this instance does
      version: str - version of this class derived from
        **VconProcessor**
      processor_options_class: typing.Type[VconProcessorOptions] -
        The class type of the options input to the **processor** method
        derived from the **VconProcessorOptions**.
      may_modify_vcons: bool - policy of whether this derived **VconProcessor**'s
        **processor* method may modify any of the **Vcon**s in the
        **VconProcessorIO**.
    """

    logger.debug("VconProcessor({}).__init__".format(init_options))
    if(init_options is not None and not isinstance(init_options, VconProcessorInitOptions)):
      raise InvalidInitClass("init_options type: {} for {} must be drived from: VconProcessorInitOptions".format(
        init_options.__class__.__name__,
        self.__class__.__name__,
        ))

    if(processor_options_class is None or
      not issubclass(processor_options_class, VconProcessorOptions)):
      raise InvalidOptionsClass("processor_options_class type: {} for {} must be drived from: VconProcessorOptions".format(
        processor_options_class.__class__.__name__,
        self.__class__.__name__,
        ))

    if(may_modify_vcons is None):
      raise MayModifyPolicyNotSet("processor method may modify Vcons policy not set for: {}".format(
        self.__class__.__name__
        ))

    if(title is None or title == ""):
      self._title = self.__class__.__name__
    else:
      self._title = title

    if(description is None or description == ""):
      self._description = self.__class__.__doc__
    else:
      self._description = description

    self._version = version
    self._processor_options_class = processor_options_class
    self._may_modify_vcons = may_modify_vcons


  async def process(
    self,
    processor_input: VconProcessorIO,
    options: VconProcessorInitOptions
    ) -> VconProcessorIO:
    """
    Abstract method for processing a **Vcon**.  Must
    be implemented in derived classes.
    """
    raise InvalidVconProcessorClass("{}.process method NOT implemented".format(self.__class__.__name__))

  def version(self) -> str:
    """
    Get the module version of the derived **VconProcessor**.
    """
    if(self._version is None or self._version == ""):
      raise Exception("{}._version NOT set".format(self.__class__.__name__))

    return(self._version)


  def title(self):
    """
    Get the short description or title for the derived **VconProcessor**.
    """
    return(self._title)

  def description(self):
    """
    Get the long description for the derived **VconProcessor**.
    """
    return(self._description)

  def may_modify_vcons(self) -> bool:
    """
    Returns whether the derived **VconProcessor** may
    modify any of the input **Vcon**s.
    """
    if(self._may_modify_vcons is None):
      raise MayModifyPolicyNotSet("processor may modify input vcons policy not set for class: {}".format(
        self.__class__.__name__))

    return(self._may_modify_vcons)


  def processor_options_class(self):
    """
    Returns the class type of the expected options
    argument to the derived **VconProcessor.process** method.
    """
    return(self._processor_options_class)


  def __del__(self):
    """ Teardown/uninitialization method for the VconProcessor """
    logger.debug("deleting {}".format(self.__class__.__name__))


# dict of names and VconProcessor registered
VCON_PROCESSOR_REGISTRY = {}


class VconProcessorRegistry:
  """
  Static class to manage registry of VconProcessors.
  """

  class VconProcessorRegistration:
    def __init__(self,
      init_options: VconProcessorInitOptions,
      name: str,
      module_name: str,
      class_name: str,
      title: typing.Union[str, None] = None,
      description: typing.Union[str, None] = None
      ):
      """
      Instantiate **VconProcessor** with instance specific
      initialization options and label it with options
      specific title and description and register the instance.
      """
      self._name = name
      self._module_name = module_name
      self._class_name = class_name
      self._module = None
      self._module_load_attempted = False
      self._module_not_found = False
      self._processor_instance = None

      logger.debug("Loading module: {} for VconProcessor: {}".format(
        self._module_name,
        self._name
        ))
      # load module
      if(self.load_module()):

        # instantiate **VconProcessor** with initialization options
        try:
          class_ = getattr(self._module, self._class_name)
          if(not issubclass(class_, VconProcessor)):
            raise InvalidVconProcessorClass("processor: {} class: {} must be derived from VconProcessor".format(
              self._name,
              self._class_name
              ))
          if(class_ == VconProcessor):
            raise InvalidVconProcessorClass(
              "abstract class VconProcessor cannot be used directly for {}, must implement a derived class".format(
              self._class_name
              ))

          try:
            self._processor_instance = class_(init_options)

            if(self._processor_instance.title() is None or
              self._processor_instance.title() == ""):
              logger.warning("class instance of {} does not provide title".format(self._class_name))
            if(self._processor_instance.description() is None or
              self._processor_instance.description() == ""):
              logger.warning("class instance of {} does not provide description".format(self._class_name))


          except TypeError as e:
            logger.exception(e)
            raise InvalidVconProcessorClass(
              "{}.__init__ should take exactly one argument of type VconProcessorInitOptions".format(
              self._class_name
              )) from e

        except AttributeError as ae:
          raise ae

        # Override the default title and description if a
        # init options specific version was provided
        if(title is not None and title != ""):
          self._processor_instance._title = title

        if(description is not None and description != ""):
          self._processor_instance._description = description


    def load_module(self) -> bool:
      """ Load the registered module name for this **VconProcessor** """
      loaded = False
      if(not self._module_load_attempted):
        try:
          logger.info("importing: {} for registering VconProcessor: {}".format(
            self._module_name,
            self._name))
          self._module = importlib.import_module(self._module_name)
          self._module_load_attempted = True
          self._module_not_found = False
          loaded = True

        except ModuleNotFoundError as mod_error:
          logger.warning("Error loading module: {} for VconProcessor: {}".format(
            self._module_name,
            self._name
            ))
          logger.exception(mod_error)
          self._module_not_found = True

      return(loaded)


  @staticmethod
  def register(
    init_options: VconProcessorInitOptions,
    name: str,
    module_name: str,
    class_name: str,
    title: typing.Union[str, None] = None,
    description: typing.Union[str, None] = None
    ):

    logger.debug("Registering VconProcessor: {}".format(name))
    processor_registration = VconProcessorRegistry.VconProcessorRegistration(
      init_options,
      name,
      module_name,
      class_name,
      title,
      description,
      )

    VCON_PROCESSOR_REGISTRY[name] = processor_registration
    logger.info("Registered VconProcessor: {}".format(name))

  @staticmethod
  def get_processor_names(successfully_loaded: bool = True) -> typing.List[str]:
    """
    Get the list of names for all of the registered VconProcessors.

    params:
      successfully_loaded: bool - True indicated to filter names to
        only **VconProcessors** which have been successfuly loaded
        and instantiated.  False indicates no filtering of names.
    """

    names = list(VCON_PROCESSOR_REGISTRY.keys())

    if(successfully_loaded):
      filtered_names = []
      for name in names:
        if(not VCON_PROCESSOR_REGISTRY[name]._module_not_found and
          VCON_PROCESSOR_REGISTRY[name]._processor_instance is not None):
          filtered_names.append(name)

      names = filtered_names

    return(names)

  @staticmethod
  def get_processor_instance(name: str) -> VconProcessor:
    """
    Get the registered **VconProcessor** for the given name.
    """
    # get VconProcessorRegistration for given name
    registration = VCON_PROCESSOR_REGISTRY.get(name, None)

    if(registration is None):
      raise VconProcessorNotRegistered("VconProcessor not registered under the name: {}".format(name))

    if(registration._processor_instance is None):
      if(registration._module_load_attempted == False):
        raise VconProcessorNotInstantiated("VconProcessor {} not instantiated, load not attemtped".format(name))

      if(registration._module_not_found == True):
        raise VconProcessorNotInstantiated("VconProcessor {} not instantiated, module: {} not found".format(
          name,
          registration._module_name
          ))

      raise VconProcessorNotInstantiated("VconProcessor not instantiated for name: {}".format(name))

    return(registration._processor_instance)

