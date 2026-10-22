# Copyright (C) 2023-2026 SIPez LLC.  All rights reserved.
# Copyright (C) 2026 SIP Spectrum, Inc.  All rights reserved.
""" OpenAI FilterPlugin implentation """
import typing
import asyncio
import inspect
import weakref
import datetime
import json
import logging
import pydantic
import openai
import jq
import tenacity
import vcon
import vcon.filter_plugins

VERBOSE = False

logger = vcon.build_logger(__name__)

OPENAI_RETRY_EXCEPTIONS = (openai.APITimeoutError)

class OpenAIKeyNotSet(Exception):
  """ Raised when an OpenAI FilterPlugin is invoked without an API key set """


class OpenAITokenLimitExceeded(Exception):
  """ Raised when an OpenAI response was cut off at max_tokens and is not usable """


class OpenAIRefusal(Exception):
  """ Raised when the OpenAI model refuses the request """


class OpenAIChatCompletionInitOptions(
  vcon.filter_plugins.FilterPluginInitOptions,
  title = "OpenAI/ChatGPT Chat Completion **FilterPlugin** intialization object"
  ):
  """
  A **OpenAIChatCompletionInitOptions** object is provided to the
  **OpenAIChatCompletion FilterPlugin.__init__** method when it is first loaded.  Its
  attributes effect how the registered **FilterPlugin** functions.
  """
  openai_api_key: str = pydantic.Field(
    title = "**OpenAI** API key",
    description = """
The **openai_api_key** is used to access the OpenAI RESTful service.
It is required to use this **FilterPlugin**.

You can get one at: https://platform.openai.com/account/api-keys
""",
    examples = ["sk-cABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstu"]
    )


