# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
import os
import sys
import time
import signal
import uvicorn
import asyncio
import fastapi
import vcon

# For dev purposes, look for relative vcon package
sys.path.append("..")

import py_vcon_server.settings
import py_vcon_server.db
import py_vcon_server.states
import py_vcon_server.queue
import py_vcon_server.metrics
from py_vcon_server.logging_utils import init_logger
import logging
import nest_asyncio

VERBOSE = False

logger = init_logger(__name__)
logger.debug("root logging handlers: {}".format(logging.getLogger().handlers))
logger.debug("logging handlers: {}".format(logger.handlers))

try:
  nest_asyncio.apply()
except ValueError:
  pass  # uvloop already patched this loop; nest_asyncio not needed

__version__ = "0.5.15"

JOB_INTERFACE = None
JOB_MANAGER = None
BACKGROUND_JOBS_RUNNING = False
BACKGROUND_JOB_TASK = None
SHUTDOWN_REQUESTED = False
ACTIVE_REQUESTS = 0    # count of non-exempt in-flight entry point requests
HEARTBEAT_RUNNING = False
HEARTBEAT_TASK = None
# Paths exempt from 503 shutdown middleware and drain tracking.
# These remain accessible during graceful shutdown for monitoring.
EXEMPT_SHUTDOWN_PATHS = {"/metrics", "/diagnostics"}

# TODO make this a setting
ASYNC_SCHEDULER = True

# Load the VconStorage DB bindings
py_vcon_server.db.import_bindings(
  py_vcon_server.db.__path__, # path
  py_vcon_server.db.__name__ + ".", # binding module name prefix
  "DB" # label
  )

# Load site specific plugins
logger.debug("PLUGIN_PATHS: {}".format(py_vcon_server.settings.PLUGIN_PATHS))
for path in py_vcon_server.settings.PLUGIN_PATHS:
  if(path and len(path) > 0):
    logger.info("checking for plugins in: \"{}\"".format(path))
    py_vcon_server.db.import_bindings(
      [path],
      "", # module prefix, allowing anything
      "site" # label
      )

# The following imports depend upon the DB binding.
# So they must be done afterwards
import py_vcon_server.vcon_api
import py_vcon_server.admin_api

# Load the builtin VconProcessor bindings
logger.debug("loading VconProcessors from: {} with prefix: {}".format(
    py_vcon_server.processor.__path__,
    py_vcon_server.processor.__name__ + "."
  ))
py_vcon_server.db.import_bindings(
  py_vcon_server.processor.__path__, # path
  py_vcon_server.processor.__name__ + ".", # binding module name prefix
  "VconProcessor" # label
  )

# Load any separately installed addon VconProcessor binding
addons_path = "{}/processor_addons".format(py_vcon_server.__path__[0])
logger.debug("Looking for addon processors in: {}".format(addons_path))
py_vcon_server.db.import_bindings(
  [addons_path],
  "", # module prefix, allowing anything
  "addons" # label
  )


async def heartbeat_loop() -> None:
  """ Periodic heartbeat to update server state in Redis """
  global HEARTBEAT_RUNNING
  while HEARTBEAT_RUNNING:
    try:
      await asyncio.sleep(py_vcon_server.settings.HEARTBEAT_PERIOD)
      if not HEARTBEAT_RUNNING:
        break
      if py_vcon_server.states.SERVER_STATE:
        await py_vcon_server.states.SERVER_STATE.update_worker_state()
        if os.environ.get("PYVCON_MASTER_PID", "") == "":
          await py_vcon_server.states.SERVER_STATE.update_server_heartbeat()

        if VERBOSE:
          logger.debug("Heartbeat updated")
    except asyncio.CancelledError:
      logger.debug("Heartbeat task cancelled")
      break
    except Exception as e:
      logger.warning("Heartbeat update failed: {}".format(e))
      # Continue - transient Redis failures should not kill the heartbeat


def _uvicorn_install_signal_handlers_needs_fix() -> bool:
  """
  Uvicorn < 0.23 uses asyncio.get_event_loop() in install_signal_handlers()
  which returns the wrong loop when nest_asyncio is applied on Python 3.8,
  causing signal handlers to never fire in spawned worker processes.
  Detect by inspecting the base method source.
  """
  try:
    import inspect as _inspect
    import uvicorn.server
    src = _inspect.getsource(uvicorn.server.Server.install_signal_handlers)
    return "get_event_loop" in src and "get_running_loop" not in src
  except Exception:
    return False  # if we can't inspect, don't override

_UVICORN_NEEDS_SIGNAL_FIX = _uvicorn_install_signal_handlers_needs_fix()


