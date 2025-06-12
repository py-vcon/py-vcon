# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
import os
import multiprocessing
from pathlib import Path

VCON_STORAGE_URL = os.getenv("VCON_STORAGE_URL", "redis://localhost")
QUEUE_DB_URL = os.getenv("QUEUE_DB__URL", VCON_STORAGE_URL)
PIPELINE_DB_URL = os.getenv("PIPELINE_DB_URL", VCON_STORAGE_URL)
STATE_DB_URL = os.getenv("STATE_DB_URL", VCON_STORAGE_URL)
REST_URL = os.getenv("REST_URL", "http://localhost:8000")
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG")
LOGGING_CONFIG_FILE = os.getenv("LOGGING_CONFIG_FILE", Path(__file__).parent / 'logging.conf')
LAUNCH_VCON_API = os.getenv("LAUNCH_VCON_API", True)
LAUNCH_ADMIN_API = os.getenv("LAUNCH_ADMIN_API", True)

# FASTapi worker processes
try:
  NUM_RESTAPI_WORKERS = int(os.getenv("NUM_RESTAPI_WORKERS", 10))
except:
  NUM_RESTAPI_WORKERS = 10

# Number of pipeline server workers (currently disabled)
try:
  NUM_WORKERS = int(os.getenv("NUM_WORKERS", 0)) #Python Multiprocessing, Syncio, Redis issue os.cpu_count()))
except:
  NUM_WORKERS = 0
if(not isinstance(NUM_WORKERS, int)):
  print("Warning: NUM_WORKERS: {} should be an int, setting to: 0".format(NUM_WORKERS))
  NUM_WORKERS = 0

PLUGIN_PATHS = os.getenv("PLUGIN_PATHS", "").split(",")

CORS_ORIGINS = []
cors_origins_string = os.getenv("CORS_ORIGINS", "").strip()
if(cors_origins_string != ""):
  CORS_ORIGINS = cors_origins_string.split(", ")

# parse out optional weights from name for each queue
manager = multiprocessing.Manager()
#WORK_QUEUES: multiprocessing.managers.DictProxy = manager.dict({})
WORK_QUEUES = {}
queue_tokens = os.getenv("WORK_QUEUES", "").split(",")
for token in queue_tokens:
  name_weight = token.split(":")
  name = name_weight[0]
  if(len(name_weight) == 1 or
    name_weight[1] is None or
    name_weight[1] == ""):
    weight = 1
  elif(len(name_weight) == 2):
    try:
      weight = int(name_weight[1])
    except ValueError as e:
      raise Exception("WORK_QUEUE weights must be an integer value for queue: {}".format(name))
  else:
    raise Exception(
      "Invalid WORK_QUEUE token: {} should be name:weight where name is a string and weight is an integer".
      format(token))

  if(len(name) > 0):
    WORK_QUEUES[name] = {"weight": weight}

