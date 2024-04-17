# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" Vcon Pipeline processor objects and methods """
import os
import typing
import time
import asyncio
import json
import pydantic
import py_vcon_server.processor
import py_vcon_server.job_worker_pool
import py_vcon_server.logging_utils
#import remote_pdb

VERBOSE = False

logger = py_vcon_server.logging_utils.init_logger(__name__)

PIPELINE_NAMES_KEY = "pipelines"
PIPELINE_NAME_PREFIX = "pipeline:"

PIPELINE_DB = None
VCON_STORAGE = None


class PipelineNotFound(Exception):
  """ Raised when Pipeline not found in the DB """

class PipelineInvalid(Exception):
  """ Raised for invalild pipelines """


class PipelineTimeout(Exception):
  """ Raised when pipeline exceeds its processing timeout """


class PipelineProcessor(pydantic.BaseModel):
  """
  Configuration for a VconProcessor in a Pipeline
  """
  processor_name: str = pydantic.Field(
      title = "VconProcessor name"
    )

  processor_options: py_vcon_server.processor.VconProcessorOptions = pydantic.Field(
      title = "VconProcessor options"
    )


class PipelineOptions(pydantic.BaseModel):
  """
  Options the effect the handling of Vcon Pipeline processing.
  """

  save_vcons: typing.Union[bool, None] = pydantic.Field(
      title = "save/update vCon(s) after pipeline processing"
    )

  timeout: typing.Union[float, int, None] = pydantic.Field(
      title = "processor timeout",
      description = """maximum timeout for any processor in the pipeline.
  If any one of the processors in the pipeline takes more than this number
 of seconds, the processor will be cancled, remaining processors will be
 skipped and the pipeline will be considered failed for the given job/vCon.
""",
  default = None
    )

  failure_queue: typing.Union[str, None] = pydantic.Field(
      title = "queue for failed pipeline jobs",
      description = """If any of the processors in the pipeline or dependant DB access fail,
 the job is added to the failure_queue if set.
"""
    )

  success_queue: typing.Union[str, None] = pydantic.Field(
      title = "queue for successfully run pipeline jobs",
      description = """If all of the processors in the pipeline succeed in running,
 the job is added to the success_queue if set.
"""
    )


class PipelineDefinition(pydantic.BaseModel):
  """ Definition of the serialized representation of a VconPipeline """
  # queue_name should this be a field or is it implied by the name the pipeline is stored under???
  # sequence: typing.List[VconProcessorAndOptions] or list[VconProcessor names] and list[VconProcessorOptions]

  pipeline_options: PipelineOptions = pydantic.Field(
      title = "pipeline execution options"
    )

  processors: typing.List[PipelineProcessor] = pydantic.Field(
      title = "list of **VconProcessorConfig**",
      description = "The sequential set of **VconProcessorConfig** for the list of \
**VconProcessor**s that get run for this **Pipeline**"
    )


