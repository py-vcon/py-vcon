# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
import os
import secrets
import shutil
import sys
import tempfile
import urllib
import asyncio
import time
import threading
import uvicorn
from . import settings, logging_utils
from py_vcon_server import Server

logger = logging_utils.init_logger(__name__)


def _setup_prometheus_multiproc_dir() -> str:
  """
  Create and register a per-instance PROMETHEUS_MULTIPROC_DIR.

  Must be called in the parent process before any workers are forked/spawned
  so that the directory path is inherited by all workers via os.environ.
  Each worker's prometheus_client will write its mmap files here;
  MultiProcessCollector reads and merges them at /metrics scrape time.

  Returns the path of the created directory so the caller can clean it up.

  Warns loudly if PROMETHEUS_MULTIPROC_DIR is already set - this indicates
  either a manual override by an operator (unsupported, risk of sharing data
  between instances) or a previous run that did not clean up.
  """
  existing = os.environ.get("PROMETHEUS_MULTIPROC_DIR", "")
  if existing:
    logger.warning(
        "PROMETHEUS_MULTIPROC_DIR is already set to '{}' in the environment. "
        "This value will be overridden. "
        "This variable is managed by py_vcon_server and should not be set "
        "manually. If multiple server instances share this directory, metrics "
        "will be incorrect and stale data from crashed instances may persist. "
        "Ensure no other server instance is using this directory.".format(existing)
      )

  prom_dir = tempfile.mkdtemp(prefix="pyvcon_prom_{}_".format(os.getpid()))
  os.environ["PROMETHEUS_MULTIPROC_DIR"] = prom_dir
  logger.info(
      "Prometheus multiprocess directory created: {} "
      "(will be removed on clean shutdown)".format(prom_dir)
    )
  return prom_dir


def _cleanup_prometheus_multiproc_dir(prom_dir: str) -> None:
  """
  Remove the PROMETHEUS_MULTIPROC_DIR created by _setup_prometheus_multiproc_dir.

  Called after all workers have exited.  prometheus_client does not remove
  its own mmap files on shutdown - without this cleanup, stale counter and
  histogram files from this run would be included in metrics for the next run.
  """
  logger.info("_cleanup_prometheus_multiproc_dir called with: {}".format(prom_dir))
  try:
    shutil.rmtree(prom_dir)
    logger.info("Prometheus multiprocess directory removed: {}".format(prom_dir))
  except Exception as e:
    logger.warning(
        "Failed to remove Prometheus multiprocess directory {}: {}. "
        "Stale mmap files may affect metrics on next server start.".format(
            prom_dir, e)
      )


def _check_shared_memory_support() -> None:
  """
  Verify that the shared memory slot claim mechanism is supported
  on this platform.  Raises RuntimeError with a clear explanation
  if not.

  Requirements:
    - POSIX platform (Linux, macOS) - fcntl required for slot claim
    - CPython implementation - shm._fd required for fcntl locking
    - Not Windows - fcntl does not exist on Windows
  """
  if sys.platform == "win32":
    raise RuntimeError(
        "Cross-worker /diagnostics aggregation is not supported on Windows. "
        "Windows does not provide fcntl, which is required for safe shared "
        "memory slot assignment across worker processes. "
        "Set NUM_RESTAPI_WORKERS=1 to run without cross-worker aggregation."
      )

  try:
    import fcntl
  except ImportError:
    raise RuntimeError(
        "Cross-worker /diagnostics aggregation requires the fcntl module "
        "which is not available on this platform ({}). "
        "Set NUM_RESTAPI_WORKERS=1 to run without cross-worker aggregation.".format(
            sys.platform)
      )

  # Verify shm._fd is available (CPython implementation detail)
  from multiprocessing.shared_memory import SharedMemory
  test_shm = SharedMemory(create=True, size=64)
  try:
    if not hasattr(test_shm, "_fd"):
      raise RuntimeError(
          "Cross-worker /diagnostics aggregation requires CPython. "
          "SharedMemory._fd is not available on this Python implementation "
          "({}). Set NUM_RESTAPI_WORKERS=1 to run without cross-worker "
          "aggregation.".format(sys.implementation.name)
        )
  finally:
    test_shm.close()
    test_shm.unlink()


