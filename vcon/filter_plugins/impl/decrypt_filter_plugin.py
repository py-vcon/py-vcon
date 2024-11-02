# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" FilterPlugin for JWE decripting of vCon """
import typing
import pydantic
import vcon.filter_plugins

logger = vcon.build_logger(__name__)


class NoPrivateKey(Exception):
  """ Raised when private key is missing """


class NoPublicKey(Exception):
  """ Raised when private key is missing """


class DecryptFilterPluginInitOptions(
  vcon.filter_plugins.FilterPluginInitOptions,
  title = "JWE decripting of vCon **FilterPlugin** intialization object"
  ):
  """
  A **DecryptFilterPluginInitOptions** object is provided to the
  **DecryptFilterPlugin.__init__** method when it is first loaded.  Its
  attributes effect how the registered **FilterPlugin** functions.
  """

  private_pem_key: typing.Union[str, None] = pydantic.Field(
    title = "default PEM format private key to use for decrypting a vCon",
    description = """
""",
    default = None
    )

  public_pem_key: typing.Union[str, None] = pydantic.Field(
    title = "default PEM format public key/cert to use for decrypting a vCon",
    description = """
""",
    default = None
    )


class DecryptFilterPluginOptions(
  vcon.filter_plugins.FilterPluginOptions,
  title = "decrypt filter method options"
  ):
  """
  Options for encrypting the vCon in filter_plugin.
  """

  private_pem_key: typing.Union[str, None] = pydantic.Field(
    title = "PEM format private key to use for decrypting the vCon",
    description = """
    Override the default PEM format private key for encrypting.
""",
    default = None
    )

  public_pem_key: typing.Union[str, None] = pydantic.Field(
    title = "PEM format public key/cert to use for encrypting the vCon",
    description = """
    Override the default PEM format public key/cert for encrypting.
""",
    default = None
    )


class DecryptFilterPlugin(vcon.filter_plugins.FilterPlugin):
  """
  **FilterPlugin** for JWE decrypting of vCon
  """
  init_options_type = DecryptFilterPluginInitOptions

  def __init__(
    self,
    init_options: DecryptFilterPluginInitOptions
    ):
    """
    Parameters:
      init_options (DecryptFilterPluginInitOptions) - the initialization options for JWE decrypting of vCon in plugin
    """
    super().__init__(
      init_options,
      DecryptFilterPluginOptions
      )


  async def filter(
    self,
    in_vcon: vcon.Vcon,
    options: DecryptFilterPluginOptions
    ) -> vcon.Vcon:
    """
    decrypt vCon using JWE

    Parameters:
      options (DecryptFilterPluginOptions)

    Returns:
      the decrypted Vcon object 
    """
    out_vcon = in_vcon

    private_key = options.private_pem_key
    # Use default if not provided
    if(private_key is None or len(private_key) == 0):
      private_key = self._init_options.private_pem_key
      if(private_key is None or len(private_key) == 0):
        raise NoPrivateKey("Encrypt filter plugin: {} no private key in DecryptFilterPluginInitOptions or DecryptFilterPluginOptions")

    public_key = options.public_pem_key
    # Use default if not provided
    if(public_key is None or len(public_key) == 0):
      public_key = self._init_options.public_pem_key
      if(public_key is None or len(public_key) == 0):
        raise NoPublicKey("Encrypt filter plugin: {} no public key in DecryptFilterPluginInitOptions or DecryptFilterPluginOptions")

    out_vcon.decrypt(private_key, public_key)
    return(out_vcon)

  def check_valid_state(
      self,
      filter_vcon: vcon.Vcon
    ) -> None:
    """
    Check to see that the vCon is in a valid state to be decripted
    """

    # do nothing, the Vcon.decrypt method will check state

