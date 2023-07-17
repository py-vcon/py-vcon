import pkgutil
import importlib
import py_vcon_server.db
import py_vcon_server.logging_utils

logger = py_vcon_server.logging_utils.init_logger(__name__)

# Import the db modules and interface registrations
for finder, module_name, is_package in pkgutil.iter_modules(py_vcon_server.db.__path__, 
  py_vcon_server.db.__name__ + "."):
  logger.info("db module load: {}".format(module_name))
  importlib.import_module(module_name)