def _setup_diagnostics_shm(num_workers: int):
  """
  Allocate a shared memory segment for cross-worker /diagnostics
  aggregation.  Must be called in the parent process before workers
  are forked so the segment name is inherited via env var.

  Sets PYVCON_DIAG_SHM and PYVCON_DIAG_NUM_SLOTS in the environment.

  Returns the SharedMemory object so the caller can clean it up.
  """
  from multiprocessing.shared_memory import SharedMemory
  from py_vcon_server.metrics import DIAG_HEADER_REGION_SIZE, DIAG_SLOT_SIZE

  total_size = DIAG_HEADER_REGION_SIZE + (num_workers * DIAG_SLOT_SIZE)
  shm = SharedMemory(create=True, size=total_size)
  shm.buf[:total_size] = b'\x00' * total_size

  os.environ["PYVCON_DIAG_SHM"] = shm.name
  os.environ["PYVCON_DIAG_NUM_SLOTS"] = str(num_workers)

  logger.info(
      "Diagnostics shared memory allocated: name={} size={}KB slots={}".format(
          shm.name, total_size // 1024, num_workers)
    )
  return shm


def _cleanup_diagnostics_shm(shm) -> None:
  """
  Close and unlink the diagnostics shared memory segment.
  Called after all workers have exited.
  """
  try:
    name = shm.name
    shm.close()
    shm.unlink()
    logger.info("Diagnostics shared memory removed: {}".format(name))
  except Exception as e:
    logger.warning(
        "Failed to remove diagnostics shared memory: {}".format(e)
      )
  finally:
    os.environ.pop("PYVCON_DIAG_SHM", None)
    os.environ.pop("PYVCON_DIAG_NUM_SLOTS", None)


def _setup_server_state(num_workers: int) -> "py_vcon_server.states.ServerState":
  """
  Construct a ServerState for the master process and set PYVCON_MASTER_PID
  and PYVCON_SERVER_START_TIME in the environment so spawned workers share
  the same server_key.  Must be called before workers are spawned.

  The server entry is written to Redis by _MasterStateThread on its own
  persistent event loop, NOT here -- registering here would bind the Redis
  connection pool to a throwaway loop, after which any later use on a
  different loop raises "got Future attached to a different loop".
  Returns the ServerState for the master thread to register and manage.
  """
  import py_vcon_server.states
  os.environ.pop("PYVCON_MASTER_PID", None)
  os.environ.pop("PYVCON_SERVER_START_TIME", None)
  os.environ["PYVCON_MASTER_PID"] = str(os.getpid())
  master_state = py_vcon_server.states.ServerState(
      settings.REST_URL,
      settings.STATE_DB_URL,
      settings.LAUNCH_ADMIN_API,
      settings.LAUNCH_VCON_API,
      num_workers
    )
  os.environ["PYVCON_SERVER_START_TIME"] = str(master_state.start_time())
  return master_state


class _MasterStateThread(threading.Thread):
  """
  Daemon thread that owns a single asyncio event loop for the master
  process server state.  All master Redis state operations -- register,
  periodic heartbeat, and shutdown deregister -- run on this one loop so
  the redis.asyncio connection pool is never used across event loops
  (which raises "got Future attached to a different loop").

  Runs only in multi-worker mode, where the master process cannot use the
  main thread's event loop because Multiprocess.run() blocks it.
  """

  def __init__(self, master_state, period, worker_wait_timeout, poll_interval):
    super().__init__(daemon=True)
    self._master_state = master_state
    self._period = period
    self._worker_wait_timeout = worker_wait_timeout
    self._poll_interval = poll_interval
    self._stop_event = threading.Event()
    self._registered_event = threading.Event()

  def run(self):
    import py_vcon_server.states
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    redis_uri = settings.STATE_DB_URL
    server_key = self._master_state.server_key()
    try:
      try:
        loop.run_until_complete(self._master_state.register_server())
        loop.run_until_complete(self._master_state.server_running())
        logger.info("Master server state registered: {}".format(server_key))
      except Exception as e:
        py_vcon_server.states.record_shutdown_failure(
            redis_uri, server_key, "register", e
          )
        logger.warning("Master server state registration failed: {}".format(e))
      finally:
        self._registered_event.set()

      # period <= 0 means no heartbeat ticks -- just wait for stop.
      heartbeat_timeout = self._period if self._period > 0 else None
      while not self._stop_event.wait(heartbeat_timeout):
        try:
          loop.run_until_complete(self._master_state.update_server_heartbeat())
        except Exception as e:
          logger.warning("Master heartbeat update failed: {}".format(e))

      try:
        loop.run_until_complete(self._master_state.server_shutting_down())
      except Exception as e:
        py_vcon_server.states.record_shutdown_failure(
            redis_uri, server_key, "server_shutting_down", e
          )
        logger.warning("Master server_shutting_down failed: {}".format(e))

      try:
        loop.run_until_complete(
            self._master_state.unregister_server_after_workers(
                self._worker_wait_timeout, self._poll_interval
              )
          )
        logger.info("Master server state deregistered")
      except Exception as e:
        py_vcon_server.states.record_shutdown_failure(
            redis_uri, server_key, "unregister_server_after_workers", e
          )
        logger.warning("Master server state deregister failed: {}".format(e))

      try:
        loop.run_until_complete(self._master_state.shutdown_redis())
      except Exception as e:
        logger.warning("Master Redis shutdown failed: {}".format(e))
    finally:
      loop.close()

  def wait_until_registered(self, timeout):
    if not self._registered_event.wait(timeout):
      logger.warning(
          "Master state thread did not signal registration within {}s".format(
              timeout))

  def stop(self):
    self._stop_event.set()


def main():
  "Start the vCon server with Uvicorn (multi-worker capable)"
  url_parser = urllib.parse.urlparse(settings.REST_URL)
  host_ip = url_parser.hostname
  port_num = url_parser.port
  logger.info("vCon server binding to host: {} port: {} with {} workers".format(
      host_ip, port_num, settings.NUM_RESTAPI_WORKERS))

  config = uvicorn.Config(
      "py_vcon_server:restapi",
      workers=settings.NUM_RESTAPI_WORKERS,
      loop="asyncio",
      host=host_ip,
      port=port_num,
    )
  server = Server(config=config)

  prom_dir = None
  if settings.ENABLE_PROMETHEUS:
    prom_dir = _setup_prometheus_multiproc_dir()

  diag_shm = None
  master_state = None
  master_thread = None
  if settings.NUM_RESTAPI_WORKERS > 1:
    try:
      _check_shared_memory_support()
      diag_shm = _setup_diagnostics_shm(settings.NUM_RESTAPI_WORKERS)
    except RuntimeError as e:
      logger.warning(
          "Cross-worker /diagnostics disabled: {}".format(e)
        )
    master_state = _setup_server_state(settings.NUM_RESTAPI_WORKERS)

  try:
    if settings.NUM_RESTAPI_WORKERS > 1:
      master_thread = _MasterStateThread(
          master_state,
          settings.HEARTBEAT_PERIOD,
          settings.SERVER_SHUTDOWN_WORKER_WAIT_TIMEOUT,
          settings.SERVER_SHUTDOWN_WORKER_POLL_INTERVAL
        )
      master_thread.start()
      master_thread.wait_until_registered(30.0)

      from uvicorn.supervisors import Multiprocess
      sock = config.bind_socket()
      Multiprocess(config, target=server.run, sockets=[sock]).run()
    else:
      server.run()
  finally:
    if master_thread:
      master_thread.stop()
      master_thread.join(
          timeout = settings.SERVER_SHUTDOWN_WORKER_WAIT_TIMEOUT + 15.0
        )
    if master_state:
      os.environ.pop("PYVCON_MASTER_PID", None)
      os.environ.pop("PYVCON_SERVER_START_TIME", None)

    if diag_shm:
      _cleanup_diagnostics_shm(diag_shm)
    if prom_dir:
      _cleanup_prometheus_multiproc_dir(prom_dir)


if __name__ == "__main__":
  main()

