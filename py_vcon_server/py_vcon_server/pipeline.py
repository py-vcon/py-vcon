""" Vcon Pipeline processor objects and methods """
import typing
import pydantic
import json
import py_vcon_server.processor
import py_vcon_server.logging_utils

logger = py_vcon_server.logging_utils.init_logger(__name__)

PIPELINE_NAMES_KEY = "pipelines"
PIPELINE_NAME_PREFIX = "pipeline:"

PIPELINE_DB = None

class PipelineNotFound(Exception):
  """ Raised when Pipeline not found in the DB """


class PipelineInvalid(Exception):
  """ Raised for invalild pipelines """


class PipelineProcessor(pydantic.BaseModel):
  """
  Configuration for a VconProcessor in a Pipeline
  """
  processor_name: str = pydantic.Field(
      title = "VconProcessor name"
    )

  processor_options: py_vcon_server.processor.VconProcessorOptions = pydantic.Field(
      title = "VconProcessor options"
    )


class PipelineOptions(pydantic.BaseModel):
  """
  Options the effect the handling of Vcon Pipeline processing.
  """

  save_vcons: typing.Union[bool, None] = pydantic.Field(
      title = "save/update vCon(s) after pipeline processing"
    )

  timeout: typing.Union[int, None] = pydantic.Field(
      title = "processor timeout",
      description = """maximum timeout for any processor in the pipeline.
  If any one of the processors in the pipeline takes more than this number
 of seconds, the processor will be cancled, remaining processors will be
 skipped and the pipeline will be considered failed for the given job/vCon.
"""
    )

  failure_queue: typing.Union[str, None] = pydantic.Field(
      title = "queue for failed pipeline jobs"
    )


class PipelineDefinition(pydantic.BaseModel):
  """ Definition of the serialized representation of a VconPipeline """
  # queue_name should this be a field or is it implied by the name the pipeline is stored under???
  # sequence: typing.List[VconProcessorAndOptions] or list[VconProcessor names] and list[VconProcessorOptions]

  pipeline_options: PipelineOptions = pydantic.Field(
      title = "pipeline execution options"
    )

  processors: typing.List[PipelineProcessor] = pydantic.Field(
      title = "list of **VconProcessorConfig**",
      description = "The sequential set of **VconProcessorConfig** for the list of \
**VconProcessor**s that get run for this **Pipeline**"
    )


