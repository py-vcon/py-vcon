import typing
import time
import copy
import asyncio
import multiprocessing
import math
import random
import pytest
import pytest_asyncio
import py_vcon_server.job_worker_pool

TOL_FACTOR = 2.5

class JobTestException(Exception):
  """ exception to be caught in unit tests """

 
class UnitJobber(py_vcon_server.job_worker_pool.JobInterface):

  def __init__(
      self,
      job_list: typing.List[typing.Dict[str, typing.Any]]
    ):
    """
    **id** -
    **raise_text** - 
    **sleep_time** -
    **cpu_time** -
    **cancel_time** -
    **timeout** -
    **expected_start** - 
    **expected_finish** - 
    **expected_result** - 
    **expected_exception_type** - 
    **time_tolerance** -

    """
    manager = multiprocessing.Manager()
    self._job_list = manager.list(job_list)
    self._time0: multiprocessing.managers.ListProxy = manager.list([])
    self._time0.append(0)
    self._first_start: multiprocessing.managers.ListProxy = manager.list([])
    self._finished_jobs: multiprocessing.managers.ListProxy = manager.list([])
    self._canceled_jobs: multiprocessing.managers.ListProxy = manager.list([])
    self._exception_jobs: multiprocessing.managers.ListProxy = manager.list([])


  def check_first_start(self, job):
    if(len(self._first_start) == 0):
      job_start = job.get("start", None)
      if(job_start):
        self._first_start.append(job_start)
        print("t0: {} actual: {}  delta: {}".format(
            self._time0[0],
            job_start,
            job_start - self._time0[0]
          ))
      else:
        # Should assert???
        print("no start")


  def remaining_jobs(self) -> int:
    return(len(self._job_list))


  async def get_job(self) -> typing.Union[typing.Dict[str, typing.Any], None]:
    if(self._time0[0] == 0):
      self._time0[0] = time.time()
    if(len(self._job_list)):
      job_def = self._job_list.pop(0)
      job_def["time0"] = self._time0[0]
      return(job_def)
    return(None)


  @staticmethod
  def do_raise(text: str):
    raise JobTestException(text)


  @staticmethod
  def cancel_task(task):
    print("canceling task")
    task.cancel()


  @staticmethod
  async def sleep_job(seconds):
    """ blocking sleep/io function """
    return(await asyncio.sleep(seconds))


  @staticmethod
  async def cpu_job(seconds):
    """ cpu intensive function """
    iterations = 2000000 * seconds
    max_operand = 1000
    operand = random.randrange(max_operand)
    result = 1.0
    for i in range(0, iterations):
      result = result * math.tan(operand)

    return(result)


  @staticmethod
  async def do_job(
      job_definition: typing.Dict[str, typing.Any]
    ) -> typing.Dict[str, typing.Any]:

    print("do_job =====")
    job_id = job_definition.get("id", None)

    # raise exception if defined
    raise_text = job_definition.get("raise_text", None)
    if(raise_text):
      UnitJobber.do_raise(raise_text)

    sleep_time = job_definition.get("sleep_time", None)
    cpu_time = job_definition.get("cpu_time", None)
    coro = None
    # do sleep if defined
    if(sleep_time and sleep_time > 0):
      coro = UnitJobber.sleep_job(sleep_time)
    # do CPU work if defined
    elif(cpu_time and cpu_time > 0):
      print("running cpu job: {}".format(cpu_time))
      coro = UnitJobber.cpu_job(cpu_time)
    # else do nothing

    if(coro):
      timeout = job_definition.get("timeout", 0)
      loop = asyncio.get_event_loop()
      task = loop.create_task(coro)

      # Setup cancel if defined
      cancel_time = job_definition.get("cancel_time", None)
      # cannot cancel immediately here
      if(cancel_time and cancel_time > 0):
        timer_handle = loop.call_at(loop.time() + cancel_time, UnitJobber.cancel_task, task)
        print("scheduling early cancel on job {}".format(job_id))
      else:
        timer_handle = None

      try:
        wait_coro = asyncio.wait_for(task, timeout)
        #print("got wait_coro job: {}".format(job_id))
        #result = loop.run_until_complete(wait_coro)
        result = await wait_coro
        job_definition["result"] = result

        if(timer_handle):
          timer_handle.cancel()

      except Exception as e:
        print("do_job {} run_until_complete got exception: {}".format(job_id, e))
        raise e


    return(job_definition)


  async def job_finished(
      self,
      results: typing.Dict[str, typing.Any]
    ) -> None:
    """ Invoked on jobs that finish normally """
    print("job finished with results: {}".format(results), flush = True)
    self.check_first_start(results)
    self._finished_jobs.append(copy.deepcopy(results))
    #assert(abs(results["start"] - self._time0 - results["expected_start"]) < results["time_tolerance"])
    #assert(abs(results["finish"] - self._time0 - results["expected_finish"]) < results["time_tolerance"])


  def get_finished_count(self) -> int:
    return(len(self._finished_jobs))


  def verify_finished_jobs(self, count: int):
    assert(len(self._finished_jobs) == count)
    if(count > 0):
      assert(len(self._first_start) == 1)
      first_start = self._first_start[0]
      assert(first_start - self._time0[0] < 10.0) # TODO wide range of 5-10 seconds startup, do not know why

    for index, job in enumerate(self._finished_jobs):
      print("verifying finished job: {} ({}/{})".format(job["id"], index, count))
      runtime = job.get("cpu_time", None)
      if(not runtime):
        runtime = job.get("sleep_time", None)
      assert(abs(job["finish"] - job["start"] - runtime) < job["time_tolerance"])
     # can't reliably predict start, hense factor of 2.0:
      assert(abs(job["start"] - first_start - job["expected_start"]) < job["time_tolerance"] * TOL_FACTOR)
      assert(abs(job["finish"] - first_start - job["expected_finish"]) < job["time_tolerance"] * TOL_FACTOR)


  def get_exception_count(self) -> int:
    return(len(self._exception_jobs))


  def verify_exception_jobs(self, count: int):
    assert(len(self._exception_jobs) == count)
    if(count > 0):
      assert(len(self._first_start) == 1)
      first_start = self._first_start[0]
      assert(first_start - self._time0[0] < 10.0) # TODO wide range of 5-10 seconds startup, do not know why

    for index, job in enumerate(self._exception_jobs):
      print("verifying exception job: {} ({}/{})".format(job["id"], index, count))
      assert(abs(job["start"] - first_start - job["expected_start"]) < job["time_tolerance"] * TOL_FACTOR)
      assert(job["start"] < job["exception_at"])
      assert(job["start"] - job["exception_at"] < job["time_tolerance"])
      assert(job["exception"])
      assert(job["exception"] == job["expected_exception_type"])
      assert(job["exception_cause"])
      # check that we have many line for stack:
      assert(len(job["exception_cause"].split()) > 25)


  def get_canceled_count(self) -> int:
    return(len(self._canceled_jobs))


  def verify_canceled_jobs(self, count: int):
    assert(len(self._canceled_jobs) == count)
    if(count > 0):
      assert(len(self._first_start) == 1)
      first_start = self._first_start[0]
      assert(first_start - self._time0[0] < 10.0) # TODO wide range of 5-10 seconds startup, do not know why

    for index, job in enumerate(self._canceled_jobs):
      assert(abs(job["canceled_at"] - first_start - job["expected_cancel"]) < job["time_tolerance"] * TOL_FACTOR)
      assert(job["cancel"] == job["expected_exception_type"])



  async def job_canceled(
      self,
      results: typing.Dict[str, typing.Any]
    ) -> None:
    """ Invoked on jobs that were cancelled **before** being started """
    print("job canceled with results: {}".format(results))
    self.check_first_start(results)
    self._canceled_jobs.append(copy.deepcopy(results))


  async def job_exception(
      self,
      results: typing.Dict[str, typing.Any]
    ) -> None:
    """ Invoked on jobs that throught an exception or are cancelled **after** being started """
    print("job exception with results: {}".format(results))
    self.check_first_start(results)
    self._exception_jobs.append(copy.deepcopy(results))
    #assert(abs(results["start"] - self._time0 - results["expected_start"]) < results["time_tolerance"])
    #assert(results["exception"] == results["expected_exception_type"])
    #assert(abs(results["finish"] - self._time0 - results["expected_finish"]) < results["time_tolerance"])

