# Copyright (C) 2023-2025 SIPez LLC.  All rights reserved.
""" FilterPlugin to fix post recording info """
import typing
import pydantic
import requests
import vcon
import vcon.filter_plugins


logger = vcon.build_logger(__name__)


class FixRecordingDialogInitOptions(
  vcon.filter_plugins.FilterPluginInitOptions,
  title = "Initialization options for fix recording info filter_plugin"
  ):
  """
  FixRecordingDialogInitOptions is a FilterPluginInitOptions with no added fields.
  A FixRecordingDialogInitOptions is passed to the JqRedaction filter_plugin when
  it is first initialized.
  """

class FixRecordingDialogOptions(
  vcon.filter_plugins.FilterPluginOptions,
  title = "Fix recording dialog filter_plugin options"
  ):
  """
  FixRecordingDialogOptions is a FilterPluginOptions with fields to
  which recording dialogs to fix.  It is sometime useful to add a recording
  dialog before the recording is complete.  At that time the recording
  duration and for externally reference recordings, the content_hash cannot
  be calculated.

  A FixRecordingDialogOptions is passed to the filter method.
  """

  input_dialogs: typing.Union[str,typing.List[int]] = pydantic.Field(
    title = "input **Vcon** recording **dialog** objects",
    description = """
Indicates which recording **dialog** objects in the given **Vcon** are
to have recording info (duration and content_hash) fixed.

 * **""** (empty str or None) - all recording **dialogs** are to be fixed.  This is the equivalent of providing "0:".
 * **n:m** (str) - **dialog** objects having indices **n-m** are to be fixed.
 * **n:m:i** (str) - **dialog** objects having indices **n-m** using interval **i** are to be fixed.
 * **[]** (empty list[int]) - none of the **dialog** objects are to be fixed.
 * **[1, 4, 5, 9]** (list[int]) - the **dialog** objects having the indices in the given list are to be fixed.

**dialog** objects in the given sequence or list which are not **recording** type dialogs are ignored.
""",
    default = "0:",
    examples = ["", "0:", "0:-2", "2:5", "0:6:2", [], [1, 4, 5, 9]]
    )

class FixRecordingDialog(vcon.filter_plugins.FilterPlugin):
  """
  filter_plugin to fix duration and content_hash which are missing
  or incorrect after a recording is completed.
  """

  init_options_type = FixRecordingDialogInitOptions

  def __init__(
    self,
    init_options: FixRecordingDialogInitOptions
    ):
    """
    Parameters:
      init_options (FixRecordingDialogInitOptions) - the initialization options for the fox recording dialog info plugin
    """
    super().__init__(
      init_options,
      FixRecordingDialogOptions
      )


  async def filter(
    self,
    in_vcon: vcon.Vcon,
    options: FixRecordingDialogOptions
    ) -> vcon.Vcon:
    """
    Fix the duration and if externally reference recording (url is present)
    also fix or set the content_hash. 

    Parameters:
      options (FixRecordingDialogOptions)

    Returns:
      the vCon with fixed dialog(s) in_vcon
    """

    dialog_indices = self.slice_indices(
      options.input_dialogs,
      len(in_vcon.dialog),
      "FixRecordingDialogOptions.input_dialogs"
      )

    for dialog_index in dialog_indices:
      dialog = in_vcon.dialog[dialog_index]
      #print("dialog keys: {}".format(dialog.keys()))
      if("type" in dialog and dialog["type"] == "recording"):

        # Get the recording content
        if("url" in dialog and dialog["url"] != ""):
          # Get body from URL using requests
          url = dialog["url"]
          # TODO: this should be configurable
          get_kwargs = {"timeout": 20}
          req = requests.get(url, **get_kwargs)
          if(not(200 <= req.status_code < 300)):
            logger.warning(f"get of {url} for dialog: {dialog_index} resulted in error: {req.status_code}")
            continue
          body = req.content

          # Calc the hash
          # TODO: make hash configureable
          sign_type = "SHA-512"
          sig_hash = vcon.security.sha_512_hash(body)
          dialog["content_hash"] = vcon.security.build_content_hash_token(sign_type, sig_hash)

      # Attempt to get the duration
      duration = vcon.utils.get_recording_duration(body)
      if(duration):
        dialog["duration"] = duration

    return(in_vcon)