class PipelineDb():
  """ DB interface for Pipeline objects """
  def __init__(self, redis_url: str):
    logger.info("connecting PipelineDb redis_mgr")
    self._redis_mgr = py_vcon_server.db.redis.redis_mgr.RedisMgr(redis_url)
    self._redis_mgr.create_pool()

    # we can gain some optimization by registering all of the Lua scripts here
    redis_con = self._redis_mgr.get_client()

    # Lua scripts

    #keys = [ PIPELINE_NAMES_KEY, PIPELINE_NAME_PREFI + name ]
    #args = [ name, pipeline ]
    lua_script_set_pipeline = """
    -- Add the pipeline name to the name list if its new
    if redis.call("SISMEMBER", KEYS[1], ARGV[1]) == 0 then
      local num_added = redis.call("SADD", KEYS[1],  ARGV[1])
      -- Don't care if the name already exists
    end
    local ret = redis.call("JSON.SET", KEYS[2], "$", ARGV[2])
    return(ret)
    """
    self._do_lua_set_pipeline = redis_con.register_script(lua_script_set_pipeline)

    #keys = [ PIPELINE_NAMES_KEY, PIPELINE_NAME_PREFIX + name ]
    #args = [ name ]
    lua_script_delete_pipeline = """
    local ret = -2
    if redis.call("SISMEMBER", KEYS[1], ARGV[1]) == 1 then
      -- pipeline name is in the pipeline list, remove it
      redis.call("SREM", KEYS[1], ARGV[1])
      ret = 0 
    else
      ret = -1 
    end
    -- Always try to delete the pipeline even if its not in the list
    redis.call("DEL", KEYS[2])
    return(ret)
    """
    self._do_lua_delete_pipeline = redis_con.register_script(lua_script_delete_pipeline)



  async def shutdown(self):
    """ Shutdown the DB connection """
    if(self._redis_mgr):
      logger.debug("shutting down PipelineDb redis_mgr")
      await self._redis_mgr.shutdown_pool()
      self._redis_mgr = None
      logger.info("shutdown PipelineDb redis_mgr")


  async def get_pipeline_names(
      self,
    )-> typing.List[str]:
    """
    Get the list of names of all Pipelines.

    Parameters: none

    Returns: list[str] - names of all pipelines
    """
    redis_con = self._redis_mgr.get_client()
    return(await redis_con.smembers(PIPELINE_NAMES_KEY))


  async def set_pipeline(
      self,
      name: str,
      pipeline: typing.Union[dict, PipelineDefinition]
    )-> None:
    """
    Add or replace a Pipeline definition.

    Parameters:
      **name**: str - the name of the Pipeline to replace or create.
      **pipeline**: PipelineDefinition - Pipeline to create

    Returns: none
    """
    assert(isinstance(name, str))
    keys = [ PIPELINE_NAMES_KEY, PIPELINE_NAME_PREFIX + name ]
    if(isinstance(pipeline, dict)):
      args = [ name, json.dumps(pipeline) ]
    else:
      args = [ name, json.dumps(pipeline.dict()) ]

    result = await self._do_lua_set_pipeline(keys = keys, args = args)
    if(result != "OK"):
      raise Exception("set_pipeline {} Lua failed: {} pipeline: {}".format(name, result, pipeline))


  async def get_pipeline(
      self,
      name: str
    )-> PipelineDefinition:
    """
    Get the named **PipelineDefinition** from DB.

    Parameters:
      **name**: str - name of the PipelineDefinition to retieve

    Returns: PipelineDefinition if found, 
             exception PipelineNotFound if name does not exist
    """
    redis_con = self._redis_mgr.get_client()
    pipeline_dict = await redis_con.json().get(PIPELINE_NAME_PREFIX + name, "$")

    if(pipeline_dict is None):
      raise PipelineNotFound("Pipeline {} not found".format(name))

    if(len(pipeline_dict) != 1):
      raise PipelineInvalid("Pipeline {} got: {}".format(name, pipeline_dict))

    return(PipelineDefinition(**pipeline_dict[0]))


  async def delete_pipeline(
      self,
      name: str
    )-> None:
    """
    Delete the named **PipelineDefinition** from DB.

    Parameters:
      **name**: str - name of the PipelineDefinition to delete

    Returns: none
             exception PipelineNotFound if name does not exist
    """
    assert(isinstance(name, str))
    keys = [ PIPELINE_NAMES_KEY, PIPELINE_NAME_PREFIX + name ]
    args = [ name ]
    result = await self._do_lua_delete_pipeline(keys = keys, args = args)
    if(result == -1):
      raise PipelineNotFound("delete of Pipeline: {} not found".format(name))

    if(result != 0):
      raise Exception("delete of Pipeline: {} failed: {}".format(name, result))


  async def set_pipeline_options(
      self,
      name: str,
      options: PipelineOptions
    )-> None:
    raise Exception("not implemented")


  async def insert_pipeline_processor(
      self,
      name: str,
      processor: PipelineProcessor,
      index: int = -1
    )-> None:
    raise Exception("not implemented")


  async def delete_pipeline_processor(
      self,
      name: str,
      index: int
    )-> None:
    raise Exception("not implemented")


class PipelineManager():
  """ Manager for a sequence of **VconProcessor**s """
  def __init__(self):
    pass

  def add_processor(
    self,
    processor_name: str,
    processor_options: py_vcon_server.processor.VconProcessorOptions):
    raise Excepiton("Not implemented")


  def loads(self, pipeline_json: str):
    """
    Load processor sequence, their options and other pipeline config from a JSON string.
    """

  async def run(self, vcon_uuids: typing.List[str]):
    """
    TODO:
    The below pseudo code does not work.  The thing that dequeus and locks need to be in one context as you may have
    to pop several jobs before finding one that can lock all the input UUIDs.  If the work dispatcher does it, then
    it does not know the processors that may write or are read only.  If the work does the above, then how is the
    queue weighting and iteration get coordinated across all the workers.

    Construct a **VconProcessorIO** object from the vcon_uuids as input to the first VconProcessor
    Lock the vcons as needed
    run the sequence of **VconProcessor**s passing the constructed **VconPocessorIO** 
    object to the first in the sequence and then passing its output to the next and so on for the whole sequence.
    Commit the new and changed **Vcon**s from the final **VconProcessor** in the sequence's output 
    """


  def pipeline_sequence_may_write(pipeline: PipelineDefinition) -> bool:
    """
    Look up to see if any of the **VconProcessor**s in the pipeline's sequence may modify its input **Vcon**s.
    """

