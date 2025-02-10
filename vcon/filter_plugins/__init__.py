# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" Vcon module providing frameword for filter plugins which take a Von in and provide a Vcon output """
from __future__ import annotations
import importlib
import os
import copy
import sys
import typing
import traceback
import operator
import logging
import pydantic
import pythonjsonlogger.jsonlogger
import vcon.pydantic_utils


# This package is dependent upon the vcon package only for typing purposes.
# This creates a circular dependency which we avoid by importing annotations
# above and importing vcon only if typing.TYPE_CHECKING
if typing.TYPE_CHECKING:
  from vcon import Vcon

# This is cloned from vcon package as we cannot import vcon here due to
# cyclical import.
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


class FilterPluginModuleNotFound(Exception):
  """ Thrown when plugin modeule fails to load """

class FilterPluginClassNotFound(Exception):
  """ Thrown when plugin class is not found in plugin module """

class FilterPluginNotImplemented(Exception):
  """ Thrown when plugin modeule and class are found, but methods are not implemented on filter"""

class FilterPluginNotRegistered(Exception):
  """ Thrown when plugin is not found in the FilterPluginRegistry """

class FilterPluginAlreadyRegistered(Exception):
  """ Thrown when plugin already exists in the FilterPluginRegistry """


class FilterPluginInitOptions(pydantic.BaseModel, **vcon.pydantic_utils.SET_ALLOW):
  """ base class for **FilterPlugin** initialization options """

  def __init_subclass__(cls, field_defaults = {}, **kwargs):
    """
    Helper to change field defaults in subclasses

    Parameters:
      field_defaults (dict[str, Any]) - field name string and new default value for that field
    """
    super().__init_subclass__(**kwargs)
    for field_name, new_default in field_defaults.items():
      cls.__fields__[field_name].default = new_default


class FilterPluginOptions(pydantic.BaseModel, **vcon.pydantic_utils.SET_ALLOW):
  """ base class for **FilterPlugin.filter** method options """

  def __init_subclass__(cls, field_defaults = {}, **kwargs):
    """
    Helper to change field defaults in subclasses

    Parameters:
      field_defaults (dict[str, Any]) - field name string and new default value for that field
    """
    super().__init_subclass__(**kwargs)
    for field_name, new_default in field_defaults.items():
      vcon.pydantic_utils.set_field_default(cls, field_name, new_default)


class TranscribeOptions(FilterPluginOptions):
  """ base class for all **FilterPlugins** that provide audio transcription """
  language: str = pydantic.Field(
    title = "transcription language",
    default = "en"
    )

  input_dialogs: typing.Union[str,typing.List[int]] = pydantic.Field(
    title = "input **Vcon** recording **dialog** objects",
    description = """
Indicates which recording **dialog** objects in the given **Vcon** are
to be transcribed.

 * **""** (empty str or None) - all recording **dialogs** are to be transcribed.  This is the equivalent of providing "0:".
 * **n:m** (str) - **dialog** objects having indices **n-m** are to be transcribed.
 * **n:m:i** (str) - **dialog** objects having indices **n-m** using interval **i** are to be transcribed.
 * **[]** (empty list[int]) - none of the **dialog** objects are to be transcribed.
 * **[1, 4, 5, 9]** (list[int]) - the **dialog** objects having the indices in the given list are to be transcribed.

**dialog** objects in the given sequence or list which are not **recording** type dialogs are ignored.
""",
    default = "",
    examples = ["", "0:", "0:-2", "2:5", "0:6:2", [], [1, 4, 5, 9]]
    )


