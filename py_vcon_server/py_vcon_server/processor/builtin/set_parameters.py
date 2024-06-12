# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.

import typing
import pydantic
import py_vcon_server.processor

class SetParametersInitOptions(py_vcon_server.processor.VconProcessorInitOptions):
  pass

class SetParametersOptions(py_vcon_server.processor.VconProcessorOptions):
  parameters: typing.Dict[str, typing.Any] = pydantic.Field(
      title = "dict of parameters to set in the output from VconProcessor",
      default = {}
    )


class SetParameters(py_vcon_server.processor.VconProcessor):
  """ Processor to set VconProcessorIO parameters from options """

  def __init__(
    self,
    init_options: SetParametersInitOptions
    ):

    super().__init__(
      "set VconProcessorIO parameters from process options input",
      "set VconProcessorIO parameters from the parameters dict field provided in the processor options",
      "0.0.1",
      init_options,
      SetParametersOptions,
      False # modifies a Vcon
      )


  async def process(self,
    processor_input: py_vcon_server.processor.VconProcessorIO,
    options: SetParametersOptions
    ) -> py_vcon_server.processor.VconProcessorIO:
    """
    Set the VconProcessorIO parameters from the input options parameters.  Does not modify the vCons.
    """

    new_values = options.parameters

    for name in new_values.keys():
       processor_input.set_parameter(name, new_values[name])

    return(processor_input)

