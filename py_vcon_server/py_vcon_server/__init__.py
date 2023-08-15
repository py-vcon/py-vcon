import sys
import pkgutil
import importlib
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

# Import the db modules and interface registrations
for finder, module_name, is_package in pkgutil.iter_modules(py_vcon_server.db.__path__, 
  py_vcon_server.db.__name__ + "."):
  logger.info("db module load: {}".format(module_name))
  importlib.import_module(module_name)

import py_vcon_server.vcon_api
import py_vcon_server.admin_api

openapi_tags = [
  {
    "name": py_vcon_server.admin_api.SERVER_TAG,
    "description": "Entry points to get and set server information",
    # "externalDocs": {
    #   "description": "online docs",
    #   "url": None
    # }
  },
  {
    "name": py_vcon_server.admin_api.QUEUE_TAG,
    "description": "Entry points to create, operate on, add to and delete job queues",
    # "externalDocs": {
    #   "description": "online docs",
    #   "url": None
    # }
  },
  {
    "name": py_vcon_server.admin_api.IN_PROGRESS_TAG,
    "description": "Entry points to get, operate on in progress pipeline job states",
    # "externalDocs": {
    #   "description": "online docs",
    #   "url": None
    # }
  },
  {
    "name": py_vcon_server.vcon_api.VCON_TAG,
    "description": "Entry points to get, query, modify or delete vCons in storage",
    # "externalDocs": {
    #   "description": "online docs",
    #   "url": None
    # }
  }
]

description = """
The Python vCon Server installed from the Python py_vcon_server package.

The vCon server provides a RESTful interface to store and operate on vCons.
These vCon operations can be a single one-off operation or can be setup 
to perform repeatable sets of operations on very large numbers of vCons.

One-off operations are performed via the vCon Storage CRUD entry points.

Repeatable sets of operations can be defined in what is called a pipeline
via the Admin: Pipelines entry points.
A queue is created for each pipeline and then jobs (e.g. vCons) are
added to the queue for the pipeline server to perform the set of processors,
defined by the pipline, on the vCon
(see the Admin: Job Queues entry points for queue managment and job queuing). 
Processors in a pipeline are sequenced such that the
input to the first processor is defined in the job from the queue.
The first processor's output is then given as input to the second processor
in the pipeline and so on.  After the last processor in a pipeline has
been run, its output is commited if marked as new or modified.  Many queues,
each with a pipeline of configured processors can exist in the system
at one time.  Pipeline servers are configured to watch for jobs in
a specific set of queues.  Consequently, a pipeline server only
runs processors defined in the pipelines configured in the
pipeline server's configure set of queues.

Servers, Job Queues and In Progress Jobs can be monitored via the following entry points:

  * Admin: Servers
  * Admin: Job Queues
  * Admin: In Progress Jobs

This server is built to scale from a simple single server to hundreds
of pipeline servers.  A server can be configured to provide any one
or conbination of the following:

  * Admin RESTful API
  * vCon RESTful API
  * Pipeline server with configured number of workers

The open source repository at: https://github.com/py-vcon/py-vcon
"""
 
restapi = fastapi.FastAPI(
  title = "Python vCon Server",
  description = description,
  summary = "vCon pipeline processor server cluster and storage API",
  version = __version__,
  # terms_of_service = "",
  contact = {
    "name": "Commercial support available from SIPez",
    "url": "http://www.sipez.com",
    },
    # email": "user@example.com",
  license_info = {
    "name": "MIT License"
    },
  openapi_tags = openapi_tags
  )

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

