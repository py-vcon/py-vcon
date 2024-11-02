# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
""" FilterPlugin for jq query based redaction of vCon """
import typing
import pyjq
import pydantic
import vcon.filter_plugins


class JqRedactionInitOptions(
  vcon.filter_plugins.FilterPluginInitOptions,
  title = "Initialization options for JQ redaction filter_plugin"
  ):
  pass


class JqRedactionOptions(
  vcon.filter_plugins.FilterPluginOptions,
  title = "JQ redaction filter_plugin options"
  ):
  """
  Options defining how a redaction will be performed using a JQ query.
  The query can add, delete, modify the original vCon to construct a
  redacted vCon.  The resulting JQ query must form a valid vCon in
  either the unsigned, signed or encrypted forms.
  """
  jq_redaction_query: str = pydantic.Field(
      title = "JQ query defining the redaction",
      description = """string containing the JQ query to apply to the input vCon
        to construct the output vCon.  The query can add, delete, modifiy the
        contents of the input vcon to define the contents of the output vCon.  The
        input vCon remains unchanged."""
    )

  redaction_type_label: str = pydantic.Field(
      title = "redaction type label to be set in the output vCon's redaction object",
    )

  uuid_domain: typing.Union[str, None] = pydantic.Field(
      title = "domain string to use when generating a new UUID for the redacted vCon",
      default = None
    )

class JqRedaction(vcon.filter_plugins.FilterPlugin):
  """
  Create a redacted vCon referencing the input vCon and use the
  JQ query to define what is deleted, kept or modified from the original
  vCon to construct the redacted vCon.
  """

  init_options_type = JqRedactionInitOptions

  def __init__(
    self,
    init_options: JqRedactionInitOptions
    ):
    """
    Parameters:
      init_options (JqRedactionInitOptions) - the initialization options for the redaction of vCon in plugin
    """
    super().__init__(
      init_options,
      JqRedactionOptions
      )


  async def filter(
    self,
    in_vcon: vcon.Vcon,
    options: JqRedactionOptions
    ) -> vcon.Vcon:
    """
    redact the in_vcon using the JQ query to construct the output
    redacted vCon.  Set the redacted Object in the output redacted vCon.
 
    Parameters:
      options (JqRedactionOptions)

    Returns:
      the redacted vCon referencing the in_vcon
    """

    # If locally signed or verified, get the verified vCon in unsigned form.
    # Do not deep copy, we are only reading the data
    vcon_dict = in_vcon.dumpd(False, False)

    out_vcon = vcon.Vcon()

    redaction_query = options.jq_redaction_query
    if(redaction_query is None or len(redaction_query) == 0):
      raise Exception("invalid JQ query for redaction: {}".format(redaction_query))

    query_result = pyjq.all(redaction_query,
         vcon_dict)[0]

    redacted_uuid = query_result.get("uuid", None)

    out_vcon.loadd(query_result)
    # cannot use same UUID
    if(redacted_uuid in (None, in_vcon.uuid)):
      if(options.uuid_domain in (None, "")):
        raise Exception("JqRedaction options.uuid_domain MUST be set")
      out_vcon.set_uuid(options.uuid_domain, True)

    # Set the redacted object and reference the original, less redacted vCon
    redaction_type_label = options.redaction_type_label
    out_vcon.set_redacted(in_vcon.uuid, redaction_type_label)

    return(out_vcon)

