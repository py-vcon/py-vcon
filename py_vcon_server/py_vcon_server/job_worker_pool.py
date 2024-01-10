""" module for multiprocess job workers and scheduler """
import typing
import sys
import os
import time
import copy
import traceback
import asyncio
import nest_asyncio
import concurrent.futures
import multiprocessing
import multiprocessing.managers
import py_vcon_server.logging_utils

#logger = multiprocessing.log_to_stderr()
#logger.setLevel(multiprocessing.SUBDEBUG)

logger = py_vcon_server.logging_utils.init_logger(__name__)


class JobInterface():
  """
  Abstract interface for getting jobs to run and handling state updates after the job is done.
  This class must be derived and its abstract methods implemented.  The derived class must be 
  picklable.
  """

  async def get_job(self) -> typing.Union[typing.Dict[str, typing.Any], None]:
    """ Get the definition of the next job to run. Called in the context of the scheduler/dispatcher process. """
    raise Exception("get_job not implemented")


  @staticmethod
  async def do_job(
      job_definition: typing.Dict[str, typing.Any]
    ) -> typing.Dict[str, typing.Any]:
    """ Function to perform job given job definition.  Called in context of worker process. """
    raise Exception("do_job not implemented")


  async def job_finished(
      self,
      results: typing.Dict[str, typing.Any]
    ) -> None:
    """ handle a successful completion of a job """
    raise Exception("job_result not implemented")


  async def job_canceled(
      self,
      results: typing.Dict[str, typing.Any]
    ) -> None:
    """ handle a cancelled job (only those that have not yet been started) """
    raise Exception("job_canceled not implemented")


  async def job_exception(
      self,
      results: typing.Dict[str, typing.Any]
    ) -> None:
    """ handle a job which threw an exception and did not complete (including jobs that have been started and then cancelled) """
    raise Exception("job_exception not implemented")


class JobSchedulerManager():
  """ Top level interface and manager for job scheduler and worker pool """

  def __init__(
      self,
      num_workers: int,
      job_interface: JobInterface
    ):
    self._num_workers = num_workers
    self._num_schedulers = 1
    self._job_scheduler = None
    self._job_interface = job_interface
    manager = multiprocessing.Manager()
    self._run_states: multiprocessing.managers.DictProxy = manager.dict(
      {
        "run": True
      })


  def start(self, wait: bool):
    """ Start scheduler and worker processes and feed them jobs """
    if(self._job_scheduler):
      raise Exception("job scheduler already started")
    if(not self._run_states["run"]):
      raise Exception("scheduler shutdown")

    self._job_scheduler = JobScheduler(
        self._run_states,
        self._num_workers,
        self._job_interface
      )

    logger.debug("starting scheduler")
    self._job_scheduler.start(wait = wait)

  def finish(self):
    """ Stop feeding jobs to workers and wait until in process jobs complete """
    self._job_scheduler.shutdown()
    self._job_scheduler.wait_on_schedulers()


  def abort(self):
    """ Stop feeding jobs to workers and cancel in process jobs update their states """
    raise Exception("abort not implemented")


  def jobs_in_process(self) -> int:
    """ Get the number of jobs currently in process by workers """
    raise Exception("jobs_in_process not implemented")
    return(-1)


  def num_workers(self) -> int:
    """ Get the number of workers """
    return(self._num_workers)


