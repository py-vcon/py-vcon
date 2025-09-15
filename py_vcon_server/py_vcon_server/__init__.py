# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
import sys
import time
import asyncio
import fastapi
import vcon

# For dev purposes, look for relative vcon package
sys.path.append("..")

import py_vcon_server.settings
import py_vcon_server.db
import py_vcon_server.states
import py_vcon_server.queue
from py_vcon_server.logging_utils import init_logger
import logging
import nest_asyncio

VERBOSE = False

logger = init_logger(__name__)
logger.debug("root logging handlers: {}".format(logging.getLogger().handlers))
logger.debug("logging handlers: {}".format(logger.handlers))
nest_asyncio.apply()

__version__ = "0.5.0"

JOB_INTERFACE = None
JOB_MANAGER = None
BACKGROUND_JOBS_RUNNING = False
BACKGROUND_JOB_TASK = None


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

restapi = py_vcon_server.restful_api.init()


async def run_background_jobs(job_interface) -> None:
  global BACKGROUND_JOBS_RUNNING
  # Wait a bit to start running jobs so that the rest of the system can get started
  await asyncio.sleep(5.0)
  if(BACKGROUND_JOBS_RUNNING):
    logger.debug("checking for pipeline jobs")
  else:
    logger.debug("background pipline server disabled")
  while(BACKGROUND_JOBS_RUNNING):
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


@restapi.on_event("startup")
async def startup():
  logger.info("event startup")

  py_vcon_server.states.SERVER_STATE = py_vcon_server.states.ServerState(
    py_vcon_server.settings.REST_URL,
    py_vcon_server.settings.STATE_DB_URL,
    py_vcon_server.settings.LAUNCH_ADMIN_API,
    py_vcon_server.settings.LAUNCH_VCON_API,
    py_vcon_server.settings.NUM_WORKERS)

  # Need to fork job worker processes before we connect or send commands to Redis due to
  # async Redis multiprocessing issue which causes hangs.
  # Start the job scheduler and worker pool
  global JOB_INTERFACE
  global JOB_MANAGER
  global RUN_BACKGROUND_JOBS
  global BACKGROUND_JOB_TASK
  #JOB_INTERFACE = py_vcon_server.job_worker_pool.JobInterface()
  if(py_vcon_server.settings.RUN_BACKGROUND_JOBS):
    JOB_INTERFACE = py_vcon_server.pipeline.PipelineJobHandler(
        py_vcon_server.settings.QUEUE_DB_URL,
        #py_vcon_server.queue.JOB_QUEUE,
        py_vcon_server.settings.PIPELINE_DB_URL,
        #py_vcon_server.pipeline.PIPELINE_DB,
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

  elif(py_vcon_server.settings.RUN_BACKGROUND_JOBS):
    global BACKGROUND_JOBS_RUNNING
    BACKGROUND_JOBS_RUNNING = True
    logger.info("starting background pipeline job server")
    BACKGROUND_JOB_TASK = asyncio.create_task(run_background_jobs(JOB_INTERFACE))

  await py_vcon_server.states.SERVER_STATE.starting()

  py_vcon_server.db.VCON_STORAGE = py_vcon_server.db.VconStorage.instantiate(py_vcon_server.settings.VCON_STORAGE_URL)

  py_vcon_server.queue.JOB_QUEUE = py_vcon_server.queue.JobQueue(py_vcon_server.settings.QUEUE_DB_URL)

  py_vcon_server.pipeline.PIPELINE_DB = py_vcon_server.pipeline.PipelineDb(py_vcon_server.settings.PIPELINE_DB_URL)
  await py_vcon_server.pipeline.PIPELINE_DB.test()

  await py_vcon_server.states.SERVER_STATE.running()
  logger.info("event startup completed")


@restapi.on_event("shutdown")
async def shutdown():
  logger.info("event shutdown")

  await py_vcon_server.states.SERVER_STATE.shutting_down()

  global JOB_MANAGER
  global JOB_INTERFACE
  global BACKGROUND_JOBS_RUNNING
  global BACKGROUND_JOB_TASK
  if(JOB_MANAGER):
    await JOB_MANAGER.finish()
    JOB_MANAGER = None
  if(BACKGROUND_JOBS_RUNNING):
    BACKGROUND_JOBS_RUNNING = False
  if(BACKGROUND_JOB_TASK):
    logger.debug("waiting for background job to complete")
    await BACKGROUND_JOB_TASK
    logger.debug("background job completed")
    BACKGROUND_JOB_TASK = None
  if(JOB_INTERFACE):
    await JOB_INTERFACE.done()
    JOB_INTERFACE = None

  await py_vcon_server.db.VCON_STORAGE.shutdown()

  await py_vcon_server.queue.JOB_QUEUE.shutdown()

  await py_vcon_server.pipeline.PIPELINE_DB.shutdown()

  await py_vcon_server.states.SERVER_STATE.unregister()

  py_vcon_server.states.SERVER_STATE = None

  # Shutdown the filter_plugins as some create stateful connections
  vcon.filter_plugins.FilterPluginRegistry.shutdown_plugins()

  logger.info("event shutdown completed")

# Enable Admin entry points
if(py_vcon_server.settings.LAUNCH_ADMIN_API):
  py_vcon_server.admin_api.init(restapi)

# Enable Vcon entry points
if(py_vcon_server.settings.LAUNCH_VCON_API):
  py_vcon_server.vcon_api.init(restapi)

