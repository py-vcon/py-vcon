

import typing
import pydantic
import py_vcon_server.processor
import py_vcon_server.logging_utils

logger = py_vcon_server.logging_utils.init_logger(__name__)


class VconPipelineModel(pydantic.BaseModel):
  """ Definition of the serialized representation of a VconPipeline """
  # queue_name should this be a field or is it implied by the name the pipeline is stored under???
  # sequence: typing.List[VconProcessorAndOptions] or list[VconProcessor names] and list[VconProcessorOptions]
  # persist_vcons: bool - should vcon changes and new Vcons created be commited at the end or dropped



class Pipeline:
  """ Container and manager for a sequence of **VconProcessor**s """
  def __init__(self):
    pass

  def add_processor(
    self,
    processor: py_vcon_server.processor.VconProcessor,
    processor_options: py_vcon_server.processor.VconProcessorOptions):
    raise Excepiton("Not implemented")

  
  def loads(self, pipeline_json: str):
    """
    Load processor sequence, their options and other pipeline config from a JSON string.
    """

  def run(self, vcon_uuids: typing.List[str]):
    """
    TODO:
    The below pseudo code does not work.  The thing that dequeus and locks need to be in one context as you may have
    to pop several jobs before finding one that can lock all the input UUIDs.  If the work dispatcher does it, then
    it does not know the processors that may write or are read only.  If the work does the above, then how is the
    queue weighting and iteration get coordinated across all the workers.

    Construct a **VconProcessorIO** object from the vcon_uuids as input to the first VconProcessor
    Lock the vcons as needed
    run the sequence of **VconProcessor**s passing the constructed **VconPocessorIO** object to the first in the sequence and then passing its output to the next and so on for the whole sequence.
    Commit the new and changed **Vcon**s from the final **VconProcessor** in the sequence's output 
    """


  def pipeline_sequence_may_write(pipeline: VconPipelineModel) -> bool:
    """
    Look up to see if any of the **VconProcessor**s in the pipeline's sequence may modify its input **Vcon**s.
    """