class Server(uvicorn.Server):
  """
  Uvicorn Server subclass implementing graceful shutdown that keeps
  the socket open (and /metrics + /diagnostics reachable) until all
  in-flight entry point requests and the current background job complete.

  Defined here (not in __main__) so that multiprocessing spawn can
  pickle the bound method server.run and find this class by its fully
  qualified name py_vcon_server.Server.
  """

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self._drain_requested = False

  if _UVICORN_NEEDS_SIGNAL_FIX:
    def install_signal_handlers(self) -> None:
      import threading
      import asyncio
      if threading.current_thread() is not threading.main_thread():
          return

      try:
          # Use get_running_loop() rather than get_event_loop() to ensure
          # we install handlers on the actual running loop.  In Python 3.8
          # with nest_asyncio, get_event_loop() may return a different loop
          # than the one actually running, causing signal handlers to never fire.
          loop = asyncio.get_running_loop()
          for sig in (signal.SIGINT, signal.SIGTERM):
              loop.add_signal_handler(sig, self.handle_exit, sig, None)
          logger.info(
              "Signal handlers installed via get_running_loop() "
              "(uvicorn get_event_loop fix applied)"
            )

      except RuntimeError:
          # No running loop - fall back to signal.signal() (Windows or
          # contexts where the loop hasn't started yet)
          for sig in (signal.SIGINT, signal.SIGTERM):
              signal.signal(sig, self.handle_exit)
          logger.info("Signal handlers installed via signal.signal()")


  def handle_exit(self, sig: int, frame) -> None:
    #import sys
    #print(f"handle_exit called sig={sig} pid={os.getpid()}", flush=True, file=sys.stderr)
    global SHUTDOWN_REQUESTED, BACKGROUND_JOBS_RUNNING

    if self.should_exit and sig == signal.SIGINT:
      self.force_exit = True
      return

    logger.info(
        "Shutdown signal {} received - starting graceful drain, "
        "socket remains open for {} during drain".format(
            sig, ", ".join(sorted(EXEMPT_SHUTDOWN_PATHS))
          )
      )

    SHUTDOWN_REQUESTED = True
    BACKGROUND_JOBS_RUNNING = False
    self._drain_requested = True
    # Do NOT call super().handle_exit() - that sets should_exit=True
    # and causes uvicorn to close the socket before drain completes.

  async def on_tick(self, counter: int) -> bool:
    if self._drain_requested:
      active = ACTIVE_REQUESTS
      bg_task = BACKGROUND_JOB_TASK
      bg_done = (bg_task is None or bg_task.done())

      if active == 0 and bg_done:
        logger.info(
            "Drain complete (active_requests={}, background_job=done) "
            "- handing shutdown to uvicorn".format(active)
          )
        self._drain_requested = False
        self.should_exit = True

    return await super().on_tick(counter)


from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
  global SHUTDOWN_REQUESTED
  global HEARTBEAT_RUNNING, HEARTBEAT_TASK
  global JOB_INTERFACE, JOB_MANAGER, BACKGROUND_JOBS_RUNNING, BACKGROUND_JOB_TASK

  # ===== STARTUP =====
  logger.info("event startup")

  SHUTDOWN_REQUESTED = False

  py_vcon_server.states.SERVER_STATE = py_vcon_server.states.ServerState(
    py_vcon_server.settings.REST_URL,
    py_vcon_server.settings.STATE_DB_URL,
    py_vcon_server.settings.LAUNCH_ADMIN_API,
    py_vcon_server.settings.LAUNCH_VCON_API,
    py_vcon_server.settings.NUM_WORKERS)

  if(py_vcon_server.settings.RUN_BACKGROUND_JOBS):
    JOB_INTERFACE = py_vcon_server.pipeline.PipelineJobHandler(
        py_vcon_server.settings.QUEUE_DB_URL,
        py_vcon_server.settings.PIPELINE_DB_URL,
        py_vcon_server.states.SERVER_STATE.server_key()
      )

  if(False):
    #if(py_vcon_server.settings.NUM_WORKERS > 0):
    logger.debug("Starting pipeline server with {} workers".format(
        py_vcon_server.settings.NUM_WORKERS
      ))
    JOB_MANAGER = py_vcon_server.job_worker_pool.JobSchedulerManager(
        py_vcon_server.settings.NUM_WORKERS,
        JOB_INTERFACE
      )
    if(ASYNC_SCHEDULER):
      await JOB_MANAGER.async_start()
    else:
      JOB_MANAGER.start(wait_scheduler = True)
    # extra time for processes to get started
    time.sleep(5.0)

  is_worker = os.environ.get("PYVCON_MASTER_PID", "") != ""
  if is_worker:
    await py_vcon_server.states.SERVER_STATE.register_worker()
  else:
    if py_vcon_server.settings.NUM_RESTAPI_WORKERS > 1:
      logger.warning(
          "lifespan: NUM_RESTAPI_WORKERS > 1 but PYVCON_MASTER_PID not set "
          "-- server entry not registered by master"
        )
    await py_vcon_server.states.SERVER_STATE.register_server()
    await py_vcon_server.states.SERVER_STATE.register_worker()

  py_vcon_server.db.VCON_STORAGE = py_vcon_server.db.VconStorage.instantiate(py_vcon_server.settings.VCON_STORAGE_URL)
  py_vcon_server.queue.JOB_QUEUE = py_vcon_server.queue.JobQueue(py_vcon_server.settings.QUEUE_DB_URL)
  py_vcon_server.pipeline.PIPELINE_DB = py_vcon_server.pipeline.PipelineDb(py_vcon_server.settings.PIPELINE_DB_URL)
  await py_vcon_server.pipeline.PIPELINE_DB.test()

  # Install processor instrumentation (must be after plugin loading, before jobs start)
  py_vcon_server.metrics.install_instrumentation()

  # Initialize cross-worker diagnostics shared memory (no-op if single-worker)
  py_vcon_server.metrics.init_diagnostics_shm()

  # all should be up at this point
  if is_worker:
    await py_vcon_server.states.SERVER_STATE.worker_running()
  else:
    await py_vcon_server.states.SERVER_STATE.server_running()
    await py_vcon_server.states.SERVER_STATE.worker_running()

  if py_vcon_server.settings.HEARTBEAT_PERIOD > 0:
    HEARTBEAT_RUNNING = True
    HEARTBEAT_TASK = asyncio.create_task(heartbeat_loop())
    logger.info("Heartbeat started (period: {}s)".format(
        py_vcon_server.settings.HEARTBEAT_PERIOD))

  # Start background jobs
  if py_vcon_server.settings.RUN_BACKGROUND_JOBS:
    BACKGROUND_JOBS_RUNNING = True
    BACKGROUND_JOB_TASK = asyncio.create_task(run_background_jobs(JOB_INTERFACE))

  logger.info("event startup completed")

  yield  # Application runs here