class FilterPlugin():
  """
  Base class for plugins to operate on a vcon.

  **FilterPlugin** take a **Vcon** and some options as
  input and output a **Vcon** which may be the input **Vcon**
  modified.

  A **FilterPlugin** as three primary operations:

   * Initialization (**__init__**) which is invoked with a
        derived class specific set of initialization 
        options (derived from **FilterPluginInitOptions**(

   * filtering (**filter**) which is the actual method 
        that operates on a **Vcon**.

   * teardown (**__del__**) which performs any shutdown or
        release of resources for the plugin.

  Initialization and teardown are only performed once.


  **FilterPlugins** is an abstract class.  One must
  implement a derived class to use it.  The derived class
  must implement the following:

   * **__init__** method SHOULD invoke super().__init__

   * **filter** method to performe the actual **Vcon** operation

   * **init_options_type** MUST be defined and set to a
        derived class of **FilterPluginInitOptions** which
        is the type of the only argument to the derived
        class's **__init__** method.

  To be used the derived class and a specific set of 
  initialization options must be registered using
  **FilterPluginRegistry.register**.  A **FilterPlugin**
  is dynamically loaded only the first time that it
  is actually used. It stays loaded until the system
  exits.
  """
  def __init__(self,
    options: FilterPluginInitOptions,
    options_type: typing.Type[FilterPluginOptions]
    ):
    """
    Instance stores the initialization options that were used.

    Instance also stores the **FilterPluginOptions** type/class
    that is used by the derived class's **filter** method.
    This is used to enforce typing and defaults for the
    options passed into the **filter** method.
    """

    if(not hasattr(self, "init_options_type")):
      raise FilterPluginNotImplemented(
        "derived class: {} has not set static attribute: init_options_type.  Value must be the type class derived from FilterPluginInitOptions.".format(
        self.__class__.__name__
        ))

    if(not issubclass(self.init_options_type, FilterPluginInitOptions)):
      raise FilterPluginNotImplemented(
        "derived class: {} static attribute: init_options_type value must be derived from FilterPluginInitOptions.  Got: {}".format(
        self.__class__.__name__,
        self.init_options_type
        ))

    if(not issubclass(options_type, FilterPluginOptions)):
      raise FilterPluginNotImplemented(
        "options_type value must be derived from FilterPluginOptions".format(
        self.__class__.__name__
        ))

    self._init_options = copy.deepcopy(options)
    self.options_type = options_type


  def init_options(self) -> FilterPluginInitOptions:
    """ Get the initialization options used for this plugin """
    return(self._init_options)


  async def filter(
    self,
    in_vcon: Vcon,
    options: FilterPluginOptions
    ) -> Vcon:
    """
    Abstract method which performs an operation on an input Vcon and 
    provides the modified Vcon as output.

    Parameters:
      in_vcon (vcon.Vcon) - input Vcon upon which an operation is to be performed by the plugin.
      options (FilterPluginOptions) - derived options specific to the filter method/opearation

    Returns:
      vcon.Vcon - the modified Vcon
    """
    raise FilterPluginNotImplemented("{}.filter not implemented".format(type(self)))


  def check_valid_state(
      self,
      filter_vcon: Vcon
    ) -> None:
    """
    Check to see that the vCon is in a valid state for the filter plugin to operate on.

    By default, this validates that the vcon is unsigned and is writeable.
    """

    filter_vcon._attempting_modify()


  def __del__(self):
    """
    Teardown/uninitialization method for the plugin

    Parameters: None
    """
    logger.debug("deleting {}".format(self.__class__))


  @staticmethod
  def get_party_label(
    in_vcon: vcon.Vcon,
    party_index: typing.Union[int, typing.List[int]],
    allow_missing_parties = False
    ) -> str:
    """ Get a label for the indicated party in the given vcon """
    if(isinstance(party_index, list)):
      parties = []
      for index in party_index:
        parties.append(FilterPlugin.get_party_label(in_vcon, index, allow_missing_parties))

      return(", ".join(parties))

    if(party_index is None or
      party_index < 0
      ):
      return("unknown")

    if(party_index >= len(in_vcon.parties)):
      if(allow_missing_parties):
        return("party[{}]".format(party_index))

      raise AttributeError("party_index: {} greater than number of parties: {}".format(
        party_index,
        len(in_vcon.parties)
        ))

    label_priority = ["name", "tel"]
    label = None
    for param_name in label_priority:
      if(param_name in in_vcon.parties[party_index]):
        label = in_vcon.parties[party_index][param_name]

    if(label is None):
      label = "party[{}]".format(party_index)

    return(label)


  @staticmethod
  def slice_indices(slice_spec: typing.Union[str, typing.List[int]],
    list_length: int,
    option_name: str
    ) -> typing.List[int]:
    """ 
    Get a list of indices for the given slice spec which may be of the form:
    (e.g. "n:m:i") to indicate elements of array to use or may be a list of int.

    Returns:
     list[int] containing indices for the slice
    """

    if(list_length == 0):
      return([])

    # Specified as a slice e.g. "n", "n:", "n:m" or "n:m:i"
    if(isinstance(slice_spec, str)):
      if(slice_spec is None or
        slice_spec == "" or
        slice_spec == ":" or
        slice_spec == "0:"
        ):
        start = 0
        end = None
        incr = None

      # No colon, must be a single int
      elif(slice_spec.find(":") == -1):
        start = int(slice_spec)
        end = start + 1
        incr = None

      else:
        slice_operands = slice_spec.split(":")
        if(len(slice_operands) > 3):
          raise AttributeError("{} string should contain 0-2 colon (':') {}".format(
            option_name,
            slice_spec
            ))

        if(len(slice_operands) == 0):
          assert(0)  # should not get here, should have been handled above

        if(len(slice_operands) >= 1):
          if(slice_operands[0] == ""):
            start = 0
          else:
            start = int(slice_operands[0])

        if(len(slice_operands) >= 2):
          if(slice_operands[1] == ""):
            end = None
          else:
            end = int(slice_operands[1])
        else:
          end = None

        if(len(slice_operands) == 3):
          if(slice_operands[2] == ""):
            incr = None
          else:
            incr = int(slice_operands[2])
        else:
          incr = None

      sliced_list = list(operator.getitem(list(range(list_length)), slice(start, end, incr)))
      logger.debug("{} given: {}  slicing using [{}:{}:{}] resulting in {} of {} items".format(
        option_name,
        slice_spec,
        start,
        end,
        incr,
        len(sliced_list),
        list_length
        ))

    # Specified as a list of indices to the dialog
    elif(isinstance(slice_spec, list)):
      sliced_list = slice_spec
      logger.debug("{} slicing using indices: {} resulting in {} of {} items".format(
        option_name,
        slice_spec,
        len(sliced_list),
        list_length
        ))

    else:
      raise AttributeError("{} should be string or list of integers: {}".format(
        option_name,
        slice_spec
        ))

    return(sliced_list)


