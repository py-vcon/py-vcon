import vcon.filter_plugins
import typing
import pydantic
import os
import json
import csv
import scrubadub
from dataprofiler import Data, Profiler

DIALOG_DATA_CSV     = "tests/redact_input.csv"
DIALOG_DATA_FIELDS  = ['parties', 'start', 'duration', 'text']
PROFILER_REPORT     = "tests/redact_profiler_report.json"

class RedactInitOptions(vcon.filter_plugins.FilterPluginInitOptions):
  redaction_key: str = pydantic.Field(
    title = "**Redaction** API key",
    description = "The **redaction_key** is a sample key needed to use this **FilterPlugin**.",
    example = "123456789e96a1da774e57abcdefghijklmnop",
    default = ""
    )


class RedactOptions(vcon.filter_plugins.FilterPluginOptions):
  """
  Options for redacting PII data in the recording **dialog** objects.  
  The resulting transcription(s) are added as transcript **analysis** 
  objects in this **Vcon**
  """
  input_dialogs: typing.Union[str,typing.List[int]] = pydantic.Field(
    title = "input **Vcon** text **dialog** objects",
    description = """
Indicates which text **dialog** and recording **dialog** object's associated
transcript **analysis** objects are to be input.  Recording **dialog**
objects that do not have transcript **analysis** objects, are transcribed
using the default FilterPlugin transcribe type.
**dialog** objects in the given sequence or list which are not **text** or **recording** type dialogs are ignored.
""",
    default = "",
    examples = ["", "0:", "0:-2", "2:5", "0:6:2", [], [1, 4, 5, 9]]
    )


class Redact(vcon.filter_plugins.FilterPlugin):
  init_options_type = RedactInitOptions

  def __init__(self, options):
    super().__init__(
      options,
      RedactOptions)
    print("Redact plugin created with options: {}".format(options))

  async def filter(
    self,
    in_vcon: vcon.Vcon,
    options: RedactOptions
    ) -> vcon.Vcon:
    print("!!!!!!!!!!! Redact filter invoked !!!!!!!!!!!")
    out_vcon = in_vcon
    if(in_vcon.dialog is None):
      print("!!!! No dialog !!!!")
      return(out_vcon)

    dialog_indices = self.slice_indices(
      options.input_dialogs,
      len(in_vcon.dialog),
      "RedactOptions.input_dialogs"
      )

    # no dialogs
    if(len(dialog_indices) == 0):
      print("!!!! No dialog indices!!!!")
      return(out_vcon)

    # clear files from previous run
    if os.path.exists(DIALOG_DATA_CSV):
      os.remove(DIALOG_DATA_CSV)

    csv_has_header = False
    

    # iterate through the vcon
    for dialog_index in dialog_indices:
      this_dialog_texts = await in_vcon.get_dialog_text(
        dialog_index,
        True, # find text from transcript analysis if dialog is a recording and transcript exists
        False # do not transcribe this recording dialog if transcript does not exist
        )
      dialog = in_vcon.dialog[dialog_index]

      text_segments = [d["text"] for d in this_dialog_texts]
      print("Dialog ", dialog_index, " type:", dialog["type"], " texts:", len(text_segments))
      # no text, no analysis
      if(len(text_segments) == 0):
        continue

      ######## Redact using scrubadub library
      has_sensitive_content = False
      for d in this_dialog_texts:
        redactedText = scrubadub.clean(d["text"])
        if(redactedText != d["text"]):
            print("!!!sanitized dialog: ", redactedText)
            has_sensitive_content = True
      
      with open(DIALOG_DATA_CSV, "a") as dialogCSV:
        writer = csv.DictWriter(dialogCSV, fieldnames=DIALOG_DATA_FIELDS)
        # write header (just once)
        if csv_has_header == False:
          writer.writeheader()
          csv_has_header = True
        # write data rows
        writer.writerows(this_dialog_texts)

      if(has_sensitive_content == False):
        print("The scrubadub library has not found any sensitive content in this vcon")
      
    ###### Redact using the DataProfiler ##############

    # Run the data profiler to analyze transcribed input from all dialog indices
    data = Data(DIALOG_DATA_CSV)
    profile =Profiler(data)
    profiler_output = profile.report(report_options={"output_format": "compact"})
    
    # Save the profiler output
    with open(PROFILER_REPORT, "w") as output_file:
      output_file.write(json.dumps(profiler_output, indent=4))

    return(out_vcon)