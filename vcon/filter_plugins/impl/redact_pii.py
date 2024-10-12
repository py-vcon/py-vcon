# Copyright (C) 2023-2024 SIPez LLC.  All rights reserved.
import typing
import tempfile
import csv
from datetime import datetime
import pydantic
import pandas as pd
import tensorflow as tf
import vcon.filter_plugins
#import dataprofiler
from dataprofiler import Data, DataLabeler
from dataprofiler.data_readers.csv_data import CSVData

logger = vcon.build_logger(__name__)

DIALOG_DATA_FIELDS  = ['parties', 'start', 'duration', 'text']

# Properties for the Analysis object with redacted data
ANALYSIS_TYPE       = 'transcript-redacted'
ANALYSIS_VENDOR    = 'CapitalOne'
ANALYSIS_PRODUCT    = 'dataprofiler'
ANALYSIS_SCHEMA     = 'data_labeler_schema'

class RedactPiiInitOptions(vcon.filter_plugins.FilterPluginInitOptions):
  # nothing to initialize here
  pass

class RedactPiiOptions(vcon.filter_plugins.FilterPluginOptions):
  """
  Options for redacting PII data in the text or transcriptions for **dialog** objects.  
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


class RedactPii(vcon.filter_plugins.FilterPlugin):
  init_options_type = RedactPiiInitOptions

  def __init__(
      self,
      init_options: RedactPiiInitOptions
    ):
    """
    Parameters:
      init_options (RedactPiiInitOptions) - the initialization options for the PII redaction plugin using the CaptialOne dataprofiler.
    """
    super().__init__(
      init_options,
      RedactPiiOptions)

  # Function to redact dialog text based on PII labels
  def redact_text_helper(self, dialog, labels):
    redacted_dialog = dialog.text
    index_adjuster = 0
    for label_info in labels:
      # start of sensitive data
      s = label_info[0] + index_adjuster
      # end of sensitive data
      e = label_info[1] + index_adjuster
      if e >= len(redacted_dialog):
        e = len(redacted_dialog) - 1
      # redact sensitive data. For example, 
      # text "my email is test@mail.com and number is 617 555 1234" 
      # becomes "my email is {{EMAIL}} and number is {{PHONE}}"
      redacted_dialog = redacted_dialog[:s] + "{{" + label_info[2] + "}}" + redacted_dialog[e:]
      # adjust the index for the next iteration as the original text has changed
      diff =e - s - len(label_info[2]) - 4
      if diff < 0:
        diff = diff * -1
      index_adjuster = index_adjuster + diff

    return(redacted_dialog)

  async def filter(
      self,
      in_vcon: vcon.Vcon,
      options: RedactPiiOptions
    ) -> vcon.Vcon:
    """
    Redact PII in the transcripts for the indicated dialogs using the
    CaptialOne dataprofiler. 

    Note: this does not guarentee that all PII is redacted.  Other data
    is sometimes mistaken as PII data.  PII data could be missed and
    not redacted.

    Parameters:
      options (RedactPiiOptions)

    Returns:
      The input vCon with the generated, redacted transcript(s) in the
      added.  DOES NOT remove the original, non-redacted transcripts.
    """
    logger.debug('Redact filter is invoked')
    out_vcon = in_vcon
    if(in_vcon.dialog is None):
      logger.info('Return as there are no dialogs..')
      return(out_vcon)

    dialog_indices = self.slice_indices(
      options.input_dialogs,
      len(in_vcon.dialog),
      "RedactOptions.input_dialogs"
      )

    # no dialogs
    if(len(dialog_indices) == 0):
      logger.warning('Return as there are no dialog indices..')
      return(out_vcon)

    logger.debug('Get dialog text')
    # iterate through the vcon
    for dialog_index in dialog_indices:
      dialog_texts = await in_vcon.get_dialog_text(
        dialog_index,
        True, # find text from transcript analysis if dialog is a recording and transcript exists
        False # do not transcribe this recording dialog if transcript does not exist
      )

      # no text, no analysis
      if(len(dialog_texts) == 0):
        logger.info('There are no dialog text at index ', dialog_index)
        continue

      logger.info('creating csv')
      csv_has_header = False
      with tempfile.NamedTemporaryFile(suffix = "csv", mode = "w") as dialog_csv:
        writer = csv.DictWriter(dialog_csv, fieldnames=DIALOG_DATA_FIELDS)
        # write header (just once)
        if(not csv_has_header):
          writer.writeheader()
          csv_has_header = True
        # write data rows
        writer.writerows(dialog_texts)

        # Label the data using CapitalOne libraries
        # structured labeler doesnt work as it considers entire dialog as a string
        # and hence is unable to come up with a label for the entire column
        logger.debug('creating data object')
        options = {'selected_columns': ['text']}
        data = CSVData(dialog_csv.name, options=options)

        labeler = DataLabeler(labeler_type='unstructured')
        labeler.set_params(
          { 'postprocessor' : {'output_format':'ner', 'use_word_level_argmax': True}}
        )

        logger.debug('predicting labels')
        predictions = labeler.predict(data)

      analysis_extras = {
        "product": ANALYSIS_PRODUCT
      }

      logger.debug('redacting dialog text')
      redacted_texts = []
      for i, dialog in data.data.iterrows():
        redacted_dialog = self.redact_text_helper(dialog, predictions['pred'][i])
        dialog_texts[i]['redacted'] = redacted_dialog
        if redacted_dialog != dialog.text:
          redacted_texts.append(dialog_texts[i])

      logger.debug('adding to aaaaanalysis')
      out_vcon.add_analysis(
        dialog_index,
        ANALYSIS_TYPE,
        redacted_texts,
        ANALYSIS_VENDOR,
        ANALYSIS_SCHEMA,
        **analysis_extras
        )

    return(out_vcon)

