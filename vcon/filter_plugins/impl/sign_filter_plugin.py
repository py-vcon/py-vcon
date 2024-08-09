# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" FilterPlugin for JWS signing of vCon """
import typing
import pydantic
import vcon.filter_plugins

logger = vcon.build_logger(__name__)

class NoPrivateKey(Exception):
  """ Raised when no provate key is provided """


class SignFilterPluginInitOptions(
  vcon.filter_plugins.FilterPluginInitOptions,
  title = "JWS signing of vCon **FilterPlugin** intialization object"
  ):
  """
  A **SignFilterPluginInitOptions** object is provided to the
  **Sign FilterPlugin.__init__** method when it is first loaded.  Its
  attributes effect how the registered **FilterPlugin** functions.
  """
  private_pem_key: typing.Union[str, None] = pydantic.Field(
    title = "default PEM format private key to use for signing vCon",
    description = """
""",
    default = None
    )

  cert_chain_pems: typing.List[str] = pydantic.Field(
    title = "default PEM certificate chain",
    description = """
default PEM format certificate chain to include in the signed (JWS x5c) vCon
and used for verification of the signed vCon.
""",
    default = []
    )


class SignFilterPluginOptions(
  vcon.filter_plugins.FilterPluginOptions,
  title = "Sign filter method options"
  ):
  """
  Options for signing vCon in filter_plugin.
  """

  private_pem_key: typing.Union[str, None] = pydantic.Field(
    title = "PEM format private key to use for signing vCon",
    description = """
    Override the default PEM format private key for signing.
""",
    default = None
    )

  cert_chain_pems: typing.List[str] = pydantic.Field(
    title = "PEM certificate chain",
    description = """
Override default PEM format certificate chain to include in the signed (JWS x5c) vCon
and used for verification of the signed vCon.
""",
    default = []
    )


class SignFilterPlugin(vcon.filter_plugins.FilterPlugin):
  """
  **FilterPlugin** for JWS signing of vCon
  """
  init_options_type = SignFilterPluginInitOptions

  def __init__(
    self,
    init_options: SignFilterPluginInitOptions
    ):
    """
    Parameters:
      init_options (SignFilterPluginInitOptions) - the initialization options for JWS signing of vCon in plugin
    """
    super().__init__(
      init_options,
      SignFilterPluginOptions
      )


  async def filter(
    self,
    in_vcon: vcon.Vcon,
    options: SignFilterPluginOptions
    ) -> vcon.Vcon:
    """
    sign vCon using JWS

    Parameters:
      options (SignFilterPluginOptions)

    Returns:
      the signed Vcon object (JWS)
    """
    out_vcon = in_vcon

    private_key = options.private_pem_key
    # Use default if not provided
    if(private_key is None or len(private_key) == 0):
      private_key = self._init_options.private_pem_key
      if(private_key is None or len(private_key) == 0):
        raise NoPrivateKey("Sign filter plugin: {} no private key in SignFilterPluginInitOptions or SignFilterPluginOptions")

    key_chain = options.cert_chain_pems
    # Use default if not provided
    if(key_chain is None or len(key_chain) == 0):
      key_chain = self._init_options.cert_chain_pems

    logger.debug("sign vCon")
    out_vcon.sign(private_key, key_chain)
    logger.debug("done signing vCon")
    return(out_vcon)

