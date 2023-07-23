import typing
import fastapi.responses
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


