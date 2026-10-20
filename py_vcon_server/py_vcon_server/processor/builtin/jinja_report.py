# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.

"""
Jinja2 template based report generator **VconProcessor**.

Renders a Jinja2 template using the VconProcessorIO (vCons and parameters)
as the template context.  The rendered output is stored as a VconProcessorIO
parameter and/or as a new analysis object in the vCon.
"""

import typing
import pydantic
import jinja2
import py_vcon_server.processor

logger = py_vcon_server.logging_utils.init_logger(__name__)

EXAMPLE_TEMPLATE = """Conversation Report
===================
UUID: {{ vcons[0].uuid }}
Subject: {{ vcons[0].subject | default("N/A", true) }}
Date: {{ vcons[0].dialog[0].start | default("N/A", true) }}
Duration: {{ vcons[0].dialog[0].duration | default("N/A", true) }} seconds

Parties:
{% for p in vcons[0].parties -%}
  - {{ p.name | default("Unknown", true) }}
{% endfor %}"""


class JinjaReportInitOptions(py_vcon_server.processor.VconProcessorInitOptions):
  """
  JinjaReportInitOptions is passed to the jinja_report processor when it is initialized.
  JinjaReportInitOptions extends VconProcessorInitOptions, but does not add any
  new fields.
  """


class JinjaReportOptions(py_vcon_server.processor.VconProcessorOptions):
  """
  JinjaReportOptions defines the Jinja2 template and output destinations for the
  jinja_report processor.

  The **template** field is a Jinja2 template string that is rendered using the
  VconProcessorIO as the template context.  The template has access to two top
  level variables:

    * **vcons** - array of dicts, one for each vCon in the VconProcessorIO
    * **parameters** - dict of parameters from the VconProcessorIO

  The rendered output is always stored in the VconProcessorIO parameter named
  by **output_parameter_name**.  If **analysis_type** is set, the rendered output
  is also added as a new analysis object in the vCon indicated by **input_vcon_index**.
  """
  template: str = pydantic.Field(
      title = "Jinja2 template string",
      description = "Jinja2 template string to render using the VconProcessorIO as"
        " the template context.  The template has access to two top level variables:"
        " **vcons** (array of vCon dicts) and **parameters** (dict of VconProcessorIO"
        " parameters).  For example: {{ vcons[0].uuid }} accesses the first vCon's UUID.",
      examples = [EXAMPLE_TEMPLATE]
    )

  output_parameter_name: str = pydantic.Field(
      title = "output parameter name for rendered template",
      description = "Name of the VconProcessorIO parameter in which to store the"
        " rendered template output string.",
      examples = ["report_output"],
      default = "report_output"
    )

  analysis_type: str = pydantic.Field(
      title = "analysis object type",
      description = "If set, the rendered template output is added as a new analysis"
        " object in the vCon indicated by **input_vcon_index** with this type value."
        "  If not set, no analysis object is created.",
      examples = ["report"],
      default = ""
    )

  analysis_vendor: typing.Union[str, None] = pydantic.Field(
      title = "analysis object vendor",
      description = "Vendor string for the analysis object.  Only used when"
        " **analysis_type** is set.",
      examples = ["jinja"],
      default = "jinja"
    )

  analysis_product: str = pydantic.Field(
      title = "analysis object product",
      description = "Product string for the analysis object.  Only used when"
        " **analysis_type** is set.  Typically only needed for non-text output"
        " formats where a consumer needs to identify the format.",
      examples = ["jinja_report"],
      default = ""
    )

  analysis_schema: str = pydantic.Field(
      title = "analysis object schema",
      description = "Schema string for the analysis object.  Only used when"
        " **analysis_type** is set.  Typically only needed for non-text output"
        " formats where a consumer needs to identify the format.",
      examples = ["text_report"],
      default = ""
    )

  media_type: str = pydantic.Field(
      title = "analysis object media type",
      description = "Media type for the analysis object.  Only used when"
        " **analysis_type** is set.",
      examples = ["text/plain", "text/html"],
      default = "text/plain"
    )

  analysis_dialog_index: typing.Union[int, typing.List[int]] = pydantic.Field(
      title = "analysis object dialog index",
      description = "Dialog index or list of dialog indices that the analysis object"
        " references.  Only used when **analysis_type** is set.  If not set (None),"
        " defaults to all dialog indices in the vCon at runtime.",
      examples = [0, [0, 1]],
      default = []
    )


