import sys
import asyncio
import fastapi

# For dev purposes, look for relative vcon package
sys.path.append("..")

import py_vcon_server.settings
import py_vcon_server.db
import py_vcon_server.states
import py_vcon_server.queue
from py_vcon_server.logging_utils import init_logger

logger = init_logger(__name__)

__version__ = "0.1"

# Load the VconStorage DB bindings
py_vcon_server.db.import_db_bindings(
  py_vcon_server.db.__path__, # path
  py_vcon_server.db.__name__ + ".", # binding module name prefix
  "DB" # label
  )

# The following imports depend upon the DB binding.
# So they must be done afterwards
import py_vcon_server.vcon_api
import py_vcon_server.admin_api

restapi = py_vcon_server.restful_api.init()

@restapi.on_event("startup")
async def startup():
  logger.info("event startup")

  py_vcon_server.states.SERVER_STATE = py_vcon_server.states.ServerState(
    py_vcon_server.settings.REST_URL,
    py_vcon_server.settings.STATE_DB_URL,
    py_vcon_server.settings.LAUNCH_ADMIN_API,
    py_vcon_server.settings.LAUNCH_VCON_API,
    {},
    py_vcon_server.settings.NUM_WORKERS)

  await py_vcon_server.states.SERVER_STATE.starting()

  await py_vcon_server.db.VconStorage.setup(py_vcon_server.settings.VCON_STORAGE_TYPE,
    py_vcon_server.settings.VCON_STORAGE_URL)

  py_vcon_server.queue.JOB_QUEUE = py_vcon_server.queue.JobQueue(py_vcon_server.settings.QUEUE_DB_URL)

  await py_vcon_server.states.SERVER_STATE.running()
  logger.info("event startup completed")


@restapi.on_event("shutdown")
async def shutdown():
  logger.info("event shutdown")

  await py_vcon_server.states.SERVER_STATE.shutting_down()

  await py_vcon_server.db.VconStorage.teardown()

  await py_vcon_server.queue.JOB_QUEUE.shutdown()

  await py_vcon_server.states.SERVER_STATE.unregister()

  py_vcon_server.states.SERVER_STATE = None

  logger.info("event shutdown completed")

# Enable Admin entry points
if(py_vcon_server.settings.LAUNCH_ADMIN_API):
  py_vcon_server.admin_api.init(restapi)

# Enable Vcon entry points
if(py_vcon_server.settings.LAUNCH_VCON_API):
  py_vcon_server.vcon_api.init(restapi)