class FilterPluginRegistration:
  """ Class containing info and helper methods on the registration for a single named plugin filter """
  def __init__(
    self,
    name: str,
    module_name: str,
    class_name: str,
    description: str,
    init_options: typing.Union[FilterPluginInitOptions, typing.Dict[str, typing.Any]]
    ):
    self.name = name
    self._module_name = module_name
    self._module_load_attempted = False
    self._module_not_found = False
    self._class_not_found = False
    self._class_name = class_name
    self.description = description
    self._init_options = init_options
    self._plugin : typing.Union[FilterPlugin, None] = None

  def import_plugin(
    self,
    init_options: typing.Union[FilterPluginInitOptions, typing.Dict[str, typing.Any]]
    ) -> bool:
    """
    Import the package which contains the implementation for the filter
    plugin and instantiate the plugin class.

    filter plugins are registered and later if used, they are imported.
    When registered, a filter plugin has a name, an implementation module,
    and a class which gets instantiated upon import of the package.

    Parameters:
      init_options - initialization options input to the plugin class constructor

    Returns:
      True/False if the plugin module imported successfully and the
        class was instantiated.
    """
    succeed = False
    if(not self._module_load_attempted):
      try:
        logger.info("importing: {} for registered filter plugin: {}".format(self._module_name, self.name))
        module = importlib.import_module(self._module_name)
        self._module_load_attempted = True
        self._module_not_found = False

        try:
          class_ = getattr(module, self._class_name)
          if(isinstance(init_options, dict)):
            # convert to proper init options type if a generic dict
            if(not hasattr(class_, "init_options_type")):
              raise FilterPluginNotImplemented(
                "filter plugin class: {} in module: {} has not set init_options_type.  It should be the type/class derived form FiterPluginInitOptions".format(
                self._class_name,
                self._module_name
                ))

            # Hide keys from logging
            init_options_hidden = init_options.copy()
            for name in init_options_hidden.keys():
              # assume field names that end in _key needs to be hidden
              if(name[-4:] == "_key" and init_options_hidden[name] != ""):
                # obscure keys
                init_options_hidden[name] = "********"
                # logger.debug("hiding value for: {}".format(name))

            logger.debug("creating init_options type: {} using: dict: {} for plugin: {}".format(
              class_.init_options_type,
              init_options_hidden,
              self.name
              ))
            init_options = class_.init_options_type(**init_options)
            # TODO raise "filter_plugin class: {} has not set static attribute: init_options_type.  Should be a class Deribed from FilterPluginInitOptions".format(self._class_name)
          self._plugin = class_(init_options)
          self._class_not_found = False
          succeed = True

        except AttributeError as ae:
          logger.warning(ae)
          self._class_not_found = True

      except ModuleNotFoundError as mod_error:
        logger.warning(mod_error)
        logger.warning(traceback.format_exc(limit=-1))
        self._module_not_found = True

    elif(self._plugin is not None):
      succeed = True

    return(succeed)

  def plugin(
    self,
    init_options: typing.Union[FilterPluginInitOptions, None] = None
    ) -> typing.Union[FilterPlugin, None]:
    """ Return the plugin filter class for this registration """
    if(not self._module_load_attempted):
      if(init_options is None):
        init_options = self._init_options
      self.import_plugin(init_options)

    return(self._plugin)


  def options_type(self, *args, **kwargs) -> FilterPluginOptions:
    plugin = self.plugin()

    if(self._module_not_found is True):
      message = "plugin: {} not loaded as module: {} was not found".format(self.name, self._module_name)
      raise FilterPluginModuleNotFound(message)

    if(self._class_not_found is True):
      message = "plugin: {} not loaded as class: {} not found in module: {}".format(self.name, self._class_name, self._module_name)
      raise FilterPluginClassNotFound(message)

    if(plugin is None):
      logger.debug("plugin: {} from class: {} module: {} load failed".format(self.name, self._class_name, self._module_name))
      raise Exception("plugin: {} from class: {} module: {} load failed".format(self.name, self._class_name, self._module_name))

    return(plugin.options_type(*args, **kwargs))


  async def filter(
    self,
    in_vcon : vcon.Vcon,
    options: FilterPluginOptions
    ) -> vcon.Vcon:
    if(not self._module_load_attempted):
      self.import_plugin(self._init_options)

    if(self._module_not_found is True):
      message = "plugin: {} not loaded as module: {} was not found".format(self.name, self._module_name)
      raise FilterPluginModuleNotFound(message)

    if(self._class_not_found is True):
      message = "plugin: {} not loaded as class: {} not found in module: {}".format(self.name, self._class_name, self._module_name)
      raise FilterPluginClassNotFound(message)

    plugin = self.plugin(self._init_options)
    if(plugin is None):
      logger.debug("plugin: {} from class: {} module: {} load failed".format(self.name, self._class_name, self._module_name))
      raise Exception("plugin: {} from class: {} module: {} load failed".format(self.name, self._class_name, self._module_name))

    if(isinstance(options, dict)):
      options = plugin.options_type(**options)

    if(not isinstance(options, FilterPluginOptions)):
      raise FilterPluginNotImplemented(
        "plugin: {} class: {} method: filter should take an instance of class derived from FilterPluginOptions, got: {}".format(
        self.name,
        self._class_name,
        type(options)
        ))

    return(await plugin.filter(in_vcon, options))

