# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
import py_vcon_server.settings
"""
Interface for server states.

Redis structure:
  "servers" hash
    key:   host:port:pid:start_time  (one entry per logical server instance)
    value: JSON blob with server metadata and settings (no heartbeat)

  "server_workers:<server_key>" set
    members: worker keys  (host:port:pid:start_time:worker_pid)
    one set per server, index of that server's workers

  "server_worker_states" hash
    key:   host:port:pid:start_time:worker_pid
    value: JSON blob with per-worker heartbeat and state

The server entry is written once at startup (or by the parent process
pre-fork in multi-worker mode) and updated only when settings change
(e.g. WORK_QUEUES) or on state transitions.

Each worker owns exactly one field in server_worker_states and the
corresponding membership in the server_workers set.  No two workers
ever write to the same field -- no races.

Crash detection: a stale server_worker_states entry with an old
last_heartbeat indicates that worker hung or crashed without cleanup.
A stale servers entry with no live workers indicates the entire server
instance died ungracefully.

States: "unknown", "starting_up", "running", "shutting_down"
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

# Redis key constants
SERVER_HASH_KEY           = "servers"
SERVER_WORKERS_SET_PREFIX = "server_workers:"
SERVER_WORKER_HASH_KEY    = "server_worker_states"

SERVER_STATE = None


class ServerStateNotFound(Exception):
  """ Raised when referencing a non-existing server state """


class ServerState:
  _states = ["unknown", "starting_up", "running", "shutting_down"]

  def __init__(
      self,
      rest_uri: str,
      redis_uri: str,
      admin_api_enabled: bool,
      vcon_api_enabled: bool,
      num_workers: int
    ):
    logger.debug("ServerState initializing RedisMgr")
    self._redis_mgr = py_vcon_server.db.redis.redis_mgr.RedisMgr(
        redis_uri, "ServerState"
      )
    self._redis_mgr.create_pool()
    logger.debug("ServerState RedisMgr pool created")

    self._pid = os.getpid()
    url_parser = urllib.parse.urlparse(rest_uri)
    self._host = url_parser.hostname
    self._port = url_parser.port
    self._start_time = time.time()
    self._num_workers = num_workers
    self._state = self._states[1]  # starting_up

    # Register Lua scripts
    redis_con = self._redis_mgr.get_client()
    self._register_lua_scripts(redis_con)

    logger.info("Server state initialized")


  def _register_lua_scripts(self, redis_con) -> None:
    """ Register all Lua scripts at init time for efficiency """

    # -- lua_register_worker ----------------------------------------------
    # Atomically add worker to the server's worker set and write worker blob.
    # KEYS = [ SERVER_WORKERS_SET_PREFIX + server_key, SERVER_WORKER_HASH_KEY ]
    # ARGV = [ worker_key, worker_json ]
    lua_register_worker = """
    redis.call("SADD", KEYS[1], ARGV[1])
    redis.call("HSET", KEYS[2], ARGV[1], ARGV[2])
    return 1
    """
    self._do_lua_register_worker = redis_con.register_script(
        lua_register_worker
      )

    # -- lua_update_server_state ------------------------------------------
    # Read-modify-write: update only the "state" field in the server blob.
    # If the entry does not exist, returns -1 (caller should use register()).
    # KEYS = [ SERVER_HASH_KEY ]
    # ARGV = [ server_key, new_state ]
    lua_update_server_state = """
    local existing = redis.call("HGET", KEYS[1], ARGV[1])
    if not existing then
      return -1
    end
    local server = cjson.decode(existing)
    server["state"] = ARGV[2]
    redis.call("HSET", KEYS[1], ARGV[1], cjson.encode(server))
    return 1
    """
    self._do_lua_update_server_state = redis_con.register_script(
        lua_update_server_state
      )

    # -- lua_unregister_worker --------------------------------------------
    # Atomically remove worker from the server's worker set and delete blob.
    # KEYS = [ SERVER_WORKERS_SET_PREFIX + server_key, SERVER_WORKER_HASH_KEY ]
    # ARGV = [ worker_key ]
    lua_unregister_worker = """
    redis.call("SREM", KEYS[1], ARGV[1])
    redis.call("HDEL", KEYS[2], ARGV[1])
    return 1
    """
    self._do_lua_unregister_worker = redis_con.register_script(
        lua_unregister_worker
      )

    # -- lua_deregister_or_delete_server ---------------------------------
    # Shared script for graceful deregister and DevOps force-delete.
    #
    # KEYS = [ SERVER_HASH_KEY, SERVER_WORKER_HASH_KEY ]
    # ARGV = [ server_key, SERVER_WORKERS_SET_PREFIX, force ]
    #   force = "1" : force-clean all worker entries, delete server entry
    #   force = "0" : return error if workers still registered, leave intact
    #
    # Returns: { status, worker_count }
    #   status  1  : success
    #   status -1  : blocked -- workers still registered (force=0 only)
    #   status -2  : server not found
    #   worker_count: number of workers present at time of call
    lua_deregister_or_delete_server = """
    local workers_set_key = ARGV[2] .. ARGV[1]
    local worker_keys = redis.call("SMEMBERS", workers_set_key)
    local worker_count = #worker_keys

    if worker_count > 0 then
      if ARGV[3] == "0" then
        -- graceful shutdown: leave evidence, return blocked error
        local ret = {}
        ret[1] = -1
        ret[2] = worker_count
        return ret
      end
      -- force: clean all worker entries and the set
      for _, worker_key in ipairs(worker_keys) do
        redis.call("HDEL", KEYS[2], worker_key)
      end
      redis.call("DEL", workers_set_key)
    end

    local deleted = redis.call("HDEL", KEYS[1], ARGV[1])
    if deleted == 0 then
      local ret = {}
      ret[1] = -2
      ret[2] = worker_count
      return ret
    end

    local ret = {}
    ret[1] = 1
    ret[2] = worker_count
    return ret
    """
    self._do_lua_deregister_or_delete_server = redis_con.register_script(
        lua_deregister_or_delete_server
      )

    # -- lua_get_server_states --------------------------------------------
    # Full traversal: fetch all server entries, for each fetch its worker
    # set and worker blobs, merge workers under server["workers"], return
    # combined JSON.  Single round trip -- no Python-side looping over Redis.
    #
    # KEYS = [ SERVER_HASH_KEY, SERVER_WORKER_HASH_KEY ]
    # ARGV = [ SERVER_WORKERS_SET_PREFIX ]
    #
    # Returns: JSON-encoded dict of server_key -> combined server+workers blob
    #   or "" if no servers
    lua_get_server_states = """
    local servers_raw = redis.call("HGETALL", KEYS[1])
    if #servers_raw == 0 then
      return "{}"
    end

    local result = {}

    -- HGETALL returns flat array: [key1, val1, key2, val2, ...]
    local i = 1
    while i <= #servers_raw do
      local server_key = servers_raw[i]
      local server_json = servers_raw[i + 1]
      i = i + 2

      local server = cjson.decode(server_json)

      -- fetch the worker key set for this server
      local workers_set_key = ARGV[1] .. server_key
      local worker_keys = redis.call("SMEMBERS", workers_set_key)

      -- fetch each worker blob
      local workers = {}
      for _, worker_key in ipairs(worker_keys) do
        local worker_json = redis.call("HGET", KEYS[2], worker_key)
        if worker_json then
          workers[worker_key] = cjson.decode(worker_json)
        end
      end

      server["workers"] = workers
      result[server_key] = server
    end

    return cjson.encode(result)
    """
    self._do_lua_get_server_states = redis_con.register_script(
        lua_get_server_states
      )


  def server_key(self) -> str:
    """
    Key for the server (parent) entry in the servers hash.
    Format: host:port:pid:start_time
    The pid+start_time combination handles container restarts that
    may reuse the same PID.
    """
    return "{}:{}:{}:{}".format(
        self._host, self._port, self._pid, self._start_time
      )


  def worker_key(self) -> str:
    """
    Key for this worker's entry in server_worker_states.
    Format: host:port:pid:start_time:worker_pid
    In single-process mode pid == worker_pid.
    In multi-worker mode worker_pid is the forked worker's PID.
    """
    return "{}:{}".format(self.server_key(), os.getpid())


  def _build_server_dict(self) -> typing.Dict[str, typing.Any]:
    """ Build the server blob (no heartbeat -- that lives in worker entry) """
    server_dict: typing.Dict[str, typing.Any] = {}
    server_dict["py_vcon_server"] = py_vcon_server.__version__
    server_dict["vcon"] = vcon.__version__
    server_dict["host"] = self._host
    server_dict["port"] = self._port
    server_dict["pid"] = self._pid
    server_dict["start_time"] = self._start_time
    server_dict["num_workers"] = self._num_workers
    server_dict["num_restapi_workers"] = py_vcon_server.settings.NUM_RESTAPI_WORKERS
    server_dict["state"] = self._state
    settings = {}
    for setting_name in py_vcon_server.settings.STATE_SETTINGS:
      settings[setting_name] = getattr(
          py_vcon_server.settings, setting_name, None
        )
    server_dict["settings"] = settings
    return server_dict


  def _build_worker_dict(self) -> typing.Dict[str, typing.Any]:
    """ Build the worker blob with heartbeat and worker-specific state """
    return {
      "worker_pid": os.getpid(),
      "start_time": time.time(),
      "state": self._state,
      "last_heartbeat": time.time(),
    }


  async def register_server(self) -> None:
    """
    Write the server entry to the servers hash.
    Single HSET -- no Lua needed.
    In single-process mode called from lifespan startup.
    In multi-worker mode called by the parent process pre-fork (sync redis),
    or by the first worker if no parent pre-registration occurs.
    """
    server_dict = self._build_server_dict()
    redis_con = self._redis_mgr.get_client()
    logger.info("registering server state: {}".format(self.server_key()))
    try:
      await redis_con.hset(
          SERVER_HASH_KEY,
          self.server_key(),
          value=json.dumps(server_dict)
        )
    except redis.exceptions.ConnectionError as redis_except:
      logger.exception(redis_except)
      raise Exception(
          "Server State DB unable to connect to Redis"
        ) from redis_except


  async def register_worker(self) -> None:
    """
    Atomically add this worker to the server's worker set and write
    the worker blob.  Uses Lua for atomicity.
    """
    worker_dict = self._build_worker_dict()
    workers_set_key = SERVER_WORKERS_SET_PREFIX + self.server_key()
    keys = [workers_set_key, SERVER_WORKER_HASH_KEY]
    args = [self.worker_key(), json.dumps(worker_dict)]
    logger.info("registering worker: {}".format(self.worker_key()))
    await self._do_lua_register_worker(keys=keys, args=args)


  async def register(self, may_exist: bool = False) -> None:
    """
    Backward-compatible register: writes both server and worker entries.
    Used in single-process mode where lifespan calls this directly.
    In multi-worker mode, register_server() and register_worker() are
    called separately.
    """
    if not may_exist:
      # Check if server key already exists -- should not occur on first register
      redis_con = self._redis_mgr.get_client()
      existing = await redis_con.hget(SERVER_HASH_KEY, self.server_key())
      if existing is not None and existing != "":
        logger.error("Server {} already exists in servers hash".format(
            self.server_key()
          ))

    await self.register_server()
    await self.register_worker()


  async def update_worker_heartbeat(self) -> None:
    """
    Update only this worker's heartbeat entry.
    Direct HSET -- single command, no Lua overhead.
    Called on every heartbeat tick.
    """
    worker_dict = {
      "worker_pid": os.getpid(),
      "state": self._state,
      "last_heartbeat": time.time(),
    }
    redis_con = self._redis_mgr.get_client()
    await redis_con.hset(
        SERVER_WORKER_HASH_KEY,
        self.worker_key(),
        value=json.dumps(worker_dict)
      )


  async def update_heartbeat(self) -> None:
    """
    Backward-compatible heartbeat update.
    Now delegates to update_worker_heartbeat() -- does NOT rewrite
    the full server entry on every tick.
    """
    await self.update_worker_heartbeat()


  async def _update_state(self, new_state: str) -> None:
    """
    Update only the state field in the server entry.
    Uses Lua read-modify-write to avoid overwriting other fields.
    Also updates the worker entry state.
    """
    self._state = new_state

    # Update server entry state field via Lua
    keys = [SERVER_HASH_KEY]
    args = [self.server_key(), new_state]
    result = await self._do_lua_update_server_state(keys=keys, args=args)
    if result == -1:
      logger.warning(
          "update_state: server entry not found for key: {}".format(
              self.server_key()
            )
        )

    # Update worker entry with new state and fresh heartbeat
    await self.update_worker_heartbeat()


  async def starting(self) -> None:
    """
    Transition to starting_up state and write both server and worker entries.
    Must be called before running() or shutting_down() since it creates
    the server entry for the first time (register() equivalent).
    """
    self._state = self._states[1]  # starting_up
    await self.register(may_exist=True)


  async def running(self) -> None:
    await self._update_state(self._states[2])  # running


  async def shutting_down(self) -> None:
    await self._update_state(self._states[3])  # shutting_down


  async def unregister_worker(self) -> None:
    """
    Atomically remove this worker from the server's worker set and
    delete its worker blob.  Uses Lua for atomicity.
    Called during graceful worker shutdown.
    """
    workers_set_key = SERVER_WORKERS_SET_PREFIX + self.server_key()
    keys = [workers_set_key, SERVER_WORKER_HASH_KEY]
    args = [self.worker_key()]
    logger.info("unregistering worker: {}".format(self.worker_key()))
    await self._do_lua_unregister_worker(keys=keys, args=args)


  async def deregister_server(self) -> None:
    """
    Graceful server shutdown: remove the server entry.
    If workers are still registered (unexpected at graceful shutdown),
    logs a warning and leaves evidence in Redis rather than force-cleaning.
    If the server entry is already gone, logs a warning rather than raising
    -- graceful shutdown should not fail due to a missing entry.
    """
    keys = [SERVER_HASH_KEY, SERVER_WORKER_HASH_KEY]
    args = [self.server_key(), SERVER_WORKERS_SET_PREFIX, "0"]
    result = await self._do_lua_deregister_or_delete_server(
        keys=keys, args=args
      )
    status = result[0]
    worker_count = result[1]

    if status == -1:
      logger.warning(
          "deregister_server: {} worker(s) still registered at shutdown "
          "for server {}  -- leaving stale entries in Redis as evidence".format(
              worker_count, self.server_key()
            )
        )
    elif status == -2:
      # Entry already gone -- warn but don't raise during graceful shutdown
      logger.warning(
          "deregister_server: server entry not found for key: {} "
          "(may have been cleaned up already)".format(self.server_key())
        )
    else:
      logger.info("deregistered server: {}".format(self.server_key()))


  async def unregister(self) -> None:
    """
    Full graceful unregister: remove worker entry then server entry.
    Shuts down the Redis pool after cleanup.
    """
    await self.unregister_worker()
    await self.deregister_server()

    if self._redis_mgr is not None:
      await self._redis_mgr.shutdown_pool()
      self._redis_mgr = None

    logger.info("Server state unregistered")


  async def get_server_state(self) -> typing.Dict[str, typing.Any]:
    """
    Get the combined server+workers state for this server instance.
    Used by /server/info endpoint.
    """
    states = await self.get_server_states()
    return states.get(self.server_key(), None)


  async def get_server_states(self) -> typing.Dict[str, dict]:
    """
    Get all server states with their workers merged in.
    Single Lua round trip -- no Python-side iteration over Redis results.
    Returns: dict of server_key -> combined server+workers blob

    Backward compatible with old-format entries (pre server/worker split):
    old entries have no server_workers:<key> set, so their workers dict
    will be empty ({}).  Old entries are returned correctly and can be
    deleted via delete_server_state() without issue.
    """
    redis_con = self._redis_mgr.get_client()
    keys = [SERVER_HASH_KEY, SERVER_WORKER_HASH_KEY]
    args = [SERVER_WORKERS_SET_PREFIX]
    result_json = await self._do_lua_get_server_states(keys=keys, args=args)

    if not result_json or result_json == "{}":
      return {}

    result = json.loads(result_json)
    logger.info("Got {} server(s)".format(len(result)))
    return result


  async def delete_server_state(self, server_key: str) -> None:
    """
    DevOps force-delete of a (possibly stale) server state entry.
    Force=True: cleans up all worker entries unconditionally.
    Logs the number of orphaned workers cleaned up.
    Returns: None (204 no content -- worker count return deferred to future PR)
    """
    keys = [SERVER_HASH_KEY, SERVER_WORKER_HASH_KEY]
    args = [server_key, SERVER_WORKERS_SET_PREFIX, "1"]
    result = await self._do_lua_deregister_or_delete_server(
        keys=keys, args=args
      )
    status = result[0]
    worker_count = result[1]

    if status == -2:
      raise ServerStateNotFound(
          "server state for: {} not found".format(server_key)
        )

    if worker_count > 0:
      logger.warning(
          "delete_server_state: force-cleaned {} orphaned worker(s) "
          "for server {}".format(worker_count, server_key)
        )
    logger.debug("Deleted server state for: {}".format(server_key))


  def pid(self) -> int:
    """ Return the server process id """
    return self._pid


  def start_time(self) -> float:
    """ Return the start time (epoch seconds) for the server """
    return self._start_time
