# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" good implementations of **VconProcessor** for testing """

import typing
import asyncio
import py_vcon_server.processor

__version__ = "0.0.1"

class AddPartyOptions(py_vcon_server.processor.VconProcessorOptions):
  tel: typing.Optional[str] = None
  

class AddParty(py_vcon_server.processor.VconProcessor):
  """ adds a new party with the Vcon Party Object parameters provided in the **AddPartyOptions** """
  def __init__(
    self,
    init_options: py_vcon_server.processor.VconProcessorInitOptions
    ):
    super().__init__(
      "Add party to Vcon",
      None,
      __version__,
      init_options,
      AddPartyOptions,
      True # modifies a Vcon
      )

  async def process(self,
    processor_input: py_vcon_server.processor.VconProcessorIO,
    options: AddPartyOptions
    ) -> py_vcon_server.processor.VconProcessorIO:
    if(options.tel is not None and
      options.tel != ""):
      index = options.input_vcon_index
      vCon = await processor_input.get_vcon(index)

      party_index = vCon.set_party_parameter("tel", options.tel)
      await processor_input.update_vcon(vCon)

    return(processor_input)