class PipelineDb():
  """ DB interface for Pipeline objects """
  def __init__(self, redis_url: str):
    logger.info("connecting PipelineDb redis_mgr pid: {}".format(os.getpid()))
    self._redis_mgr = py_vcon_server.db.redis.redis_mgr.RedisMgr(redis_url, "PipelineDB")
    self._redis_mgr.create_pool()

    # we can gain some optimization by registering all of the Lua scripts here
    redis_con = self._redis_mgr.get_client()

    # Lua scripts

    #keys = [ PIPELINE_NAMES_KEY, PIPELINE_NAME_PREFI + name ]
    #args = [ name, pipeline ]
    lua_script_set_pipeline = """
    -- Add the pipeline name to the name list if its new
    if redis.call("SISMEMBER", KEYS[1], ARGV[1]) == 0 then
      local num_added = redis.call("SADD", KEYS[1],  ARGV[1])
      -- Don't care if the name already exists
    end
    local ret = redis.call("JSON.SET", KEYS[2], "$", ARGV[2])
    return(ret)
    """
    self._do_lua_set_pipeline = redis_con.register_script(lua_script_set_pipeline)

    #keys = [ PIPELINE_NAMES_KEY, PIPELINE_NAME_PREFIX + name ]
    #args = [ name ]
    lua_script_delete_pipeline = """
    local ret = -2
    if redis.call("SISMEMBER", KEYS[1], ARGV[1]) == 1 then
      -- pipeline name is in the pipeline list, remove it
      redis.call("SREM", KEYS[1], ARGV[1])
      ret = 0 
    else
      ret = -1 
    end
    -- Always try to delete the pipeline even if its not in the list
    redis.call("DEL", KEYS[2])
    return(ret)
    """
    self._do_lua_delete_pipeline = redis_con.register_script(lua_script_delete_pipeline)



  async def shutdown(self):
    """ Shutdown the DB connection """
    if(self._redis_mgr):
      logger.debug("shutting down PipelineDb redis_mgr")
      await self._redis_mgr.shutdown_pool()
      self._redis_mgr = None
      logger.info("shutdown PipelineDb redis_mgr")


  async def get_pipeline_names(
      self,
    )-> typing.List[str]:
    """
    Get the list of names of all Pipelines.

    Parameters: none

    Returns: list[str] - names of all pipelines
    """
    redis_con = self._redis_mgr.get_client()
    return(await redis_con.smembers(PIPELINE_NAMES_KEY))


  async def set_pipeline(
      self,
      name: str,
      pipeline: typing.Union[dict, PipelineDefinition]
    )-> None:
    """
    Add or replace a Pipeline definition.

    Parameters:
      **name**: str - the name of the Pipeline to replace or create.
      **pipeline**: PipelineDefinition - Pipeline to create

    Returns: none
    """
    assert(isinstance(name, str))
    keys = [ PIPELINE_NAMES_KEY, PIPELINE_NAME_PREFIX + name ]
    if(isinstance(pipeline, dict)):
      args = [ name, json.dumps(pipeline) ]
    else:
      args = [ name, json.dumps(pipeline.dict()) ]

    result = await self._do_lua_set_pipeline(keys = keys, args = args)
    if(result != "OK"):
      raise Exception("set_pipeline {} Lua failed: {} pipeline: {}".format(name, result, pipeline))


  async def get_pipeline(
      self,
      name: str
    )-> PipelineDefinition:
    """
    Get the named **PipelineDefinition** from DB.

    Parameters:
      **name**: str - name of the PipelineDefinition to retieve

    Returns: PipelineDefinition if found, 
             exception PipelineNotFound if name does not exist
    """
    redis_con = self._redis_mgr.get_client()
    logger.debug("getting pipeline: {} redis con: {} pid: {}".format(name, redis_con, os.getpid()))
    try:
      pipeline_dict = await redis_con.json().get(PIPELINE_NAME_PREFIX + name, "$")
      logger.debug("returned from getting pipeline: {}".format(name))
    except Exception as e:
      logger.debug("pipeline redis get exception: {}".format(e))
      raise e

    if(pipeline_dict is None):
      logger.debug("pipeline: {} not found".format(name))
      raise PipelineNotFound("Pipeline {} not found".format(name))

    if(len(pipeline_dict) != 1):
      logger.debug("pipeline get({}) error: {}".format(name, pipeline_dict))
      raise PipelineInvalid("Pipeline {} got: {}".format(name, pipeline_dict))

    logger.debug("got pipeline: {}".format(name))
    return(PipelineDefinition(**pipeline_dict[0]))


  async def delete_pipeline(
      self,
      name: str
    )-> None:
    """
    Delete the named **PipelineDefinition** from DB.

    Parameters:
      **name**: str - name of the PipelineDefinition to delete

    Returns: none
             exception PipelineNotFound if name does not exist
    """
    assert(isinstance(name, str))
    keys = [ PIPELINE_NAMES_KEY, PIPELINE_NAME_PREFIX + name ]
    args = [ name ]
    result = await self._do_lua_delete_pipeline(keys = keys, args = args)
    if(result == -1):
      raise PipelineNotFound("delete of Pipeline: {} not found".format(name))

    if(result != 0):
      raise Exception("delete of Pipeline: {} failed: {}".format(name, result))


  async def set_pipeline_options(
      self,
      name: str,
      options: PipelineOptions
    )-> None:
    raise Exception("not implemented")


  async def insert_pipeline_processor(
      self,
      name: str,
      processor: PipelineProcessor,
      index: int = -1
    )-> None:
    raise Exception("not implemented")


  async def delete_pipeline_processor(
      self,
      name: str,
      index: int
    )-> None:
    raise Exception("not implemented")


