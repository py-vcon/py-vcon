# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.

import typing
import pydantic
import py_vcon_server.processor


class QueueJobInitOptions(py_vcon_server.processor.VconProcessorInitOptions):
  """
  QueueJobInitOptions is passed to the queue_job processor when it is initialized.
  QueueJobInitOptions extends VconProcessorInitOptions, but does not add any new fields.
  """

class QueueJobOptions(py_vcon_server.processor.VconProcessorOptions):
  """
  QueueJobOptions is passed to the jqueue_job processor when processing the given VconProcessorIO.
  QueueJobOptions indicates where the job is to be queued and optionally labels the queued job
  with the queue from which it came.
  """
  queue_name: str = pydantic.Field(
      title = "Job queue name",
      description = "name of the queue to put the job in",
      default = ""
    )

  from_queue: typing.Union[str, None] = pydantic.Field(
      title = "From queue name",
      description = "name of the queue in which this processor is run."
        "  This may be used for diagnostic purpose to track what pipeline the job came from."
        "  This string does not effect the functionality.",
      default = None
    )


class QueueJob(py_vcon_server.processor.VconProcessor):
  """
  Processor to add a job to a **JobQueue**.

  A vcon_uuid Job is added to the named queue, using the UUID from the vCon at
  the **input_vcon_index** in the input options.
  """

  def __init__(
    self,
    init_options: QueueJobInitOptions
    ):

    super().__init__(
      "Processor to add a job to a **JobeQueue**",
      "A vCon_uuid Job is added to the named queue, using the UUID from the vCon at"
      " the **input_vcon_index** in the input options.",
      "0.0.1",
      init_options,
      QueueJobOptions,
      False # modifies a Vcon
      )


  async def process(self,
    processor_input: py_vcon_server.processor.VconProcessorIO,
    options: QueueJobOptions
    ) -> py_vcon_server.processor.VconProcessorIO:
    """
    Set the VconProcessorIO parameters from the input options parameters.  Does not modify the vCons.
    """
    uuid = await processor_input.get_vcon(
        options.input_vcon_index,
        py_vcon_server.processor.VconTypes.UUID
      )

    processor_input.add_vcon_uuid_queue_job(
        options.queue_name,
        [uuid],
        options.from_queue
      )
    return(processor_input)