class JobScheduler():
  """ Process which schedules and feeds jobs to worker pool """
  def __init__(
      self,
      run_states: multiprocessing.managers.DictProxy,
      num_workers: int,
      job_state_updater: JobInterface
    ):
    # Available in all processes
    self._run_states = run_states
    self._num_workers = num_workers
    self._num_schedulers = 1 # work required to increase this
    self._job_state_updater = job_state_updater

    # Set in originator process only
    self._scheduler_pool: typing.Union[JobScheduler, None] = None
    self._scheduler_futures: typing.List[concurrent.futures._base.Future] = []


  def start(self, wait: bool):
    """ Start scheduler and work processes """

    if(self._scheduler_pool):
      raise Exception("scheduler already started, scheduler_pool exists")
    if(len(self._scheduler_futures) != 0):
      raise Exception("scheduler already started, scheduler_futures not empty")
    if(not self._run_states["run"]):
      raise Exception("scheduler shutdown")

    logger.debug("creating schedluler process pool")
    scheduler_pool = concurrent.futures.ProcessPoolExecutor(
      max_workers = self._num_schedulers,
      initializer = JobScheduler.process_init,
      initargs = (self._run_states,),
      # so as to not inherit signal handlers and file handles from parent/FastAPI
      # use spawn:
      mp_context = multiprocessing.get_context(method = "fork"))
      #mp_context = multiprocessing.get_context(method = "spawn"))

    logger.debug("submitting scheduler task")
    # Start the scheduler
    # Which in turn sets up the job worker pool of processes
    # Before supporting multiple scheduler processes will need to setup
    # work pool here, but I am not sure if the worker pool is picklable.
    self._scheduler_futures.append(scheduler_pool.submit(
        JobScheduler._scheduler_exception_wrapper,
        JobScheduler.do_scheduling,
        self._run_states,
        self._num_workers,
        self._job_state_updater
      ))

    logger.debug("submitted scheduler task, run_states: {} tasks: {}".format(self._run_states, self._scheduler_futures))
    # Set scheduler pool on self after submit, as pool cannot be pickled
    # This also means that it is set only in this context/process
    self._scheduler_pool = scheduler_pool

    if(wait):
      prior_num_keys = 0
      while(True):
        # TODO make this a little smarter and look at the task info in run_states
        num_sched = 0
        num_workers = 0
        for key in self._run_states.keys():
           value = self._run_states.get(key, None)
           logger.debug("run_states[{}] = {}".format(key, value))
           if(value and isinstance(key, int) and isinstance(value, dict)):
             proc_type = value.get("type", None)
             if(proc_type == "worker"):
               num_workers +=1
             if(proc_type == "scheduler"):
               num_sched += 1
        num_keys = len(self._run_states.keys())
        logger.debug("num_sched: {} num_workeres: {} num_keys: {}".format(
            num_sched,
            num_workers,
            num_keys
          ))
        if(prior_num_keys != num_keys):
          logger.debug("waiting run_states: {}".format(self._run_states))
          prior_num_keys = num_keys

        # we wait until scheduler and workers states show up
        # JobWorkerPool.process_init adds pid and start time even if no jobs are queued or run
        if((num_sched >= self._num_schedulers and num_workers >= self._num_workers) or
          not self._run_states["run"]):
          logger.debug("done waiting run_states: {}".format(self._run_states))
          break

        time.sleep(0.1)


  @staticmethod
  def _scheduler_exception_wrapper(
      func,
      *args,
      **kwargs
    ):
    """ Wraps func in order to preserve the traceback of any kind of raised exception """
    logger.debug("running in scheduler exception wrapper")

    try:
      start = time.time()
      # job_definition = args[0]
      # job_definition["start"] = start
      # job_id = job_definition.get("id", None)
      logger.info("start scheduler time: {}".format(start))

      if(asyncio.iscoroutinefunction(func)):
        nest_asyncio.apply()
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(func(*args, **kwargs))
      else:
        result = func(*args, **kwargs)

      finish = time.time()
      logger.info("end scheduler time: {}".format(finish))
      #if(not isinstance(result, dict)):
      #  logger.warning("job function: {} did not return type dict (type: {} value: {})".format(
      #      func,
      #      type(result),
      #      result
      #    ))
      #else:
      #  result["finish"] = finish

      return(result)

    except Exception:
      # start = args[0].get("start", None)
      exc = sys.exc_info()[0](traceback.format_exc())
      logger.warning("exc type: {}".format(type(exc)))
      # if(start):
      #   exc.start = start
      raise exc


  @staticmethod
  def process_init(run_states: multiprocessing.managers.DictProxy):
    """ Initialization function for scheduler process """
    logger.info("Initializing scheduler process")
    try:
      pid = os.getpid()
      start = time.time()
      process_state = {"type": "scheduler", "start": start}
      run_states[pid] = process_state
    except Exception as e:
      logger.exception(e)
      raise e

  @staticmethod
  def do_nothing() -> None:
    logger.debug("scheduler do nothing")
    time.sleep(1)
    logger.debug("scheduler done do nothing")


  @staticmethod
  async def do_scheduling(
      run_states,
      num_workers: int,
      job_state_updater: JobInterface
    ) -> None:
    """ Main function of scheduling run in scheduler process """
    logger.debug("creating worker pool")
    job_worker_pool = JobWorkerPool(
        num_workers,
        run_states,
        job_state_updater.do_job,
        job_state_updater
      )

    #job_futures = []
    timeout = 1.0
    job_count = 0
    while(run_states["run"]):
      try:
        num_job_futures = await job_worker_pool.check_jobs(timeout)

        while(num_job_futures < num_workers):
          logger.debug("getting a job")
          job_def = await job_state_updater.get_job()
          if(job_def):
            logger.debug("got a job")
            num_job_futures += 1
            job_count += 1
            job_worker_pool.run_job(job_def)
            job_id = job_def["id"]
            logger.info("job id: {} count: {} submitted".format(job_id, job_count))

          # No jobs available to schedule
          else:
            break

        run_states["scheduler"] = "ran all jobs"

      except Exception as e:
        logger.error("do_scheduling caught exception: {}".format(e))
        raise e

    # Shutting down, wait for running jobs to complete
    job_worker_pool.stop_unstarted()
    while(True):
      num_job_futures = await job_worker_pool.check_jobs(timeout)
      if(num_job_futures == 0):
        break

    job_worker_pool.wait_for_workers()

    logger.info("do_scheduling done")


  def check_scheduler(
      self,
      timeout
    ):
    """
    Checks on the state of the scheduler process(es).

    Returns: the number of scheduler processes still running
    """
    logger.debug("check_scheduler run states: {} waiting on scheduler to complete".format(
        self._run_states
      ))
    scheduler_state = concurrent.futures.wait(
        self._scheduler_futures,
        timeout = timeout,
        return_when = concurrent.futures.FIRST_COMPLETED)
    #print("sched state: {}".format(scheduler_state))

    logger.debug("check_scheduler: {}".format(scheduler_state)) 

    # TODO: currently assumes only one scheduler process
    scheduler_done = scheduler_state.done
    if(len(scheduler_done) > 0):
      logger.info("scheduler done")
      try:
        logger.debug("getting scheduler job fut")
        job_fut = scheduler_done.pop()
        logger.debug("getting scheduler job result")
        job_fut.result(timeout = 0)
      except Exception as e:
        logger.exception("scheduler exception: {}".format(e))
        # TODO: how to recover??

    self._scheduler_futures = list(scheduler_state.not_done)
    #print("sched futs (not_done): {}".format(scheduler_future))
    return(len(self._scheduler_futures))


  def shutdown(self):
    """ Stop starting new jobs and tell processes to finish jobs and shutdown """
    logger.debug("shutdown run_states: {}".format(self._run_states))
    self._run_states["run"] = False


  def wait_on_schedulers(self):
    """ Wait until all jobs and all of the schdulers have finished and processes have exited """
    logger.debug("wait_on_schedulers: {}".format(self._scheduler_futures))
    try:
      while(True):
        num_scheduler_futures = self.check_scheduler(1.0)
        if(num_scheduler_futures <= 0):
          break

    except Exception as e:
      logger.error("shutdown_scheduler caught exception: {} \n{}".format(
          e,
          str(getattr(e, "__cause__", None))
        ))
      raise

    self._scheduler_pool.shutdown(wait = True)


