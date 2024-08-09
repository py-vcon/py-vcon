# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" FilterPlugin for JWS verification of vCon """
import typing
import pydantic
import vcon.filter_plugins


class VerifyFilterPluginInitOptions(
  vcon.filter_plugins.FilterPluginInitOptions,
  title = "JWS verification of vCon **FilterPlugin** intialization object"
  ):
  """
  A **VerifyFilterPluginInitOptions** object is provided to the
  **Verify FilterPlugin.__init__** method when it is first loaded.  Its
  attributes effect how the registered **FilterPlugin** functions.
  """

  allowed_ca_cert_pems: typing.List[str] = pydantic.Field(
    title = "default list of trusted CA PEMs",
    description = """
default list of trusted Certificate Authority certificate PEMs.  
In order to be valid/trusted, one of the certs in the JWS x5c certificate chain
must be a trusted CA (i.e. in this list).  verifcation will fail if
this is not the case.
""",
    default = []
    )



class VerifyFilterPluginOptions(
  vcon.filter_plugins.FilterPluginOptions,
  title = "verify filter method options"
  ):
  """
  Options for JWS verification of vCon in filter_plugin.
  """

  allowed_ca_cert_pems: typing.List[str] = pydantic.Field(
    title = "list of trusted CA PEMs",
    description = """
list of trusted Certificate Authority certificate PEMs to use in filter method.
In order to be valid/trusted, one of the certs in the JWS x5c certificate chain
must be a trusted CA (i.e. in this list).  Verifcation will fail if
this is not the case.
""",
    default = []
    )


class VerifyFilterPlugin(vcon.filter_plugins.FilterPlugin):
  """
  **FilterPlugin** for JWS verification of vCon
  """
  init_options_type = VerifyFilterPluginInitOptions

  def __init__(
    self,
    init_options: VerifyFilterPluginInitOptions
    ):
    """
    Parameters:
      init_options (VerifyFilterPluginInitOptions) - the initialization options for JWS verification of vCon in plugin
    """
    super().__init__(
      init_options,
      VerifyFilterPluginOptions
      )


  async def filter(
    self,
    in_vcon: vcon.Vcon,
    options: VerifyFilterPluginOptions
    ) -> vcon.Vcon:
    """
    verify vCon using JWS

    Parameters:
      options (VerifyFilterPluginOptions)

    Returns:
      the verified Vcon object (JWS)
    """
    out_vcon = in_vcon

    ca_list = options.allowed_ca_cert_pems
    # Use default if not provided
    if(ca_list is None or len(ca_list) == 0):
      ca_list = self._init_options.allowed_ca_cert_pems

    out_vcon.verify(ca_list)
    return(out_vcon)


  def check_valid_state(
      self,
      filter_vcon: vcon.Vcon
    ) -> None:
    """
    Check to see that the vCon is in a valid state to have signaure verified
    """

    # do nothing, the Vcon.verify method will check state


