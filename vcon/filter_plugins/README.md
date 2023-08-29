
# Filter Plugins

## Table of Contents
 + [Introduction](#introduction)
 + [Filter Plugin Classes](filter-plugin-classes)
   - [vcon.filter_plugins.impl.whisper.Whisper](#vconfilter_pluginsimplwhisperwhisper)
   - [vcon.filter_plugins.FilterPlugin](#vconfilter_pluginsfilterplugin)
 + [Filter Plugin Initialization Options Classes](filter-plugin-initialization-options-classes)
   - [vcon.filter_plugins.FilterPluginInitOptions](#vconfilter_pluginsfilterplugininitoptions)
   - [vcon.filter_plugins.impl.whisper.WhisperInitOptions](#vconfilter_pluginsimplwhisperwhisperinitoptions)
 + [Filter Plugin Options Classes](filter-plugin-options-classes)
   - [vcon.filter_plugins.impl.whisper.WhisperOptions](#vconfilter_pluginsimplwhisperwhisperoptions)
   - [vcon.filter_plugins.FilterPluginOptions](#vconfilter_pluginsfilterpluginoptions)

## Introduction

TBD

# Filter Plugin Classes


## vcon.filter_plugins.impl.whisper.Whisper

  **FilterPlugin** to generate transcriptions for a **Vcon**
  

**Methods**:

### \_\_init__
\_\_init__(self, init_options: vcon.filter_plugins.impl.whisper.WhisperInitOptions)

Parameters:
  init_options (WhisperInitOptions) - the initialization options for the Whisper trascription plugin


**init_options** - [vcon.filter_plugins.impl.whisper.WhisperInitOptions](#vconfilter_pluginsimplwhisperwhisperinitoptions)

### filter(self, in_vcon: vcon.Vcon, options: vcon.filter_plugins.impl.whisper.WhisperOptions) -> vcon.Vcon


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

### \_\_del__(self)


Teardown/uninitialization method for the plugin

Parameters: None



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

### \_\_init__
\_\_init__(self, options: 'FilterPluginInitOptions', options_type: 'typing.Type[FilterPluginOptions]')

Instance stores the initialization options that were used.

Instance also stores the **FilterPluginOptions** type/class
that is used by the derived class's **filter** method.
This is used to enforce typing and defaults for the
options passed into the **filter** method.


**options** - [vcon.filter_plugins.FilterPluginInitOptions](#vconfilter_pluginsfilterplugininitoptions)

### filter(self, in_vcon: 'Vcon', options: 'FilterPluginOptions') -> 'Vcon'


Abstract method which performs an operation on an input Vcon and 
provides the modified Vcon as output.

Parameters:
  in_vcon (vcon.Vcon) - input Vcon upon which an operation is to be performed by the plugin.
  options (FilterPluginOptions) - derived options specific to the filter method/opearation

Returns:
  vcon.Vcon - the modified Vcon


**options** - [vcon.filter_plugins.FilterPluginOptions](#vconfilter_pluginsfilterpluginoptions)

### \_\_del__(self)


Teardown/uninitialization method for the plugin

Parameters: None




# Filter Plugin Initialization Options Classes


## vcon.filter_plugins.FilterPluginInitOptions
 - FilterPluginInitOptions

base class for **FilterPlugin** initialization options 

#### Fields:
None
## vcon.filter_plugins.impl.whisper.WhisperInitOptions
 - Whisper **FilterPlugin** intialization object

A **WhisperInitOptions** object is provided to the
**Whisper FilterPlugin.__init__** funcion when it is first loaded.  Its
attributes effect how the registered **FilterPlugin** functions.

#### Fields:

##### model_size (str)
**Whisper** model size name

Model size name to use for transcription", (e.g. "tiny", "base") as defined on
https://github.com/openai/whisper#available-models-and-languages

example: None
examples: ['tiny', 'base']
default: "base"


# Filter Plugin Options Classes


## vcon.filter_plugins.impl.whisper.WhisperOptions
 - WhisperOptions

Options for transcibing the one or all dialogs in a **Vcon** using the **OpenAI Whisper** implementation.

#### Fields:

##### language (str)
transcription language
None
example: None
examples: None
default: "en"

##### output_types (typing.List[str])
transcription output types

List of output types to generate.  Current set of value supported are:

  * "vendor" - add the Whisper specific JSON format transcript as an analysis object
  * "word_srt" - add a .srt file with timing on a word or small phrase basis as an analysis object
  * "word_ass" - add a .ass file with sentence and highlighted word timeing as an analysis object
       Not specifing "output_type" assumes all of the above will be output, each as a separate analysis object.

example: None
examples: None
default: ['vendor', 'word_srt', 'word_ass']

## vcon.filter_plugins.FilterPluginOptions
 - FilterPluginOptions

base class for **FilterPlugin.filter** method options 

#### Fields:
None

