# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
import os
import multiprocessing

VCON_STORAGE_URL = os.getenv("VCON_STORAGE_URL", "redis://localhost")
QUEUE_DB_URL = os.getenv("QUEUE_DB__URL", VCON_STORAGE_URL)
PIPELINE_DB_URL = os.getenv("PIPELINE_DB_URL", VCON_STORAGE_URL)
STATE_DB_URL = os.getenv("STATE_DB_URL", VCON_STORAGE_URL)
REST_URL = os.getenv("REST_URL", "http://localhost:8000")
PROXY_PATH = os.getenv("PROXY_PATH", None)
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG")
LAUNCH_VCON_API = os.getenv("LAUNCH_VCON_API", True)
LAUNCH_ADMIN_API = os.getenv("LAUNCH_ADMIN_API", True)
DEFAULT_PROCESSOR_TIMEOUT = float(os.getenv("DEFAULT_PROCESSOR_TIMEOUT", 300.0))
HEARTBEAT_PERIOD = int(os.getenv("HEARTBEAT_PERIOD", 60))
SERVER_SHUTDOWN_WORKER_WAIT_TIMEOUT = float(os.getenv("SERVER_SHUTDOWN_WORKER_WAIT_TIMEOUT", 30.0))
SERVER_SHUTDOWN_WORKER_POLL_INTERVAL = float(os.getenv("SERVER_SHUTDOWN_WORKER_POLL_INTERVAL", 0.5))

# FASTapi worker processes
try:
  NUM_RESTAPI_WORKERS = int(os.getenv("NUM_RESTAPI_WORKERS", 10))
except:
  NUM_RESTAPI_WORKERS = 10

# Enable background pipeline server
RUN_BACKGROUND_JOBS = os.getenv("RUN_BACKGROUND_JOBS", True)
if(isinstance(RUN_BACKGROUND_JOBS, str)):
  if(RUN_BACKGROUND_JOBS.lower() == "true"):
    RUN_BACKGROUND_JOBS = True
  else:
    RUN_BACKGROUND_JOBS = False

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
#manager = multiprocessing.Manager()
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

STATE_SETTINGS = []
state_settings_list = os.getenv("STATE_SETTINGS", "REST_URL, PROXY_PATH, INSTANCE_ID, LOG_LEVEL, LAUNCH_VCON_API, LAUNCH_ADMIN_API, NUM_RESTAPI_WORKERS, PLUGIN_PATHS, CORS_ORIGINS, WORK_QUEUES, HEARTBEAT_PERIOD, DEFAULT_PROCESSOR_TIMEOUT").strip()
if(state_settings_list != ""):
  STATE_SETTINGS = state_settings_list.split(", ")

# Enable Prometheus metrics entry point
ENABLE_PROMETHEUS = os.getenv("ENABLE_PROMETHEUS", False)
if(isinstance(ENABLE_PROMETHEUS, str)):
  if(ENABLE_PROMETHEUS.lower() == "true"):
    ENABLE_PROMETHEUS = True
  else:
    ENABLE_PROMETHEUS = False

INSTANCE_ID = os.getenv("INSTANCE_ID", "")

SERVICE_NAME = "py_vcon_server"

