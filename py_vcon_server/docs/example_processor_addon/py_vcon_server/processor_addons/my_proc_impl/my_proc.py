
import typing
import pydantic
import py_vcon_server.processor

logger = py_vcon_server.logging_utils.init_logger(__name__)

class MyProcInitOptions(py_vcon_server.processor.VconProcessorInitOptions):
  """
  MyProcInitOptions is passed to the my_proc processor when it is initialized.
  MyProcInitOptions extends VconProcessorInitOptions, but does not add any new fields.
  """

class MyProcOptions(py_vcon_server.processor.VconProcessorOptions):
  """
  MyProcOptions is passed to the my_proc processor.
  It does not add any new options.
  """


class MyProc(py_vcon_server.processor.VconProcessor):
  """
  Example addon processor that counts the number or parties.
  This is just to demonstrate out to create a separate addon processor.
  It is quite simple to thet the party count using the jq processor without
  creating a new processor.
  """

  def __init__(
    self,
    init_options: MyProcInitOptions
    ):

    super().__init__(
      "example addon VconProcessor to count parties",
      "This is just to demonstrate out to create a separate addon processor."
      " It is quite simple to thet the party count using the jq processor without"
      " creating a new processor.   The party count get set in the VconProcessorIO"
      " parameter: **party_count**.",
      "0.0.1",
      init_options,
      MyProcOptions,
      False # modifies a Vcon
      )


  async def process(self,
    processor_input: py_vcon_server.processor.VconProcessorIO,
    options: MyProcOptions
    ) -> py_vcon_server.processor.VconProcessorIO:
    """
    Set the VconProcessorIO parameters from the input options parameters.  Does not modify the vCons.
    """

    useVcon = await processor_input.get_vcon(options.input_vcon_index)
    party_count = 0
    if(useVcon):
      party_count = len(useVcon.parties)

    processor_input.set_parameter("party_count", party_count)

    return(processor_input)