class OpenAIChatCompletionOptions(
  vcon.filter_plugins.FilterPluginOptions,
  title = "OpenAI Chat Completion filter method options"
  ):
  """
  Options for generative AI using **OpenAI** chat completion (e.g. ChatGPT)
  on the text dialogs and/or transcription analysis in the given
  **Vcon**

  More details on the OpenAI specific parameters can be found here:
  https://platform.openai.com/docs/api-reference/chat/create
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
    client = openai.OpenAI(api_key = "your key here")
    print([model.id for model in client.models.list()])
""",
    default = 'gpt-6-sol',
    examples = [
      'gpt-6-sol',
      'gpt-6-luna',
      'gpt-6.1-sol',
      'gpt-6-astra'
      ]
    )

  prompt: str = pydantic.Field(
    title = "the prompt or question to ask about the transcription/text",
    description = """
The **OpenAI** model is given text from the dialog and
given this prompt to instruct it what generative AI text
that you would like from it.
""",
    default = "Summarize the transcript in these messages."
    )

  max_tokens: int = pydantic.Field(
    title = "maximum number of tokens of output",
    description = """
The **max_tokens** limits the size of the output generative AI text.
A token is approximately a syllable.  On average a word is 1.33 tokens.

For reasoning models (e.g. gpt-6-sol and gpt-6-luna), **max_tokens** also
includes the hidden reasoning tokens, which can use more of the allotment than
the output text itself.  If the allotment is used up before any text is
output, **OpenAITokenLimitExceeded** is raised.  See also **reasoning_effort**
and **fail_on_truncation**.
""",
    default = 1000
    )

  temperature: float = pydantic.Field(
    title = "**OpenAI** sampling temperature",
    description = """
lower number is more deterministic, higher is more random.

values should range from 0.0 to 2.0

Only sent to **OpenAI** when not 1.0 (the **OpenAI** default).  Some models
(e.g. gpt-6-sol and gpt-6-luna) only accept the default and reject any other value.
""",
    default = 1.0
    )

  jq_result: str = pydantic.Field(
    title = "**jq** query of result",
    description = """
The **OpenAI** chat completion outputs a JSON
[Chat Completion Object](https://platform.openai.com/docs/api-reference/chat/object)

The **jq_results** string contains a **jq**  filter/query string that
is applied to the output to determine what is saved in the
created **Vcon** **analysis** object.

* **"."** - results in a query that returns the entire JSON object.
* **".choices[0].message.content"** - results in a query which contains only the text portion of the completion output

For more information on creating **jq filters** see:
https://jqlang.github.io/jq/manual/

""",
   default = ".choices[0].message.content",
   examples = [".", ".choices[0].message.content" ]
    )

  json_response: bool = pydantic.Field(
      title = "provide response in JSON format",
      description = "If False (default) response will be in a readable text format."
        "  If True, the response from ChatGPT will be in a JSON formatted document."
        "  If a JSON response is desired, your prompt should specify the format of"
        " the JSON content or parameters."
        "  JSON output cut off at **max_tokens** is never valid JSON, so setting"
        " **fail_on_truncation** to True is recommended when this is True.",
      default = False
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

  reasoning_effort: str = pydantic.Field(
    title = "**OpenAI** reasoning effort",
    description = """
How much hidden reasoning a reasoning model does before it outputs text.
Passed to **OpenAI** as **reasoning_effort**.

 * **""** (empty string, default) - not sent, the model uses its own default
 * **"none"**, **"minimal"**, **"low"**, **"medium"**, **"high"**, **"xhigh"**, **"max"**

Which values are accepted varies by model (e.g. gpt-6.1-sol does not accept
"none") and models without reasoning reject this parameter, so leave it
empty for those.  The value is not checked here, **OpenAI** rejects values
that the model does not support.

Reasoning tokens count against **max_tokens**.
""",
    default = "",
    examples = ["", "none", "minimal", "low", "medium", "high", "xhigh", "max"]
    )

  fail_on_truncation: bool = pydantic.Field(
    title = "fail if the output is cut off at **max_tokens**",
    description = """
If True, **OpenAITokenLimitExceeded** is raised when the output was cut off
at **max_tokens**.

If False (default), output that was cut off is kept, a warning is logged and
**"truncated": true** is set on the new **analysis** object.

In either case, **OpenAITokenLimitExceeded** is always raised when no text
was output at all, or when **json_response** is True and the JSON output was
cut off.
""",
    default = False
    )


class OpenAIClient():
  """ Wrapper around the **OpenAI** AsyncOpenAI client (one per event loop) """
  def __init__(
      self,
      init_options,
      name: str
    ):
    if(init_options.openai_api_key is None or
      init_options.openai_api_key == ""):
      logger.warning("OpenAIClient in {} plugin: key not set.  Plugin will be a no-op".format(name))
      self.key_set = False
    else:
      self.key_set = True

    if(self.key_set):
      # created on first use, per event loop (see _async_client)
      self._api_key = init_options.openai_api_key
      self.client = None
      self._client_loop = None


  def _async_client(self):
    """
    The AsyncOpenAI client for the running event loop.

    A client's connection pool is bound to the event loop it is first used on,
    so a client created on an earlier loop fails once that loop is closed
    (RuntimeError: Event loop is closed).  This plugin outlives any one loop
    (e.g. successive asyncio.run() calls, or a test framework giving each test
    its own loop), so a new client is created when the loop changes.
    """
    loop = asyncio.get_running_loop()
    if(self.client is None or self._client_loop is None or self._client_loop() is not loop):
      self.client = openai.AsyncOpenAI(
          api_key = self._api_key
        )
      # weak, so a finished loop is not kept alive by the plugin
      self._client_loop = weakref.ref(loop)

    return(self.client)


  async def chat_completions(
      self,
      options,
      messages
    ):
    """ Generative AI completion on set of messages, from potentially mutliple people """
    additional_args = {}
    if(options.json_response):
      additional_args["response_format"] = {"type": "json_object"}
    if(options.temperature != 1.0):
      additional_args["temperature"] = options.temperature
    if(options.reasoning_effort != ""):
      additional_args["reasoning_effort"] = options.reasoning_effort

    # chat_completion_object is openai.types.chat.chat_completion.ChatCompletion
    chat_completion_object = await self._async_client().chat.completions.create(
        model = options.model,
        messages = messages,
        max_completion_tokens = options.max_tokens,
        **additional_args
      )
    chat_completion_result = chat_completion_object.dict()

    return(chat_completion_result)

  async def aclose(self):
    """
    Close the client of the running event loop, from that loop.

    Connections can only be closed on the loop that opened them, so this has to
    be awaited on that loop while it is still running.  Anything that uses more
    than one event loop (successive asyncio.run() calls, or a test framework
    giving each test its own loop) should await this before a loop ends.  A
    client left behind is closed by the OpenAI SDK's __del__ on whatever loop
    is running when it is garbage collected, which fails with "Event loop is
    closed" and is reported by asyncio as an unretrieved task exception.
    """
    client = getattr(self, "client", None)
    if(client is None):
      return

    logger.debug("closing OpenAI client for this event loop")
    self.client = None
    self._client_loop = None
    result = client.close()
    if(inspect.isawaitable(result)):
      await result


  def close(self):
    """
    Release the client, from outside a coroutine.  Prefer aclose() when there
    is a running event loop: connections can only be closed on the loop that
    opened them, so a client whose loop has gone is dropped without closing
    (the connections went with the loop).
    """
    client = getattr(self, "client", None)
    if(client is None):
      logger.debug("None OpenAI client")
      return

    logger.debug("closing OpenAI client")
    self.client = None
    loop_ref = getattr(self, "_client_loop", None)
    loop = loop_ref() if(loop_ref is not None) else None
    self._client_loop = None

    result = client.close()
    # Newer openAI is async, need to see which form
    if(not inspect.isawaitable(result)):
      return

    if(loop is None or loop.is_closed()):
      # close the coroutine, so it is not reported as never awaited
      result.close()
      logger.debug("OpenAI client's event loop has gone, dropped without closing")
      return

    def closed(task):
      """ take the result, so asyncio does not report it as unretrieved """
      if(not task.cancelled() and task.exception() is not None):
        logger.debug("closing OpenAI client failed: {}".format(task.exception()))

    try:
      if(loop.is_running()):
        loop.create_task(result).add_done_callback(closed)
      else:
        loop.run_until_complete(result)
    except Exception as e:
      logger.debug("could not close OpenAI client: {}".format(e))
      result.close()


class OpenAIChatCompletion(vcon.filter_plugins.FilterPlugin):
  """
  **FilterPlugin** to for generative AI using **OpenAI** chat completion (e.g. ChatGPT)

  **OpenAIChatCompletion** uses the context of all of the text dialog and
  transcribe analysis objects as input labeled by time and party and generates
  a single prompt response or answer in one new analysis object.
  """
  init_options_type = OpenAIChatCompletionInitOptions

  def __init__(
    self,
    init_options: OpenAIChatCompletionInitOptions
    ):
    """
    Parameters:
      init_options (OpenAIChatCompletionInitOptions) - the initialization options for the **OpenAI** chat completion plugin
    """
    super().__init__(
      init_options,
      OpenAIChatCompletionOptions
      )

    logger.debug("OpenAIChatComplete setting client")
    self.client =  OpenAIClient(init_options, self.__class__.__name__)

    self.last_stats: typing.Dict[str, int] = {}


  @tenacity.retry(
      retry = tenacity.retry_if_exception_type(OPENAI_RETRY_EXCEPTIONS),
      wait = tenacity.wait_random_exponential(multiplier = 1, max = 90),
      stop = tenacity.stop_after_attempt(16),
      before = tenacity.before_log(logger, logging.DEBUG),
      after = tenacity.after_log(logger, logging.DEBUG)
    )
  async def chat_completions_with_retry(self, messages, options):
    """ Retry chat_completions if connectivity or service availability problems """
    logger.debug("attempting chat_completions")
    chat_completion_result = await self.client.chat_completions(
        options,
        messages
      )
    return(chat_completion_result)


  def check_response(
    self,
    chat_completion_result: typing.Dict[str, typing.Any],
    options: OpenAIChatCompletionOptions
    ) -> bool:
    """
    Check the chat completion response for a refusal or for output cut off
    at **max_tokens**.

    Parameters:
      chat_completion_result (dict) - the chat completion object as a dict
      options (OpenAIChatCompletionOptions) - the options used for the request

    Raises:
      OpenAIRefusal - the model refused the request
      OpenAITokenLimitExceeded - the output was cut off at **max_tokens** and is not usable

    Returns:
      True if the output was cut off at **max_tokens** but is kept, otherwise False
    """
    choice = chat_completion_result["choices"][0]
    message = choice.get("message") or {}

    refusal = message.get("refusal")
    if(refusal):
      raise OpenAIRefusal("{}: model {} refused the request: {}".format(
        self.__class__.__name__,
        options.model,
        refusal
        ))

    if(choice.get("finish_reason") != "length"):
      return(False)

    usage = chat_completion_result.get("usage") or {}
    completion_tokens = usage.get("completion_tokens")
    reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    usage_text = ""
    if(completion_tokens is not None):
      usage_text = "; {} used".format(completion_tokens)
      if(reasoning_tokens):
        usage_text += ", {} for reasoning".format(reasoning_tokens)
    limit_text = "{}: model {} response was cut off at max_tokens ({}{})".format(
      self.__class__.__name__,
      options.model,
      options.max_tokens,
      usage_text
      )
    advice = "Increase max_tokens or lower reasoning_effort."

    content = message.get("content")
    if(content is None or content == ""):
      raise OpenAITokenLimitExceeded("{} and returned no text.  {}".format(limit_text, advice))

    if(options.json_response):
      try:
        json.loads(content)
      except ValueError:
        raise OpenAITokenLimitExceeded("{} and the JSON is incomplete.  {}".format(limit_text, advice))

    if(options.fail_on_truncation):
      raise OpenAITokenLimitExceeded("{}.  {}".format(limit_text, advice))

    logger.warning("{}.  Keeping the truncated output.  {}".format(limit_text, advice))
    return(True)

  async def filter(
    self,
    in_vcon: vcon.Vcon,
    options: OpenAIChatCompletionOptions
    ) -> vcon.Vcon:
    """
    Perform generative AI using **OpenAI** chat completion on the
    text **dialogs** and/or transcription **analysis** objects
    in the given **Vcon** using the given **options.prompt**.

    Parameters:
      options (OpenAIChatCompletionOptions)

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

    if(not self.client.key_set):
      message = "OpenAIChatCompletion.filter: OPENAI_API_KEY is not set"
      logger.error(message)
      raise OpenAIKeyNotSet(message)

    dialog_text: typing.List[typing.Dict[str, str]] = []
    # Loop through the text dialogs and add them to the list
    num_text_dialogs = 0
    num_transcribe_analysis = 0
    # NOTE: the dialog_list may not be the full list of dialogs in
    # this Vcon.  So the index into dialog_list is meaningless
    for dialog_index in dialog_indices:
      this_dialog_texts = await in_vcon.get_dialog_text(
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
        except (AttributeError, KeyError) as e:
          logger.exception(e)
          logger.warning("vcon: {} get_dialog_text dialog_index: {} text[{}]: missing parties: {}".format(
            in_vcon.uuid,
            dialog_index,
            text_index,
            text_dict.get("parties", None)
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

    chat_completion_result = await self.chat_completions_with_retry(sorted_messages, options)
    truncated = self.check_response(chat_completion_result, options)

    compiled_query = jq.compile(options.jq_result)
    query_result = compiled_query.input_value(chat_completion_result).all()
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

    if(truncated):
      addition_analysis_parameters["truncated"] = True

    # guess the body type
    if(isinstance(new_analysis_body, str)):
      encoding = "none"
      schema = "text"
      addition_analysis_parameters["mediatype"] = vcon.Vcon.MEDIATYPE_TEXT_PLAIN
    else:
      encoding = "json"
      schema = "chat_completion_object"
      if(options.jq_result != "."):
        schema += " ?jq=" + options.jq_result
      addition_analysis_parameters["mediatype"] = vcon.Vcon.MEDIATYPE_JSON

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


  def __del__(self):
    """ Close down OpenAI client if created. """
    if(hasattr(self, "client") and self.client):
      logger.debug("OpenAIChatCompletion closing OpenAIClient")
      self.client.close()
      self.client = None
    else:
      logger.debug("OpenAIChatCompletion None OpenAIClient")
    super().__del__()


