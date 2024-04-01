"""
Interface for server states

The various states that are used include:
  server instances
    host
    port
    pid
    name/id
    start time
    vcon_api_enabled
    admin_api_enabled
    num_workers
    last heartbeat time
    state =  one of: "unknown", "starting_up", "running", "shutting_down"

  pipeline definitions
    input queue name
    vcon: { readonly, readwrite}
    timeout
    array of processor names and options

  pipeline jobs in progress
    server name/id
    start time
    timeout
    queue name
    queue item (type, and info)
"""

import os
import urllib
import time
import typing
import json
import vcon
import py_vcon_server.db.redis.redis_mgr
import py_vcon_server.logging_utils
# Should remove this when abstracted from Redis
import redis

logger = py_vcon_server.logging_utils.init_logger(__name__)

SERVER_STATE = None

class ServerState:
  # key for hash of all servers
  _hash_key = "servers"
  _states = ["unknown", "starting_up", "running", "shutting_down"]

  def __init__(
      self,
      rest_uri: str,
      redis_uri: str,
      admin_api_enabled: bool,
      vcon_api_enabled: bool,
      num_workers: int
    ):
    # Connect
    logger.debug("ServerState intializing RedisMgr")
    self._redis_mgr = py_vcon_server.db.redis.redis_mgr.RedisMgr(redis_uri, "ServerState")

    # Setup connection pool
    self._redis_mgr.create_pool()
    logger.debug("ServerState intializing RedisMgr pool created")

    # Intialize
    self._pid = os.getpid()
    url_parser = urllib.parse.urlparse(rest_uri)
    self._host = url_parser.hostname
    self._port = url_parser.port
    self._start_time = time.time()
    self._num_workers = num_workers
    self._state = self._states[1]
    logger.info("Server state intialized")


  def server_key(self) -> str:
    # a new container may get the same pid repeatedly
    # need to add something else to add uniqueness e.g. start time
    return("{}:{}:{}:{}".format(self._host, self._port, self._pid, self._start_time))

  async def register(self, may_exist: bool = False) -> None:
    server_key = self.server_key()

    server_dict: typing.Dict[str, typing.Any] = {}
    server_dict["py_vcon_server"] = py_vcon_server. __version__
    server_dict["vcon"] = vcon.__version__
    server_dict["host"] = self._host
    server_dict["port"] = self._port
    server_dict["pid"] = self._pid
    server_dict["start_time"] = self._start_time
    server_dict["num_workers"] = self._num_workers
    server_dict["state"] = self._state
    server_dict["last_heartbeat"] = time.time()

    redis_con = self._redis_mgr.get_client()

    if(not may_exist):
      # Check if key already exists.  This should not occur
      server_json_string = await redis_con.hget(self._hash_key, self.server_key())
      if(server_json_string is not None or server_json_string != ""):
        logger.error("Server {} already exists in hash: {} {}".format(
          self.server_key(),
          self._hash_key,
          server_json_string))

    # save to a redis hash
    logger.info("setting server state: {}".format(server_dict))
    try:
      await redis_con.hset(self._hash_key, self.server_key(), value = json.dumps(server_dict))
    except redis.exceptions.ConnectionError as redis_except:
      logger.exception(redis_except)
      logger.debug("Unable to connect to Redis State DB: host: {} port: {}".format(
          self._redis_mgr._redis_pool.connection_kwargs.get("host", "None"),
          self._redis_mgr._redis_pool.connection_kwargs.get("port", "None")
        ))
      raise Exception("Server State DB unable to connect to Redis host: {} port: {}".format(
          self._redis_mgr._redis_pool.connection_kwargs.get("host", "None"),
          self._redis_mgr._redis_pool.connection_kwargs.get("port", "None")
        ))


  async def unregister(self) -> None:
    await self.delete_server_state(self.server_key())

    if(self._redis_mgr is not None):
      await self._redis_mgr.shutdown_pool()
      self._redis_mgr = None

    logger.info("Server state unregistered")

  async def update_heartbeat(self) -> None:
    self.register(True)

  async def starting(self) -> None:
    await self.register(True)

  async def running(self) -> None:
    self._state = self._states[2]
    await self.register(True)

  async def shutting_down(self) -> None:
    self._state = self._states[3]
    await self.register(True)


  async def get_server_state(self) -> typing.Dict[str, dict]:
    # TODO refactor register so that we need not touch redis for this data
    redis_con = self._redis_mgr.get_client()
    server_json_string = await redis_con.hget(self._hash_key, self.server_key())
    if(server_json_string):
      server_json_string = json.loads(server_json_string)
    return(server_json_string)


  async def get_server_states(self) -> typing.Dict[str, dict]:
    redis_con = self._redis_mgr.get_client()
    server_key_value_pairs = await redis_con.hgetall(self._hash_key)

    # Need to deserialize the values for each server
    for server in server_key_value_pairs:
      server_key_value_pairs[server] = json.loads(server_key_value_pairs[server])

    logger.info("Got servers: {}".format(server_key_value_pairs))

    return(server_key_value_pairs)


  async def delete_server_state(self, server_key: str) -> None:
    redis_con = self._redis_mgr.get_client()
    # Remove server from hash
    await redis_con.hdel(self._hash_key, server_key)
    logger.debug("Deleted server state for: {}".format(server_key))

  def pid(self) -> str:
    """ Return the server prociess id """
    return( self._pid )

  def start_time(self) -> float:
    """ Return the start time (epoch seconds) for the server """
    return(self._start_time)

