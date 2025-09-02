# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" FilterPlugin for JWE encryption of vCon """
import typing
import pydantic
import vcon.filter_plugins

logger = vcon.build_logger(__name__)


class AppendedFilterPluginInitOptions(
  vcon.filter_plugins.FilterPluginInitOptions,
  title = "Create appended vCOn filter_plugin initialization optios"
  ):
  """
  A **AppendedFilterPluginInitOptions** object is provided to the
  **AppendedFilterPlugin.__init__** method when it is first loaded.  Its
  attributes effect how the registered **FilterPlugin** functions.
  AppendedFilterPluginInitOptions does not add any new fields to
  FilterPluginInitOptions.
  """

class AppendedFilterPluginOptions(
  vcon.filter_plugins.FilterPluginOptions,
  title = "Appended filter method options"
  ):
  """
  Options for creating an appended vCon in filter_plugin.
  AppendedFilterPluginOptions adds no new fields to FilterPluginOptions
  """

class AppendedFilterPlugin(vcon.filter_plugins.FilterPlugin):
  """
  **FilterPlugin** for creating an appended version of the input vCon.
  The vCon must be either in the unsigned or verified states to be able to 
  create a appendable copy.
  """
  init_options_type = AppendedFilterPluginInitOptions


  def __init__(
    self,
    init_options: AppendedFilterPluginInitOptions
    ):
    """
    Parameters:
      init_options (AppendedFilterPluginInitOptions) - the initialization options for the create appended vCon in plugin
    """
    super().__init__(
      init_options,
      AppendedFilterPluginOptions
      )


  async def filter(
    self,
    in_vcon: vcon.Vcon,
    options: AppendedFilterPluginOptions
    ) -> vcon.Vcon:
    """
    Create appendable copy of input vCon

    Parameters:
      options (AppendedFilterPluginOptions)

    Returns:
      the appended Vcon object
    """

    # Serialize unsigned, verified data, don't deep copy as
    # it will get desrialized in loadd
    vcon_dict = in_vcon.dumpd(False, False);

    out_vcon = vcon.Vcon()
    out_vcon.loadd(vcon_dict)

    # The appendable vcon needs its own UUID
    out_vcon.set_uuid("py-test.org", True)

    # Set appended properties for prior version of vCon
    out_vcon.set_appended(in_vcon.uuid)

    return(out_vcon)


  def check_valid_state(
      self,
      filter_vcon: vcon.Vcon
    ) -> None:
    """
    Check to see that the vCon is in a valid state to create an appendable copy
    """

    if(filter_vcon._state not in [vcon.VconStates.UNSIGNED, vcon.VconStates.VERIFIED]):
      raise vcon.InvalidVconState("Cannot create/copy vCon to appended vCon unless current state is UNSIGNED or VERIFIED."
        "  Current state: {}".format(filter_vcon._state))

