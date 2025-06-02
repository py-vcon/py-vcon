# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" Redis implementation of the Vcon storage DB interface """

import typing
import json
import vcon
import py_vcon_server.db
import py_vcon_server.db.redis.redis_mgr
import py_vcon_server.logging_utils

logger = py_vcon_server.logging_utils.init_logger(__name__)

class RedisVconStorage(py_vcon_server.db.VconStorage):
  """ Redis binding of VconStorage """
  def __init__(self):
    self._redis_mgr = None

  def setup(self, redis_uri : str) -> None:
    """ Initialize redis connect """
    if(self._redis_mgr is not None):
      raise Exception("Redis Vcon storage interface already setup")

    # Connect
    self._redis_mgr = py_vcon_server.db.redis.redis_mgr.RedisMgr(redis_uri, "VconStorage")

    # Setup connection pool
    self._redis_mgr.create_pool()

  async def shutdown(self) -> None:
    """ shutdown and wait for redis connections to close """
    if(self._redis_mgr is None):
      logger.error("Redis Vcon storage not setup, nothing to teardown")

    else:
      rm = self._redis_mgr
      self._redis_mgr = None
      await rm.shutdown_pool()


  def __del__(self):
    if(self._redis_mgr is not None):
      logger.error("RedisVconStorage not shutdown")


  async def set(self, save_vcon : typing.Union[vcon.Vcon, dict, str]) -> None:
    """ save **Vcon** to redis storage """
    redis_con = self._redis_mgr.get_client()

    if(isinstance(save_vcon, vcon.Vcon)):
      # Don't deepcopy as we don't modify the dict
      # TODO: handle signed and encrypted where UUID is not a top level member
      vcon_dict = save_vcon.dumpd(True, False)
      uuid = save_vcon.uuid

    elif(isinstance(save_vcon, dict)):
      vcon_dict = save_vcon
      uuid = vcon.Vcon.get_dict_uuid(save_vcon)

    elif(isinstance(save_vcon, str)):
      vcon_dict = json.loads(save_vcon)
      uuid = vcon.Vcon.get_dict_uuid(vcon_dict)

    else:
      raise Exception("Invalid type: {} for Vcon to be saved to redis".format(type(save_vcon)))

    await redis_con.json().set("vcon:{}".format(uuid), "$", vcon_dict)

  async def get(self, vcon_uuid : str) -> typing.Union[None, vcon.Vcon]:
    """ Get Vcon from redis storage """
    redis_con = self._redis_mgr.get_client()

    vcon_dict = await redis_con.json().get("vcon:{}".format(vcon_uuid))
    # logger.debug("Got {} vcon: {}".format(vcon_uuid, vcon_dict))
    if(vcon_dict is None):
      raise py_vcon_server.db.VconNotFound("vCon not found for UUID: {}".format(vcon_uuid))

    a_vcon = vcon.Vcon()
    a_vcon.loadd(vcon_dict)

    return(a_vcon)

  async def jq_query(
      self,
      vcon_uuid: str,
      jq_query_string: str
    ) -> typing.Union[dict, None]:
    """ Get the jq query results for the given **Vcon** """

    a_vcon = await self.get(vcon_uuid)
    if(a_vcon is None):
      return(None)

    query_result = a_vcon.jq(jq_query_string)

    return(query_result)


  async def json_path_query(self, vcon_uuid : str, json_path_query_string : str) -> list:
    """ Get the JSON path query results for the given **Vcon** """
    redis_con = self._redis_mgr.get_client()

    query_list = await redis_con.json().get("vcon:{}".format(vcon_uuid), json_path_query_string)

    return(query_list)


  async def delete(self, vcon_uuid : str) -> None:
    """ Delete the Vcon with the given UUID """

    redis_con = self._redis_mgr.get_client()
    await redis_con.delete(f"vcon:{str(vcon_uuid)}")

