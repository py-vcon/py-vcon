# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
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
import logging
#import multiprocessing_logging

#logger = multiprocessing.log_to_stderr()
#logger.setLevel(multiprocessing.SUBDEBUG)


logger = py_vcon_server.logging_utils.init_logger(__name__)

#multiprocessing_logging.install_mp_handler()
# DO NOT COMMIT with VERBOSE
VERBOSE = True

# multiprocessing.managers.DictProxy does not seem to work nor
# does logging with spawn
#CONTEXT_METHOD = "spawn"


CONTEXT_METHOD = None
#CONTEXT_METHOD = "fork"
#CONTEXT_METHOD = "forkserver"


class JobSchedulerFailedToStart(Exception):
  """ Thrown when Job Scheduler processes fail to start """


class JobInterface():
  """
  Abstract interface for getting jobs to run and handling state updates after the job is done.
  This class must be derived and its abstract methods implemented.  The derived class must be 
  picklable.
  """

  async def get_job(self) -> typing.Union[typing.Dict[str, typing.Any], None]:
    """ Get the definition of the next job to run. Called in the context of the scheduler/dispatcher process. """
    #raise Exception("get_job not implemented")


  @staticmethod
  async def do_job(
      job_definition: typing.Dict[str, typing.Any]
    ) -> typing.Dict[str, typing.Any]:
    """ Function to perform job given job definition.  Called in context of worker process. """
    #raise Exception("do_job not implemented")
    return(job_definition)


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


  async def done(self):
    pass


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
    self._manager = manager
    self._run_states: multiprocessing.managers.DictProxy = manager.dict(
      {
        "run": True
      })
    self._run_list: multiprocessing.managers.ListProxy = multiprocessing.Manager().list([])

  async def async_start(self) -> None:
    if(self._job_scheduler):
      raise Exception("job scheduler already started")
    if(not self._run_states["run"]):
      raise Exception("scheduler shutdown")

    self._job_scheduler = JobScheduler(
        self._run_states,
        self._run_list,
        self._num_workers,
        self._job_interface
      )

    logger.debug("starting async JobScheduler")
    await self._job_scheduler.async_start()


  def start(self, wait: bool = False, wait_scheduler = False) -> None:
    """ Start scheduler and worker processes and feed them jobs """
    if(self._job_scheduler):
      raise Exception("job scheduler already started")
    if(not self._run_states["run"]):
      raise Exception("scheduler shutdown")

    self._job_scheduler = JobScheduler(
        self._run_states,
        self._run_list,
        self._num_workers,
        self._job_interface
      )

    logger.debug("starting scheduler process")
    self._job_scheduler.start(wait = wait, wait_scheduler = wait_scheduler)

    
    num_schedulers = self._job_scheduler.check_scheduler(1.0)
    if(num_schedulers <= 0):
      logger.error("No schedulers started")
      raise JobSchedulerFailedToStart("No schedulers started")


  async def finish(self):
    """ Stop feeding jobs to workers and wait until in process jobs complete """
    logger.debug("entering finished")
    self._job_scheduler.shutdown()
    await self._job_scheduler.wait_on_schedulers()
    logger.debug("jobs and schedulers finished")


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
      run_list: multiprocessing.managers.ListProxy,
      num_workers: int,
      job_state_updater: JobInterface
    ):
    # Available in all processes
    self._run_states = run_states
    self._run_list = run_list
    self._num_workers = num_workers
    self._num_schedulers = 1 # work required to increase this
    self._job_state_updater = job_state_updater

    # Set in originator process only
    self._scheduler_pool: typing.Union[JobScheduler, None] = None # process run scheduler
    self._scheduler_futures: typing.List[concurrent.futures._base.Future] = []
    self._scheduler_task: asyncio.Task = None # async run of scheduler

  def start(self, wait: bool = False, wait_scheduler = False):
    """ Start scheduler and work processes """

    if(self._scheduler_pool):
      raise Exception("scheduler already started, scheduler_pool exists")
    if(len(self._scheduler_futures) != 0):
      raise Exception("scheduler already started, scheduler_futures not empty")
    if(not self._run_states["run"]):
      raise Exception("scheduler shutdown")
    if(self._scheduler_task):
      raise Exception("cannot start scheduler process, running async in loop")

    logger.debug("creating schedluler process pool")
    scheduler_pool = concurrent.futures.ProcessPoolExecutor(
      max_workers = self._num_schedulers,
      initializer = JobScheduler.process_init,
      initargs = (self._run_states, self._run_list),
      # so as to not inherit signal handlers and file handles from parent/FastAPI
      # use spawn:
      mp_context = multiprocessing.get_context(method = CONTEXT_METHOD))

    logger.debug("submitting scheduler task")
    # Start the scheduler
    # Which in turn sets up the job worker pool of processes
    # Before supporting multiple scheduler processes will need to setup
    # work pool here, but I am not sure if the worker pool is picklable.
    self._scheduler_futures.append(scheduler_pool.submit(
        JobScheduler._scheduler_exception_wrapper,
        JobScheduler.do_scheduling,
        self._run_states,
        self._run_list,
        self._num_workers,
        self._job_state_updater
      ))

    logger.debug("submitted scheduler task, run_states: {} tasks: {}".format(self._run_states, self._scheduler_futures))

    # Set scheduler pool on self after submit, as pool cannot be pickled
    # This also means that it is set only in this context/process
    self._scheduler_pool = scheduler_pool

    if(wait or wait_scheduler):
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
        logger.debug("RUN_LIST: {}".format(self._run_list))
        if(prior_num_keys != num_keys):
          logger.debug("waiting run_states: {}".format(self._run_states))
          prior_num_keys = num_keys

        # we wait until scheduler and workers states show up
        # JobWorkerPool.process_init adds pid and start time even if no jobs are queued or run
        if((wait and num_sched >= self._num_schedulers and num_workers >= self._num_workers) or
          (wait_scheduler and num_sched >= self._num_schedulers) or
          not self._run_states["run"]):
          logger.debug("done waiting run_states: {}".format(self._run_states))
          logger.debug("RUN_LIST: {}".format(self._run_list))
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
  def process_init(
      run_states: multiprocessing.managers.DictProxy,
      run_list: multiprocessing.managers.ListProxy
    ):
    """ Initialization function for scheduler process """
    logger.info("Initializing scheduler process")
    try:
      pid = os.getpid()
      start = time.time()
      process_state = {"type": "scheduler", "start": start}
      run_list.append(process_state)
      run_states[pid] = process_state
    except Exception as e:
      logger.exception(e)
      raise e

  @staticmethod
  def do_nothing() -> None:
    logger.debug("scheduler do nothing")
    time.sleep(1)
    logger.debug("scheduler done do nothing")


  async def async_start(self):
    if(self._scheduler_pool):
      raise Exception("cannot run async scheduler, process already started, scheduler_pool exists")
    if(len(self._scheduler_futures) != 0):
      raise Exception("scheduler already started, scheduler_futures not empty")
    if(not self._run_states["run"]):
      raise Exception("scheduler shutdown")
    if(self._scheduler_task):
      raise Exception("scheduler task already looped")

    logger.debug("getting do_scheduler coro")
    scheduler_coro = JobScheduler.do_scheduling(
        self._run_states,
        self._run_list,
        self._num_workers,
        self._job_state_updater
      )

    logger.debug("creating async do_scheduler task")
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    logging.getLogger("asyncio").setLevel(logging.DEBUG)
    self._scheduler_task = asyncio.create_task(scheduler_coro)
    logger.debug("created async do_scheduler task too slow: {}".format(
        loop.slow_callback_duration
      ))

    # logger.debug("start_async waiting for workers to initialize")
    # worker_started = False
    # while(self._run_states["run"] == True and not worker_started):
    #   # wait until job process initialized
    #   for key in self._run_states.keys():
    #     logger.debug("run_states key: {}".format(key))
    #     try:
    #       if(isinstance(int(key), int) and self._run_states[key].get("type", None) == "worker"):
    #         worker_started = True
    #         logger.debug("start_async workers initialized")
    #         break
    #     except ValueError:
    #       pass

    #   await asyncio.sleep(1.0)

    logger.debug("start_async workers initialized, starting scheduling")


  @staticmethod
  async def do_scheduling(
      run_states,
      run_list,
      num_workers: int,
      job_state_updater: JobInterface
    ) -> None:
    """ Main function of scheduling run in scheduler process """
    logger.debug("creating worker pool")
    job_worker_pool = JobWorkerPool(
        num_workers,
        run_states,
        run_list,
        job_state_updater.do_job,
        job_state_updater
      )

    # logger.debug("do_scheduler waiting for workers to initialize")
    # worker_started = False
    # while(run_states["run"] == True and not worker_started):
    #   # wait until job process initialized
    #   for key in run_states.keys():
    #     logger.debug("run_states key: {}".format(key))
    #     try:
    #       if(isinstance(int(key), int) and run_states[key].get("type", None) == "worker"):
    #         worker_started = True
    #         logger.debug("do_scheduler workers initialized")
    #         break
    #     except ValueError:
    #       pass

    #   await asyncio.sleep(0.1)

    # logger.debug("do_scheduler workers initialized, starting scheduling")

    #job_futures = []
    timeout = 1.0
    job_count = 0
    while(run_states["run"] == True):
      try:
        # Note: if there are no jobs running or completed, this does not yield
        num_job_futures = await job_worker_pool.check_jobs(timeout)
        if(VERBOSE):
          logger.debug("num futures: {} run_states: {}".format(num_job_futures, run_states))

        new_started = 0
        while(num_job_futures < num_workers):
          if(VERBOSE):
            logger.debug("getting a job")
          job_def = await job_state_updater.get_job()
          if(job_def):
            logger.debug("got a job")
            new_started += 1
            num_job_futures += 1
            job_count += 1
            job_worker_pool.run_job(job_def)
            job_id = job_def["id"]
            logger.info("job id: {} count: {} submitted".format(job_id, job_count))

          # No jobs available to schedule
          else:
            if(VERBOSE):
              logger.debug("no jobs")
            # yield to other tasks.  check_jobs does not yeild if 
            # nothing is running
            if(num_job_futures <= 0):
              await asyncio.sleep(0.1)
            break

        run_states["scheduler"] = "started: {} new jobs in {} workers".format(new_started, num_workers)

      except Exception as e:
        logger.error("do_scheduling caught exception: {}".format(e))
        raise e

    run_states["scheduler"] = "done scheduling new jobs, waiting for shutdown"
    # Shutting down, wait for running jobs to complete
    #job_worker_pool.stop_unstarted()
    logger.debug("do_scheduling shutting down, waiting on jobs")
    while(True):
      num_job_futures = await job_worker_pool.check_jobs(timeout)
      if(num_job_futures == 0):
        break
      await asyncio.sleep(0.1)

    job_worker_pool.wait_for_workers()

    logger.debug("do_scheduler done with JobInterface")
    await job_state_updater.done()
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
        logger.debug("getting scheduler fut")
        job_fut = scheduler_done.pop()
        logger.debug("getting scheduler result")
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


  async def wait_on_schedulers(self):
    if(self._scheduler_pool):
      """ Wait until all jobs and all of the schdulers have finished and processes have exited """
      logger.debug("wait_on_schedulers: {}".format(self._scheduler_futures))
      logger.debug("RUN_LIST: {}".format(self._run_list))
      try:
        while(True):
          num_scheduler_futures = self.check_scheduler(1.0)
          if(num_scheduler_futures <= 0):
            logger.debug("schedulers all shutdown and exited")
            break

      except Exception as e:
        logger.error("shutdown_scheduler caught exception: {} \n{}".format(
            e,
            str(getattr(e, "__cause__", None))
          ))
        raise

      logger.debug("waiting on scheduler tasks to shutdown")
      self._scheduler_pool.shutdown(wait = True)
      logger.debug("scheduler tasks shutdown")
      logger.debug("RUN_LIST: {}".format(self._run_list))

    elif(self._scheduler_task):
      scheduler_task = self._scheduler_task
      self._scheduler_task = None
      while(True):
        try:
          logger.debug("scheduler_task getting result")
          scheduler_task.result()
          break
        except asyncio.CancelledError as ce:
          logger.error("JobScheduler task cancelled: {}".format(ce))
          raise

        except asyncio.InvalidStateError as ise:
          logger.debug("waiting for scheduler task to complete: {}".format(ise))
          logger.debug("shutdown run_states: {}".format(self._run_states))
          await asyncio.sleep(0.2)

    else:
      if(self._run_states["run"]):
        logger.error("JobScheduler not running yet")
      else:
        logger.error("JobScheduler already being shutdown")