class JobWorkerPool():
  """ Manager and Pool of worker processes """
  def __init__(
      self,
      num_workers: int,
      run_states: multiprocessing.managers.DictProxy,
      job_func,
      job_state_updater: JobInterface
    ):

    self._job_futures: typing.List[concurrent.futures._base.Future] = []
    self._num_workers: int = num_workers
    self._job_func = job_func
    self._run_states = run_states
    self._job_state_updater = job_state_updater
    self._workers = concurrent.futures.ProcessPoolExecutor(
      max_workers = num_workers,
      initializer = JobWorkerPool.process_init,
      initargs = (run_states,),
      # so as to not inherit signal handlers and file handles from parent/FastAPI
      # use spawn:
      mp_context = multiprocessing.get_context(method = "fork"))
      #mp_context = multiprocessing.get_context(method = "spawn"))
      #max_tasks_per_child = 1)

  @staticmethod
  def _job_exception_wrapper(
      run_states: multiprocessing.managers.DictProxy,
      func,
      *args,
      **kwargs
    ):
    """ Wraps func in order to preserve the traceback of any kind of raised exception """
    logger.debug("running in exception wrapper")
    job_id = None
    start = time.time()

    try:
      process_info = run_states.get(os.getpid(), {})
      job_definition = args[0]
      job_definition["start"] = start
      job_id = job_definition.get("id", None)
      process_info["job_id"] = job_id
      run_states[os.getpid()] = process_info
      logger.info("start job: {} time: {}".format(job_id, start))

      if(asyncio.iscoroutinefunction(func)):
        nest_asyncio.apply()
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(func(*args, **kwargs))
      else:
        result = func(*args, **kwargs)

      finish = time.time()
      logger.info("end job: {} time: {}".format(job_id, finish))
      if(not isinstance(result, dict)):
        logger.warning("job function: {} did not return type dict (type: {} value: {})".format(
            func,
            type(result),
            result
          ))
      else:
        result["finish"] = finish
      process_info = run_states.get(os.getpid(), {})
      process_info["job_id"] = None
      run_states[os.getpid()] = process_info

      return(result)

    except (
        Exception,
        # CancelledError apparently does not inherit from Exception.
        # It does inherit from BaseException which seems like that might
        # catch stuff that  we should not be dealing with (not possitive about that).
        asyncio.exceptions.CancelledError
      ) as e:
      logger.warning("job wrapper caught exception")
      logger.exception(e)
      exc = sys.exc_info()[0](traceback.format_exc())
      logger.warning("exc type: {}".format(type(exc)))
      exc.start = start
      process_info = run_states.get(os.getpid(), {})
      process_info["job_id"] = str(job_id) + "_exception"
      run_states[os.getpid()] = process_info
      raise exc


  @staticmethod
  def process_init(run_states: multiprocessing.managers.DictProxy):
    """ Job process initialization function """
    start = time.time()
    logger.debug("worker process initializing time: {}".format(start))
    try:
      pid = os.getpid()
      run_states[pid] = {"type": "worker", "start": start}
    except Exception as e:
      logger.exception(e)
      run_states[pid] = {"type": "worker", "Exception in init:": str(e)}
      raise e
    # loop = asyncio.get_event_loop()
    # loop.run_until_complete(asyncio.sleep(5))
    # logger.debug("worker process started")


  def run_job(self,
      job_definition: typing.Dict[str, typing.Any]
    ) -> None:
    """ Start a new job in one of the worker processes, queue it if all processing busy """
    try:
      job_fut = self._workers.submit(
          JobWorkerPool._job_exception_wrapper,
          self._run_states,
          self._job_func,
          job_definition
        )
      job_fut.job_data = job_definition
      self._job_futures.append(job_fut)
      job_id = job_definition.get("id", None)
      logger.info("job {} func: {} submitted".format(job_id, self._job_func))

    except Exception as e:
      logger.error("run_job caught exception: {}".format(e))
      raise e

  async def check_jobs(
      self,
      timeout: float
    ) -> int:
    """
    Check for finished, canceled, or excepted jobs.
    Returns: count of in process jobs
    """
    completed_states = concurrent.futures.wait(
      self._job_futures,
      timeout = timeout,
      return_when = concurrent.futures.FIRST_COMPLETED)
    logger.debug("check_jobs completed: {} running: {}".format(
      len(completed_states.done),
      len(completed_states.not_done)
      ))

    for done_job in completed_states.done:
      #print("job type: {} id: {}".format(type(done_job), done_job.job_data["id"]))
      job_data = done_job.job_data
      if(done_job.cancelled()):
        try:
          exc = done_job.exception(timeout = 0)
          if(exc):
            #job_data["cancel"] = type(exc)
            job_data["canceled_at"] = time.time()
            job_data["cancel"] = exc.__class__.__name__
            job_data["cancel_cause"] = str(getattr(exc, "__cause__", None))
            # Currently labeling this an error as it has not occurred in normal cases
            logger.error("job: {} GOT CANCEL EXCEPTION".format(
              job_data))
            await self._job_state_updater.job_canceled(job_data)
        except (
            Exception,
            asyncio.exceptions.CancelledError
          ) as e:
          logger.warning("canceled job done_job.exception: {}".format(
              getattr(e, "__cause__", None)
            ))
          job_data["canceled_at"] = time.time()
          #logger.exception(e)
          logger.debug("dir e: {}".format(dir(e)))
          job_data["cancel"] = e.__class__.__name__
          job_data["cancel_cause"] = str(getattr(e, "__cause__", None))

        logger.warning("job: {} CANCELED".format(
          job_data))
        await self._job_state_updater.job_canceled(job_data)

      elif(done_job.done()):
        try:
          #print("getting job {} result".format(
          #  done_job.job_data["id"]))

          exc = done_job.exception(timeout = 0)
          if(exc):
            #print("except dir: {}".format(dir(exc)))
            #print("except call type: {}".format(type(exc)))
            #print("except call args: {}".format(exc.args))
            #print("except call args len: {}".format(len(exc.args)))
            #print("except call _traceback_: {}".format(exc.__traceback__))
            #print("except call __cause__: {}".format(exc.__cause__))
            #print("exc str len: {}".format(len(exc_str)))
            #print("exc str: {}".format(exc_str))
            #print("except call __context__: {}".format(exc.__context__))
            exc_str = "{}".format(exc)
            if(len(exc_str) == 0 or len(exc.args) == 0):
              logger.warning("BAD EXCEPTION str len: {} args: {}".format(len(exc_str), len(exc.args)))
              # The following, if uncommented will cause this process to end with no exception
              #print("except call: {}".format(exc))
            job_data["exception_at"] = time.time()
            #job_data["exception"] = type(exc)
            job_data["exception"] = exc.__class__.__name__
            job_data["exception_cause"] = str(getattr(exc, "__cause__", None))
            start = getattr(exc, "start", None)
            if(start):
              job_data["start"] = start
            logger.warning("job: {} GOT EXCEPTION".format(job_data))
            logger.debug("_job_state_updater type: {}".format(
                type(self._job_state_updater)
              ))
            await self._job_state_updater.job_exception(job_data)

          else:
            res = done_job.result(timeout = 0)

            res["result_at"] = time.time()
            logger.info("job: {} result: {}".format(
                job_data,
                res
              ))
            await self._job_state_updater.job_finished(res)

        except Exception as e:
          job_data["exception_at"] = time.time()
          #job_data["exception"] = type(exc)
          job_data["exception"] = e.__class__.__name__
          cause = getattr(e, "__cause__", None)
          if(not cause):
            cause =  "".join(traceback.format_tb(e.__traceback__))
          else:
            cause = str(cause)
          job_data["exception_cause"] = cause
          start = getattr(e, "start", None)
          if(start):
            job_data["start"] = start
          logger.error("job: {} GOT RESULT EXCEPTION".format(job_data))
          logger.exception(e)
          logger.debug("after log exception")
          await self._job_state_updater.job_exception(job_data)
          #print("dir: {}".format(dir(e)))
          # for index, stack_item in enumerate(traceback.format_tb(e.__traceback__)):
          #   print("  traceback[{}]: {}".format(index, stack_item))
          # raise e

      else:
        logger.error("unknown job state ???: {} {}".format(job_data, done_job))

    #print("running tasks: {}".format(completed_states.not_done))
    self._job_futures = list(completed_states.not_done)

    return(len(self._job_futures))

  def stop_unstarted(self) -> int:
    """
    Stop any jobs not yet started in a worker process and update job states.

    Returns: number of unstarted jobs that were canceled
    """
    cancelled = 0
    # Start at the end of the list as they were last added
    # and more likely to not have started yet.
    logger.debug("attempting to cancel {} unstarted jobs".format(len(self._job_futures)))
    for job in self._job_futures[::-1]:
      if(job.cancel()):
        cancelled += 1

    logger.debug("cancelled {} of {} jobs".format(cancelled, len(self._job_futures)))
    return(cancelled)


  def wait_for_workers(self):
    """ Wait for worker processes to exit and shutdown """
    self._workers.shutdown(wait = True)

  def cancel_in_process(self):
    """ Stop all jobs and abort as soon as possible and update job states """
    raise Exception("cancel_in_process not implemented")

