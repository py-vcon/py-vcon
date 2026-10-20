# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.

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
  QueueJobOptions is passed to the queue_job processor when processing the given VconProcessorIO.
  QueueJobOptions indicates where the job is to be queued and optionally labels the queued job
  with the queue from which it came.
  """
  queue_name: str = pydantic.Field(
      title = "Job queue name",
      description = "name of the queue to put the job in",
      min_length = 1
    )

  create_queue: bool = pydantic.Field(
      title = "Create queue if missing",
      description = "When True, create the named queue if it does not already"
        " exist before queuing the job.  When False (default), queuing to a"
        " queue that does not exist fails.",
      default = False
    )

  from_queue: typing.Union[str, None] = pydantic.Field(
      title = "From queue name",
      description = "name of the queue in which this processor is run."
        "  This may be used for diagnostic purpose to track what pipeline the job came from."
        "  This string does not effect the functionality.",
      default = ""
    )

  job_parameters: typing.Dict[str, typing.Any] = pydantic.Field(
      title = "Job parameters",
      description = "Optional parameters set on the pipeline input before the"
        " queued job runs.  Serialized into the queued job under the parameters"
        " key.  Named job_parameters to distinguish from the processor IO"
        " parameters.  May be set from parameters using format_options; see the"
        " format_options description for the dict template rules and examples.",
      default = {},
      examples = [
          {"customer_tier": "gold"},
          {"summary_prompt": "Summarize the transcript in two sentences."}
        ]
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
      "0.0.2",
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
    if(options.queue_name is None or options.queue_name == ""):
      raise Exception("queue_job processor: queue_name must be a non-empty string")

    uuid = await processor_input.get_vcon(
        options.input_vcon_index,
        py_vcon_server.processor.VconTypes.UUID
      )

    processor_input.add_vcon_uuid_queue_job(
        options.queue_name,
        options.create_queue,
        [uuid],
        options.from_queue,
        options.job_parameters
      )
    return(processor_input)

