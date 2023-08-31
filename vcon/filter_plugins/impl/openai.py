""" OpenAI FilterPlugin implentation """
import pydantic
import openai
import vcon
import vcon.filter_plugins
import pyjq

logger = vcon.build_logger(__name__)


class OpenAICompletionInitOptions(
  vcon.filter_plugins.FilterPluginInitOptions,
  title = "OpenAI/ChatGPT **FilterPlugin** intialization object"
  ):
  """
  A **OpenAIInitOptions** object is provided to the
  **OpenAI FilterPlugin.__init__** method when it is first loaded.  Its
  attributes effect how the registered **FilterPlugin** functions.
  """
  openai_api_key: str = pydantic.Field(
    title = "**OpenAI iAPI key",
    description = """
The **openai_api_key** is used to access the OpenAI RESTful service.
It is required to use this **FilterPlugin**.

You can get one at: https://platform.openai.com/account/api-keys
""",
    example = "sk-cABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstu"
    )


class OpenAICompletionOptions(
  vcon.filter_plugins.FilterPluginOptions,
  title = "OpenAI filter method options"
  ):
  """
  Options for generative AI using **OpenAI** completion (e.g. ChatGPT)
  on the text dialogs and/or transcription analysis in the given
  **Vcon**

  More details on the OpenAI specific parameters can be found here:
  https://platform.openai.com/docs/api-reference/completions/create
  """
  input_dialogs: bool = pydantic.Field(
    title = "input **Vcon** text **dialog** objects",
    description = """
 * **True** - all text **dialog** objects are fed into **OpenAI** model to complete the response to the **prompt**
 * **False** - none of the **dialog** objects are fed to the the model.

TODO: select specific **Vcon dialog** objects by index as input.
""",
    default = True,
    examples = [True, False]
    )

  input_transcripts: bool = pydantic.Field(
    title = "input **Vcon** transcript type **analysis** objects",
    description = """
 * **True** - all transcription **analysis** objects are fed into **OpenAI** model to complete the response to the **prompt**
 * **False** - none of the **analysis** object are fed to the the model.

TODO: select specific **Vcon analysis** objects by index as input.
""",
    default = True,
    examples = [True, False]
    )

  model: str = pydantic.Field(
    title = "**OpenAI** model name to use for generative AI",
    description = """
The named model is used to feed the transcription/text and then ask it the
given prompt.
OpenAI has numerous trained models, the latest of which may not be listed here
in examples.

You can get the current list of of available models for
your license/API key using the following:

    import openai
    openai.api_key = "your key here"
    openai.Model.list()
""",
    default = 'text-davinci-003',
    examples = [
      'davinci',
      'gpt-4',
      'text-davinci-001',
      'text-search-curie-query-001',
      'gpt-3.5-turbo',
      'gpt-4-0613',
      'babbage',
      'text-babbage-001',
      'curie-instruct-beta',
      'davinci-similarity',
      'code-davinci-edit-001',
      'text-similarity-curie-001',
      'ada-code-search-text',
      'gpt-3.5-turbo-0613',
      'text-search-ada-query-001',
      'gpt-3.5-turbo-16k-0613',
      'gpt-4-0314',
      'babbage-search-query',
      'ada-similarity',
      'text-curie-001',
      'gpt-3.5-turbo-16k',
      'text-search-ada-doc-001',
      'text-search-babbage-query-001',
      'code-search-ada-code-001',
      'curie-search-document',
      'davinci-002',
      'text-search-davinci-query-001',
      'text-search-curie-doc-001',
      'babbage-search-document',
      'babbage-002',
      'babbage-code-search-text',
      'text-embedding-ada-002',
      'davinci-instruct-beta',
      'davinci-search-query',
      'text-similarity-babbage-001',
      'text-davinci-002',
      'code-search-babbage-text-001',
      'text-davinci-003',
      'text-search-davinci-doc-001',
      'code-search-ada-text-001',
      'ada-search-query',
      'text-similarity-ada-001',
      'ada-code-search-code',
      'whisper-1',
      'text-davinci-edit-001',
      'davinci-search-document',
      'curie-search-query',
      'babbage-similarity',
      'ada',
      'ada-search-document',
      'text-ada-001',
      'text-similarity-davinci-001',
      'curie-similarity',
      'babbage-code-search-code',
      'code-search-babbage-code-001',
      'text-search-babbage-doc-001',
      'gpt-3.5-turbo-0301',
      'curie'
      ]
    )

  prompt: str = pydantic.Field(
    title = "the prompt or question to ask about the transcription/text",
    description = """
The **OpenAI** model is given text from the dialog and
given this prompt to instruct it what generative AI text
that you would like from it.
""",
    default = "Summarize this conversation: "
    )

  max_tokens: int = pydantic.Field(
    title = "maximum number of tokens of output",
    description = """
The **max_tokens** limits the size of the output generative AI text.
A token is approximately a syllable.  On average a word is 1.33 tokens.
""",
    default = 100
    )

  temperature: float = pydantic.Field(
    title = "**OpenAI** sampling temperature",
    description = """
lower number is more deterministic, higher is more random.

values should range from 0.0 to 2.0
""",
    default = 0.0
    )

  jq_result: str = pydantic.Field(
    title = "**jq** query of result",
    description = """
The **OpenAI** completion outputs a JSON 
[Completion Object](https://platform.openai.com/docs/api-reference/completions/object)

The **jq_results** string contains a **jq**  filter/query string that
is applied to the output to determine what is saved in the
created **Vcon** analysis** object.

* **"."** - results in a query that returns the entire JSON object.
* **".choices[0].text"** - results in a query which contains only the text portion of the completion output

For more information on creating **jq filters** see:
https://jqlang.github.io/jq/manual/

""",
   default = ".choices[0].text",
   examples = [".", ".choices[0].text" ]
    )

  analysis_type: str = pydantic.Field(
    title = "the **Vcon analysis** object type",
    description = """
The results of the completion are saved in a new **analysis**
object which is added to the input **Vcon**.
**analysis_type** is the **analysis** type token that is set
on the new **analysis** object in the **Vcon**.
""",
    default = "summary"
    )


