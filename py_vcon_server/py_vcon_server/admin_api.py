import typing
import time
import os
import fastapi.responses
import pydantic
import py_vcon_server
import py_vcon_server.logging_utils
import py_vcon_server.settings
from . import __version__
import vcon

logger = py_vcon_server.logging_utils.init_logger(__name__)

SERVER_TAG = "Admin: Servers"
QUEUE_TAG = "Admin: Job Queues"
IN_PROGRESS_TAG = "Admin: In Progress Jobs"

class ServerInfo(pydantic.BaseModel):
    py_vcon_server: str = pydantic.Field(
      title = "server version",
      description= "Python package py_vcon_server version number",
      default = py_vcon_server.__version__
      )
    vcon: str  = pydantic.Field(
      title = "vcon version",
      description = "Python package **py_vcon** version number",
      default = vcon.__version__
      )
    start_time: float = pydantic.Field(
      title = "server start time",
      description = "epoch seconds time at which this server started",
      example = time.time()
      )
    pid: int = pydantic.Field(
      title = "server process id",
      example = os.getpid()
      )


class ServerState(pydantic.BaseModel):
    host: str = pydantic.Field(
      title = "server host",
      description = "the server's host as configured in the REST_URL",
      examples = ["locahost", "192.168.0.23", "example.com"]
      )
    port: int = pydantic.Field(
      title = "server port",
      description = "the server's port as configured in the REST_URL",
      example = 8000
      )
    pid: int = pydantic.Field(
      title = "server process id",
      example = os.getpid()
      )
    start_time: float = pydantic.Field(
      title = "server start up time",
      description = "epoch seconds time at which this server started",
      example = time.time()
      )
    num_workers: int = pydantic.Field(
      title = "number of server worker processes",
      description = "the number of pipeline worker processes configured in NUM_WORKERS for this server",
      example = 4
      )
    state: str = pydantic.Field(
      title = "server state",
      examples = ["starting_up", "running", "shutting_down", "unknown"],
      example = "running"
      )
    last_heartbeat: float = pydantic.Field(
      title = "heartbeat time stamp",
      description = "epoch seconds time for the last heartbeat on this server",
      example = time.time()
      )


class QueueProperties(pydantic.BaseModel):
    weight: int = pydantic.Field(
      title = "server's queue weight",
      description = "number of times that the pipeline server should pop a job from this queue before iterating to the server's next queue.",
      default = 1
      )


class QueueJob(pydantic.BaseModel): # may need to add extra=pydantic.Extra.allow
    job_type: str = pydantic.Field(
      description = "queue job type (currently only \"vcon_uuid\" allowed)",
      default = "vcon_uuid"
      )
    vcon_uuids: typing.List[str] = pydantic.Field(
      title = "vCon UUIDs",
      description = "array of vCon UUIDs (currently must be exactly 1)",
      example = ["0185656d-fake-UUID-84fd-5b4de1ef42b4"],
      default = []
      )


class InProgressJob(pydantic.BaseModel):
    jobid: int = pydantic.Field(
      title = "job id",
      description = "unique (across all pipeline servers) integer job id for this in progress job",
      example = 3456
      )
    queue: str = pydantic.Field(
      title = "job queue name",
      description = "the job queue name from which this in progress job was popped"
      )
    job: QueueJob = pydantic.Field(
      description = "the queue job that was popped by the pipeline server and initiated this in progress job"
      )
    start: float = pydantic.Field(
      title = "job start time",
      description = "epoch seconds time at which this in progress job started",
      example = time.time()
      )
    server: str = pydantic.Field(
      title = "server key",
      description = "the server key to the pipeline server upon which this in progress job is running."
      + "<br> server_keys are of the format host:port:pid:start_time"
      + "<br> to iterate server keys see entry point get /servers.",
      example = "localhost:8000:765:1692125691.2032259"
      )


