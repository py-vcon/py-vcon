import vcon.filter_plugins
import typing
import pydantic
import os
import json
import csv
from datetime import datetime
import pandas as pd
import tensorflow as tf
import dataprofiler
from dataprofiler import Data, Profiler, DataLabeler
from dataprofiler.data_readers.csv_data import CSVData


DIALOG_DATA_CSV     = "examples/redact_input.csv"
DIALOG_DATA_FIELDS  = ['parties', 'start', 'duration', 'text']

# Properties for the Analysis object with redacted data
ANALYSIS_TYPE       = 'pii-labels'
ANALYSIS_PRODUCT    = 'CapitalOne'
ANALYSIS_SCHEMA     = 'data_labeler_schema'

# Register plugin
registration_options: typing.Dict[str, typing.Any] = {}
vcon.filter_plugins.FilterPluginRegistry.register(
  "redact",
  "examples.redact_vcon",
  "Redact",
  "Adds analysis object to vcon with PII labels and redacted dialog",
  registration_options
  )


class RedactInitOptions(vcon.filter_plugins.FilterPluginInitOptions):
  # nothing to initialize here
  print('RedactInitOptions invoked')
  

class RedactOptions(vcon.filter_plugins.FilterPluginOptions):
  """
  Options for redacting PII data in the recording **dialog** objects.  
  The resulting dialogs(s) are added to **analysis** objects in this **Vcon**
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

  # Function to redact dialog text based on PII labels
  def redact_text_helper(self, dialog, labels):
    redacted_dialog = dialog.text
    index_adjuster = 0
    for labelInfo in labels:
      # start of sensitive data
      s = labelInfo[0] + index_adjuster
      # end of sensitive data
      e = labelInfo[1] + index_adjuster
      if e >= len(redacted_dialog):
        e = len(redacted_dialog) - 1
      # redact sensitive data. For example, 
      # text "my email is test@mail.com and number is 617 555 1234" 
      # becomes "my email is {{EMAIL}} and number is {{PHONE}}"
      redacted_dialog = redacted_dialog[:s] + "{{" + labelInfo[2] + "}}" + redacted_dialog[e:]
      # adjust the index for the next iteration as the original text has changed
      diff =e - s - len(labelInfo[2]) - 4
      if diff < 0:
        diff = diff * -1
      index_adjuster = index_adjuster + diff

    return(redacted_dialog)

  async def filter(
    self,
    in_vcon: vcon.Vcon,
    options: RedactOptions
    ) -> vcon.Vcon:

    print(datetime.now(), 'Redact filter is invoked')
    out_vcon = in_vcon
    if(in_vcon.dialog is None):
      print('Return as there are no dialogs..')
      return(out_vcon)

    dialog_indices = self.slice_indices(
      options.input_dialogs,
      len(in_vcon.dialog),
      "RedactOptions.input_dialogs"
      )

    # no dialogs
    if(len(dialog_indices) == 0):
      print('Return as there are no dialog indices..')
      return(out_vcon)

    print(datetime.now(), 'Get dialog text')
    # iterate through the vcon
    for dialog_index in dialog_indices:
      dialog_texts = await in_vcon.get_dialog_text(
        dialog_index,
        True, # find text from transcript analysis if dialog is a recording and transcript exists
        False # do not transcribe this recording dialog if transcript does not exist
      )
      
      # no text, no analysis
      if(len(dialog_texts) == 0):
        print(datetime.now(), 'There are no dialog text at index ', dialog_index)
        continue

      print(datetime.now(), 'creating csv')
      csv_has_header = False
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
      print(datetime.now(), 'creating data object')
      options = {'selected_columns': ['text']}
      data = CSVData(DIALOG_DATA_CSV, options=options)
      
      labeler = DataLabeler(labeler_type='unstructured')
      labeler.set_params(
        { 'postprocessor' : {'output_format':'ner', 'use_word_level_argmax': True}}
      )

      print(datetime.now(), 'predicting labels')
      predictions = labeler.predict(data)
      
      analysis_extras = {
        "product": ANALYSIS_PRODUCT
      }
    
      print(datetime.now(), 'redacting dialog text')
      redacted_texts = []
      for i, dialog in data.data.iterrows():
        redacted_dialog = self.redact_text_helper(dialog, predictions['pred'][i])
        dialog_texts[i]['redacted'] = redacted_dialog
        if redacted_dialog != dialog.text:
          redacted_texts.append(dialog_texts[i])

      print(datetime.now(), 'adding to aaaaanalysis')
      out_vcon.add_analysis(
        dialog_index,
        ANALYSIS_TYPE,
        redacted_texts,
        ANALYSIS_PRODUCT,
        ANALYSIS_SCHEMA,
        **analysis_extras
        )

    # cleanup
    if os.path.exists(DIALOG_DATA_CSV):
      os.remove(DIALOG_DATA_CSV)

    return(out_vcon)