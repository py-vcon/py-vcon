""" 
Package to manage Redis connection pool and clients

Setup of redis clients cannot be done globally in each module as it will 
bind to a asyncio loop which may be started and stopped.  In which case
redis will be bound to an old loop which will no longer work

The redis connection pool must be shutdown and restarted when FASTApi does.
"""

import py_vcon_server.logging_utils
import redis.asyncio.connection
import redis.asyncio.client
import pytest_asyncio
import pytest
import uuid


logger = py_vcon_server.logging_utils.init_logger(__name__)

class RedisMgr():

  def __init__(self, redis_url: str):
    self._redis_url = redis_url
    self._redis_pool = None
    self._redis_pool_initialization_count = 0


  def create_pool(self):
      self._redis_pool
      self._redis_pool_initialization_count
      if self._redis_pool is not None:
          logger.info("Redis pool already created")
      else:
          logger.info("Creating Redis pool...")
          self._redis_pool_initialization_count += 1
          options = {"decode_responses": True}
          self._redis_pool = redis.asyncio.connection.ConnectionPool.from_url(self._redis_url,
            **options)
          logger.info(
              "Redis pool created. redis connection: host: {} port: {} max connections: {} initialization count: {}".format(
                  self._redis_pool.connection_kwargs.get("host", "None"),
                  self._redis_pool.connection_kwargs.get("port", "None"),
                  self._redis_pool.max_connections,
                  self._redis_pool_initialization_count,
              )
          )
  
      #logger.debug(dir(self._redis_pool))
  
  
  async def shutdown_pool(self):
      self._redis_pool
      if self._redis_pool is not None:
          logger.info("disconnecting Redis pool")
          self.log_pool_stats()
          tmp_pool = self._redis_pool
          self._redis_pool = None
          await tmp_pool.disconnect(inuse_connections=True)
          logger.info("Redis pool shutdown")
  
      else:
          logger.info("Redis pool already disconnected")
  
  
  def log_pool_stats(self):
    if(self._redis_pool):
      logger.info("redis pool max: {} in use: {}  available: {}".format(self._redis_pool.max_connections,
        len(self._redis_pool._in_use_connections),
        len(self._redis_pool._available_connections)))
    else:
      logger.info("no active redis pool")
  
  def get_client(self):
    logger.debug("entering get_client")
    self._redis_pool
    if self._redis_pool is None:
      logger.info("redis_pool is not initialized")
      raise Exception("redis pool not initialize")

    r = redis.asyncio.client.Redis(connection_pool=self._redis_pool)
    logger.debug("client type: {}".format(type(r)))
    return r

