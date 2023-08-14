import typing
import fastapi.responses
import pydantic
import py_vcon_server
import py_vcon_server.logging_utils
import py_vcon_server.settings
from . import __version__
import vcon

logger = py_vcon_server.logging_utils.init_logger(__name__)

class QueueProperties(pydantic.BaseModel):
    weight: int = 1

class QueueJob(pydantic.BaseModel): # may need to add extra=pydantic.Extra.allow
    job_type: str = "vcon_uuid"
    vcon_uuids: typing.List[str] = []

def init(restapi):

  @restapi.get("/server/info")
  async def get_server_info():
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


  @restapi.get("/servers")
  async def get_server_states():
    """ Get a JSON dictionary of running server states """

    try:
      logger.debug("getting servers")
      server_dict = await py_vcon_server.server_state.get_server_states()

    except Exception as e:
      logger.info("Error: {}".format(e))
      return None

    logger.debug( "Returning {} servers".format(len(server_dict)))
    logger.debug( "servers type: {}".format(type(server_dict)))
    logger.debug( "servers: {}".format(server_dict))

    return(fastapi.responses.JSONResponse(content=server_dict))


  @restapi.delete("/servers/{server_key}")
  async def delete_server_state(server_key: str):
    """
    Delete the server state entry for the given server_key.
    <br><i> This should generally only used to clean up server states for servers that did not gracefully shutdown.</i>

    The server key is composed as: "host:port:pid:start_time".
    <br>  host and port are from the REST_URL setting.
    """

    try:
      logger.debug("deleting server state: {}".format(server_key))
      server_dict = await py_vcon_server.server_state.delete_server_state(server_key)

    except Exception as e:
      logger.info("Error: {}".format(e))
      return 500

    logger.debug("Deleted server state: {}".format(server_key))

    # no return should cause 204, no content


  @restapi.get("/server/queues")
  async def get_server_queues():
    """ Get the list of queues and related configuration for for this server """
    try:
      logger.debug("getting server queue info")
      queue_info = py_vcon_server.settings.WORK_QUEUES
    
    except Exception as e:
      logger.info("Error: {}".format(e))
      return None

    return(fastapi.responses.JSONResponse(content=queue_info))


  @restapi.post("/server/queue")
  async def post_server_queue(properties: QueueProperties, name: str) -> None:
    """
    Set the properties on the named queue on this server.

    <br> Currently the only queue property is the "weight".
    weight must be an integer value and indicates how many
    items should be de-queued from the given queue before
    rotating to hte nex queue.
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


  @restapi.delete("/server/queue/{name}")
  async def delete_server_queue(name: str):
    """
    Remove the named queue from the list of queues to process on this server
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


  @restapi.get("/queues")
  async def get_job_queue_names():
    """ Get a list of the names of all the job queues """

    try:
      logger.debug("getting queue names")
      queue_names = list(await py_vcon_server.queue.JOB_QUEUE.get_queue_names())

    except Exception as e:
      logger.info("Error: {}".format(e))
      return None

    logger.debug( "Returning queues: {} ".format(queue_names))

    return(fastapi.responses.JSONResponse(content=queue_names))


  @restapi.get("/queue/{name}")
  async def get_queued_jobs(name: str):
    """
    Get the jobs queued in the named queue.

    <br> Note: this is only for montoring purposes,
    Do not use this to operate on a queue as removing a job
    and placing it in an inprogress state should be an atomic
    operation.
    """

    try:
      logger.debug("getting jobs in queue: {}".format(name))
      jobs = await py_vcon_server.queue.JOB_QUEUE.get_queue_jobs(name)

    except Exception as e:
      logger.info("Error: {}".format(e))
      return None

    logger.debug( "Returning queue: {} jobs: {}".format(name, jobs))

    return(fastapi.responses.JSONResponse(content=jobs))


  @restapi.put("/queue/{name}")
  async def add_queue_job(name: str, job: QueueJob):
    """ Add the given job to the named queue """

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


  @restapi.post("/queue/{name}")
  async def create_new_job_queue(name: str):
    """ Create the named new queue """

    try:
      logger.debug("Creating new queue: {}".format(name))
      # TODO should error if queue exists
      await py_vcon_server.queue.JOB_QUEUE.create_new_queue(name)

    except Exception as e:
      logger.info("Error: {}".format(e))
      return None

    logger.debug( "Created new queue: {}".format(name))

    # no return should cause 204, no content


  @restapi.delete("/queue/{name}")
  async def delete_job_queue(name: str) -> typing.List[dict]:
    """
    Delete the named job queue and return any jobs that were in the queue.
    """

    try:
      logger.debug("Delete job queue: {}".format(name))
      jobs = await py_vcon_server.queue.JOB_QUEUE.delete_job_queue(name)

    except Exception as e:
      logger.info("Error: {}".format(e))
      return None

    logger.debug( "Deleted queue: {}, {} jobs removed from queue.".format(name, len(jobs)))

    return(fastapi.responses.JSONResponse(content = jobs))


  @restapi.get("/jobs/in_progress")
  async def get_in_progress_jobs() -> typing.Dict[int, dict]:
    """
    Get the list of jobs which are dequeued and supposed to be work in progress on a server."

    Returns: dict - dict of in progress job data (dict) where key is the unique int job id.
      The job data dict contains the following keys:
        jobid: int - unique job id for this job on the given server
        queue: str - name of the queue from which the job was popped
        job: dict - queue job object (keys: job_type: str and job type specific keys)
        start: float - epoch time UTC when the job was dequeued
        server: str - server_key: "<host>:<port>:<pid>:start_time>" for server
          which will run the job, this is attained from the "/servers" entry 
          point in the admin REST API or from ServerState.server_key()
    """

    try:
      logger.debug("getting in progress jobs")
      jobs = await py_vcon_server.queue.JOB_QUEUE.get_in_progress_jobs()

    except Exception as e:
      logger.info("Error: {}".format(e))
      return None

    logger.debug( "Got in progress jobs: {}.".format(jobs))

    return(fastapi.responses.JSONResponse(content = jobs))


  @restapi.put("/jobs/in_progress/{job_id}")
  async def requeue_in_progress_job(job_id: int) -> None:
    """
    Requeue the in process job indicated by its job id and
    put it at the front of the queue from which it came.
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


  @restapi.delete("/jobs/in_progress/{job_id}")
  async def remove_in_progress_job(job_id: int) -> None:
    """
    Remove the in process job indicated by its job id and
    do NOTE add it back to the queue from which it came.
    This does not cancel the job if it is still in progress.
    This is typically used to cancel, rather than reschedule,
    jobs from  a server that has stalled or died.
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
