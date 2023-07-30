"""
Interface for server states

The various states that are used include:
  server instances
    host
    port
    pid
    name/id
    start time
    queue names
    vcon_api_enabled
    admin_api_enabled
    num_workers
    last heartbeat time
    state =  one of: "unknown", "starting_up", "running", "shutting_down"

  pipeline job queues
    type: {vcon, vcon_set}
    vcon_uuid or vcon_uuid_set
    
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
import py_vcon_server.db.redis.redis_mgr
import py_vcon_server.logging_utils

logger = py_vcon_server.logging_utils.init_logger(__name__)

STATE_INTERFACE = None



class ServerState:
  # key for hash of all servers
  _hash_key = "servers"
  _states = ["unknown", "starting_up", "running", "shutting_down"]

  def __init__(self, 
                     rest_uri: str,
                     redis_uri: str,
                     admin_api_enabled: bool,
                     vcon_api_enabled: bool,
                     queues: dict,
                     num_workers: int):
    # Connect
    self._redis_mgr = py_vcon_server.db.redis.redis_mgr.RedisMgr(redis_uri)

    # Setup connection pool
    self._redis_mgr.create_pool()

    # Intialize
    self._pid = os.getpid()
    url_parser = urllib.parse.urlparse(rest_uri)
    self._host = url_parser.hostname
    self._port = url_parser.port
    self._start_time = time.time()
    self._queues = queues
    self._num_workers = num_workers
    self._state = self._states[1]

  def server_key(self) -> str:
    return("{}:{}:{}".format(self._host, self._port, self._pid))

  async def register(self, may_exist: bool = False) -> None:
    server_key = self.server_key()

    server_dict = {}
    server_dict["host"] = self._host
    server_dict["port"] = self._port
    server_dict["pid"] = self._pid
    server_dict["start_time"] = self._start_time
    server_dict["queues"] = self._queues
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
    logger.info("setting server states: {}".format(server_dict))
    await redis_con.hset(self._hash_key, self.server_key(), value = json.dumps(server_dict))

  async def unregister(self) -> None:
    redis_con = self._redis_mgr.get_client()
    # Remove server from hash
    await redis_con.hdel(self._hash_key, self.server_key())

    if(self._redis_mgr is not None):
      await self._redis_mgr.shutdown_pool()
      self._redis_mgr = None

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

  async def get_servers(self) -> typing.Dict[str, dict]:
    redis_con = self._redis_mgr.get_client()
    server_key_value_pairs = await redis_con.hgetall(self._hash_key)
    logger.info("Got servers: {}".format(server_key_value_pairs))

    return(server_key_value_pairs)

  # TODO queue/working


