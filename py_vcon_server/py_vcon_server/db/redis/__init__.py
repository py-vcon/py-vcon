""" Redis implementation of the Vcon storage DB interface """

import typing
import json
import pyjq
import vcon
import py_vcon_server.db.redis.redis_mgr
import py_vcon_server.logging_utils

logger = py_vcon_server.logging_utils.init_logger(__name__)

class RedisVconStorage:
  def __init__(self):
    self._redis_mgr = None

  def setup(self, redis_uri : str) -> None:
    if(self._redis_mgr is not None):
      raise(Exception("Redis Vcon storage interface alreadu setup"))

    # Connect
    self._redis_mgr = py_vcon_server.db.redis.redis_mgr.RedisMgr(redis_uri)

    # Setup connection pool
    self._redis_mgr.create_pool()

  async def teardown(self) -> None:
    if(self._redis_mgr is None):
      logger.info("Redis Vcon storage not setup, nothing to teardown")

    else:
      await self._redis_mgr.shutdown_pool()

  async def set(self, save_vcon : typing.Union[vcon.Vcon, dict, str]) -> None:
    redis_con = self._redis_mgr.get_client()

    if(isinstance(save_vcon, vcon.Vcon)):
      # Don't deepcopy as we don't modify the dict
      # TODO: handle signed and encrypted where UUID is not a top level member
      vcon_dict = save_vcon.dumpd(True, False)
      uuid = save_vcon.uuid

    elif(isinstance(save_vcon, dict)):
      vcon_dict = save_vcon
      uuid = save_vcon["uuid"]

    elif(isinstance(save_vcon, str)):
      vcon_dict = json.loads(save_vcon)
      uuid = save_vcon["uuid"]

    else:
      raise(Exception("Invalid type: {} for Vcon to be saved to redis".format(type(save_vcon))))
    
    await redis_con.json().set("vcon:{}".format(uuid), "$", vcon_dict)

  async def get(self, vcon_uuid : str) -> typing.Union[None, vcon.Vcon]:
    redis_con = self._redis_mgr.get_client()

    vcon_dict = await redis_con.json().get("vcon:{}".format(vcon_uuid))
    # logger.debug("Got {} vcon: {}".format(vcon_uuid, vcon_dict))
    if(vcon_dict is None):
      return(None)

    vCon = vcon.Vcon()
    vCon.loadd(vcon_dict)

    return(vCon)

  async def jq_query(self, vcon_uuid : str, jq_query_string : str) -> dict:

    vcon = await self.get(vcon_uuid)

    query_result = pyjq.all(jq_query_string, vcon.dumpd())

    return(query_result)

  async def json_path_query(self, vcon_uuid : str, json_path_query_string : str) -> list:
    redis_con = self._redis_mgr.get_client()

    query_list = await redis_con.json().get("vcon:{}".format(vcon_uuid), json_path_query_string)

    return(query_list)

  async def delete(self, vcon_uuid : str) -> None:
    """ Delete the Vcon with the given UUID """

    redis_con = self._redis_mgr.get_client()
    await redis_con.delete(f"vcon:{str(vcon_uuid)}")