TIME_TOLERANCE = 1.7

SHORT_SLEEP_JOB = {
    "id": "sleep1",
    "raise_text": None,
    "sleep_time": 2,
    "cpu_time": None,
    "cancel_time": None,
    "timeout": None,
    "expected_start": 0.0, # TODO: Not sure why it takes 5 seconds to start
    "expected_finish": 2.0,
    "expected_result": None,
    "expected_exception_type": None,
    "time_tolerance": TIME_TOLERANCE
  }


SHORT_CPU_JOB = {
    "id": "cpu1",
    "raise_text": None,
    "sleep_time": None,
    "cpu_time": 2,
    "cancel_time": None,
    "timeout": None,
    "expected_start": 0.0, # TODO: Not sure why it takes 5 seconds to start
    "expected_finish": 2.0,
    "expected_result": None,
    "expected_exception_type": None,
    "time_tolerance": TIME_TOLERANCE
  }


EXCEPT_JOB = {
    "id": "except1",
    "raise_text": "Test exception",
    "sleep_time": None,
    "cpu_time": None,
    "cancel_time": None,
    "timeout": None,
    "expected_start": 0.0, # TODO: Not sure why it takes 5 seconds to start
    "expected_finish": 2.0,
    "expected_result": None,
    "expected_exception_type": "JobTestException",
    "time_tolerance": TIME_TOLERANCE
  }