class PipelineRunner():
  """
  Run vCon(s) through a Pipeline
  """
  def __init__(
      self,
      pipeline: PipelineDefinition,
      name: typing.Union[str, None] = None
    ):
    self._pipeline = pipeline
    self._pipeline_name = name

  async def run(
      self,
      processor_input: py_vcon_server.processor.VconProcessorIO
    ) -> py_vcon_server.processor.VconProcessorIO:
    """
    Run the VconProcessorIO through all the VconProcessor(s) in the Pipeline

    Parameters:
      **processor_input** () - the input to the first VconProcessor in the Pipeline

    Returns:
      The output VconProcessorIO from the last VconProcessor in the Pipeline
    """
    logger.debug("PipelineDef: {}".format(self._pipeline.dict()))
    timeout = self._pipeline.pipeline_options.timeout
    run_future = self._do_processes(
        processor_input
      )

    logger.debug("Running pipeline {} with timeout: {}".format(
        self._pipeline_name,
        timeout
      ))
    try:
      pipeline_output = await asyncio.wait_for(
          run_future,
          timeout
        )
      logger.debug("Completed pipeline {}".format(
          self._pipeline_name
        ))

    #except asyncio.exceptions.CancelledError as ce:
    except asyncio.exceptions.TimeoutError as ce:
      raise PipelineTimeout("pipeline {} timed out with {} second timeout".format(
          self._pipeline_name,
          timeout
        )) from ce
    return(pipeline_output)


  async def _do_processes(
      self,
      processor_input: py_vcon_server.processor.VconProcessorIO
    ) -> py_vcon_server.processor.VconProcessorIO:

    next_proc_input = processor_input
    for processor_config in self._pipeline.processors:
      processor_name = processor_config.processor_name
      processor = py_vcon_server.processor.VconProcessorRegistry.get_processor_instance(processor_name)
      processor_options = processor_config.processor_options
      # Recaste options to proper type
      # This becomes important when the options has multiple inheretance to get the
      # correct type (e.g. FilterPluginOptions).
      processor_type_options = processor.processor_options_class()(** processor_options.dict())
      vcon_index = processor_type_options.input_vcon_index
      logger.debug("Starting pipeline {} processor: {} on vCon: {} (index: {})".format(
          self._pipeline_name,
          processor_name,
          await next_proc_input.get_vcon(vcon_index, py_vcon_server.processor.VconTypes.UUID),
          vcon_index
        ))
      next_proc_input = await processor.process(next_proc_input, processor_type_options)

    return(next_proc_input)


