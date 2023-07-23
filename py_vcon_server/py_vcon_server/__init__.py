import sys
import pkgutil
import importlib
import asyncio
import fastapi

# For dev purposes, look for relative vcon package
sys.path.append("..")

import py_vcon_server.settings
import py_vcon_server.db
from py_vcon_server.logging_utils import init_logger

logger = init_logger(__name__)

__version__ = "0.1"

# Import the db modules and interface registrations
for finder, module_name, is_package in pkgutil.iter_modules(py_vcon_server.db.__path__, 
  py_vcon_server.db.__name__ + "."):
  logger.info("db module load: {}".format(module_name))
  importlib.import_module(module_name)


import py_vcon_server.vcon_api
import py_vcon_server.admin_api

restapi = fastapi.FastAPI()

@restapi.on_event("startup")
async def startup():
  logger.info("event startup")
  await py_vcon_server.db.VconStorage.setup(py_vcon_server.settings.VCON_STORAGE_TYPE,
    py_vcon_server.settings.VCON_STORAGE_URL)

@restapi.on_event("shutdown")
async def shutdown():
  logger.info("event shutdown")
  await py_vcon_server.db.VconStorage.teardown()

# Enable Admin entry points
if(py_vcon_server.settings.LAUNCH_ADMIN_API):
  py_vcon_server.admin_api.init(restapi)

# Enable Vcon entry points
if(py_vcon_server.settings.LAUNCH_VCON_API):
  py_vcon_server.vcon_api.init(restapi)