CANCEL_SLEEP_JOB = {
    "id": "cancelsleep1",
    "raise_text": None,
    "sleep_time": 4,
    "cpu_time": None,
    "cancel_time": 1.5,
    "timeout": None,
    "expected_start": 0.0, 
    "expected_finish": 1.5,
    "expected_result": None,
    "expected_exception_type": "CancelledError",
    "time_tolerance": TIME_TOLERANCE
  }


CANCEL_IMMEDIATE_JOB = {
    "id": "cancelimmediate1",
    "raise_text": None,
    "sleep_time": 4,
    "cpu_time": None,
    "cancel_time": 0,
    "timeout": None,
    "expected_start": 0.0, 
    "expected_finish": 4.0,
    "expected_cancel": 1.0,
    "expected_result": None,
    "expected_exception_type": "CancelledError",
    "time_tolerance": TIME_TOLERANCE
  }


async def start_run_stop_job_worker(jobs: list, tasks = 4):
  job_defs = copy.deepcopy(jobs)

  test_jobber = UnitJobber(job_defs)

  manager = multiprocessing.Manager()
  run_states: multiprocessing.managers.DictProxy = manager.dict(
      {
        "run": True
      })
  job_pool = py_vcon_server.job_worker_pool.JobWorkerPool(
      tasks,
      run_states,
      test_jobber.do_job,
      test_jobber
    )

  job_to_run = await test_jobber.get_job()
  assert(job_to_run)
  total_cancelled = 0
  while(job_to_run):
    cancel_time = job_to_run.get("cancel_time", None)
    print("starting job with cancel time: {}".format(cancel_time))
    job_pool.run_job(job_to_run)
    if(cancel_time is not None and cancel_time <= 0):
      print("canceling job")
      #last_job =  job_pool._job_futures[-1]
      #got_canceled = last_job.cancel()
      num_cancelled = job_pool.stop_unstarted()
      print("got cancelled: {}".format(num_cancelled))
      total_cancelled += num_cancelled

    print("run_states: {}".format(run_states))
    job_to_run = await test_jobber.get_job()

  num_job_futures = await job_pool.check_jobs(1)

  # This depends a lot upon timing, so commented out
  #assert(len(job_defs) >= num_job_futures + total_cancelled)

  while(num_job_futures):
    num_job_futures = await job_pool.check_jobs(1)
    print("run_states: {}".format(run_states))

  #time.sleep(0.5)
  job_pool.wait_for_workers()

  return(test_jobber)


