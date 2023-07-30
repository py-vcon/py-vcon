import typing
import fastapi.responses
import py_vcon_server
import py_vcon_server.logging_utils
from . import __version__
import vcon

logger = py_vcon_server.logging_utils.init_logger(__name__)

def init(restapi):
  @restapi.get("/version")
  async def get_version():
    try:
      logger.debug("getting version")
      versions = {
        "py_vcon_server": __version__,
        "vcon": vcon.__version__
        }

    except Exception as e:
      logger.info("Error: {}".format(e))
      return None

    logger.debug( "Returning versions")

    return(fastapi.responses.JSONResponse(content=versions))

  @restapi.get("/servers")
  async def get_servers():

    try:
      logger.debug("getting servers")
      server_dict = await py_vcon_server.server_state.get_servers()

    except Exception as e:
      logger.info("Error: {}".format(e))
      return None

    logger.debug( "Returning {} servers".format(len(server_dict)))
    logger.debug( "servers type: {}".format(type(server_dict)))
    logger.debug( "servers: {}".format(server_dict))

    return(fastapi.responses.JSONResponse(content=server_dict))