class FilterPluginRegistry:
  """ class/scope for Vcon filter plugin registrations and defaults for plugin types """
  _registry: typing.Dict[str, FilterPluginRegistration] = {}
  _defaults: typing.Dict[str, str] = {}

  @staticmethod
  def __add_plugin(plugin: FilterPluginRegistration, replace=False):

    name_registered = FilterPluginRegistry._registry.get(plugin.name)
    if(name_registered is None):
      # TODO: fix circular import dependency problem
      #import vcon
      #if(vcon.Vcon.attribute_exists(plugin.name)):
      #  raise AttributeError("{} is a reserved name already used as a Vcon class or instance name".format(plugin.name))
      pass

    if(name_registered is None or replace):
         
      FilterPluginRegistry._registry[plugin.name] = plugin
    else:
      raise FilterPluginAlreadyRegistered("Plugin {} already registered".format(plugin.name))


  @staticmethod
  def register(
    name: str,
    module_name: str,
    class_name: str,
    description: str,
    init_options: typing.Union[FilterPluginInitOptions, typing.Dict[str, typing.Any]],
    replace: bool = False) -> None:
    """
    Register a named filter plugin.

    Parameters:  
      **name** (str) - the name to register the plugin  
      **module_name** (str) - the module name to import where the plugin class is implmented  
      **class_name** (str) - the class name for the plugin implementation in the named module  
      **description** (str) - a text description of what the plugin does  
      **replace** (bool) - if True replace the already registered plugin of the same name  
                       if False throw an exception if a plugin of the same name is already register

    Returns: none
    """
    logger.info("Registering FilterPlugin: {}".format(locals()))
    entry = FilterPluginRegistration(
      name,
      module_name,
      class_name,
      description,
      init_options
      )
    FilterPluginRegistry.__add_plugin(entry, replace)


  @staticmethod
  def get(name: str,
    check_type_default: bool = False,
    load_plugin: bool = False
    ) -> FilterPluginRegistration:

    """
    Returns registration for named plugin
    """
    plugin_reg = FilterPluginRegistry._registry.get(name, None)
    if(plugin_reg is None and not check_type_default):
      raise FilterPluginNotRegistered("Filter plugin {} is not registered".format(name))

    if(plugin_reg is None):
      try:
        plugin_reg = FilterPluginRegistry.get_type_default_plugin(name)

      except FilterPluginNotRegistered as e:
        raise FilterPluginNotRegistered("filter plugin name {} is not register and is not a type default".format(
          name
          ))

    if(load_plugin):
      plugin_reg.import_plugin(plugin_reg._init_options)

    return(plugin_reg)

  @staticmethod
  def get_names() -> typing.List[str]:
    """
    Returns list of plugin names
    """
    return(FilterPluginRegistry._registry.keys())

  @staticmethod
  def set_type_default_name(plugin_type: str, name: str) -> None:
    """ Set the default filter name for the given filter type """
    FilterPluginRegistry._defaults[plugin_type] = name

  @staticmethod
  def get_type_default_name(plugin_type: str) -> typing.Union[str, None]:
    """ Get the default plugin name for the given filter type """
    return(FilterPluginRegistry._defaults.get(plugin_type, None))

  @staticmethod
  def get_types() -> typing.List[str]:
    """
    Get the set of FilterPlugin types.

    Returns:
      list(str) - names of all the types for which a default is set.
    """
    return(FilterPluginRegistry._defaults.keys())

  @staticmethod
  def get_type_default_plugin(plugin_type: str) -> FilterPluginRegistration:
    """ Get the default FilterPlauginRegistration for the named filter type """
    if(not isinstance(plugin_type, str)):
      raise AttributeError("plugin_type argument should be a string, not {}".format(type(plugin_type)))

    name = FilterPluginRegistry.get_type_default_name(plugin_type)
    if(name is None):
      raise FilterPluginNotRegistered("Filter plugin default type name {} is not set".format(plugin_type))
    return(FilterPluginRegistry.get(name))

  @staticmethod
  def shutdown_plugins():
    """
    Shutdown any of the registered filter_plugins which have been instantiated.
    This invokes the __del__ method on any of the loaded/instantiated filter_plugins,
    but does not unregister them.
    """
    plugin_name_list = FilterPluginRegistry._registry.keys()
    for plugin_name in plugin_name_list:
      logger.debug("shutting down plugin: {}".format(plugin_name))
      plugin = FilterPluginRegistry._registry[plugin_name]

      # Reset load states as we are only shutting down the plugin,
      # not onregistering it or preventing it from be re-loaded
      plugin._module_load_attempted = False
      plugin._module_not_found = False
      plugin._class_not_found = False
      # This should cause __del__ to be invoked on the plugin
      del plugin._plugin
      plugin._plugin = None

