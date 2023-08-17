""" Common setup and components for the RESTful APIs """
import pydantic
import fastapi
from py_vcon_server import __version__
import py_vcon_server.logging_utils

logger = py_vcon_server.logging_utils.init_logger(__name__)


class HttpErrorResponseBody(pydantic.BaseModel):
  """ Error return type object for APIs """
  detail: str

ERROR_RESPONSES = {
  404: {
    "model" : HttpErrorResponseBody
    },
  500: {
    "model" : HttpErrorResponseBody
    }
}


class NotFoundResponse(fastapi.responses.JSONResponse):
  """ Helper class to handle 404 Not Found cases """
  def __init__(self, detail: str):
    super().__init__(status_code = 404,
      content = {"detail": detail})

class InternalErrorResponse(fastapi.responses.JSONResponse):
  """ Helper class to handle 500 internal server error case """
  def __init__(self, exception: Exception):
    super().__init__(status_code = 500,
      content = {"detail": str(exception)})


def log_exception(exception: Exception):
  """ General exception logger for APIs """
  logger.info("Error: Exception: {} {}".format(exception.__class__.__name__, exception))

# These are used to label different sections or groups of FastAPI entry points
SERVER_TAG = "Admin: Servers"
QUEUE_TAG = "Admin: Job Queues"
IN_PROGRESS_TAG = "Admin: In Progress Jobs"
VCON_TAG = "vCon Storage CRUD"
PROCESSOR_TAG = "vCon Processors"

openapi_tags = [
  {
    "name": SERVER_TAG,
    "description": "Entry points to get and set server information",
    # "externalDocs": {
    #   "description": "online docs",
    #   "url": None
    # }
  },
  {
    "name": QUEUE_TAG,
    "description": "Entry points to create, operate on, add to and delete job queues",
    # "externalDocs": {
    #   "description": "online docs",
    #   "url": None
    # }
  },
  {
    "name": IN_PROGRESS_TAG,
    "description": "Entry points to get, operate on in progress pipeline job states",
    # "externalDocs": {
    #   "description": "online docs",
    #   "url": None
    # }
  },
  {
    "name": VCON_TAG,
    "description": "Entry points to get, query, modify or delete vCons in storage",
    # "externalDocs": {
    #   "description": "online docs",
    #   "url": None
    # }
  },
  {
    "name": PROCESSOR_TAG,
    "description": "Entry points to run a single processor on a vCon"
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
def init() -> fastapi.FastAPI:
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

  return(restapi)