@pytest.mark.asyncio
async def test_job_worker_pool_sleep():
  test_jobber = await start_run_stop_job_worker([SHORT_SLEEP_JOB])
  test_jobber.verify_finished_jobs(1)
  test_jobber.verify_exception_jobs(0)
  test_jobber.verify_canceled_jobs(0)


@pytest.mark.asyncio
async def test_job_worker_pool_cpu():
  test_jobber = await start_run_stop_job_worker([SHORT_CPU_JOB])
  test_jobber.verify_finished_jobs(1)
  test_jobber.verify_exception_jobs(0)
  test_jobber.verify_canceled_jobs(0)


@pytest.mark.asyncio
async def test_job_worker_pool_except():
  test_jobber = await start_run_stop_job_worker([EXCEPT_JOB])
  test_jobber.verify_finished_jobs(0)
  test_jobber.verify_exception_jobs(1)
  test_jobber.verify_canceled_jobs(0)


@pytest.mark.asyncio
async def test_job_worker_pool_cancel_sleep():
  test_jobber = await start_run_stop_job_worker([CANCEL_SLEEP_JOB])
  test_jobber.verify_finished_jobs(0)
  test_jobber.verify_exception_jobs(1)
  test_jobber.verify_canceled_jobs(0)


@pytest.mark.asyncio
async def test_job_worker_pool_cancel_immediate():
  can2 = copy.deepcopy(CANCEL_IMMEDIATE_JOB)
  can2["id"] = "cancelimmediate2"
  can2["expected_start"] += CANCEL_IMMEDIATE_JOB["expected_finish"]
  can2["expected_finish"] += CANCEL_IMMEDIATE_JOB["expected_finish"]
  can3 = copy.deepcopy(CANCEL_IMMEDIATE_JOB)
  can3["id"] = "cancelimmediate3"
  can3["expected_start"] += can2["expected_finish"]
  can3["expected_finish"] += can2["expected_finish"]
  can4 = copy.deepcopy(CANCEL_IMMEDIATE_JOB)
  can4["id"] = "cancelimmediate4"
  can4["expected_start"] += can3["expected_finish"]
  can4["expected_finish"] += can3["expected_finish"]
  test_jobber = await start_run_stop_job_worker([CANCEL_IMMEDIATE_JOB, can2, can3, can4], tasks = 1)
  cancel_count = test_jobber.get_canceled_count()
  assert(cancel_count > 0)
  finish_count = test_jobber.get_finished_count()
  assert(cancel_count + finish_count == 4)
  test_jobber.verify_finished_jobs(finish_count)
  test_jobber.verify_exception_jobs(0)
  test_jobber.verify_canceled_jobs(cancel_count)


@pytest.mark.asyncio
async def test_job_worker_pool_four():
  cpu2 = copy.deepcopy(SHORT_CPU_JOB)
  cpu2["id"] = "cpu2"
  sleep2 = copy.deepcopy(SHORT_SLEEP_JOB)
  sleep2["id"] = "sleep2"
  test_jobber = await start_run_stop_job_worker([SHORT_CPU_JOB, SHORT_SLEEP_JOB, cpu2, sleep2])
  test_jobber.verify_finished_jobs(4)
  test_jobber.verify_exception_jobs(0)
  test_jobber.verify_canceled_jobs(0)


