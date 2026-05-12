# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" 
Package to manage Redis connection pool and clients

Supports two modes via URL:
1. Single Redis instance: redis://host:port/db or rediss://host:port/db
2. Sentinel (HA): sentinel://host1:port1,host2:port2/master_name?db=0&password=xxx

Setup of redis clients cannot be done globally in each module as it will 
bind to a asyncio loop which may be started and stopped.  In which case
redis will be bound to an old loop which will no longer work

The redis connection pool must be shutdown and restarted when FASTApi does.
"""
import os
import asyncio
import traceback
import urllib.parse
import redis.asyncio.connection
import redis.asyncio.client
from redis.asyncio.sentinel import Sentinel
import py_vcon_server.logging_utils


VERBOSE = False
FAIL_NEXT = 0

logger = py_vcon_server.logging_utils.init_logger(__name__)


def parse_sentinel_url(url):
  """
  Parse a sentinel:// URL into its components.

  Handles comma-separated sentinel hosts which urllib.parse.urlparse
  cannot handle (it only sees the first host in the netloc).

  URL formats supported:
    sentinel://host1:port1,host2:port2,host3:port3/master_name
    sentinel://host1:port1,host2:port2/master_name?db=0
    sentinel://:password@host1:port1,host2:port2/master_name?db=0
    sentinel://host1:port1/master_name?db=0&password=xxx&sentinel_password=yyy

  Returns a dict with keys:
    sentinel_hosts  - list of (host, port) tuples
    master_name     - str, defaults to 'mymaster'
    db              - int, defaults to 0
    password        - str or None, Redis master/replica password
    sentinel_password - str or None, Sentinel auth password
  """
  # Strip scheme
  remainder = url
  if remainder.startswith("sentinel://"):
    remainder = remainder[len("sentinel://"):]

  # Extract credentials (optional :password@ prefix)
  url_password = None
  if "@" in remainder:
    credentials, remainder = remainder.split("@", 1)
    # credentials is either "user:pass" or ":pass"
    if ":" in credentials:
      url_password = credentials.split(":", 1)[1]
    else:
      url_password = credentials

  # Split host section from path+query on first "/"
  if "/" in remainder:
    host_section, path_and_query = remainder.split("/", 1)
  else:
    host_section = remainder
    path_and_query = ""

  # Parse individual sentinel hosts from comma-separated host section
  sentinel_hosts = []
  for host_port in host_section.split(","):
    host_port = host_port.strip()
    if ":" in host_port:
      host, port_str = host_port.rsplit(":", 1)
      sentinel_hosts.append((host, int(port_str)))
    else:
      sentinel_hosts.append((host_port, 26379))

  # Use urlparse only for path and query on a synthetic URL
  synthetic = "redis://localhost/{}".format(path_and_query)
  parsed = urllib.parse.urlparse(synthetic)

  # Master name from path component
  master_name = parsed.path.lstrip("/")
  if not master_name:
    master_name = "mymaster"

  # Query params
  params = urllib.parse.parse_qs(parsed.query)
  db = int(params.get("db", ["0"])[0])

  # Password: query param overrides URL authority credential
  password_list = params.get("password", None)
  if password_list is not None:
    password = password_list[0]
  else:
    password = url_password

  sentinel_password_list = params.get("sentinel_password", None)
  sentinel_password = sentinel_password_list[0] if sentinel_password_list is not None else None

  return {
    "sentinel_hosts": sentinel_hosts,
    "master_name": master_name,
    "db": db,
    "password": password,
    "sentinel_password": sentinel_password,
  }


class RedisPoolNotInitialized(Exception):
  """ raised when redis_mgr is not initialized """


class RedisMgr():
  """ 
  Interface/wrapper for redis clients and the management of them.
  
  Supports two connection modes:
  - Single instance: redis://host:port/db
  - Sentinel (HA): sentinel://sentinel1:26379,sentinel2:26379/master_name?db=0
  """

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
    
    # Parse URL to determine mode
    parsed = urllib.parse.urlparse(redis_url)
    self._mode = 'single' if parsed.scheme in ['redis', 'rediss'] else 'sentinel'
    
    # Sentinel-specific attributes
    self._sentinel = None
    self._master_name = None


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
      
      logger.info("Creating Redis pool ({}) for {} in {} mode...".format(
          self._label,
          self._redis_url,
          self._mode
        ))
      
      self._redis_pool_initialization_count += 1
      
      if self._mode == 'single':
        self._create_single_pool()
      else:  # sentinel mode
        self._create_sentinel_pool()
      
      logger.info(
        "Redis pool ({}) created. mode: {} initialization count: {}".format(
          self._label,
          self._mode,
          self._redis_pool_initialization_count,
          )
        )


  def _create_single_pool(self):
    """Create a connection pool for single Redis instance"""
    options = {"decode_responses": True}
    self._redis_pool = redis.asyncio.connection.ConnectionPool.from_url(
        self._redis_url,
        **options
    )
    logger.info(
      "Single Redis pool ({}) configured: host: {} port: {} max connections: {}".format(
        self._label,
        self._redis_pool.connection_kwargs.get("host", "None"),
        self._redis_pool.connection_kwargs.get("port", "None"),
        self._redis_pool.max_connections,
        )
      )


  def _create_sentinel_pool(self):
    """
    Create a Sentinel connection for HA Redis setup.
    URL formats supported:
      sentinel://:password@host1:port1,host2:port2/master_name?db=0
      sentinel://host1:port1,host2:port2/master_name?db=0&password=xxx
    """
    parsed = parse_sentinel_url(self._redis_url)

    sentinel_hosts = parsed["sentinel_hosts"]
    self._master_name = parsed["master_name"]
    db = parsed["db"]
    password = parsed["password"]
    sentinel_password = parsed["sentinel_password"]

    # Create Sentinel instance
    self._sentinel = Sentinel(
        sentinel_hosts,
        socket_timeout=0.1,
        password=sentinel_password
    )

    # Get the master connection pool
    master_client = self._sentinel.master_for(
        self._master_name,
        socket_timeout=0.1,
        db=db,
        password=password,
        decode_responses=True
    )

    # Store the underlying connection pool for compatibility
    self._redis_pool = master_client.connection_pool

    logger.info(
      "Sentinel pool ({}) configured: sentinels: {} master: {} db: {}".format(
        self._label,
        sentinel_hosts,
        self._master_name,
        db
        )
      )


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
      
      # Shutdown based on mode
      if self._mode == 'sentinel' and self._sentinel:
        # Close sentinel connections
        await self._sentinel.close()
        self._sentinel = None
        self._master_name = None
      
      # Disconnect the pool
      tmp_pool = self._redis_pool
      self._redis_pool = None
      await tmp_pool.disconnect(inuse_connections=True)
      logger.info("Redis pool ({}) shutdown".format(self._label))

    else:
        logger.info("Redis pool ({}) already disconnected".format(self._label))


  def log_pool_stats(self):
    """ Log info about current client pool """
    if(self._redis_pool):
      try:
        logger.info("redis pool ({}) mode: {} max: {} in use: {} available: {}".format(
            self._label,
            self._mode,
            self._redis_pool.max_connections,
            len(self._redis_pool._in_use_connections),
            len(self._redis_pool._available_connections)
          ))
      except AttributeError:
        # Some pool types may not have these attributes
        logger.info("redis pool ({}) mode: {} max: {}".format(
            self._label,
            self._mode,
            getattr(self._redis_pool, 'max_connections', 'unknown')
          ))
    else:
      logger.info("no active redis pool ({})".format(self._label))


  def get_client(self):
    """ get a redis client from the pool """
    if(VERBOSE):
      logger.debug("entering ({}) get_client pid: {} mode: {}".format(
          self._label,
          os.getpid(),
          self._mode
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

    global FAIL_NEXT
    if(FAIL_NEXT > 0):
      FAIL_NEXT -= 1
      raise RedisPoolNotInitialized("Force failure for testing, FAIL_NEXT: {}".format(FAIL_NEXT))

    # Create client from pool
    if self._mode == 'sentinel':
      # For Sentinel, get a fresh master connection
      # This ensures automatic failover works correctly
      client = self._sentinel.master_for(
          self._master_name,
          socket_timeout=0.1,
          decode_responses=True
      )
    else:
      # For single instance, use the pool directly
      client = redis.asyncio.client.Redis(connection_pool=self._redis_pool)
    
    if(VERBOSE):
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
