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
  async def get_server_states():
    """ Get a JSON dictionary of running server states """

    try:
      logger.debug("getting servers")
      server_dict = await py_vcon_server.server_state.get_server_states()

    except Exception as e:
      logger.info("Error: {}".format(e))
      return None

    logger.debug( "Returning {} servers".format(len(server_dict)))
    logger.debug( "servers type: {}".format(type(server_dict)))
    logger.debug( "servers: {}".format(server_dict))

    return(fastapi.responses.JSONResponse(content=server_dict))

  @restapi.delete("/server/{server_key}")
  async def delete_server_state(server_key: str):
    """
    Delete the server state entry for the given server_key.
    <br><i> This should generally only used to clean up server states for servers that did not gracefully shutdown.</i>

    The server key is composed as: "host:port:pid".
    <br>  host and port are from the REST_URL setting.
    """

    try:
      logger.debug("deleting server state: {}".format(server_key))
      server_dict = await py_vcon_server.server_state.delete_server_state(server_key)

    except Exception as e:
      logger.info("Error: {}".format(e))
      return 500

    logger.debug("Deleted server state: {}".format(server_key))

    # no return should cause 204, no content

