# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" FilterPlugin for JWE encryption of vCon """
import typing
import pydantic
import vcon.filter_plugins

logger = vcon.build_logger(__name__)


class AmendedFilterPluginInitOptions(
  vcon.filter_plugins.FilterPluginInitOptions,
  title = "Create amended vCOn filter_plugin initialization optios"
  ):
  """
  A **AmendedFilterPluginInitOptions** object is provided to the
  **AmendedFilterPlugin.__init__** method when it is first loaded.  Its
  attributes effect how the registered **FilterPlugin** functions.
  AmendedFilterPluginInitOptions does not add any new fields to
  FilterPluginInitOptions.
  """

class AmendedFilterPluginOptions(
  vcon.filter_plugins.FilterPluginOptions,
  title = "Amended filter method options"
  ):
  """
  Options for creating an amended vCon in filter_plugin.
  AmendedFilterPluginOptions adds no new fields to FilterPluginOptions
  """

class AmendedFilterPlugin(vcon.filter_plugins.FilterPlugin):
  """
  **FilterPlugin** for creating an amended version of the input vCon.
  The vCon must be either in the unsigned or verified states to be able to 
  create a amendable copy.
  """
  init_options_type = AmendedFilterPluginInitOptions


  def __init__(
    self,
    init_options: AmendedFilterPluginInitOptions
    ):
    """
    Parameters:
      init_options (AmendedFilterPluginInitOptions) - the initialization options for the create amended vCon in plugin
    """
    super().__init__(
      init_options,
      AmendedFilterPluginOptions
      )


  async def filter(
    self,
    in_vcon: vcon.Vcon,
    options: AmendedFilterPluginOptions
    ) -> vcon.Vcon:
    """
    Create amendable copy of input vCon

    Parameters:
      options (AmendedFilterPluginOptions)

    Returns:
      the amended Vcon object
    """

    # Serialize unsigned, verified data, don't deep copy as
    # it will get desrialized in loadd
    vcon_dict = in_vcon.dumpd(False, False);

    out_vcon = vcon.Vcon()
    out_vcon.loadd(vcon_dict)

    # The amendable vcon needs its own UUID
    out_vcon.set_uuid("py-test.org", True)

    # Set amended properties for prior version of vCon
    out_vcon.set_amended(in_vcon.uuid)

    return(out_vcon)


  def check_valid_state(
      self,
      filter_vcon: vcon.Vcon
    ) -> None:
    """
    Check to see that the vCon is in a valid state to create an amendable copy
    """

    if(filter_vcon._state not in [vcon.VconStates.UNSIGNED, vcon.VconStates.VERIFIED]):
      raise vcon.InvalidVconState("Cannot create/copy vCon to amended vCon unless current state is UNSIGNED or VERIFIED."
        "  Current state: {}".format(filter_vcon._state))