class JinjaReport(py_vcon_server.processor.VconProcessor):
  """
  Jinja2 template based report generator **VconProcessor**.

  Renders a Jinja2 template using the VconProcessorIO (vCons and parameters)
  as context.  Output can be stored as a VconProcessorIO parameter and/or
  as a new analysis object in the vCon.
  """

  def __init__(
    self,
    init_options: JinjaReportInitOptions
    ):

    super().__init__(
      "Jinja2 template report generator **VconProcessor**",
      "Renders a Jinja2 template using the VconProcessorIO as the template"
      " context.  The template has access to all vCons and parameters in"
      " the VconProcessorIO.  The rendered output is stored as a"
      " VconProcessorIO parameter and optionally as a new analysis object"
      " in the vCon.",
      "0.0.1",
      init_options,
      JinjaReportOptions,
      True # may modify a Vcon (when analysis_type is set)
      )


  async def process(self,
    processor_input: py_vcon_server.processor.VconProcessorIO,
    options: JinjaReportOptions
    ) -> py_vcon_server.processor.VconProcessorIO:
    """
    Render the Jinja2 template using the VconProcessorIO as context.
    Store the result in a parameter and optionally as a vCon analysis object.
    Does not modify the vCon unless analysis_type is set.
    """

    # Build the template context dict from VconProcessorIO
    # This follows the same pattern as the jq processor
    context = {
        "vcons": [],
        "parameters": processor_input._parameters
      }

    for mVcon in processor_input._vcons:
      a_vcon = await mVcon.get_vcon(py_vcon_server.processor.VconTypes.OBJECT)
      logger.debug("jinja_report processor adding vcon uuid={}".format(a_vcon.uuid))
      context["vcons"].append(a_vcon.dumpd(signed = False, deepcopy = False))

    # Render the template
    try:
      env = jinja2.Environment(undefined = jinja2.StrictUndefined)
      template = env.from_string(options.template)
      result = template.render(**context)
    except jinja2.TemplateError as template_error:
      logger.error("jinja_report template rendering error: {}".format(template_error))
      raise

    logger.debug("jinja_report rendered {} characters to parameter: {}".format(
        len(result),
        options.output_parameter_name
      ))

    # Always store the rendered output as a parameter
    processor_input.set_parameter(options.output_parameter_name, result)

    # Optionally add the rendered output as an analysis object
    if(options.analysis_type is not None and
      options.analysis_type != ""):

      index = options.input_vcon_index
      in_vcon = await processor_input.get_vcon(index)
      if(in_vcon is None):
        raise Exception("Vcon not found for index: {}".format(index))

      # Determine dialog index
      dialog_index = options.analysis_dialog_index
      if(isinstance(dialog_index, list) and len(dialog_index) == 0):
        # Default to all dialog indices
        num_dialogs = len(in_vcon.dialog) if in_vcon.dialog else 0
        if(num_dialogs > 1):
          dialog_index = list(range(num_dialogs))
        elif(num_dialogs == 1):
          dialog_index = 0
        else:
          dialog_index = 0

      # Build optional parameters for add_analysis
      extra_params = {}
      extra_params["mediatype"] = options.media_type
      if(options.analysis_product is not None and
        options.analysis_product != ""):
        extra_params["product"] = options.analysis_product

      logger.debug("jinja_report adding analysis type={} to vcon uuid={} dialog={}".format(
          options.analysis_type,
          in_vcon.uuid,
          dialog_index
        ))

      in_vcon.add_analysis(
        dialog_index,
        options.analysis_type,
        result,
        options.analysis_vendor,
        options.analysis_schema,
        "none",
        **extra_params
        )

      await processor_input.update_vcon(in_vcon)

    return(processor_input)
