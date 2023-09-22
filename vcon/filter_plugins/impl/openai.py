""" OpenAI FilterPlugin implentation """
import typing
import datetime
import pydantic
import openai
import vcon
import vcon.filter_plugins
import pyjq

VERBOSE = False

logger = vcon.build_logger(__name__)


class OpenAICompletionInitOptions(
  vcon.filter_plugins.FilterPluginInitOptions,
  title = "OpenAI/ChatGPT Completion **FilterPlugin** intialization object"
  ):
  """
  A **OpenAIInitOptions** object is provided to the
  **OpenAI FilterPlugin.__init__** method when it is first loaded.  Its
  attributes effect how the registered **FilterPlugin** functions.
  """
  openai_api_key: str = pydantic.Field(
    title = "**OpenAI** API key",
    description = """
The **openai_api_key** is used to access the OpenAI RESTful service.
It is required to use this **FilterPlugin**.

You can get one at: https://platform.openai.com/account/api-keys
""",
    example = "sk-cABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstu"
    )


class OpenAICompletionOptions(
  vcon.filter_plugins.FilterPluginOptions,
  title = "OpenAI Completion filter method options"
  ):
  """
  Options for generative AI using **OpenAI** completion (e.g. ChatGPT)
  on the text dialogs and/or transcription analysis in the given
  **Vcon**

  More details on the OpenAI specific parameters can be found here:
  https://platform.openai.com/docs/api-reference/completions/create
  """
  input_dialogs: typing.Union[str,typing.List[int]] = pydantic.Field(
    title = "input **Vcon** text **dialog** objects",
    description = """
Indicates which text **dialog** and recording **dialog** object's associated
transcript **analysis** objects are to be input.  Recording **dialog**
objects that do not have transcript **analysis** objects, are transcribed
using the default FilterPlugin transcribe type.

 * **""** (empty str or None) - all **dialogs** are fed into **OpenAI** model to complete the response to the **prompt**.  This is the equivalent of providing "0:".
 * **n:m** (str) - **dialog** objects having indices **n-m** are fed into **OpenAI** model to complete the response to the **prompt** 
 * **n:m:i** (str) - **dialog** objects having indices **n-m** using interval **i** are fed into **OpenAI** model to complete the response to the **prompt** 
 * **[]** (empty list[int]) - none of the **dialog** objects are fed to the the model.
 * **[1, 4, 5, 9]** (list[int]) - the **dialog** objects having the indices in the given list are fed to the the model.

**dialog** objects in the given sequence or list which are not **text** or **recording** type dialogs are ignored.
""",
    default = "",
    examples = ["", "0:", "0:-2", "2:5", "0:6:2", [], [1, 4, 5, 9]]
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
created **Vcon** **analysis** object.

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

  **OpenAICompletion** differs from **OpenAIChatCompletion** in that is uses
  only imputs a single text dialog or transcribe analysis text when asking
  for a completion to the prompt.  **OpenAIChatCompletion** by default will
  iterate through all of the text dialog or transcribe analysis text, but it
  evaluates the prompt for only one text input at a time.  Thus generating
  a prompt answer as a new analysis obejct for each text dialog or
  transcribe analysis text analysed.

  In contrast, **OpenAIChatCompletion** inputs the context of all of the text
  dialog and transcribe analysis objects as input labeled by time and party
  and will generate a single prompt response as one new analysis object.
  
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
      "product": "Completion"
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

    dialog_indices = self.slice_indices(
      options.input_dialogs,
      len(in_vcon.dialog),
      "OpenaiCompletionOptions.input_dialogs"
      )

    # no dialogs
    if(len(dialog_indices) == 0):
      return(out_vcon)

    if(openai.api_key is None or
      openai.api_key == ""):
      logger.warning("OpenAICompletion.filter: OpenAI API key is not set, no filtering performed")
      return(out_vcon)

    for dialog_index in dialog_indices:
      this_dialog_texts = in_vcon.get_dialog_text(
        dialog_index,
        True, # find text from transcript analysis if dialog is a recording and transcript exists
        True  # transcribe this recording dialog if transcript does not exist
        )
      dialog = in_vcon.dialog[dialog_index]
      for text_item in this_dialog_texts:
        out_vcon = self.complete(
          out_vcon,
          options,
          text_item["text"],
          dialog_index,
          )

    return(out_vcon)


chat_completions_init_options_defaults = {
}

class OpenAIChatCompletionInitOptions(
  OpenAICompletionInitOptions,
  field_defaults = chat_completions_init_options_defaults,
  title = "OpenAI/ChatGPT Chat Completion **FilterPlugin** intialization object"
  ):
  pass


chat_completion_options_defaults = {
  "jq_result": ".choices[0].message.content",
  "model": "gpt-4",
  "prompt": "Summarize the transcript in these messages."
  }

class OpenAIChatCompletionOptions(
  OpenAICompletionOptions,
  field_defaults = chat_completion_options_defaults,
  title = "OpenAI Chat Completion filter method options"
  ):
  pass


class OpenAIChatCompletion(OpenAICompletion):
  """
  **FilterPlugin** to for generative AI using **OpenAI** chat completion (e.g. ChatGPT)

  **OpenAIChatCompletion** differs from **OpenAICompletion** in that is uses the
  context of all of the text dialog and transcribe analysis objects as input labeled by
  time and party and generates a single prompt response or answer in one new analysis
  object.  In contrast, **OpenAICompletion** only imputs a single text dialog
  or transcribe analysis text when asking for a completion to the prompt, generating
  a prompt response and a new analysis object for each text dialog and transcribe
  analysis object analysed.
  """

  def __init__(
    self,
    init_options: OpenAIChatCompletionInitOptions
    ):
    """
    Parameters:
      init_options (OpenAICompletionInitOptions) - the initialization options for the **OpenAI** completion plugin
    """
    super().__init__(init_options)

    self.options_type = OpenAIChatCompletionOptions
    if(init_options.openai_api_key is None or
      init_options.openai_api_key == ""):
      logger.warning("OpenAI completion plugin: key not set.  Plugin will be a no-op")
    openai.api_key = init_options.openai_api_key
    self.last_stats = {}

  def filter(
    self,
    in_vcon: vcon.Vcon,
    options: OpenAIChatCompletionOptions
    ) -> vcon.Vcon:
    """
    Perform generative AI using **OpenAI** chat completion on the
    text **dialogs** and/or transcription **analysis** objects
    in the given **Vcon** using the given **options.prompt**.
`
    Parameters:
      options (OpenAICompletionOptions)

    Returns:
      the modified Vcon with a single analysis object added in total
      for all of the text dialogs and transcription analysis object
      analysed.
    """

    out_vcon = in_vcon

    dialog_indices = self.slice_indices(
      options.input_dialogs,
      len(in_vcon.dialog),
      "OpenaiChatCompletionOptions.input_dialogs"
      )

    dialog_text: typing.List[typing.Dict[str, str]] = []
    # Loop through the text dialogs and add them to the list
    num_text_dialogs = 0
    num_transcribe_analysis = 0
    # NOTE: the dialog_list may not be the full list of dialogs in
    # this Vcon.  So the index into dialog_list is meaningless
    for dialog_index in dialog_indices:
      this_dialog_texts = in_vcon.get_dialog_text(
        dialog_index,
        True, # find text from transcript analysis if dialog is a recording and transcript exists
        True  # transcribe this recording dialog if transcript does not exist
        )
      dialog = in_vcon.dialog[dialog_index]
      if(VERBOSE):
        logger.debug("text dialog[{}] text(s): {}".format(dialog_index, this_dialog_texts))
      for text_index, text_dict in enumerate(this_dialog_texts):
        try:
          party_label = self.get_party_label(in_vcon, text_dict["parties"], True)
        except AttributeError as e:
          logger.exception(e)
          logger.warning("vcon: {} get_dialog_text dialog_index: {} text[{}]: missing parties: {}".format(
            in_vcon.uuid,
            dialog_index,
            text_index,
            text_dict["parties"]
            ))
          party_label = "unknown"

        if(text_dict["duration"] is not None and
          text_dict["duration"] > 0
          ):
          call_end = datetime.datetime.fromisoformat(vcon.utils.cannonize_date(text_dict["start"])) +\
            datetime.timedelta(0, text_dict["duration"])
          call_end_string = " to " + call_end.isoformat()
        else:
          call_end_string = "" # don't know so don't say anything about call end

        # role is user, prepend date and party label for content
        text_dict["role"] = "user"
        if(dialog["type"] == "text"):
          num_text_dialogs += 1
          text_dict["content"] = "in chat at {}, {} said: {}".format(
            text_dict["start"],
            party_label,
            text_dict["text"]
            )
        elif(dialog["type"] == "recording"):
          num_transcribe_analysis += 1
          text_dict["content"] = "in a call that took place at {}{}, {} said: {}".format(
            text_dict["start"],
            call_end_string,
            party_label,
            text_dict["text"]
            )

        dialog_text.append(text_dict)

    # Nothing to summary or analyze.
    if(len(dialog_text) == 0):
      return(out_vcon)

    # sort the text by start date and remove the date parameter
    sorted_messages = sorted(dialog_text.copy(), key = lambda msg: msg["start"])
    logger.debug("generated {} messages from {} text dialogs and {} recording dialogs out of {} input dialogs".format(
      len(sorted_messages),
      num_text_dialogs,
      num_transcribe_analysis,
      len(dialog_indices)
      ))

    # For test and debugging
    self.last_stats["num_messages"] = len(sorted_messages)
    self.last_stats["num_text_dialogs"] = num_text_dialogs
    self.last_stats["num_dialog_list"] = len(dialog_indices)
    self.last_stats["num_transcribe_analysis"] = num_transcribe_analysis

    # Remove stuff that ChatCompletion does not expect
    for msg in sorted_messages:
      # Remove everything except role and content
      remove_keys = list(msg.keys())
      remove_keys.remove("role")
      remove_keys.remove("content")
      for param in remove_keys:
        del msg[param]

    # add the system role at the end so that dialog does not over ride it
    sorted_messages.append({"role": "system", "content": "You are a helpful assistant."})

    # Add the prompt
    sorted_messages.append({"role": "system", "content": options.prompt})

    if(VERBOSE):
      logger.debug("OpenAIChatCompletion messages: {}".format(sorted_messages))
    # feed message to ChatGPT

    chat_completion_result = openai.ChatCompletion.create(
      model = options.model,
      messages = sorted_messages,
      max_tokens = options.max_tokens,
      temperature = options.temperature
      )

    query_result = pyjq.all(options.jq_result, chat_completion_result)
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
      "product": "ChatCompletion"
      }

    # guess the body type
    if(isinstance(new_analysis_body, str)):
      encoding = "none"
      schema = "text"
      addition_analysis_parameters["mimetype"] = vcon.Vcon.MIMETYPE_TEXT_PLAIN
    else:
      encoding = "json"
      schema = "chat_completion_object"
      if(options.jq_result != "."):
        schema += " ?jq=" + options.jq_result
      addition_analysis_parameters["mimetype"] = vcon.Vcon.MIMETYPE_JSON

    if(len(dialog_indices) == 1):
      analysis_dialogs = dialog_indices[0]
    elif(len(dialog_indices) > 1):
      analysis_dialogs = dialog_indices
    else:
      raise Exception("creating analysis from zero dialogs")

    out_vcon.add_analysis(
      analysis_dialogs,
      options.analysis_type,
      new_analysis_body,
      'openai',
      schema,
      encoding,
      **addition_analysis_parameters
      )

    return(out_vcon)

