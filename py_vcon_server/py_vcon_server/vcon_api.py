import typing
import pydantic
import datetime
import time
import fastapi.responses
import py_vcon_server.db
import py_vcon_server.pipeline
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
  @restapi.get("/vcon/{vcon_uuid}", tags = [ py_vcon_server.restful_api.VCON_TAG ])
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

  @restapi.post("/vcon", tags = [ py_vcon_server.restful_api.VCON_TAG ])
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

  @restapi.delete("/vcon/{vcon_uuid}",
    status_code = 204,
    tags = [ py_vcon_server.restful_api.VCON_TAG ])
  async def delete_vcon(vcon_uuid: str):
    """
    Delete the vCon idenfied by the given UUID from VconStorage

    Returns: None
    """
    try:
      logger.debug("deleting vcon UUID: {}".format(vcon_uuid))
      await py_vcon_server.db.VconStorage.delete(vcon_uuid)

    except Exception as e:
      logger.info("Error: {}".format(e))
      return 500

    logger.debug("Deleted vcon: UUID={}".format(vcon_uuid))

    # no return should cause 204, no content

  @restapi.get("/vcon/{vcon_uuid}/jq", tags = [ py_vcon_server.restful_api.VCON_TAG ])
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

  @restapi.get("/vcon/{vcon_uuid}/jsonpath",
    tags = [ py_vcon_server.restful_api.VCON_TAG ])
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


  class VconProcessorOptions(pydantic.BaseModel):
    """ Base class options for vCon processors """
    input_vcon_index: int = pydantic.Field(
      title = "PipelineIO input vCon index",
      description = "Index to which vCon in the PipelineIO is to be used for input",
      default = 0
      )

  class AOptions(VconProcessorOptions):
    """ input options for the A vCon processor """
    a: int = pydantic.Field(
      title = "A's a",
      description = "A bunch of A stuff for a",
      example = 7
      )
    b: int = pydantic.Field(
      title = "A's b",
      description = "A bunch of A stuff for b",
      example = 1111 
      )

  class B(VconProcessorOptions):
    MM: str = pydantic.Field(
      title = "B's a",
      description = "A bunch of B stuff for MM",
      example = "ddddddd"
      )
    NN: str = pydantic.Field(
      title = "B's NN",
      description = "A bunch of B stuff for NN",
      example = "fffffff ff"
      )
    OO: str = pydantic.Field(
      title = "B's OO",
      description = "A bunch of N stuff for OO",
      example = "aa dd gg"
      )

  class C(VconProcessorOptions):
    a: int = pydantic.Field(
      title = "C's a",
      description = "A bunch of C stuff for a",
      example = 9
      )
    b: int = pydantic.Field(
      title = "C's b",
      description = "A bunch of C stuff for b",
      example = 2222 
      )

  import enum
  processor_types = (AOptions, B, C)
  processor_names = {"A": "A", "B": "B", "C": "C"}
  processor_name_dict = {"A": AOptions, "B": B, "C": C}
  processor_type_dict = {AOptions: "A", B: "B", C: "C"}
  processor_name_enum = enum.Enum("DynamicEnum", processor_names)
  processor_doc = {
    "A": "A does special stuff with a and b",
    "B": "B does special suff with MM, NN and OO",
    "C": "C does special stuff with a and b"
    }

  for processor_name in processor_names:
    @restapi.post("/vcon/{{vcon_uuid}}/{}".format(processor_name),
      summary = "Run the {} Processor on vCon".format(processor_name),
      tags = [ py_vcon_server.restful_api.PROCESSOR_TAG ])
    async def run_vcon_processor(
      options: processor_name_dict[processor_name],
      vcon_uuid: str,
      request: fastapi.Request,
      save_result: bool = True
      ) -> str:
      processor_name = processor_type_dict[type(options)]
      path = request.url.path
      logger.debug("type: {} path: {} ({}) prop: {}".format(processor_name, path, type(options), options))

      pipeline_input = py_vcon_server.pipeline.PipelineIO()
      pipeline_input.add_vcon(vcon_uuid)

      # TODO remove this, its only for testing
      # get vcon to test if the UUID is a valid one
      vcon_object = await pipeline_input.get_vcon(options.input_vcon_index,
        py_vcon_server.pipeline.VconTypes.OBJECT)
      #assert(isinstance(vcon_object, vcon.Vcon))
      logger.debug("got type: {} vcon: {}".format(type(vcon_object), vcon_object))

      return(fastapi.responses.JSONResponse(content = vcon_object))

