# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
""" Common setup and components for the RESTful APIs """
import typing
import traceback
import pydantic
import fastapi
import fastapi.middleware.cors
import vcon
from py_vcon_server import __version__
import py_vcon_server.logging_utils
import py_vcon_server.settings

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


class ValidationError(fastapi.responses.JSONResponse):
  """ Helper class to handle 422 validation error case"""
  def __init__(self, detail: str):
    super().__init__(status_code = 422,
      content = {"detail": detail})


class ProcessingTimeout(fastapi.responses.JSONResponse):
  """ Helper class to indicate timeouts when processing or waiting for subordinate request """
  def __init__(self, detail: str):
    super().__init__(status_code = 430,
      content = {"detail": detail})


class InternalErrorResponse(fastapi.responses.JSONResponse):
  """ Helper class to handle 500 internal server error case """

  def __init__(
      self, 
      exception: Exception,
      extra_content: typing.Union[None, typing.Dict[str, typing.Any]] = None
    ):

    content = {
        "detail": "Exception: {} {} {}".format(exception.__class__.__name__, exception.__cause__, exception.__context__),
        "exception": "{}".format(exception),
        "exception_args": "{}".format(exception.args),
        #"exception_dir": "{}".format(dir(exception)),
        "exception_module": "{}".format(getattr(exception, "__module__", None)),
        "exception_class": "{}".format(exception.__class__.__name__),
        "exception_stack": traceback.format_exception(None, exception, exception.__traceback__),
        # Make it easier for reporting issues by including versions
        "py_vcon_server_version": __version__,
        "py_vcon_version": vcon.__version__
      }

    if(extra_content is not None):
      for name in extra_content:
        content[name] = extra_content[name]

    super().__init__(
        status_code = 500,
        content = content
      )


def log_exception(exception: Exception):
  """ General exception logger for APIs """
  # Brief:
  #logger.info("Error: Exception: {} {}".format(exception.__class__.__name__, exception))
  # Full:
  logger.exception(exception)

# These are used to label different sections or groups of FastAPI entry points
SERVER_TAG = "Admin: Servers"
QUEUE_TAG = "Admin: Job Queues"
PIPELINE_CRUD_TAG = "Admin: Pipelines"
IN_PROGRESS_TAG = "Admin: In Progress Jobs"
VCON_TAG = "vCon: Storage CRUD"
PROCESSOR_TAG = "vCon: Processors"
PIPELINE_RUN_TAG = "vCon: Pipelines"

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
    "name": PIPELINE_CRUD_TAG,
    "description": "Entry points to create, update and delete pipelines\n\n"
       "**New:** [Visual Pipeline Editor](./pipeline_editor/index.html) (Note: link works only on live server)",
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
  },
  {
    "name": PIPELINE_RUN_TAG,
    "description": "Entry points to run a pipeline of processor(s) on a vCon"
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

**New:**

  * [Visual Pipeline Editor](./pipeline_editor/index.html) (Note: link works only on live server)

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

  # Paths that need root_path for correct OpenAPI server URL generation
  OPENAPI_PATHS = {'/openapi.json', '/docs', '/redoc'}

  # Middleware to read X-Forwarded-Prefix from nginx and set ASGI root_path
  # This makes FastAPI advertise the correct nginx-prefixed URL in openapi.json
  # so Swagger UI "Try it out" / Execute sends requests to the right nginx path.
  # Has no effect when accessed directly (no X-Forwarded-Prefix header present).
  @restapi.middleware("http")
  async def set_root_path_from_header(request: fastapi.Request, call_next):
    forwarded_prefix = request.headers.get("x-forwarded-prefix")
    if forwarded_prefix and request.url.path in OPENAPI_PATHS:
      request.scope["root_path"] = forwarded_prefix
    return await call_next(request)

  # CORS stuff
  logger.debug("CORS_ORIGINS: {}".format(py_vcon_server.settings.CORS_ORIGINS))
  if(py_vcon_server.settings.CORS_ORIGINS):
    logger.info("Enabling CORS for {}".format(py_vcon_server.settings.CORS_ORIGINS))
    restapi.add_middleware(
        fastapi.middleware.cors.CORSMiddleware,
        allow_origins=py_vcon_server.settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
      )

  if(py_vcon_server.settings.ENABLE_PROMETHEUS):
    logger.info("Prometheus metrics enabled")

    import prometheus_fastapi_instrumentator
    import prometheus_fastapi_instrumentator.metrics
    import prometheus_client
    def http_requests_by_client():
      metric = prometheus_client.Counter(
          'http_requests_by_client_total',
          'Total requests by calling service',
          ['client_host', 'method', 'handler', 'status']
        )

      def instrumentation(info: prometheus_fastapi_instrumentator.metrics.Info) -> None:
        client_host = info.request.client.host
        metric.labels(
            client_host=client_host,
            method=info.method,
            handler=info.modified_handler,
            status=info.modified_status
          ).inc()

      return instrumentation

    prometheus_instrumentor = prometheus_fastapi_instrumentator.Instrumentator(
        should_group_status_codes = False,
        should_ignore_untemplated = False,
        should_respect_env_var = False,
        should_instrument_requests_inprogress = True,
        excluded_handlers=["/metrics"],
        #inprogress_name="http_requests_inprogress",
        inprogress_labels=True,
      )

    # Default out of the box FASTapi metrices
    # Per entry point stats
    # Add request counter (http_requests_total)
    prometheus_instrumentor.add(prometheus_fastapi_instrumentator.metrics.requests())

    # Add latency with custom buckets (seconds)
    prometheus_instrumentor.add(
      prometheus_fastapi_instrumentator.metrics.latency(
          buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0)
        )
      )

    # Per client stats
    prometheus_instrumentor.add(http_requests_by_client())
    prometheus_instrumentor.instrument(restapi)
    prometheus_instrumentor.expose(restapi)

  else:
    logger.info(f"Prometheus metrics disabled ({py_vcon_server.settings.ENABLE_PROMETHEUS})")

  return(restapi)