class OpenAICompletion(vcon.filter_plugins.FilterPlugin):
  """
  **FilterPlugin** to for generative AI using **OpenAI** completion (e.g. ChatGPT)
  """
  init_options_type = OpenAICompletionInitOptions

  def __init__(
    self,
    init_options: OpenAICompletionInitOptions
    ):
    """
    Parameters:
      init_options (OpenAICompletionInitOptions) - the initialization options for the **OpenAI** completion plugin
    """
    super().__init__(
      init_options,
      OpenAICompletionOptions
      )

    if(init_options.openai_api_key is None or
      init_options.openai_api_key == ""):
      logger.warning("OpenAI completion plugin: key not set.  Plugin will be a no-op")
    openai.api_key = init_options.openai_api_key

  def complete(
    self,
    out_vcon: vcon.Vcon,
    options: OpenAICompletionOptions,
    text_body: str,
    dialog_index: int
    ) -> vcon.Vcon:
    """ Run **OpenAI completion* on the given text and create a new analysis object """

    completion_result = openai.Completion.create(
      model = options.model,
      prompt = options.prompt + text_body,
      max_tokens = options.max_tokens,
      temperature = options.temperature
      )

    query_result = pyjq.all(options.jq_result, completion_result)
    if(len(query_result) == 0):
      logger.warning("{} jq query resulted in no elements.  No analysis object added".format(
       self.__class__.__name__
       ))
      return(out_vcon)
    if(len(query_result) == 1):
      new_analysis_body = query_result[0]
    else:
      # TODO: is this what we should be doing??
      logger.warning("{} jq query resulted in {} elements.  Dropping all but the first one.".format(
       self.__class__.__name__,
       len(query_result)
       ))
      new_analysis_body = query_result[0]

    addition_analysis_parameters = {
      "prompt": options.prompt,
      "model": options.model,
      "vendor_product": "completion"
      }

    # guess the body type
    if(isinstance(new_analysis_body, str)):
      encoding = "none"
      schema = "text"
      addition_analysis_parameters["mimetype"] = vcon.Vcon.MIMETYPE_TEXT_PLAIN
    else:
      encoding = "json"
      schema = "completion_object"
      if(options.jq_result != "."):
        schema += " ?jq=" + options.jq_result
      addition_analysis_parameters["mimetype"] = vcon.Vcon.MIMETYPE_JSON

    out_vcon.add_analysis(
      dialog_index,
      options.analysis_type,
      new_analysis_body,
      'openai',
      schema,
      encoding,
      **addition_analysis_parameters
      )

    return(out_vcon)


  def filter(
    self,
    in_vcon: vcon.Vcon,
    options: OpenAICompletionOptions
    ) -> vcon.Vcon:
    """
    Perform generative AI using **OpenAI** completion on the
    text **dialogs** and/or transcription **analysis** objects
    in the given **Vcon** using the given **options.prompt**.
`
    Parameters:
      options (OpenAICompletionOptions)

    Returns:
      the modified Vcon with added analysis objects for the text dialogs and transcription analysis.
    """
    out_vcon = in_vcon

    # no dialogs and we are not to input analysis
    if(in_vcon.dialog is None and
      not options.input_transcripts):
      return(out_vcon)

    if(openai.api_key is None or
      openai.api_key == ""):
      logger.warning("OpenAICompletion.filter: OpenAI API key is not set, no filtering performed")
      return(out_vcon)

    if(options.input_dialogs):
      for dialog_index, dialog in enumerate(in_vcon.dialog):
        if(dialog["type"] == "text"):
          #if(dialog["mimetype"] in self._supported_media):
          # If inline or externally referenced recording:
          body_bytes = in_vcon.get_dialog_body(dialog_index)
          if(isinstance(body_bytes, bytes)):
            body_bytes = str(body_bytes, encoding = "utf-8")

          out_vcon = self.complete(
            out_vcon,
            options,
            body_bytes,
            dialog_index,
            )
        else:
          pass # ignore??

          # else:
          #  print("unsupported media type: {} in dialog[{}], skipped whisper transcription".format(dialog.mimetype, dialog_index))

    if(in_vcon.analysis is None or
      not options.input_transcripts):
      return(out_vcon)

    for analysis_index, analysis in enumerate(in_vcon.analysis):
       if(analysis["type"] == "transcript"):
         if(analysis["vendor"] == "Whisper" and
           analysis["vendor_schema"] == "whisper_word_timestamps"
          ):
          text_body = analysis["body"]["text"]
          dialog_index = analysis["dialog"]
          out_vcon = self.complete(
            out_vcon,
            options,
            text_body,
            dialog_index,
            )
    return(out_vcon)

