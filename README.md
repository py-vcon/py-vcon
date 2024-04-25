# The Repo for the python-vcon and py-vcon-server Projects

## Introduction

We are working to make vCon a new IETF standard for containing conversational data.  Conversational data may consists of:
 * The metadata (who, what, when, where, how, why, etc.) including partipants or **parties**
 * The conversation exchange or **dialog** in its original mode (text, audio, video)
 * Related documents or **attachments** (e.g. presentations, images, contracts and other files)
 * **Analysis** (e.g. transcritpions, translations, summary, notes, sentiment analysis, action items, bullet points, etc.).

The point of a vCon standard is to make it easier to integrate communication platforms with post conversation analysis services.
We want to make it easier to take your converstation data from your contact center, phone application or video conferencing service and allow you use 3rd party SaaS offerings for conversation analysis.

Want to learn more about vCon? see: [What is a vCon?](#what-is-a-vcon)

The py-vcon project provides open source solutions in the form of Python packages to help you work with vCon's.
Currently this consists of two primary Python packages:

 * The py-vcon Vcon package (py-vcon on pypi) provides
   * python [Vcon API](vcon/README.md) - for constructing and operating on Vcon objects
   * [command line interface](vcon/bin/README.md) - supporting piping of Vcon construction and operations
   * [Filter plugins](#vcon-filter-plugins) - to extend operations to perform on a Vcon

 * The [py-vcon-server package](py_vcon_server/README.md) provides (release coming soon):
   * RESTful APIs
   * Flexible Architecture
   * Scales from 1 to 1000s of servers
   * Storage - abstracted to enable support for your favorite database
   * Job Queuing - for performing a sequence of processing operations on vCons
   * Pipelining - naming and configuring sequences of processor operations to repeatedly perform on vCons
   * Extensible modules - framework for adding open source or proprietary vCon processor operations


## Table of Contents

  + [Introduction](#introduction)
  + [What is a vCon?](#what-is-a-vcon)
  + [vCon Presentations, Whitepapers and Tutorials](#vcon-presentations-whitepapers-and-tutorials)
  + [Vcon Package Documentation](#vcon-package-documentation)
  + [Installing py-vcon](#installing-py-vcon)
  + [Vcon Filter Plugins](#vcon-filter-plugins)
  + [Adding Vcon Filter Plugins](#adding-vcon-filter-plugins)
  + [Third Party API Keys](#third-party-api-keys)
  + [Vcon Package Building and Testing](#vcon-package-building-and-testing)
  + [Testing the Vcon Package](#testing-the-vcon-package)
  + [Support](#Support)
  + [Contributing](#contributing)


## What is a vCon?

Here is a [quick overview](Vcon-Quick-Overview.md) of the different parts of a vCon.

### vCon Presentations, Whitepapers and Tutorials

 * Read the [IETF Contact Center Requirements draft proposal](https://datatracker.ietf.org/doc/draft-rosenberg-vcon-cc-usecases/)
 * Read the [IETF draft proposal](https://datatracker.ietf.org/doc/html/draft-petrie-vcon)
 * Participate in the [IETF vCon Working Group](https://datatracker.ietf.org/group/vcon/about/)
 * Read the [white paper](https://docs.google.com/document/d/1TV8j29knVoOJcZvMHVFDaan0OVfraH_-nrS5gW4-DEA/edit?usp=sharing)
 * See the [Birds of a Feather session at IETF 116, Yokohama](https://youtu.be/EF2OMbo6Qj4)
 * See the [presentation at TADSummit](https://youtu.be/ZBRJ6FcVblc)
 * See the [presentation at IETF](https://youtu.be/dJsPzZITr_g?t=243)
 * See the [presentation at IIT](https://youtu.be/s-pjgpBOQqc)
 * See the [key note proposal for vCons](https://blog.tadsummit.com/2021/12/08/strolid-keynote-vcons/).

## Vcon Package Documentation

  * [Vcon API](vcon/README.md) - for constructing and operating on Vcon objects
  * [command line interface](vcon/bin/README.md) - supporting piping of Vcon construction and operations
  * [Filter plugins](#vcon-filter-plugins) - to extend operations to perform on a Vcon
  * [vCon Library Quick Start for Python](Vcon-Quick-Start.md)

## Installing py-vcon

    pip install python-vcon

## Vcon Filter Plugins

![FilterPlugin Diagram](../docs/FilterPlugin.png)
[Filter plugins](vcon/filter_plugins/README.md) are plugin modules that perform some sort of operation on a Vcon.
They perform an operation on an input Vcon and provide a resulting Vcon as the output.
A FilterPlugin takes a set of options as input which have defaults, but may be overrided.
The py-vcon project comes with a set of FilterPlugins which will grow over time.
You can also create proprietary FilterPlugins which may be used with py-vcon.
FilterPlugins get registered with a unique name and a default set of options.
FilterPlugins can be invoked using the [Vcon.filter](vcon/README.md#filter) method or
invoked using the registered name as the method name with the signature:

    my_vcon.<registered_name>(options)

You can get the list of registered filter plugins using the following:

    import vcon
    vcon.filter_plugins.FilterPluginRegistry.get_names()

## Adding Vcon Filter Plugins

You can build your own FilterPlugins by extending the [FilterPlugin class](vcon/filter_plugins#vconfilter_pluginsfilterplugin).
You must implement the [filter method](vcon/filter_plugins#filterpluginfilter) and optionally implement the [__init__ method](vcon/filter_plugins#filterplugin__init__) or [__del__ method](vcon/filter_plugins#filterplugin__del__) if your plugin requires some initialization or teardown before it can be used.

If your custom FilterPlugin requires initialization options or options to be passed to the filter method, you must implement a derived class from [FilterPluginInitOptions](vcon/filter_plugins#vconfilter_pluginsfilterplugininitoptions) or [FilterPluginOptions](vcon/filter_plugins#vconfilter_pluginsfilterpluginoptions) respectively.

You can then register your custom vCon using the following code:

    vcon.filter_plugins.FilterPluginRegistrar.register(
        name: str,
        module_name: str,
        class_name: str,
        description: str,
        init_options: typing.Union[FilterPluginInitOptions, typing.Dict[str, typing.Any]],
        replace: bool = False
      ) -> None:

Register a named filter plugin.

Parameters:  
    **name** (str) - the name to register the plugin  
    **module_name** (str) - the module name to import where the plugin class is implmented  
    **class_name** (str) - the class name for the plugin implementation in the named module   
    **description** (str) - a text description of what the plugin does  
    **replace** (bool) - if True replace the already registered plugin of the same name  
                     if False throw an exception if a plugin of the same name is already register

Returns: none

## Third Party API Keys
Some of the [Vcon Filter Plugins](#Vcon-filter-plugins) use third party provided functionality that require API keys to use or test the full functionality.
The current set of API keys are needed for:

  * Deepgram transcription ([Deepgram FilterPlugin](vcon/filter_plugins/README.md#vconfilter_pluginsimpldeepgramdeepgram)): DEEPGRAM__KEY
  <br>You can get a key at: https://platform.openai.com/account/api-keys

  * OpenAI Generative AI ([OpenAICompletion](vcon/filter_plugins/README.md#vconfilter_pluginsimplopenaiopenaicompletion) and [OpenAIChatCompletion](vcon/filter_plugins/README.md#vconfilter_pluginsimplopenaiopenaichatcompletion) FilterPlugins): OPENAI_API_KEY
  <br>You can get a key at: https://console.deepgram.com/signup?jump=keys

The easiest way to use these plugins is to set the keys as an environmental variable.  For example on linux bash shell"

    export DEEPGRAM__KEY="your Deepgram key here"
    export OPENAI_API_KEY="your OpenAI key here"

However you can also set these keys using init_options and filter options.

## Vcon Package Building and Testing

Instructions for building the Vcon package for pypi can be found [here](BUILD.md)

## Testing the Vcon Package
A suite of pytest unit tests exist for the Vcon package in: [tests](tests).
If you do not run the unit tests in this directory in a clone of the repo, you will need to copy the following directories from the repo in order to run the unit tests:

    cp -r tests examples certs <your_test_directory>
    mkdir <your_test_directory>/py_vcon_server
    cp -r py_vcon_server/tests <your_test_directory>/py_vcon_server

These can be run using the following command in the current directory:

    export OPENAI_API_KEY="your_openai_api_key_here"
    export DEEPGRAM_KEY="your_deepgram_key_here"
    pytest -v -rP tests


Please also run separately the following unit test as it will check for spurious stdout from the Vcon package that will likely cause the CLI to break:

    pytest -v -rP tests/test_vcon_cli.py

Note: These errors may not show up when you run test_vcon_cli.py with the rest of the unit tests as some stdout may only occur when the Vcon package is first imported and may not get trapped/detected by other unit tests.


##  Support

The first lilne of support is to help yourself by reading the documentation and the code.
If this does not yeild results, submit an issue to the py-vcon project on github.
We will do our best to respond.
Commercial support is available from [SIPez](http://www.sipez.com).

## Contributing

We do our best to document our project and provide test coverage.
The code and documentation is not perfect and we do not have 100% test coverage.
We will strive to improve on all three fronts over time.
You can contribute by helping with any or all of this.
Submit a PR, we are happy to consider contributions.
It is expected that you will have run all unit tests for both the Vcon and Vcon Server projects before submitting the PR.
If you are submitting new code or fixes, you are expected to add new unit test cases to cover the fix or feature.
A fair amount of the documentation is generated from the Python docs, perhaps more in the future.
For this reason, any contibutions with additions or changed to APIs must document classes, methods and arguments with typing.
We are a small group supporting this project.
We cannot be sustainable without additional automated unit testing and documentation.
This serves you, in helping to be sure no one breaks your contribution, as well as the project.