# ===== SHUTDOWN =====
  logger.info("event shutdown")
  SHUTDOWN_REQUESTED = True

  # Stop heartbeat before state transition
  HEARTBEAT_RUNNING = False
  if HEARTBEAT_TASK:
    HEARTBEAT_TASK.cancel()
    try:
      await HEARTBEAT_TASK
    except asyncio.CancelledError:
      pass
    HEARTBEAT_TASK = None

  # State transition to shutting_down
  if is_worker:
    await py_vcon_server.states.SERVER_STATE.worker_shutting_down()
  else:
    await py_vcon_server.states.SERVER_STATE.server_shutting_down()
    await py_vcon_server.states.SERVER_STATE.worker_shutting_down()

  if JOB_MANAGER:
    await JOB_MANAGER.finish()
    JOB_MANAGER = None

  if BACKGROUND_JOBS_RUNNING:
    BACKGROUND_JOBS_RUNNING = False
  if BACKGROUND_JOB_TASK:
    logger.debug("waiting for background job to complete")
    await BACKGROUND_JOB_TASK
    logger.debug("background job completed")
    BACKGROUND_JOB_TASK = None
  if JOB_INTERFACE:
    await JOB_INTERFACE.done()
    JOB_INTERFACE = None

  if py_vcon_server.db.VCON_STORAGE:
    await py_vcon_server.db.VCON_STORAGE.shutdown()
    py_vcon_server.db.VCON_STORAGE = None

  if py_vcon_server.queue.JOB_QUEUE:
    await py_vcon_server.queue.JOB_QUEUE.shutdown()
    py_vcon_server.queue.JOB_QUEUE = None

  if py_vcon_server.pipeline.PIPELINE_DB:
    await py_vcon_server.pipeline.PIPELINE_DB.shutdown()
    py_vcon_server.pipeline.PIPELINE_DB = None

  vcon.filter_plugins.FilterPluginRegistry.shutdown_plugins()

  py_vcon_server.metrics.shutdown_diagnostics_shm()

  # Unregister after all shutdown work complete
  if is_worker:
    await py_vcon_server.states.SERVER_STATE.unregister_worker()
    await py_vcon_server.states.SERVER_STATE.shutdown_redis()
  else:
    await py_vcon_server.states.SERVER_STATE.unregister_worker()
    await py_vcon_server.states.SERVER_STATE.unregister_server()
    await py_vcon_server.states.SERVER_STATE.shutdown_redis()

  py_vcon_server.states.SERVER_STATE = None

  logger.info("event shutdown completed")


async def run_background_jobs(job_interface) -> None:
  global BACKGROUND_JOBS_RUNNING
  # Wait a bit to start running jobs so that the rest of the system can get started
  await asyncio.sleep(5.0)
  if(BACKGROUND_JOBS_RUNNING):
    logger.debug("checking for pipeline jobs")
  else:
    logger.debug("background pipline server disabled")
  while(BACKGROUND_JOBS_RUNNING):
    py_vcon_server.metrics.update_background_job_heartbeat()
    job_id = await job_interface.run_one_job()

    # Prevent a fast spin when no job in queue
    if(job_id is None):
      if(VERBOSE):
        logger.debug("no job waiting a bit")
      await asyncio.sleep(0.5)
      if(VERBOSE):
        logger.debug("no job done waiting")

    else:
      logger.debug("completed job: {} in background".format(job_id))

  logger.debug("Not checking for background jobs")


restapi = py_vcon_server.restful_api.init(lifespan=lifespan)


# Enable Admin entry points
if(py_vcon_server.settings.LAUNCH_ADMIN_API):
  py_vcon_server.admin_api.init(restapi)

# Enable Vcon entry points
if(py_vcon_server.settings.LAUNCH_VCON_API):
  py_vcon_server.vcon_api.init(restapi)

