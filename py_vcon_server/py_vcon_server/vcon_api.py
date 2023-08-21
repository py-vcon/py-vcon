import os
import typing
import pydantic
import datetime
import time
import enum
import logging
import fastapi
import fastapi.responses
import py_vcon_server.db
import py_vcon_server.processor
import py_vcon_server.logging_utils
import vcon
import vcon.utils

logger = py_vcon_server.logging_utils.init_logger(__name__)

class VconPartiesObject(pydantic.BaseModel, extra=pydantic.Extra.allow):
  tel: str = pydantic.Field(
    title = "tel URI",
    description = "a telephone number",
    example = "+1 123 456 7890"
    )

date_examples = [ int(time.time()),
  time.time(),
  "Wed, 14 May 2022 18:16:19 -0000",
  vcon.utils.cannonize_date(time.time()),
  "2022-05-14T18:16:19.000+00:00"
  ]

class VconObject(pydantic.BaseModel, extra=pydantic.Extra.allow):
  vcon: str = pydantic.Field(
    title = "vCon format version",
    #description = "vCon format version,
    default = vcon.Vcon.CURRENT_VCON_VERSION
    )
  uuid: str
  created_at: typing.Union[pydantic.PositiveInt, pydantic.PositiveFloat, str, datetime.datetime] = pydantic.Field(
    title = "vCon format version",
    #description = "vCon format version,
    default_factory=lambda: vcon.utils.cannonize_date(time.time()),
    example = date_examples[3],
    examples = date_examples
    )

  # subject: str = None
  # redacted: typing.Optional[typing.Union[typing.List[dict], None]] = None
  # appended: typing.Optional[typing.Union[typing.List[dict], None]] = None
  # group: typing.Optional[typing.Union[typing.List[dict], None]] = None
  parties: typing.Optional[typing.Union[typing.List[VconPartiesObject], None]] = None
  dialog: typing.Optional[typing.Union[typing.List[dict], None]] = None
  analysis: typing.Optional[typing.Union[typing.List[dict], None]] = None
  attachments: typing.Optional[typing.Union[typing.List[dict], None]] = None

