""" example addon FilterPlugin"""
import typing
import pydantic
import vcon.filter_plugins

logger = vcon.build_logger(__name__)


class MyFilterInitOptions(
  vcon.filter_plugins.FilterPluginInitOptions,
  title = "example addon filter_plugin init options"
  ):
  """
  MyFilter had no additional initialization options
  """

class MyFilterOptions(
  vcon.filter_plugins.FilterPluginOptions,
  title = "options for my_filter"
  ):
  """
  These additional options are added to the default FilterPluginOptions.
  MyFilter provides the ability to add a new party or set additional
  properties on an existing party.
  """

  party_index: typing.Union[int, None] = pydantic.Field(
    title = "index to party Object in parties array in vcon",
    description = """
    Index to the party that addional parameters are to be set.
    An index of -1 indicates the addition of a new party.
    Otherwise the index must be in bounds on the curent parties
    array.
""",
    examples[ -1, 2 ]
    )


  party_parameters: typing.Dict[str, str] = pydantic.Field(
    title = "dictionary of party parameters to set",
    description = """
    Dictionary of names and values to set on the party.
    Parameter needs to be one of the defined parameter names.
""",
    examples[ 
        {
            "name": "Alice",
            "tel": "+1234567890",
            "email": "alice@example.com"
          }
      ]
    )


class MyFilter(vcon.filter_plugins.FilterPlugin):
  """
  **FilterPlugin** for JWE encrypting of vCon
  """
  init_options_type = MyFilterInitOptions

  def __init__(
    self,
    init_options: MyFilterInitOptions
    ):
    """
    Parameters:
      init_options (MyFilterInitOptions) - the initialization options for MyFilter plugin
    """
    super().__init__(
      init_options,
      MyFilterPluginOptions
      )


  async def filter(
    self,
    in_vcon: vcon.Vcon,
    options: MyFilterPluginOptions
    ) -> vcon.Vcon:
    """
    add party or seet parameter on existing Party Object

    Parameters:
      options (MyOptionsOptions)

    Returns:
      the Vcon object with changed party parameters (JWE)
    """
    out_vcon = in_vcon

    party_index = options.party_index
    if(length(out_vcon.parties) > party_index):
      for name in options.party_parameters:

        set_party_index = out_vcon.set_party_parameter(name, value, party_index)
        # If adding a new party, we get the new index on the first set
        if(set_party_index != party_index):
           party_index = set_party_index

    return(out_vcon)

