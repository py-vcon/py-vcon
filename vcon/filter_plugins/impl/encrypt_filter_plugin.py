# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" FilterPlugin for JWE encryption of vCon """
import typing
import pydantic
import vcon.filter_plugins

logger = vcon.build_logger(__name__)


class EncryptFilterPluginInitOptions(
  vcon.filter_plugins.FilterPluginInitOptions,
  title = "JWE encryption of vCon **FilterPlugin** intialization object"
  ):
  """
  A **EncryptFilterPluginInitOptions** object is provided to the
  **EncryptFilterPlugin.__init__** method when it is first loaded.  Its
  attributes effect how the registered **FilterPlugin** functions.
  """
  private_pem_key: typing.Union[str, None] = pydantic.Field(
    title = "default PEM format private key to use for encrypting a vCon",
    description = """
""",
    default = None
    )


class EncryptFilterPluginOptions(
  vcon.filter_plugins.FilterPluginOptions,
  title = "encrypt filter method options"
  ):
  """
  Options for encrypting the vCon in filter_plugin.
  """

  private_pem_key: typing.Union[str, None] = pydantic.Field(
    title = "PEM format private key to use for encrypting the vCon",
    description = """
    Override the default PEM format private key for encrypting.
""",
    default = None
    )


class EncryptFilterPlugin(vcon.filter_plugins.FilterPlugin):
  """
  **FilterPlugin** for JWE encrypting of vCon
  """
  init_options_type = EncryptFilterPluginInitOptions

  def __init__(
    self,
    init_options: EncryptFilterPluginInitOptions
    ):
    """
    Parameters:
      init_options (EncryptFilterPluginInitOptions) - the initialization options for JWE encrypting of vCon in plugin
    """
    super().__init__(
      init_options,
      EncryptFilterPluginOptions
      )


  async def filter(
    self,
    in_vcon: vcon.Vcon,
    options: EncryptFilterPluginOptions
    ) -> vcon.Vcon:
    """
    encrypt vCon using JWE

    Parameters:
      options (EncryptFilterPluginOptions)

    Returns:
      the encrypted Vcon object (JWE)
    """
    out_vcon = in_vcon

    private_key = options.private_pem_key
    # Use default if not provided
    if(private_key is None or len(private_key) == 0):
      private_key = self._init_options.private_pem_key
      if(private_key is None or len(private_key) == 0):
        raise NoPrivateKey("Encrypt filter plugin: {} no private key in EncryptFilterPluginInitOptions or EncryptFilterPluginOptions")

    out_vcon.encrypt(private_key)
    return(out_vcon)

  def check_valid_state(
      self,
      filter_vcon: vcon.Vcon
    ) -> None:
    """
    Check to see that the vCon is in a valid state to have signaure verified
    """

    # do nothing, the Vcon.encrypt method will check state