class JobWorkerPool():
  """ Manager and Pool of worker processes """
  def __init__(
      self,
      num_workers: int,
      run_states: multiprocessing.managers.DictProxy,
      run_list: multiprocessing.managers.ListProxy,
      job_func,
      job_state_updater: JobInterface
    ):
    self._job_futures: typing.List[concurrent.futures._base.Future] = []
    self._num_workers: int = num_workers
    self._job_func = job_func
    self._run_states = run_states
    self._run_list = run_list
    self._job_state_updater = job_state_updater
    self._workers = concurrent.futures.ProcessPoolExecutor(
      max_workers = num_workers,
      initializer = JobWorkerPool.process_init,
      initargs = (run_states, run_list),
      # so as to not inherit signal handlers and file handles from parent/FastAPI
      # use spawn:
      mp_context = multiprocessing.get_context(method = CONTEXT_METHOD))
      #max_tasks_per_child = 1)
    logger.debug("job worker executor created")

    job_definition = {"job_id": None }
    job_fut = self._workers.submit(
        JobWorkerPool._job_exception_wrapper,
        self._run_states,
        JobWorkerPool._do_nothing,
        job_definition
      )

    job_fut.job_data = job_definition
    self._job_futures.append(job_fut)


  @staticmethod
  async def _do_nothing(
      job_definition: typing.Dict[str, typing.Any]
    ) -> typing.Dict[str, typing.Any]:

    return(job_definition)


  @staticmethod
  def _job_exception_wrapper(
      run_states: multiprocessing.managers.DictProxy,
      func,
      *args,
      **kwargs
    ):
    """ Wraps func in order to preserve the traceback of any kind of raised exception """
    logger.debug("running in job exception wrapper")
    job_id = None
    start = time.time()
    my_pid = os.getpid()

    try:
      process_info = run_states.get(my_pid, {})
      if(process_info.get("init", None) is None):
        logger.warning("job started before process_init run pid: {}".format(my_pid))
      job_definition = args[0]
      process_info["start"] = start
      job_definition["start"] = start
      job_id = job_definition.get("id", None)
      process_info["job_id"] = job_id
      run_states[my_pid] = process_info
      logger.info("start job: {} time: {}".format(job_id, start))

      if(asyncio.iscoroutinefunction(func)):
        nest_asyncio.apply()
        loop = asyncio.get_event_loop()

        result = loop.run_until_complete(func(*args, **kwargs))
        # cannot run this before run_until_complete as loop is not started yet
        try:
          for task in asyncio.all_tasks():
            logger.debug("running task in job process: {}".format(task))
        except RuntimeError as e:
          logger.debug("no loop in job process to get tasks")

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
      process_info = run_states.get(my_pid, {})
      process_info["job_id"] = None
      run_states[my_pid] = process_info
      logger.debug("exiting job exception wrapper")

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
      process_info = run_states.get(my_pid, {})
      process_info["job_id"] = str(job_id) + "_exception"
      run_states[my_pid] = process_info
      raise exc


  @staticmethod
  def process_init(
      run_states: multiprocessing.managers.DictProxy,
      run_list: multiprocessing.managers.ListProxy
    ):
    """ Job process initialization function """
    # DO NOT COMMIT THIS:
    # make sure we don't get a DB from parent process
    if(py_vcon_server.pipeline.VCON_STORAGE is not None):
      logger.error("job process got VCON_STORAGE from parent")
    py_vcon_server.pipeline.VCON_STORAGE = None

    start = time.time()
    logger.debug("worker process initializing time: {}".format(start))
    try:
      pid = os.getpid()
      run_list.append({"type": "worker", "init": start})
      run_states[pid] = {"type": "worker", "init": start}

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
    if(VERBOSE):
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
            # The first jobe sent through to force the job worker processes to be 
            # spawned has no job_id.  Ignore it.
            if(res.get("id", None) is not None):
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
    logger.debug("waiting on worker tasks to shutdown")
    self._workers.shutdown(wait = True)
    logger.debug("worker task shutdown")

  def cancel_in_process(self):
    """ Stop all jobs and abort as soon as possible and update job states """
    raise Exception("cancel_in_process not implemented")

