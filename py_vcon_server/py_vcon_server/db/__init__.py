# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
import typing
import urllib
import asyncio
import pkgutil
import importlib
import vcon
import py_vcon_server.logging_utils
#from py_vcon_server.processor import ProcessorIO

logger = py_vcon_server.logging_utils.init_logger(__name__)

class VconNotFound(Exception):
  """ Rasied when the vCon for the given UUID does not exist """


def import_bindings(path: str, module_prefix: str, label: str):
  """ Import the modules and interface registrations """
  for finder, module_name, is_package in pkgutil.iter_modules(
    path,
    module_prefix
    ):
    logger.info("{} module load: {}".format(label, module_name))
    importlib.import_module(module_name)


# Should this be a class or global methods??
class VconStorage():
  _vcon_storage_implementations = {}


  @staticmethod
  def instantiate(db_url : str = "redis://localhost") -> 'VconStorage':
    """ Setup Vcon storage DB type, factory and connection URL """
    #  Need to setup Vcon storage type and URL
    url_object = urllib.parse.urlparse(db_url)
    db_type = url_object.scheme

    impl_class = VconStorage._vcon_storage_implementations[db_type]
    instance = impl_class()

    instance.setup(db_url)

    return(instance)


  async def shutdown(self) -> None:
    """ teardown for Vcon storage interface to force closure and clean up of connections """
    raise Exception("teardown not implemented")





  @staticmethod
  def register(name : str, class_type : typing.Type):
    """ method to register storage class types """

    VconStorage._vcon_storage_implementations[name] = class_type
    logger.info("registered {} Vcon storage implementation".format(name))


  async def set(self, save_vcon : typing.Union[vcon.Vcon, dict, str]) -> None:
    """ add or update a Vcon in persistent storage """
    raise Exception("set not implemented")


  async def commit(
      self,
      processor_output #: VconProcessorIO
    ) -> None:
    """
    Helper function to save changed **Vcon**s from the
    output of a **VconProcessor** or **Pipeline**.

    Saves **Vcon**s which have been marked as modified
    or new in the given **VconProcessorIO**
    """
    num_vcons = processor_output.num_vcons()
    for index in range(0, num_vcons):
      if(processor_output.is_vcon_modified(index)):
        vcon_dict = await processor_output.get_vcon(
          index,
          py_vcon_server.processor.VconTypes.DICT
          )

        await self.set(vcon_dict)


  async def get(self, vcon_uuid : str) -> typing.Union[None, vcon.Vcon]:
    """ Get a Vcon from storage using its UUID as the key """
    raise Exception("get not implemented")


  async def jq_query(
      self,
      vcon_uuid: str,
      jq_query_string: str
    ) -> str:
    """
    Apply the given JQ query/transform on the Vcon from storage given its UUID as the key.

    Returns: json query/transform in the form of a string
    """
    raise Exception("jq_query not implemented")


  @staticmethod
  async def json_path_query(vcon_uuid : str, json_path_query_string : str) -> str:
    """
    Apply the given JsonPath query on the Vcon from storage given its UUID as the key.

    Returns: json path query in the form of a string
    """
    raise Exception("json_path_query not implemented")


  async def delete(self, vcon_uuid : str) -> None:
    """ Delete the Vcon from storage identified by its UUID as the key """
    raise Exception("delete not implemented")


  # TODO: Need connection status method


VCON_STORAGE: typing.Union[VconStorage, None] = None