class PipelineJobHandler(py_vcon_server.job_worker_pool.JobInterface):
  """ Class to get, run and handle results of Pipeline Jobs """
  def __init__(
      self,
      job_queue_db_url: str,
      #job_queue: py_vcon_server.queue.JobQueue,
      pipeline_db_url: str,
      #pipeline_db: PipelineDb,
      server_key: str
    ):
    self._job_queue_db_url = job_queue_db_url
    self._job_queue: typing.Union[py_vcon_server.queue.JobQueue, None] = None
    self._pipeline_db_url = pipeline_db_url
    self._pipeline_db = None
    self._server_key = server_key
    # TODO: setup queue iterator
    self._queue_iterator = py_vcon_server.queue.QueueIterator()
    self._last_queue_check = time.time()
    self._queue_check_time = 10 # seconds

  async def _init_databases(self):
    """
    This has to be done in scheduler context as we cannot pass DB connection
    accross processes.
    """
    if(self._job_queue == None):
      logger.debug("initialising Queue DB: {} pid: {}".format(self._job_queue_db_url, os.getpid()))
      self._job_queue = py_vcon_server.queue.JobQueue(self._job_queue_db_url)
      try:
        logger.debug("getting queue list pid: {}".format(os.getpid()))
        #remote_pdb.set_trace()
        #breakpoint()
        queue_list = await self._job_queue.get_queue_names()
        logger.debug("got queue list: {}".format(queue_list))
      except Exception as e:
        logger.debug("got exception: {} getting queue list".format(e))

    if(self._pipeline_db == None):
      logger.debug("initialising Pipeline DB: {}".format(self._pipeline_db_url))
      self._pipeline_db = py_vcon_server.pipeline.PipelineDb(self._pipeline_db_url)
      logger.debug("initialed Pipeline DB")
      # test/debug junk for python multiprocessing, asycnio, redis interaction problem
      # Multiprocessing is currently disabled
      # try:
      #   pipe_def = await self._pipeline_db.get_pipeline("A")
      #   logger.debug("test got Pipeline A: {}".format(pipe_def))
      # except Exception as e:
      #   logger.debug("test pipeline A not found as expected: {}".format(e))

  async def run_one_job(self) -> typing.Union[str, None]:
    """
    Attempt to pull a job from the set of queues and run the job.

    Returns: job_id (str) if a job was found or None
    """

    job_id = None
    job_def = await self.get_job()

    if(job_def):

      job_id = job_def["id"]

      try:
        job_results = await PipelineJobHandler.do_job(job_def)

        await self.job_finished(job_results)

      except Exception as job_error:
        logger.warning("exception while running job: {}".format(job_def))
        logger.exception(job_error)
        await self.job_exception(job_def)


    elif(VERBOSE):
      logger.debug("no job")

    return(job_id)


  async def done(self):
    if(self._job_queue):
      logger.debug("releasing job_queue")
      job_queue = self._job_queue
      self._job_queue = None
      await job_queue.shutdown()
    if(self._pipeline_db):
      logger.debug("releasing pipeline_db")
      pipeline_db = self._pipeline_db
      self._pipeline_db = None
      await pipeline_db.shutdown()

    global VCON_STORAGE
    if(VCON_STORAGE):
      logger.debug("shutting down PipelineJobHandler in done VconStorage")
      vs = VCON_STORAGE
      VCON_STORAGE = None
      await vs.shutdown()


  async def get_job(self) -> typing.Union[typing.Dict[str, typing.Any], None]:
    """ Get the definition of the next job to run. Called in the context of the scheduler/dispatcher process. """
    jobs_locks_not_available: list = []
    #  init DBs in scheduler context
    await self._init_databases()
    job: typing.Union[typing.Dict[str, typing.Any], None] = None

    # Check for updates to server queue config every self._queue_check_time seconds
    now = time.time()
    if(now - self._last_queue_check > self._queue_check_time):
      if(VERBOSE):
        logger.debug("checking server job queue updates")
      if(self._queue_iterator.check_update()):
        logger.debug("updated job queue sequence")
      self._last_queue_check = now
    queue_cycle_count = self._queue_iterator.get_cycle_count()
    if(VERBOSE):
      logger.debug("got job queue cycle count: {}".format(queue_cycle_count))
    queues_checked = 0

    # loop no more than once through the queue cycle before giving up and not getting a job
    while(queues_checked < queue_cycle_count):
      # get server's next queue from list (considering weights)
      queues_checked += 1
      queue_name = self._queue_iterator.get_next_queue()
      logger.debug("attempting schedule queue: {}".format(queue_name))
      # TODO: we can do some optimization here and skip repeated weighted queues
      # i.e. those with weight greter than 1 will be repeated, if we just checked
      # the queue and it was empty, no sense in getting pipeline def and checking
      # queue multiple times in a row.

      # Get the pipeline definition
      try:
        # seem to hang in redis here, trying to yeild first
        logger.debug("yeilding before getting pipeline def")
        await asyncio.sleep(0)
        # The following was part of debuging multiprocessing, asyncio, redis problem
        # see what else is running
        # for task in asyncio.all_tasks():
        #   logger.debug("running task: {}".format(task))
        logger.debug("getting pipeline def")
        pipe_def = await self._pipeline_db.get_pipeline(queue_name)
        if(pipe_def is None):
          logger.error("get_pipeine is not supposed to return None, should have thrown exception")
          continue
        else:
          logger.debug("got pipeline def")

      except py_vcon_server.pipeline.PipelineNotFound:
        # TODO: this message should be throttled for some period or number of times
        logger.warning("no definition for pipeline: {}".format(queue_name))
        # nothing to do for this queue
        continue
      except Exception as e:
        logger.debug("get_pipeline exception: {}".format(e))
        raise e

      # Get job from queue and mark it as in process
      try:
        logger.debug("getting job for queue: {}".format(queue_name))
        # try yeilding to avoid getting stuck in redis
        await asyncio.sleep(0)
        job = await self._job_queue.pop_queued_job(
            queue_name,
            self._server_key
          )
        if(job is None):
          logger.error("pop_queued_job is not supposed to return None, should have thrown exception")
          continue

      except py_vcon_server.queue.EmptyJobQueue:
        # No jobs in queue, go to next queue
        # TODO: This will be too noisy, disable it after debugging
        logger.debug("queue: {} is emtpy".format(queue_name))
        continue

      except py_vcon_server.queue.QueueDoesNotExist:
        # TODO: throttle down the logging of repeated messages or create
        # a queue black list for some period of time
        logger.warning("queue: {} does not exist".format(queue_name))
        continue

      # the job is already labeled with the queue to which it belongs
      # so on need to set job["queue"] = queue_name

      logger.debug("got job from queue: {} job: {}".format(queue_name, job))

      # Add pipeline def to job
      job["pipeline"] = pipe_def.dict()

      # Get locks if pipeline needs them
      if(pipe_def.pipeline_options.save_vcons):
        locks: typing.List[str] = []
        queue_job = job["job"]
        job_type = queue_job.get("job_type", None)
        if(job_type == "vcon_uuid"):
          for vcon_uuid in job.get("vcon_uuid", []):
            lock = "None"
            if(lock):
              locks.append(lock)
            else:
              # If cannot get all locks
              #TODO: release locks that were taken
              for lock in locks:
                pass
              logger.info("lock not available for vCon: {} job: {}".format(
                  vcon_uuid,
                  job["id"]
                ))
              jobs_locks_not_available.append(job)
              # skip to next queue job
              break

          # Add the locks to the job
          job["locks"] = locks

          # Successfuly got a job and locked its vCons
          logger.debug("got job: {} and locked its vCons".format(job["id"]))
          break

        else:
          logger.error("unsupported job_type: {} not queued in failure queue: {}".format(
              job_type,
              pipe_def.pipeline_options.get("failure_queue", None)
            ))
          continue

      else:
        logger.debug("read only vCon for job: {}, no locks needed".format(job["id"]))


    # Put jobs which were not lockable back in the queue
    # start at end and push them to the front of the queue
    # so that they are in the original order.
    # TODO: need to put try block finally around the following:
    for unlockable in jobs_locks_not_available[::-1]:
      #TODO move from inprocess back to queue
      await self._job_queue.requeue_in_progress_job(unlockable["id"])

    return(job)


  @staticmethod
  async def do_job(
      job_definition: typing.Dict[str, typing.Any]
    ) -> typing.Dict[str, typing.Any]:
    """ Function to perform job given job definition.  Called in context of worker process. """
    job_id = job_definition["id"]

    # Create pipeline definition
    pipe_def = job_definition.get("pipeline", None)
    if(pipe_def is None):
      raise Exception("no pipeline definition for job: {}".format(job_id))
    pipeline = PipelineDefinition(**pipe_def)

    queue_name = job_definition.get("queue", None)
    logger.info("doing job: {} from queue: {}".format(
        job_id,
        queue_name
      ))
    queue_job = job_definition.get("job", None)
    if(queue_job is None):
      raise Exception("job id: {} with no queue job definition".format(job_definition.get("id")))

    job_type = queue_job.get("job_type", None)
    if(job_type is None):
      raise Exception("job id: {} with no queue job type".format(job_definition.get("id")))

    # Create runner
    runner = PipelineRunner(pipeline, queue_name)

    # Initialize VCON_STORAGE if not already done
    global VCON_STORAGE
    if(VCON_STORAGE is None):
      logger.info("instantiating pipeline worker VconStorage")
      VCON_STORAGE = py_vcon_server.db.VconStorage.instantiate(
          py_vcon_server.settings.VCON_STORAGE_URL
        )

    # Create Processor input
    pipeline_input = py_vcon_server.processor.VconProcessorIO(VCON_STORAGE)
    locks = job_definition.get("locks", [])
    lock_len = len(locks)
    if(job_type == "vcon_uuid"):
      for index, vcon_uuid in enumerate(queue_job["vcon_uuid"]):
        if(lock_len > index):
          lock = locks[index]
        else:
          lock = None
        await pipeline_input.add_vcon(vcon_uuid, lock, False)

    else:
      raise Exception("unsupported queue job type: {}".format(job_type))

    logger.debug("running pipeline job: {}".format(
        job_id
      ))
    pipeline_output = await runner.run(pipeline_input)

    # Unfortunately, need to do the commit here
    save_vcons = pipeline.pipeline_options.save_vcons
    if(save_vcons):
      logger.debug("committing pipeline results from job: {}".format(
          job_id
        ))
      # Save changed Vcons
      await VCON_STORAGE.commit(pipeline_output)

    return(job_definition)


  async def job_finished(
      self,
      results: typing.Dict[str, typing.Any]
    ) -> None:
    """ handle a successful completion of a job """
    job_id = results["id"]

    removed_job = await self._job_queue.remove_in_progress_job(job_id)
    if(removed_job.get("id", None) == job_id):
      logger.debug("job: {} removed from in progress list".format(job_id))
    else:
      logger.warning("attempt to remove job: {} from in progress list yielded: {}".format(
          job_id,
          removed_job
        ))


  async def job_canceled(
      self,
      results: typing.Dict[str, typing.Any]
    ) -> None:
    """ handle a cancelled job (only those that have not yet been started) """
    job_id = results["id"]

    await self._job_queue.requeue_in_progress_job(job_id)


  async def job_exception(
      self,
      results: typing.Dict[str, typing.Any]
    ) -> None:
    """ handle a job which threw an exception and did not complete (including jobs that have been started and then cancelled) """
    job_id = results["id"]
    queue_job = results["job"]
    job_type = queue_job.get("job_type", None)
    queue_name = results["queue"]
    job_type = queue_job["job_type"]
    pipeline = results.get("pipeline", None)
    if(pipeline):
      failure_queue = pipeline["pipeline_options"].get("failure_queue", None)
      if(failure_queue and failure_queue != ""):
        # TODO: add some info from failure
        if(job_type == "vcon_uuid"):
          logger.debug("queuing job: {} from: {} to failure queue: {}".format(
              job_id,
              queue_name,
              failure_queue
            ))
          # add queue_name and job_id to job def in failure queue
          await self._job_queue.push_vcon_uuid_queue_job(
              failure_queue,
              queue_job["vcon_uuid"],
              queue_name,
              job_id
            )
        else:
          # should not get here as the job_type should have been screened at the start
          logger.error("Unsupported job type: {}".format(job_type))
      else:
        logger.info("no error queue for job: {} pipeline: {}".format(job_id, queue_name))

    else:
      logger.error("no pipeline definition for: {} job id: {}".format(
         queue_name,
         job_id
        ))

    await self._job_queue.remove_in_progress_job(job_id)


