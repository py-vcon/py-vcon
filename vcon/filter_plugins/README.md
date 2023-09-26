
# Filter Plugins

## Table of Contents
 + [Introduction](#introduction)
 + [Filter Plugin Classes](#filter-plugin-classes)
   - [vcon.filter_plugins.FilterPlugin](#vconfilter_pluginsfilterplugin)
   - [vcon.filter_plugins.impl.deepgram.Deepgram](#vconfilter_pluginsimpldeepgramdeepgram)
   - [vcon.filter_plugins.impl.openai.OpenAIChatCompletion](#vconfilter_pluginsimplopenaiopenaichatcompletion)
   - [vcon.filter_plugins.impl.openai.OpenAICompletion](#vconfilter_pluginsimplopenaiopenaicompletion)
   - [vcon.filter_plugins.impl.whisper.Whisper](#vconfilter_pluginsimplwhisperwhisper)
 + [Filter Plugin Initialization Options Classes](#filter-plugin-initialization-options-classes)
   - [vcon.filter_plugins.FilterPluginInitOptions](#vconfilter_pluginsfilterplugininitoptions)
   - [vcon.filter_plugins.impl.deepgram.DeepgramInitOptions](#vconfilter_pluginsimpldeepgramdeepgraminitoptions)
   - [vcon.filter_plugins.impl.openai.OpenAIChatCompletionInitOptions](#vconfilter_pluginsimplopenaiopenaichatcompletioninitoptions)
   - [vcon.filter_plugins.impl.openai.OpenAICompletionInitOptions](#vconfilter_pluginsimplopenaiopenaicompletioninitoptions)
   - [vcon.filter_plugins.impl.whisper.WhisperInitOptions](#vconfilter_pluginsimplwhisperwhisperinitoptions)
 + [Filter Plugin Options Classes](#filter-plugin-options-classes)
   - [vcon.filter_plugins.FilterPluginOptions](#vconfilter_pluginsfilterpluginoptions)
   - [vcon.filter_plugins.impl.deepgram.DeepgramOptions](#vconfilter_pluginsimpldeepgramdeepgramoptions)
   - [vcon.filter_plugins.impl.openai.OpenAIChatCompletionOptions](#vconfilter_pluginsimplopenaiopenaichatcompletionoptions)
   - [vcon.filter_plugins.impl.openai.OpenAICompletionOptions](#vconfilter_pluginsimplopenaiopenaicompletionoptions)
   - [vcon.filter_plugins.impl.whisper.WhisperOptions](#vconfilter_pluginsimplwhisperwhisperoptions)

## Introduction

TBD

# Filter Plugin Classes


## vcon.filter_plugins.FilterPlugin

  Base class for plugins to operate on a vcon.

  **FilterPlugin** take a **Vcon* and some options as
  input and output a **Vcon** which may be the input **Vcon**
  modified.

  A **FilterPlugin** as three primary operations:

   * Initialization (**__init__**) which is invoked with a
        derived class specific set of initialization 
        options (derived from **FilterPluginInitOptions**(

   * filtering (**filter**) which is the actual method 
        that operates on a **Vcon**.

   * teardown (**__del__**) which performs any shutdown or
        release of resources for the plugin.

  Initialization and teardown are only performed once.


  **FilterPlugins** is an abstract class.  One must
  implement a derived class to use it.  The derived class
  must implement the following:

   * **__init__** method SHOULD invoke super().__init__

   * **filter** method to performe the actual **Vcon** operation

   * **init_options_type** MUST be defined and set to a
        derived class of **FilterPluginInitOptions** which
        is the type of the only argument to the derived
        class's **__init__** method.

  To be used the derived class and a specific set of 
  initialization options must be registered using
  **FilterPluginRegistry.register**.  A **FilterPlugin**
  is dynamically loaded only the first time that it
  is actually used. It stays loaded until the system
  exits.
  

**Methods**:

### FilterPlugin.\_\_init__
\_\_init__(self, options: 'FilterPluginInitOptions', options_type: 'typing.Type[FilterPluginOptions]')

Instance stores the initialization options that were used.

Instance also stores the **FilterPluginOptions** type/class
that is used by the derived class's **filter** method.
This is used to enforce typing and defaults for the
options passed into the **filter** method.


**options** - [vcon.filter_plugins.FilterPluginInitOptions](#vconfilter_pluginsfilterplugininitoptions)

### FilterPlugin.filter
filter(self, in_vcon: 'Vcon', options: 'FilterPluginOptions') -> 'Vcon'


Abstract method which performs an operation on an input Vcon and 
provides the modified Vcon as output.

Parameters:
  in_vcon (vcon.Vcon) - input Vcon upon which an operation is to be performed by the plugin.
  options (FilterPluginOptions) - derived options specific to the filter method/opearation

Returns:
  vcon.Vcon - the modified Vcon


**options** - [vcon.filter_plugins.FilterPluginOptions](#vconfilter_pluginsfilterpluginoptions)

### FilterPlugin.\_\_del__
\_\_del__(self)


Teardown/uninitialization method for the plugin

Parameters: None



## vcon.filter_plugins.impl.deepgram.Deepgram

  **FilterPlugin** to for transcription using **Deepgram** 
  

**Methods**:

### Deepgram.\_\_init__
\_\_init__(self, init_options: vcon.filter_plugins.impl.deepgram.DeepgramInitOptions)

Parameters:
  init_options (DeepgramInitOptions) - the initialization options for the **Deepgram** transcription plugin


**init_options** - [vcon.filter_plugins.impl.deepgram.DeepgramInitOptions](#vconfilter_pluginsimpldeepgramdeepgraminitoptions)

### Deepgram.filter
filter(self, in_vcon: vcon.Vcon, options: vcon.filter_plugins.impl.deepgram.DeepgramOptions) -> vcon.Vcon


Transcribe the recording dialog objects using **Deepgram**.

Parameters:
  options (DeepgramOptions)

Returns:
  the modified Vcon with added transcript analysis objects for the recording dialogs.


**options** - [vcon.filter_plugins.impl.deepgram.DeepgramOptions](#vconfilter_pluginsimpldeepgramdeepgramoptions)

### Deepgram.\_\_del__
\_\_del__(self)


Teardown/uninitialization method for the plugin

Parameters: None



## vcon.filter_plugins.impl.openai.OpenAIChatCompletion

  **FilterPlugin** to for generative AI using **OpenAI** chat completion (e.g. ChatGPT)

  **OpenAIChatCompletion** differs from **OpenAICompletion** in that is uses the
  context of all of the text dialog and transcribe analysis objects as input labeled by
  time and party and generates a single prompt response or answer in one new analysis
  object.  In contrast, **OpenAICompletion** only imputs a single text dialog
  or transcribe analysis text when asking for a completion to the prompt, generating
  a prompt response and a new analysis object for each text dialog and transcribe
  analysis object analysed.
  

**Methods**:

### OpenAIChatCompletion.\_\_init__
\_\_init__(self, init_options: vcon.filter_plugins.impl.openai.OpenAIChatCompletionInitOptions)

Parameters:
  init_options (OpenAICompletionInitOptions) - the initialization options for the **OpenAI** completion plugin


**init_options** - [vcon.filter_plugins.impl.openai.OpenAIChatCompletionInitOptions](#vconfilter_pluginsimplopenaiopenaichatcompletioninitoptions)

### OpenAIChatCompletion.filter
filter(self, in_vcon: vcon.Vcon, options: vcon.filter_plugins.impl.openai.OpenAIChatCompletionOptions) -> vcon.Vcon


Perform generative AI using **OpenAI** chat completion on the
text **dialogs** and/or transcription **analysis** objects
in the given **Vcon** using the given **options.prompt**.

Parameters:
  options (OpenAICompletionOptions)

Returns:
  the modified Vcon with a single analysis object added in total
  for all of the text dialogs and transcription analysis object
  analysed.


**options** - [vcon.filter_plugins.impl.openai.OpenAIChatCompletionOptions](#vconfilter_pluginsimplopenaiopenaichatcompletionoptions)

### OpenAIChatCompletion.\_\_del__
\_\_del__(self)


Teardown/uninitialization method for the plugin

Parameters: None



## vcon.filter_plugins.impl.openai.OpenAICompletion

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
  
  

**Methods**:

### OpenAICompletion.\_\_init__
\_\_init__(self, init_options: vcon.filter_plugins.impl.openai.OpenAICompletionInitOptions)

Parameters:
  init_options (OpenAICompletionInitOptions) - the initialization options for the **OpenAI** completion plugin


**init_options** - [vcon.filter_plugins.impl.openai.OpenAICompletionInitOptions](#vconfilter_pluginsimplopenaiopenaicompletioninitoptions)

### OpenAICompletion.filter
filter(self, in_vcon: vcon.Vcon, options: vcon.filter_plugins.impl.openai.OpenAICompletionOptions) -> vcon.Vcon


Perform generative AI using **OpenAI** completion on the
text **dialogs** and/or transcription **analysis** objects
in the given **Vcon** using the given **options.prompt**.

Parameters:
  options (OpenAICompletionOptions)

Returns:
  the modified Vcon with added analysis objects for the text dialogs and transcription analysis.


**options** - [vcon.filter_plugins.impl.openai.OpenAICompletionOptions](#vconfilter_pluginsimplopenaiopenaicompletionoptions)

### OpenAICompletion.\_\_del__
\_\_del__(self)


Teardown/uninitialization method for the plugin

Parameters: None



## vcon.filter_plugins.impl.whisper.Whisper

  **FilterPlugin** to generate transcriptions for a **Vcon**
  

**Methods**:

### Whisper.\_\_init__
\_\_init__(self, init_options: vcon.filter_plugins.impl.whisper.WhisperInitOptions)

Parameters:
  init_options (WhisperInitOptions) - the initialization options for the Whisper trascription plugin


**init_options** - [vcon.filter_plugins.impl.whisper.WhisperInitOptions](#vconfilter_pluginsimplwhisperwhisperinitoptions)

### Whisper.filter
filter(self, in_vcon: vcon.Vcon, options: vcon.filter_plugins.impl.whisper.WhisperOptions) -> vcon.Vcon


Transcribe recording dialogs in given Vcon using the Whisper implementation

Parameters:
  options (WhisperOptions)

  options.output_types List[str] - list of output types to generate.  Current set
  of value supported are:

   * "vendor" - add the Whisper specific JSON format transcript as an analysis object
   * "word_srt" - add a .srt file with timing on a word or small phrase basis as an analysis object
   * "word_ass" - add a .ass file with sentence and highlighted word timeing as an analysis object

  Not specifing "output_type" assumes all of the above will be output, each as a separate analysis object.

Returns:
  the modified Vcon with added analysis objects for the transcription.


**options** - [vcon.filter_plugins.impl.whisper.WhisperOptions](#vconfilter_pluginsimplwhisperwhisperoptions)

### Whisper.\_\_del__
\_\_del__(self)


Teardown/uninitialization method for the plugin

Parameters: None




# Filter Plugin Initialization Options Classes


## vcon.filter_plugins.FilterPluginInitOptions
 - FilterPluginInitOptions

base class for **FilterPlugin** initialization options 

#### Fields:
None

## vcon.filter_plugins.impl.deepgram.DeepgramInitOptions
 - Deepgram transcription **FilterPlugin** intialization object

A **DeepgramInitOptions** object is provided to the
**Deepgram FilterPlugin.__init__** method when it is first loaded.  Its
attributes effect how the registered **FilterPlugin** functions.

#### Fields:

##### deepgram_key (str)
**Deepgram** API key

The **deepgram_key** is used to access the Deepgram RESTful transcription service.
It is required to use this **FilterPlugin**.

You can get one at: https://console.deepgram.com/signup?jump=keys


example: 123456789e96a1da774e57abcdefghijklmnop

default: ""

## vcon.filter_plugins.impl.openai.OpenAIChatCompletionInitOptions
 - OpenAI/ChatGPT Chat Completion **FilterPlugin** intialization object

A **OpenAIInitOptions** object is provided to the
**OpenAI FilterPlugin.__init__** method when it is first loaded.  Its
attributes effect how the registered **FilterPlugin** functions.

#### Fields:

##### openai_api_key (str)
**OpenAI** API key

The **openai_api_key** is used to access the OpenAI RESTful service.
It is required to use this **FilterPlugin**.

You can get one at: https://platform.openai.com/account/api-keys


example: sk-cABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstu

default: None

## vcon.filter_plugins.impl.openai.OpenAICompletionInitOptions
 - OpenAI/ChatGPT Completion **FilterPlugin** intialization object

A **OpenAIInitOptions** object is provided to the
**OpenAI FilterPlugin.__init__** method when it is first loaded.  Its
attributes effect how the registered **FilterPlugin** functions.

#### Fields:

##### openai_api_key (str)
**OpenAI** API key

The **openai_api_key** is used to access the OpenAI RESTful service.
It is required to use this **FilterPlugin**.

You can get one at: https://platform.openai.com/account/api-keys


example: sk-cABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstu

default: None

## vcon.filter_plugins.impl.whisper.WhisperInitOptions
 - Whisper **FilterPlugin** intialization object

A **WhisperInitOptions** object is provided to the
**Whisper FilterPlugin.__init__** method when it is first loaded.  Its
attributes effect how the registered **FilterPlugin** functions.

#### Fields:

##### model_size (str)
**Whisper** model size name

Model size name to use for transcription", (e.g. "tiny", "base") as defined on
https://github.com/openai/whisper#available-models-and-languages


examples: ['tiny', 'base']

default: "base"


# Filter Plugin Options Classes


## vcon.filter_plugins.FilterPluginOptions
 - FilterPluginOptions

base class for **FilterPlugin.filter** method options 

#### Fields:
None

## vcon.filter_plugins.impl.deepgram.DeepgramOptions
 - Deepgram transcription filter method options

Options for transcribing the recording **dialog** objects using
Deepgram transcription service.  The resulting transcription(s)
are added as transcript **analysis** objects in this **Vcon**

More details on the OpenAI specific parameters can be found here:
https://developers.deepgram.com/reference/pre-recorded

#### Fields:

##### language (str)
transcription language
None

example: 

default: "en"

##### input_dialogs (typing.Union[str, typing.List[int]])
input **Vcon** recording **dialog** objects

Indicates which recording **dialog** objects in the given **Vcon** are
to be transcribed.

 * **""** (empty str or None) - all recording **dialogs** are to be transcribed.  This is the equivalent of providing "0:".
 * **n:m** (str) - **dialog** objects having indices **n-m** are to be transcribed.
 * **n:m:i** (str) - **dialog** objects having indices **n-m** using interval **i** are to be transcribed.
 * **[]** (empty list[int]) - none of the **dialog** objects are to be transcribed.
 * **[1, 4, 5, 9]** (list[int]) - the **dialog** objects having the indices in the given list are to be transcribed.

**dialog** objects in the given sequence or list which are not **recording** type dialogs are ignored.


examples: ['', '0:', '0:-2', '2:5', '0:6:2', [], [1, 4, 5, 9]]

default: 

## vcon.filter_plugins.impl.openai.OpenAIChatCompletionOptions
 - OpenAI Chat Completion filter method options

Options for generative AI using **OpenAI** completion (e.g. ChatGPT)
on the text dialogs and/or transcription analysis in the given
**Vcon**

More details on the OpenAI specific parameters can be found here:
https://platform.openai.com/docs/api-reference/completions/create

#### Fields:

##### input_dialogs (typing.Union[str, typing.List[int]])
input **Vcon** text **dialog** objects

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


examples: ['', '0:', '0:-2', '2:5', '0:6:2', [], [1, 4, 5, 9]]

default: 

##### model (str)
**OpenAI** model name to use for generative AI

The named model is used to feed the transcription/text and then ask it the
given prompt.
OpenAI has numerous trained models, the latest of which may not be listed here
in examples.

You can get the current list of of available models for
your license/API key using the following:

    import openai
    openai.api_key = "your key here"
    openai.Model.list()


examples: ['davinci', 'gpt-4', 'text-davinci-001', 'text-search-curie-query-001', 'gpt-3.5-turbo', 'gpt-4-0613', 'babbage', 'text-babbage-001', 'curie-instruct-beta', 'davinci-similarity', 'code-davinci-edit-001', 'text-similarity-curie-001', 'ada-code-search-text', 'gpt-3.5-turbo-0613', 'text-search-ada-query-001', 'gpt-3.5-turbo-16k-0613', 'gpt-4-0314', 'babbage-search-query', 'ada-similarity', 'text-curie-001', 'gpt-3.5-turbo-16k', 'text-search-ada-doc-001', 'text-search-babbage-query-001', 'code-search-ada-code-001', 'curie-search-document', 'davinci-002', 'text-search-davinci-query-001', 'text-search-curie-doc-001', 'babbage-search-document', 'babbage-002', 'babbage-code-search-text', 'text-embedding-ada-002', 'davinci-instruct-beta', 'davinci-search-query', 'text-similarity-babbage-001', 'text-davinci-002', 'code-search-babbage-text-001', 'text-davinci-003', 'text-search-davinci-doc-001', 'code-search-ada-text-001', 'ada-search-query', 'text-similarity-ada-001', 'ada-code-search-code', 'whisper-1', 'text-davinci-edit-001', 'davinci-search-document', 'curie-search-query', 'babbage-similarity', 'ada', 'ada-search-document', 'text-ada-001', 'text-similarity-davinci-001', 'curie-similarity', 'babbage-code-search-code', 'code-search-babbage-code-001', 'text-search-babbage-doc-001', 'gpt-3.5-turbo-0301', 'curie']

default: "gpt-4"

##### prompt (str)
the prompt or question to ask about the transcription/text

The **OpenAI** model is given text from the dialog and
given this prompt to instruct it what generative AI text
that you would like from it.


example: 

default: "Summarize the transcript in these messages."

##### max_tokens (int)
maximum number of tokens of output

The **max_tokens** limits the size of the output generative AI text.
A token is approximately a syllable.  On average a word is 1.33 tokens.


example: 

default: 100

##### temperature (float)
**OpenAI** sampling temperature

lower number is more deterministic, higher is more random.

values should range from 0.0 to 2.0


example: 

default: 0.0

##### jq_result (str)
**jq** query of result

The **OpenAI** completion outputs a JSON 
[Completion Object](https://platform.openai.com/docs/api-reference/completions/object)

The **jq_results** string contains a **jq**  filter/query string that
is applied to the output to determine what is saved in the
created **Vcon** **analysis** object.

* **"."** - results in a query that returns the entire JSON object.
* **".choices[0].text"** - results in a query which contains only the text portion of the completion output

For more information on creating **jq filters** see:
https://jqlang.github.io/jq/manual/



examples: ['.', '.choices[0].text']

default: ".choices[0].message.content"

##### analysis_type (str)
the **Vcon analysis** object type

The results of the completion are saved in a new **analysis**
object which is added to the input **Vcon**.
**analysis_type** is the **analysis** type token that is set
on the new **analysis** object in the **Vcon**.


example: 

default: "summary"

## vcon.filter_plugins.impl.openai.OpenAICompletionOptions
 - OpenAI Completion filter method options

Options for generative AI using **OpenAI** completion (e.g. ChatGPT)
on the text dialogs and/or transcription analysis in the given
**Vcon**

More details on the OpenAI specific parameters can be found here:
https://platform.openai.com/docs/api-reference/completions/create

#### Fields:

##### input_dialogs (typing.Union[str, typing.List[int]])
input **Vcon** text **dialog** objects

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


examples: ['', '0:', '0:-2', '2:5', '0:6:2', [], [1, 4, 5, 9]]

default: 

##### model (str)
**OpenAI** model name to use for generative AI

The named model is used to feed the transcription/text and then ask it the
given prompt.
OpenAI has numerous trained models, the latest of which may not be listed here
in examples.

You can get the current list of of available models for
your license/API key using the following:

    import openai
    openai.api_key = "your key here"
    openai.Model.list()


examples: ['davinci', 'gpt-4', 'text-davinci-001', 'text-search-curie-query-001', 'gpt-3.5-turbo', 'gpt-4-0613', 'babbage', 'text-babbage-001', 'curie-instruct-beta', 'davinci-similarity', 'code-davinci-edit-001', 'text-similarity-curie-001', 'ada-code-search-text', 'gpt-3.5-turbo-0613', 'text-search-ada-query-001', 'gpt-3.5-turbo-16k-0613', 'gpt-4-0314', 'babbage-search-query', 'ada-similarity', 'text-curie-001', 'gpt-3.5-turbo-16k', 'text-search-ada-doc-001', 'text-search-babbage-query-001', 'code-search-ada-code-001', 'curie-search-document', 'davinci-002', 'text-search-davinci-query-001', 'text-search-curie-doc-001', 'babbage-search-document', 'babbage-002', 'babbage-code-search-text', 'text-embedding-ada-002', 'davinci-instruct-beta', 'davinci-search-query', 'text-similarity-babbage-001', 'text-davinci-002', 'code-search-babbage-text-001', 'text-davinci-003', 'text-search-davinci-doc-001', 'code-search-ada-text-001', 'ada-search-query', 'text-similarity-ada-001', 'ada-code-search-code', 'whisper-1', 'text-davinci-edit-001', 'davinci-search-document', 'curie-search-query', 'babbage-similarity', 'ada', 'ada-search-document', 'text-ada-001', 'text-similarity-davinci-001', 'curie-similarity', 'babbage-code-search-code', 'code-search-babbage-code-001', 'text-search-babbage-doc-001', 'gpt-3.5-turbo-0301', 'curie']

default: "text-davinci-003"

##### prompt (str)
the prompt or question to ask about the transcription/text

The **OpenAI** model is given text from the dialog and
given this prompt to instruct it what generative AI text
that you would like from it.


example: 

default: "Summarize this conversation: "

##### max_tokens (int)
maximum number of tokens of output

The **max_tokens** limits the size of the output generative AI text.
A token is approximately a syllable.  On average a word is 1.33 tokens.


example: 

default: 100

##### temperature (float)
**OpenAI** sampling temperature

lower number is more deterministic, higher is more random.

values should range from 0.0 to 2.0


example: 

default: 0.0

##### jq_result (str)
**jq** query of result

The **OpenAI** completion outputs a JSON 
[Completion Object](https://platform.openai.com/docs/api-reference/completions/object)

The **jq_results** string contains a **jq**  filter/query string that
is applied to the output to determine what is saved in the
created **Vcon** **analysis** object.

* **"."** - results in a query that returns the entire JSON object.
* **".choices[0].text"** - results in a query which contains only the text portion of the completion output

For more information on creating **jq filters** see:
https://jqlang.github.io/jq/manual/



examples: ['.', '.choices[0].text']

default: ".choices[0].text"

##### analysis_type (str)
the **Vcon analysis** object type

The results of the completion are saved in a new **analysis**
object which is added to the input **Vcon**.
**analysis_type** is the **analysis** type token that is set
on the new **analysis** object in the **Vcon**.


example: 

default: "summary"

## vcon.filter_plugins.impl.whisper.WhisperOptions
 - WhisperOptions

Options for transcribing the one or all dialogs in a **Vcon** using the **OpenAI Whisper** implementation.

#### Fields:

##### language (str)
transcription language
None

example: 

default: "en"

##### input_dialogs (typing.Union[str, typing.List[int]])
input **Vcon** recording **dialog** objects

Indicates which recording **dialog** objects in the given **Vcon** are
to be transcribed.

 * **""** (empty str or None) - all recording **dialogs** are to be transcribed.  This is the equivalent of providing "0:".
 * **n:m** (str) - **dialog** objects having indices **n-m** are to be transcribed.
 * **n:m:i** (str) - **dialog** objects having indices **n-m** using interval **i** are to be transcribed.
 * **[]** (empty list[int]) - none of the **dialog** objects are to be transcribed.
 * **[1, 4, 5, 9]** (list[int]) - the **dialog** objects having the indices in the given list are to be transcribed.

**dialog** objects in the given sequence or list which are not **recording** type dialogs are ignored.


examples: ['', '0:', '0:-2', '2:5', '0:6:2', [], [1, 4, 5, 9]]

default: 

##### output_types (typing.List[str])
transcription output types

List of output types to generate.  Current set of value supported are:

  * "vendor" - add the Whisper specific JSON format transcript as an analysis object
  * "word_srt" - add a .srt file with timing on a word or small phrase basis as an analysis object
  * "word_ass" - add a .ass file with sentence and highlighted word timeing as an analysis object
       Not specifing "output_type" assumes all of the above will be output, each as a separate analysis object.


example: 

default: ['vendor', 'word_srt', 'word_ass']