def init(restapi):
  @restapi.get("/vcon/{vcon_uuid}",
    responses = py_vcon_server.restful_api.ERROR_RESPONSES,
    tags = [ py_vcon_server.restful_api.VCON_TAG ])
  async def get_vcon(vcon_uuid: str):
    """
    Get the vCon object identified by the given UUID.

    Returns: dict - vCon object which may be in the unencrypted, signed or encrypted JSON forms
    """

    try:
      logger.debug("getting vcon UUID: {}".format(vcon_uuid))
      vCon = await py_vcon_server.db.VconStorage.get(vcon_uuid)

    except py_vcon_server.db.VconNotFound as e:
      py_vcon_server.restful_api.log_exception(e)
      return(py_vcon_server.restful_api.NotFoundResponse("vCon UUID: {} not found".format(vcon_uuid)))

    except Exception as e:
      py_vcon_server.restful_api.log_exception(e)
      return(py_vcon_server.restful_api.InternalErrorResponse(e))

    logger.debug(
      "Returning whole vcon for {} found: {}".format(vcon_uuid, vCon is not None))

    if(vCon is None):
      raise(fastapi.HTTPException(status_code=404, detail="Vcon not found"))

    return(fastapi.responses.JSONResponse(content=vCon.dumpd()))

  @restapi.post("/vcon",
    status_code = 204,
    responses = py_vcon_server.restful_api.ERROR_RESPONSES,
    tags = [ py_vcon_server.restful_api.VCON_TAG ])
  async def post_vcon(inbound_vcon: VconObject):
    """
    Store the given vCon in VconStorage, replace if it exists for the given UUID
    """
    try:
      vcon_dict = inbound_vcon.dict(exclude_none = True)

      vcon_uuid = vcon_dict.get("uuid", None)
      logger.debug("setting vcon UUID: {}".format(vcon_uuid))

      if(vcon_uuid is None or len(vcon_uuid) < 1):
        return(py_vcon_server.restful_api.ValidationError("vCon UUID: not set"))

      vcon_object = vcon.Vcon()
      vcon_object.loadd(vcon_dict)

      await py_vcon_server.db.VconStorage.set(vcon_dict)

    except vcon.InvalidVconJson as e:
      py_vcon_server.restful_api.log_exception(e)
      return(py_vcon_server.restful_api.ValidationError(str(e)))

    except Exception as e:
      py_vcon_server.restful_api.log_exception(e)
      return(py_vcon_server.restful_api.InternalErrorResponse(e))

    # No return should emmit 204, no content

  @restapi.delete("/vcon/{vcon_uuid}",
    status_code = 204,
    responses = py_vcon_server.restful_api.ERROR_RESPONSES,
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
      py_vcon_server.restful_api.log_exception(e)
      return(py_vcon_server.restful_api.InternalErrorResponse(e))

    logger.debug("Deleted vcon: UUID={}".format(vcon_uuid))

    # no return should cause 204, no content

  @restapi.get("/vcon/{vcon_uuid}/jq",
    responses = py_vcon_server.restful_api.ERROR_RESPONSES,
    tags = [ py_vcon_server.restful_api.VCON_TAG ])
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
      py_vcon_server.restful_api.log_exception(e)
      return(py_vcon_server.restful_api.InternalErrorResponse(e))

    return(fastapi.responses.JSONResponse(content=transform_result))

  @restapi.get("/vcon/{vcon_uuid}/jsonpath",
    responses = py_vcon_server.restful_api.ERROR_RESPONSES,
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
      py_vcon_server.restful_api.log_exception(e)
      return(py_vcon_server.restful_api.InternalErrorResponse(e))

    return(fastapi.responses.JSONResponse(content=query_result))


  class AOptions(py_vcon_server.processor.VconProcessorOptions):
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

  class B(py_vcon_server.processor.VconProcessorOptions):
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

  class C(py_vcon_server.processor.VconProcessorOptions):
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
      response_model = VconObject,
      responses = py_vcon_server.restful_api.ERROR_RESPONSES,
      tags = [ py_vcon_server.restful_api.PROCESSOR_TAG ])
    async def run_vcon_processor(
      options: processor_name_dict[processor_name],
      vcon_uuid: str,
      request: fastapi.Request,
      save_result: pydantic.StrictBool = True
      ) -> str:

      try:
        processor_name = processor_type_dict[type(options)]
        path = request.url.path
        processor_name_from_path = os.path.basename(path)

        logger.debug("type: {} path: {} ({}) options: {} processor: {}".format(
          processor_name, path, type(options), options, processor_name_from_path))

        processor_input = py_vcon_server.processor.VconProcessorIO()
        await processor_input.add_vcon(vcon_uuid)

        # TODO remove this, its only for testing
        # get vcon to test if the UUID is a valid one
        vcon_object = await processor_input.get_vcon(options.input_vcon_index,
          py_vcon_server.processor.VconTypes.OBJECT)
        #assert(isinstance(vcon_object, vcon.Vcon))

        # Avoid serialization of Vcon if e are not logging debug
        logger.debug("Effective level: {}".format(logger.getEffectiveLevel()))
        if(logger.getEffectiveLevel() <= logging.DEBUG):
          logger.debug("got type: {} vcon: {}".format(type(vcon_object), vcon_object.dumps()))

      except py_vcon_server.db.VconNotFound as e:
        py_vcon_server.restful_api.log_exception(e)
        return(py_vcon_server.restful_api.NotFoundResponse("vCon UUID: {} not found".format(vcon_uuid)))

      except Exception as e:
        py_vcon_server.restful_api.log_exception(e)
        return(py_vcon_server.restful_api.InternalErrorResponse(e))

      return(fastapi.responses.JSONResponse(content = vcon_object.dumpd()))