class PipelineManager():
  """ Manager for a sequence of **VconProcessor**s """
  def __init__(self):
    pass

  def add_processor(
    self,
    processor_name: str,
    processor_options: py_vcon_server.processor.VconProcessorOptions):
    raise Excepiton("Not implemented")


  def loads(self, pipeline_json: str):
    """
    Load processor sequence, their options and other pipeline config from a JSON string.
    """

  async def run(self, vcon_uuids: typing.List[str]):
    """
    TODO:
    The below pseudo code does not work.  The thing that dequeus and locks need to be in one context as you may have
    to pop several jobs before finding one that can lock all the input UUIDs.  If the work dispatcher does it, then
    it does not know the processors that may write or are read only.  If the work does the above, then how is the
    queue weighting and iteration get coordinated across all the workers.

    Construct a **VconProcessorIO** object from the vcon_uuids as input to the first VconProcessor
    Lock the vcons as needed
    run the sequence of **VconProcessor**s passing the constructed **VconPocessorIO** 
    object to the first in the sequence and then passing its output to the next and so on for the whole sequence.
    Commit the new and changed **Vcon**s from the final **VconProcessor** in the sequence's output 
    """


  def pipeline_sequence_may_write(pipeline: PipelineDefinition) -> bool:
    """
    Look up to see if any of the **VconProcessor**s in the pipeline's sequence may modify its input **Vcon**s.
    """

