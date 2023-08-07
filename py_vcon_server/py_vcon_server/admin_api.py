import typing
import fastapi.responses
import pydantic
import py_vcon_server
import py_vcon_server.logging_utils
import py_vcon_server.settings
from . import __version__
import vcon

logger = py_vcon_server.logging_utils.init_logger(__name__)

class QueueProperties(pydantic.BaseModel):
    weight: int = 1


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

  @restapi.delete("/servers/{server_key}")
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

  @restapi.get("/server/queues")
  async def get_server_queues():
    """ Get the list of queues and related configuration for for this server """
    try:
      logger.debug("getting server queue info")
      queue_info = py_vcon_server.settings.WORK_QUEUES
    
    except Exception as e:
      logger.info("Error: {}".format(e))
      return None

    return(fastapi.responses.JSONResponse(content=queue_info))

  @restapi.post("/server/queue")
  async def post_server_queue(properties: QueueProperties, name: str) -> None:
    """
    Set the properties on the named queue on this server.

    <br> Currently the only queue property is the "weight".
    weight must be an integer value and indicates how many
    items should be de-queued from the given queue before
    rotating to hte nex queue.
    """

    try:
      logger.debug("setting queue: {} property: {}".format(name, properties))
      if(not isinstance(properties, QueueProperties)):
        raise Exception("Invalid type: {} for queue: {} properties: {}".format(type(properties), name, properties))
      py_vcon_server.settings.WORK_QUEUES[name] = dict(properties)
      logger.debug("WORK_QUEUES: {}".format(py_vcon_server.settings.WORK_QUEUES))

    except Exception as e:
        logger.info("Error: {}".format(e))
        return None

    # no return should cause 204, no content

  @restapi.delete("/server/queue/{name}")
  async def delete_server_queue(name: str):
    """
    Remove the named queue from the list of queues to process on this server
    """

    try:
      logger.debug("removing queue: {} from WORK_QUEUES".format(name))

      if(py_vcon_server.settings.WORK_QUEUES.get(name, None) is None):
        raise(fastapi.HTTPException(status_code=404,
          detail="queue: {} not found".format(name)))

      del py_vcon_server.settings.WORK_QUEUES[name]

    except Exception as e:
        logger.info("Error: {}".format(e))
        return None

    # no return should cause 204, no content

