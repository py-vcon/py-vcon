#! /usr/bin/python3
# Python 3.8.10
import os
import sys
import multiprocessing
import concurrent.futures
import asyncio
import nest_asyncio # 1.5.6
import pytest
import psutil
import redis.asyncio # 5.0.1

DB_URL = "redis://localhost"
DB_OPTIONS = {"decode_responses": True}
DB_JUNK = "unit_test_redis_junk"

PARENT_PID = os.getpid()

nest_asyncio.apply()

async def get_things(db_pool):
  print("getting client")
  client = redis.asyncio.client.Redis(connection_pool = db_pool)
  print("getting things")
  if(os.getpid() != PARENT_PID):
    print("hangs here in forked process: {}".format(os.getpid()))
  things = await client.smembers(DB_JUNK)
  assert(things is not None)
  assert(len(things) == 2)
  print("got things pid: {}".format(os.getpid()))
  client = None


async def connect_and_get_things():
  print("entering connect_and_get_things")
  show_sockets()
  db_pool2 = redis.asyncio.connection.ConnectionPool.from_url(
      DB_URL,
      **DB_OPTIONS
    )
  print("setup pool")
  for i in range(4):
    await get_things(db_pool2)
    show_sockets()

  await db_pool2.disconnect(inuse_connections=True)


def do_in_other_process():
  print("other process pid: {}".format(os.getpid()))
  loop = asyncio.get_event_loop()

  result = loop.run_until_complete(connect_and_get_things())

  return(result)


def show_sockets():
  p = psutil.Process()
  sockets = p.connections(kind = "inet")
  print("pid: {} open sockets: {}".format(os.getpid(), sockets))


@pytest.mark.asyncio
async def test_redis_multiprocessing():
  show_sockets()
  test_redis_in_parent = True
  db_pool = redis.asyncio.connection.ConnectionPool.from_url(
      DB_URL,
      **DB_OPTIONS
    )
  client = redis.asyncio.client.Redis(connection_pool = db_pool)
  if(test_redis_in_parent):
    try:
      await client.sadd(DB_JUNK, "A")
      await client.sadd(DB_JUNK, "B")
    except redis.exceptions.ConnectionError as re:
      print("error connection or writing to redis: {}".format(DB_URL))
      raise re
    client = None
    show_sockets()

    for i in range(4):
      await get_things(db_pool)

  process_pool = concurrent.futures.ProcessPoolExecutor(
      max_workers = 4,
      mp_context = multiprocessing.get_context(method = "fork")
    )
  job_fut = process_pool.submit(do_in_other_process)


  completed_states = concurrent.futures.wait(
      [job_fut],
      timeout = 20,
      return_when = concurrent.futures.FIRST_COMPLETED
    )

  show_sockets()
  if(len(completed_states.done) == 1):
    job_fut.result(timeout = 0)
    print("SUCCESS")
  if(len(completed_states.not_done) == 1):
    print("db hung on connect in other process")

  assert(len(completed_states.done) == 1)
  assert(len(completed_states.not_done) == 0)

  if(test_redis_in_parent):
    await db_pool.disconnect(inuse_connections=True)

if(__name__ == '__main__'):
  sys.exit(asyncio.run(test_redis_multiprocessing()))
