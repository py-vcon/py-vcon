import vcon.filter_plugins
import typing
import pydantic
import os
import json
import csv
import scrubadub
import pandas as pd
import tensorflow as tf
import dataprofiler
from dataprofiler import Data, Profiler, DataLabeler


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

  analysis_type: str = pydantic.Field(
    title = "the **Vcon analysis** object type",
    description = """
The results of the completion are saved in a new **analysis**
object which is added to the input **Vcon**.
**analysis_type** is the **analysis** type token that is set
on the new **analysis** object in the **Vcon**.
""",
    default = "pii-labels"
    )


class Redact(vcon.filter_plugins.FilterPlugin):
  init_options_type = RedactInitOptions

  def __init__(self, options):
    super().__init__(
      options,
      RedactOptions)
    print("Redact plugin created with options: {}".format(options))

  def redact_text_helper(self, row, dialog_num, predictions):
    redacted_dialog = row.text
    index_adjuster = 0
    for pred in predictions['pred'][dialog_num]:
      # start of sensitive data
      s = pred[0] + index_adjuster
      # end of sensitive data
      e = pred[1] + index_adjuster
      if e >= len(redacted_dialog):
        e = len(redacted_dialog) - 1
      # redact sensitive data. For example, 
      # text "my email is test@mail.com and number is 617 555 1234" 
      # becomes "my email is {{EMAIL}} and number is {{PHONE}}"
      redacted_dialog = redacted_dialog[:s] + "{{" + pred[2] + "}}" + redacted_dialog[e:]
      # adjust the index for the next iteration as the original text has changed
      diff =e - s - len(pred[2]) - 4
      if diff < 0:
        diff = diff * -1
      index_adjuster = index_adjuster + diff

    return(redacted_dialog)

  # Not used for now
  def redact_using_scrubadub(self, dialog_texts):
      has_sensitive_content = False
      for d in dialog_texts:
        redactedText = scrubadub.clean(d["text"])
        if(redactedText != d["text"]):
            print("!!!sanitized dialog: ", redactedText)
            has_sensitive_content = True
      
      if(has_sensitive_content == False):
        print("The scrubadub library has not found any sensitive content in this vcon")
      

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
      dialog_texts = await in_vcon.get_dialog_text(
        dialog_index,
        True, # find text from transcript analysis if dialog is a recording and transcript exists
        False # do not transcribe this recording dialog if transcript does not exist
      )
      
      # no text, no analysis
      if(len(dialog_texts) == 0):
        continue

      with open(DIALOG_DATA_CSV, "w") as dialogCSV:
        writer = csv.DictWriter(dialogCSV, fieldnames=DIALOG_DATA_FIELDS)
        # write header (just once)
        if csv_has_header == False:
          writer.writeheader()
          csv_has_header = True
        # write data rows
        writer.writerows(dialog_texts)

      # Label the data using CapitalOne libraries
      # structured labeler doesnt work as it considers entire dialog as a string
      # and hence is unable to come up with a label for the entire column
      options = {'selected_columns': ['text']}
      data = Data(DIALOG_DATA_CSV, options=options)
      labeler = DataLabeler(labeler_type='unstructured')
      labeler.set_params(
        { 'postprocessor' : {'output_format':'ner', 'use_word_level_argmax': True}}
      )
      predictions = labeler.predict(data)
      
      analysis_extras = {
        "product": "capitalone"
      }
    
      redacted_texts = []
      for i, row in data.data.iterrows():
        redacted_dialog = self.redact_text_helper(row, i, predictions)
        dialog_texts[i]['redacted'] = redacted_dialog
        if redacted_dialog != row.text:
          redacted_texts.append(dialog_texts[i])

      out_vcon.add_analysis(
        dialog_index,
        'pii-labels',
        redacted_texts,
        'capitalone',
        'data_labeler_schema',
        **analysis_extras
        )

    return(out_vcon)