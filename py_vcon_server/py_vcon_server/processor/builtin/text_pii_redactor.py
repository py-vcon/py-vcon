# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.

import typing
import pydantic
import pyjq
import vcon.filter_plugins.impl.jq_redaction
import vcon.filter_plugins.impl.redact_pii
import py_vcon_server.processor

logger = py_vcon_server.logging_utils.init_logger(__name__)

class TextPiiRedactorInitOptions(py_vcon_server.processor.VconProcessorInitOptions,
      vcon.filter_plugins.impl.jq_redaction.JqRedactionInitOptions,
      vcon.filter_plugins.impl.redact_pii.RedactPiiInitOptions
    ):
  """
  TextPiiRedactorInitOptions is passed to the test_pii_redactor processor when it is initialized.
  TextPiiRedactorInitOptions extends VconProcessorInitOptions, but does not add any new fields.
  """


class TextPiiRedactorOptions(py_vcon_server.processor.VconProcessorOptions,
      vcon.filter_plugins.impl.jq_redaction.JqRedactionOptions,
      vcon.filter_plugins.impl.redact_pii.RedactPiiOptions
    ):
  """
  TextPiiRedactorOptions provides the filter_plugin PII redaction options which
  defines how the transcript(s) is redacted for PII as well
  as the filter_plugin jq query options which defines which parameters are
  redacted from the original vCon.
  """
  # TODO: set the default JQ query to redact audio, video and unredacted text


class TextPiiRedactor(py_vcon_server.processor.VconProcessor):
  """ Processor to perform PII redaction of text/transcript and generate a redacted vCon using a JS query """

  def __init__(
    self,
    init_options: TextPiiRedactorInitOptions
    ):

    super().__init__(
      "create a redacted vCon with the text PII redacted from the given input vCon",
      "the PII in the input vCon is redacted using the **pii_redact** filter_plugin.  "
      "By default, the redacted transcript is not saved and the input vCon is unmodified.  "
      "A new redacted vCon is created, referencing the input, unredacted vCon.  "
      "By default the unredacted vCon is copied to the redacted vCon with the text, "
      "audio and video media in the dialogs removed.  The parts removed, is defined by a "
      "JQ query in the **jq_redaction_query** parameter.",
      "0.0.1",
      init_options,
      TextPiiRedactorOptions,
      True # modifies a Vcon
      )


  async def process(self,
    processor_input: py_vcon_server.processor.VconProcessorIO,
    options: TextPiiRedactorOptions
    ) -> py_vcon_server.processor.VconProcessorIO:
    """
    Redact the Personal Identifable Information (PII) from the text/transcript of the input vCon,
    generate a redacted vCon referencing the original vCon.
    """

    if(isinstance(options, dict)):
      formatted_options = TextPiiRedactorOptions(**options)
    else:
      formatted_options = options

    unredacted = await processor_input.get_vcon(formatted_options.input_vcon_index)

    # Add a redacted transcript to the temporary unredacted vCon
    # Note: the modified unredacted vCon is not marked for update unless processor_input.update_vcon is invoked
    await unredacted.redact_pii(formatted_options)

    if(formatted_options.jq_redaction_query in (None, "")):
      raise Exception("redaction query options.jq_redaction_query is not set")
    # Copy/delete content from the unredacted to the redacted per JQ query
    redacted = await unredacted.jq_redaction(formatted_options)

    # Add the redacted to the output as a new vCon
    processor_output = processor_input
    await processor_output.add_vcon(redacted, None, False)

    return(processor_output)