def init(restapi):

  @restapi.get("/server/info",
    response_model = ServerInfo,
    tags = [ SERVER_TAG ])
  async def get_server_info() -> ServerInfo:
    """
    Get information about the server running at this host and port.

    Returns: ServerInfo - attributes of this server.
    """

    try:
      logger.debug("getting server info")
      info = {
        "py_vcon_server": __version__,
        "vcon": vcon.__version__,
        "start_time": py_vcon_server.states.SERVER_STATE.start_time(),
        "pid": py_vcon_server.states.SERVER_STATE.pid()
        }

    except Exception as e:
      logger.info("Error: {}".format(e))
      return None

    logger.debug( "Returning server info")

    return(fastapi.responses.JSONResponse(content=info))


  @restapi.get("/servers",
    response_model = typing.Dict[str, ServerState],
    tags = [ SERVER_TAG ])
  async def get_server_states() -> ServerState:
    """
    Get a JSON dictionary of running server states

    Returns: dict[server_key, ServerState] where keys are server_keys 
    <br> The value associated with the server key is a dict containing server info 

    The list may contain servers which did not gracefully shutdown.
    It is up to the user to remove these stale server states and
    clean up and requeue any in_progress jobs which the server did
    not complete.  A pipeline of well behaved processors does not
    commit changes until all of the pipeline's processor have
    completed.  Assuming this is the case,
    the following pseudo code will clean up appropriately:
    NOTE: This is not done automatically as it is a DEV OPS 
    policy issue and is dependent upon potentially custom or
    proprietary processors behavor.

        get the list of server states from the /servers entry point
        for each unique pair of server hosts and ports:
            get the active server key from the /server/info entry point
            for stale server_keys (all other server keys with the same host:port prefix):
               for all of the in_progress jobs having the stale server_key (entry point: /in_progress):
                   requeue the job (entry point: put /_in_progress/{job_id}
               remove the stale server (entry point: delete /servers/{server_key}
    """

    try:
      logger.debug("getting servers")
      server_dict = await py_vcon_server.states.SERVER_STATE.get_server_states()

    except Exception as e:
      logger.info("Error: {}".format(e))
      return None

    logger.debug( "Returning {} servers".format(len(server_dict)))
    logger.debug( "servers type: {}".format(type(server_dict)))
    logger.debug( "servers: {}".format(server_dict))

    return(fastapi.responses.JSONResponse(content=server_dict))


  @restapi.delete("/servers/{server_key}",
    tags = [ SERVER_TAG ])
  async def delete_server_state(server_key: str):
    """
    Delete the server state entry for the given server_key.
    <br><i> This should generally only be used to clean up server states for servers that did not gracefully shutdown.</i>

    Before doing this, you may want to check to see if
    there are in progress jobs (via the /in_progress entry
    point) left over for this server and requeue them.

    The server key is composed as: "host:port:pid:start_time".
    <br>  host and port are from the REST_URL setting.
    """

    try:
      logger.debug("deleting server state: {}".format(server_key))
      server_dict = await py_vcon_server.states.SERVER_STATE.delete_server_state(server_key)

    except Exception as e:
      logger.info("Error: {}".format(e))
      return 500

    logger.debug("Deleted server state: {}".format(server_key))

    # no return should cause 204, no content


  @restapi.get("/server/queues",
    response_model = typing.Dict[str, QueueProperties],
    tags = [ QUEUE_TAG ])
  async def get_server_queues_names():
    """
    Get the list of queues and related configuration for
    for this server.

    This is the list names of queues that this server is
    actively popping jobs from and running the pipeline
    processors assocated with the queue name.

    Returns: dict[str, dict] - dict with keys being queue names and values are a dict of queue properties

    keys for queue properties:

        weight: int - number of times to pull a job out of the
            named queue, before iterating to the next name
            queue configured for this server.
    """

    try:
      logger.debug("getting server queue info")
      queue_info = py_vcon_server.settings.WORK_QUEUES
    
    except Exception as e:
      logger.info("Error: {}".format(e))
      return None

    return(fastapi.responses.JSONResponse(content=queue_info))


  @restapi.post("/server/queue/{name}",
    response_model = None,
    tags = [ QUEUE_TAG ])
  async def set_server_queue_properties(properties: QueueProperties, name: str) -> None:
    """
    Set the properties on the named queue on this server.

    This adds or updated the properties for the queue and
    identifies the queue to be processed by this server
    using the pipeline processors associated with this
    queue name.

    Currently the only queue property is the "weight".
    weight must be an integer value and indicates how many
    jobs should be popped from the named queue before
    iterating to the next queue configured for this server.
    Jobs are popped one at a time by the server such that
    the configured NUM_WORKERS are each busy on one job at
    a time.  These jobs that the server is busy on are 
    called in_progress jobs.

    Returns: None
    """

    try:
      logger.debug("setting queue: {} property: {}".format(name, properties))
      if(not isinstance(properties, QueueProperties)):
        raise Exception("Invalid type: {} for queue: {} properties: {}".format(type(properties), name, properties))
      py_vcon_server.settings.WORK_QUEUES[name] = dict(properties)
      logger.debug("WORK_QUEUES: {}".format(py_vcon_server.settings.WORK_QUEUES))

    except Exception as e:
        logger.info("Error: {}".format(e))
        return None

    # no return should cause 204, no content


  @restapi.delete("/server/queue/{name}",
    tags = [ QUEUE_TAG ])
  async def delete_server_queue(name: str):
    """
    Remove the named queue from the list of queues to process on this server.

    This indicates, to this server, to ignore the queue deleted from the server's queue list.
    This does not remove or modify the queue itself or the jobs contained in the queue.
    """

    try:
      logger.debug("removing queue: {} from WORK_QUEUES".format(name))

      if(py_vcon_server.settings.WORK_QUEUES.get(name, None) is None):
        raise(fastapi.HTTPException(status_code=404,
          detail="queue: {} not found".format(name)))

      del py_vcon_server.settings.WORK_QUEUES[name]

    except Exception as e:
        logger.info("Error: {}".format(e))
        return None

    # no return should cause 204, no content


  @restapi.get("/queues",
    response_model = typing.List[str],
    tags = [ QUEUE_TAG ])
  async def get_job_queue_names():
    """
    Get a list of the names of all the job queues.

    Jobs are added to queues from which they are popped
    to run through a pipeline (set of processors).
    The jobs pipeline server(s) pop jobs from the list
    of names of queues, configured for the server to watch.
    The server runs the set of processors configured in
    the pipeline, having the same name as the queue.
    Most pipeline processors create, operate on or modify
    a vCon and have zero or more vCons as input and zero
    or more vCons as output.

    Returns: list[str] - queue names
    """

    try:
      logger.debug("getting queue names")
      queue_names = list(await py_vcon_server.queue.JOB_QUEUE.get_queue_names())

    except Exception as e:
      logger.info("Error: {}".format(e))
      return None

    logger.debug( "Returning queues: {} ".format(queue_names))

    return(fastapi.responses.JSONResponse(content=queue_names))


  @restapi.get("/queue/{name}",
    response_model = typing.List[QueueJob],
    tags = [ QUEUE_TAG ])
  async def get_queued_jobs(name: str):
    """
    Get the jobs queued in the named queue.

    These jobs are input to the pipeline, having
    the same name as the queue, when a pipeline
    server worker is available to work on it.

    Note: this is only for montoring purposes,
    Do not use this to operate on a queue as removing a job
    and placing it in an in progress state should be an atomic
    operation.

    Returns: list[dict] - list of job objects in the queue
    """

    try:
      logger.debug("getting jobs in queue: {}".format(name))
      jobs = await py_vcon_server.queue.JOB_QUEUE.get_queue_jobs(name)

    except Exception as e:
      logger.info("Error: {}".format(e))
      return None

    logger.debug( "Returning queue: {} jobs: {}".format(name, jobs))

    return(fastapi.responses.JSONResponse(content=jobs))


  @restapi.put("/queue/{name}",
    response_model = int,
    tags = [ QUEUE_TAG ])
  async def add_queue_job(name: str, job: QueueJob):
    """
    Add the given job to the named job queue.

    Currently only one job_type is supported: "vcon_uuid"
    which has an array of vCon UUIDs contained in
    vcon_uuids.  vcon_uuids is currently liimited to
    exactly one vCon UUID.

    Returns: int - the positiion of the added job in the queue.
    """

    try:
      logger.debug("adding job: {} to queue: {}".format(job, name))
      # TODO should error if queue does not exist???
      if(job.job_type is not "vcon_uuid"):
        logger.info("Error: unsupport job type: {}".format(job.job_type))

      queue_length = await py_vcon_server.queue.JOB_QUEUE.push_vcon_uuid_queue_job(name, job.vcon_uuids)

    except Exception as e:
      logger.info("Error: {}".format(e))
      return None

    logger.debug( "job: {} added to queue: {}".format(job, name))

    # TODO: return queue length ???
    return(fastapi.responses.JSONResponse(content = queue_length))


  @restapi.post("/queue/{name}",
    tags = [ QUEUE_TAG ])
  async def create_new_job_queue(name: str):
    """
    Create the named new job queue.

    You must also define a pipeline of processors (entry point
    post /pipeline) with the same name as this new queue.
    You must then configure one or more pipeline servers
    to perform the pipeline processing for the jobs in the
    queue, by adding the queue name to the set of queues
    for the server to monitor (entry point /server/queues).
    Without defining a pipeline and one or more servers to
    perform them, the jobs will just sit in the queue.
    """

    try:
      logger.debug("Creating new queue: {}".format(name))
      # TODO should error if queue exists
      await py_vcon_server.queue.JOB_QUEUE.create_new_queue(name)

    except Exception as e:
      logger.info("Error: {}".format(e))
      return None

    logger.debug( "Created new queue: {}".format(name))

    # no return should cause 204, no content


  @restapi.delete("/queue/{name}",
    response_model = typing.List[QueueJob],
    tags = [ QUEUE_TAG ])
  async def delete_job_queue(name: str) -> typing.List[QueueJob]:
    """
    Delete the named job queue and return any jobs that were in the queue.

    Returns: list[dict] - list of jobs that were in the queue
    """

    try:
      logger.debug("Delete job queue: {}".format(name))
      jobs = await py_vcon_server.queue.JOB_QUEUE.delete_job_queue(name)

    except Exception as e:
      logger.info("Error: {}".format(e))
      return None

    logger.debug( "Deleted queue: {}, {} jobs removed from queue.".format(name, len(jobs)))

    return(fastapi.responses.JSONResponse(content = jobs))


  @restapi.get("/in_progress",
    response_model = typing.Dict[int, InProgressJob],
    tags = [ IN_PROGRESS_TAG ])
  async def get_in_progress_jobs() -> typing.Dict[int, InProgressJob]:
    """
    Get the list of jobs which are dequeued and supposed to be work in progress on a pipeline server.

    Returns: dict - dict of in progress job objects (dict) where the keys are the unique int job id.
    """

    try:
      logger.debug("getting in progress jobs")
      jobs = await py_vcon_server.queue.JOB_QUEUE.get_in_progress_jobs()

    except Exception as e:
      logger.info("Error: {}".format(e))
      return None

    logger.debug( "Got in progress jobs: {}.".format(jobs))

    return(fastapi.responses.JSONResponse(content = jobs))


  @restapi.put("/in_progress/{job_id}",
    tags = [ IN_PROGRESS_TAG ])
  async def requeue_in_progress_job(job_id: int) -> None:
    """
    Requeue the in process job indicated by its job id and
    put it at the front (first to be worked on) of the job
    queue from which it came.

    WARNING: This does not cancel the job if it is still in
    progress.
    Requeing an in progress job while a pipeline server is
    still working on it will have unpredictable results.
    
    This is typically used to reschedule, rather than cancel,
    jobs from  a server that has hung or died (see entry point get /servers).
    """

    try:
      logger.debug("removing job: {} from in progress and pushing to queue")
      if(not isinstance(job_id, int)):
        logger.info("Error: unsupport job_id type: {}".format(job_id))
        return None

      await py_vcon_server.queue.JOB_QUEUE.requeue_in_progress_job(job_id)

    except Exception as e:
      logger.info("Error: {}".format(e))
      return None

    logger.debug( "job: {} added to front of queue".format(job_id))

    # No return, should respond with 204


  @restapi.delete("/in_progress/{job_id}",
    tags = [ IN_PROGRESS_TAG ])
  async def remove_in_progress_job(job_id: int) -> None:
    """
    Remove the in progress job indicated by its job id and
    do NOT add it back to the queue from which it came.

    WARNING: This does not cancel the job if it is still in
    progress.
    Removing an in progress job while a pipeline server is
    still working on it will have unpredictable results.
    
    This is typically used to cancel, rather than reschedule,
    jobs from  a server that has hung or died
    (see entry point get /servers).

    Returns: None
    """

    try:
      logger.debug("removing job: {} from in progress")
      if(not isinstance(job_id, int)):
        logger.info("Error: unsupport job_id type: {}".format(job_id))
        return None

      await py_vcon_server.queue.JOB_QUEUE.requeue_in_progress_job(job_id)

    except Exception as e:
      logger.info("Error: {}".format(e))
      return None

    logger.debug( "job: {} removed from in progress hash".format(job_id))

    # No return, should respond with 204