def run_jobs_in_scheduler(jobs: list):
  test_jobber = UnitJobber(jobs)

  job_manager = py_vcon_server.job_worker_pool.JobSchedulerManager(4, test_jobber)
  assert(job_manager.num_workers() == 4)

  job_manager.start(wait = True)

  # Make sure there was time to start all the jobs, before telling it to finish up
  while(True):
    remaining_jobs = test_jobber.remaining_jobs()
    if(remaining_jobs <= 0):
      break
    print("waiting for {} remaining jobs".format(remaining_jobs), flush = True)
    time.sleep(0.1)

  job_manager.finish()

  return(test_jobber)


def test_job_scheduler_manager_sleep():
  job_def = copy.deepcopy(SHORT_SLEEP_JOB)
  test_jobber = run_jobs_in_scheduler([job_def])
  test_jobber.verify_finished_jobs(1)
  test_jobber.verify_exception_jobs(0)
  test_jobber.verify_canceled_jobs(0)


def test_job_scheduler_manager_cpu():
  job_def = copy.deepcopy(SHORT_CPU_JOB)
  test_jobber = run_jobs_in_scheduler([job_def])
  test_jobber.verify_finished_jobs(1)
  test_jobber.verify_exception_jobs(0)
  test_jobber.verify_canceled_jobs(0)


def test_job_scheduler_manager_except():
  job_def = copy.deepcopy(EXCEPT_JOB)
  test_jobber = run_jobs_in_scheduler([job_def])
  test_jobber.verify_finished_jobs(0)
  test_jobber.verify_exception_jobs(1)
  test_jobber.verify_canceled_jobs(0)


def test_job_scheduler_manager_cancel_sleep():
  job_def = copy.deepcopy(CANCEL_SLEEP_JOB)
  test_jobber = run_jobs_in_scheduler([job_def])
  test_jobber.verify_finished_jobs(0)
  test_jobber.verify_exception_jobs(1)
  test_jobber.verify_canceled_jobs(0)


def test_job_scheduler_manager_four():
  cpu2 = copy.deepcopy(SHORT_CPU_JOB)
  cpu2["id"] = "cpu2"
  sleep2 = copy.deepcopy(SHORT_SLEEP_JOB)
  sleep2["id"] = "sleep2"
  test_jobber = run_jobs_in_scheduler(
    [
      copy.deepcopy(SHORT_CPU_JOB),
      copy.deepcopy(SHORT_SLEEP_JOB),
      cpu2,
      sleep2
    ])
  test_jobber.verify_finished_jobs(4)
  test_jobber.verify_exception_jobs(0)
  test_jobber.verify_canceled_jobs(0)


def test_job_scheduler_manager_more():
  cpu1 = copy.deepcopy(SHORT_CPU_JOB)
  cpu2 = copy.deepcopy(SHORT_CPU_JOB)
  cpu2["id"] = "cpu2"
  sleep3 = copy.deepcopy(SHORT_SLEEP_JOB)
  sleep3["id"] = "sleep3"
  sleep4 = copy.deepcopy(SHORT_SLEEP_JOB)
  sleep4["id"] = "sleep4"
  cancel5 = copy.deepcopy(CANCEL_SLEEP_JOB)
  cancel5["id"] = "cancel5"
  except6 = copy.deepcopy(EXCEPT_JOB)
  except6["id"] = "except6"
  # TODO figure out how to cancel a not started job
  cpu9 = copy.deepcopy(SHORT_CPU_JOB)
  cpu9["id"] = "cpu9"
  cpu9["expected_start"] += cpu1["expected_finish"]
  cpu9["expected_finish"] += cpu1["expected_finish"]

  test_jobber = run_jobs_in_scheduler(
    [
      cpu1,
      cpu2,
      sleep3,
      sleep4,
      cancel5,
      except6,
      cpu9
    ])
  test_jobber.verify_finished_jobs(5)

  # cancel5 cancels work in progress which results in an exception
  # plus except5
  test_jobber.verify_exception_jobs(2)

  # jobs are considered canceled only if cancelled before starting
  test_jobber.verify_canceled_jobs(0)


