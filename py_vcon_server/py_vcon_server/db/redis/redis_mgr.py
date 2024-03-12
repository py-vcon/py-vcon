""" 
Package to manage Redis connection pool and clients

Setup of redis clients cannot be done globally in each module as it will 
bind to a asyncio loop which may be started and stopped.  In which case
redis will be bound to an old loop which will no longer work

The redis connection pool must be shutdown and restarted when FASTApi does.
"""
import os
import asyncio
import traceback
import redis.asyncio.connection
import redis.asyncio.client
import py_vcon_server.logging_utils


VERBOSE = False

logger = py_vcon_server.logging_utils.init_logger(__name__)

class RedisPoolNotInitialized(Exception):
  """ raised when redis_mgr is not initialized """

class RedisMgr():
  """ Interface/wrapper for redis clients and the management of them """

  def __init__(
      self,
      redis_url: str,
      label: str = None):
    self._redis_url = redis_url
    self._redis_pool = None
    self._redis_pool_initialization_count = 0
    self._label = label # for debug and logging
    self._pid = os.getpid()
    self._creation_stack = traceback.format_list(traceback.extract_stack(f=None, limit=None))


  def create_pool(self):
    """ Create a redis client pool """

    if self._redis_pool is not None:
      logger.info("Redis pool ({}) already created".format(self._label))
    else:
      if(self._pid != os.getpid()):
        current_stack = traceback.format_list(traceback.extract_stack(f=None, limit=None))
        logger.error(
            "redis pool ({}) created in different process: {} from contruction: {} creation stack: {} current stack: {}".format(
            self._label,
            os.getpid(),
            self._pid,
            self._creation_stack,
            current_stack
          ))
      logger.info("Creating Redis pool ({})...".format(self._label))
      self._redis_pool_initialization_count += 1
      options = {"decode_responses": True}
      self._redis_pool = redis.asyncio.connection.ConnectionPool.from_url(self._redis_url,
        **options)
      logger.info(
        "Redis pool ({}) created. redis connection: host: {} port: {} max connections: {} initialization count: {}".format(
          self._label,
          self._redis_pool.connection_kwargs.get("host", "None"),
          self._redis_pool.connection_kwargs.get("port", "None"),
          self._redis_pool.max_connections,
          self._redis_pool_initialization_count,
          )
        )

    #logger.debug(dir(self._redis_pool))


  async def shutdown_pool(self):
    """ shutdown the client pool and wait for busy ones to complete """
    if self._redis_pool is not None:
      if(self._pid != os.getpid()):
          logger.error("redis pool release in different process: {} from contruction: {}".format(
              os.getpid(),
              self._pid
            ))
      logger.info("disconnecting Redis pool ({})".format(self._label))
      self.log_pool_stats()
      tmp_pool = self._redis_pool
      self._redis_pool = None
      await tmp_pool.disconnect(inuse_connections=True)
      logger.info("Redis pool ({}) shutdown".format(self._label))

    else:
        logger.info("Redis pool ({}) already disconnected".format(self._label))


  def log_pool_stats(self):
    """ Log infor about current client pool """
    if(self._redis_pool):
      logger.info("redis pool ({}) max: {} in use: {}  available: {}".format(
          self._label,
          self._redis_pool.max_connections,
          len(self._redis_pool._in_use_connections),
          len(self._redis_pool._available_connections)
        ))
    else:
      logger.info("no active redis pool ({})".format(self._label))


  def get_client(self):
    """ get a redis client from the pool """
    if(VERBOSE):
      logger.debug("entering ({}) get_client pid: {}".format(
          self._label,
          os.getpid()
        ))
      current_stack = traceback.format_list(traceback.extract_stack(f=None, limit=None))
      logger.debug("get_client stack: {}".format(
         current_stack
        ))
    if(self._pid != os.getpid()):
      if(not VERBOSE):
        current_stack = traceback.format_list(traceback.extract_stack(f=None, limit=None))
      logger.error(
          "redis client ({}) created in different process: {} from contruction: {} creation stack: {} current stack: {}".format(
            self._label,
            os.getpid(),
            self._pid,
            self._creation_stack,
            current_stack
        ))
    if(self._redis_pool is None):
      logger.info("redis_pool ({}) is not initialized".format(self._label))
      raise RedisPoolNotInitialized("redis pool ({}) not initialize".format(self._label))

    client = redis.asyncio.client.Redis(connection_pool=self._redis_pool)
    logger.debug("redis ({}) client type: {}".format(
        self._label,
        type(client)
      ))

    if(VERBOSE):
      try:
        for task in asyncio.all_tasks():
          logger.debug("redis.get_client running task: {}".format(task))

      except RuntimeError as e:
        logger.debug("no loop to get tasks")

    return(client)


  def __del__(self):
    if(self._redis_pool):
      logger.error("redis_mgr ({}) not shutdown pid: {} created stack: {}".format(
          self._label,
          os.getpid(),
          self._creation_stack
        ))

