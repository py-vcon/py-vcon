import typing
import pydantic
import datetime
import time
import fastapi.responses
import py_vcon_server.db
import py_vcon_server.logging_utils
import vcon
import vcon.utils

logger = py_vcon_server.logging_utils.init_logger(__name__)

class Vcon(pydantic.BaseModel, extra=pydantic.Extra.allow):
  vcon: str = vcon.Vcon.CURRENT_VCON_VERSION
  uuid: str
  created_at: typing.Union[int, str, datetime.datetime] = pydantic.Field(default_factory=lambda: vcon.utils.cannonize_date(time.time()))
  subject: str = None
  redacted: dict = None
  appended: dict = None
  group: typing.List[dict] = []
  parties: typing.List[dict] = []
  dialog: typing.List[dict] = []
  analysis: typing.List[dict] = []
  attachments: typing.List[dict] = []

def init(restapi):
  @restapi.get("/vcon/{vcon_uuid}")
  async def get_vcon(vcon_uuid: str):
    """
    Get the vCon object identified by the given UUID.

    Returns: dict - vCon object which may be in the unencrypted, signed or encrypted JSON forms
    """

    try:
      logger.debug("getting vcon UUID: {}".format(vcon_uuid))
      vCon = await py_vcon_server.db.VconStorage.get(vcon_uuid)

    except Exception as e:
      logger.info("Error: {}".format(e))
      return None
    logger.debug(
        "Returning whole vcon for {} found: {}".format(vcon_uuid, vCon is not None)
    )
    if(vCon is None):
      raise(fastapi.HTTPException(status_code=404, detail="Vcon not found"))

    return(fastapi.responses.JSONResponse(content=vCon.dumpd()))

  @restapi.post("/vcon")
  async def post_vcon(inbound_vcon: Vcon, vcon_uuid: typing.Union[str, None] = None):
    """
    Store the given vCon in VconStorage, replace if it exists for the given UUID
    """
    try:
      logger.debug("setting vcon UUID: {}".format(vcon_uuid))
      vcon = await py_vcon_server.db.VconStorage.set(inbound_vcon.dict())
    except Exception as e:
      logger.info("Error: {}".format(e))
      return None
    return(fastapi.responses.JSONResponse(content=vcon))

  @restapi.delete("/vcon/{vcon_uuid}")
  async def delete_vcon(vcon_uuid: str):
    """
    Delete the vCon idenfied by the given UUID from VconStorage
    """
    try:
      logger.debug("deleting vcon UUID: {}".format(vcon_uuid))
      await py_vcon_server.db.VconStorage.delete(vcon_uuid)

    except Exception as e:
      logger.info("Error: {}".format(e))
      return 500

    logger.debug("Deleted vcon: UUID={}".format(vcon_uuid))

    # no return should cause 204, no content

  @restapi.get("/vcon/{vcon_uuid}/jq")
  async def get_vcon_jq_transform(vcon_uuid: str, jq_transform: str):
    """
    Apply the given jq transform to the vCon identified by the given UUID and return the results.

    Returns: list - containing jq tranform of the vCon.
    """
    try:
      logger.info("vcon UID: {} jq transform string: {}".format(vcon_uuid, jq_transform))
      transform_result = await py_vcon_server.db.VconStorage.jq_query(vcon_uuid, jq_transform)
      logger.debug("jq  transform result: {}".format(transform_result))

    except Exception as e:
        logger.info("Error: {}".format(e))
        return None

    return(fastapi.responses.JSONResponse(content=transform_result))

  @restapi.get("/vcon/{vcon_uuid}/jsonpath")
  async def get_vcon_jsonpath_query(vcon_uuid: str, path_string: str):
    """
    Apply the given JSONpath query to the vCon idntified by the given UUID.

    Returns: list - the JSONpath query results
    """

    try:
      logger.info("vcon UID: {} jsonpath query string: {}".format(vcon_uuid, path_string))
      query_result = await py_vcon_server.db.VconStorage.json_path_query(vcon_uuid, path_string)
      logger.debug("jsonpath query result: {}".format(query_result))

    except Exception as e:
        logger.info("Error: {}".format(e))
        return None

    return(fastapi.responses.JSONResponse(content=query_result))

