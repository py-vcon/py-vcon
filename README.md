# The Repo for the python-vcon and py-vcon-server Projects

## Python Packages:
![vcon package name](https://img.shields.io/badge/pip_install-python__vcon-blue)
![python_vcon PyPI Version](https://img.shields.io/pypi/v/python_vcon.svg)
[![vcon unit tests](https://github.com/py-vcon/py-vcon/actions/workflows/python-test.yml/badge.svg?branch=main&python-version=3)](https://github.com/py-vcon/py-vcon/actions)
![Coverage Badge](coverage-badge.svg)

![vcon server package name](https://img.shields.io/badge/pip_install-py__vcon__server-blue)
![python_vcon PyPI Version](https://img.shields.io/pypi/v/py_vcon_server.svg)
[![vcon server unit tests](https://github.com/py-vcon/py-vcon/actions/workflows/python-server-test.yml/badge.svg?branch=main)](https://github.com/py-vcon/py-vcon/actions)
![Coverage Badge](py_vcon_server/coverage-badge.svg)

![Python 3.8](https://img.shields.io/badge/python-3.8-blue.svg)
![Python 3.9](https://img.shields.io/badge/python-3.9-blue.svg)
![Python 3.10](https://img.shields.io/badge/python-3.10-blue.svg)
![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)

## Introduction

We are working to make **vCon** a new IETF standard for containing conversational data.
**vCon** aims to unify and standardize how we handle data from diverse communication sources, making it easier to integrate and apply analysis, categorization, and decision-making to business conversations.

**Conversational data** may consist of the following components:
- **Metadata**: Information such as participants (parties), timestamps, context (who, what, when, where, how, why, etc.), and more.
- **Dialog**: The conversation exchange itself, in its original mode, whether text, audio, or video.
- **Attachments**: Related documents, such as presentations, images, contracts, and other files shared during the conversation.
- **Analysis**: Post-conversation insights, including transcriptions, translations, summaries, sentiment analysis, action items, and key takeaways.

The purpose of the **vCon standard** is to simplify the integration of communication platforms with post-conversation analysis services, enabling more efficient workflows for businesses.
By standardizing the format of conversational data, **vCon** allows seamless interaction with **AI-driven analysis** and decision-making tools, enhancing the value of the data for actionable insights.

With the **py-vcon** project, we are making it easier to extract, manage, and process conversation data from various sources, such as contact centers, phone applications, and video conferencing services.
The **py-vcon-server** package further extends this by offering a flexible and scalable server framework for processing and analyzing vCon conversations.

The goal is to provide a seamless way to use third-party SaaS offerings and integrate them into your workflows for advanced conversation analysis-whether it's for customer support, sales, or any communication-driven business process.

By adopting the **vCon** standard and utilizing the **py-vcon** tools, businesses can unlock the power of their conversational data and apply AI-driven workflows that automate tasks like categorization, sentiment analysis, and decision-making.

### Key Features of py-vcon and py-vcon-server:
- **Python Library**: Construct and operate on individual vCons using Python.
- **Command Line Interface**: Construct and operate on individual vCons in your favorite command shell.
- **Integration**: Leverage a pluggable framework for third-party analysis tools and services.
- **Extensibility**: Add custom processors to handle specific tasks related to your conversation data.
- **AI Workflows**: Automatically categorize, analyze, and process conversations using AI-driven pipelines.
- **Flexible API**: Interact with vCon conversations programmatically through RESTful APIs.
- **Scalability**: Easily scale your pipeline processing, from a single instance to thousands of servers.

We are committed to making **vCon** the go-to standard for conversational data and helping businesses optimize how they manage and analyze conversations at scale.

Want to learn more about vCon? see: [What is a vCon?](#what-is-a-vcon)

The py-vcon project provides open source solutions in the form of Python packages to help you work with vCon's.
Currently this consists of two primary Python packages:

 * The py-vcon Vcon package (py-vcon on pypi) provides
   * python [Vcon API](vcon/README.md) - for constructing and operating on Vcon objects
   * [command line interface](vcon/bin/README.md) - supporting piping of Vcon construction and operations
   * [Filter plugins](#vcon-filter-plugins) - to extend operations to perform on a Vcon

* The [py-vcon-server package](py_vcon_server/README.md) extends the **python-vcon** package to provide:

AI-driven workflows and decision-making for your business conversations, whether they originate from a call center, contact center, customer support, or your phone and video conferencing applications.
The server offers the following capabilities:

- **RESTful APIs** for seamless integration and interaction with your systems
- **Flexible Architecture** to adapt to various use cases and environments
- **Scalability** to scale from a single server to thousands of instances
- **Storage** abstraction, enabling support for your preferred database solution
- **Job Queuing** for efficiently processing vCon conversations through AI workflows, analysis, and decision-making
- **Pipelining** to define, name, and configure workflows for repetitive operations on vCon conversations
- **Extensible Modules** to add open-source or proprietary vCon processor operations, enhancing functionality

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

 * Read the [IETF vCon Container Internet Draft (standard work in process)](https://datatracker.ietf.org/doc/html/draft-ietf-vcon-vcon-container)
 * Participate in the [IETF vCon Working Group](https://datatracker.ietf.org/group/vcon/about/)
 * See the [Fall 2024 VON presentation by Dan Petrie: covering a quick overview of vCon, update on IETF status and introduction to py-vcon packages](http://sipez.com/Dan_Petrie_vCon_workshop_Fall_VON_2024.mp4)
 * See the [vCon presentation at the SIP Forum AI Summit](https://register.gotowebinar.com/register/408072084535831130)
 * Read the [IETF Contact Center Requirements draft proposal](https://datatracker.ietf.org/doc/draft-rosenberg-vcon-cc-usecases/)
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

    pip3 install python-vcon


  Note: we are nearing the end of life of Python 3.8 support.  You can still run python-vcon on 3.8 by doing the following:

    pip3 uninstall --yes cryptography
    pip3 install 'cryptography<45.0.0'

  python-jose version 3.5.x is not supported on Python 3.8.
  To avoid an undefined RAND_bytes exception, you need to hold back to Cryptograhy version 44.X.X.

## Vcon Filter Plugins

![FilterPlugin Diagram](docs/FilterPlugin.png)

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

A simple example filter_plugin and python build tree and setup.py file can be copied from [here](docs/example_filter_plugin_addon).
This build, allows you to create a python package that can be installed seperately and on top of python-vcon.

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

Example code:
  + [Example vCon FilterPlugin for Deepgram](vcon/filter_plugins/impl/deepgram.py)
  + [Example registration for Deepgram FilterPlugin](vcon/filter_plugins/deepgram.py)
  + [Abstract FilterPlugin interface documentation](vcon/filter_plugins#vconfilter_pluginsfilterplugin)

## Third Party API Keys
Some of the [Vcon Filter Plugins](#Vcon-filter-plugins) use third party provided functionality that require API keys to use or test the full functionality.
The current set of API keys are needed for:

  * Deepgram transcription ([Deepgram FilterPlugin](vcon/filter_plugins/README.md#vconfilter_pluginsimpldeepgramdeepgram)): DEEPGRAM_KEY
  <br>You can get a key at: https://console.deepgram.com/signup?jump=keys

  * OpenAI Generative AI ([OpenAICompletion](vcon/filter_plugins/README.md#vconfilter_pluginsimplopenaiopenaicompletion) and [OpenAIChatCompletion](vcon/filter_plugins/README.md#vconfilter_pluginsimplopenaiopenaichatcompletion) FilterPlugins): OPENAI_API_KEY
  <br>You can get a key at: https://platform.openai.com/account/api-keys

The easiest way to use these plugins is to set the keys as an environmental variable.  For example on linux bash shell"

    export DEEPGRAM_KEY="your Deepgram key here"
    export OPENAI_API_KEY="your OpenAI key here"

However you can also set these keys using init_options and filter options.

## Vcon Package Building and Testing

Instructions for building the Vcon package for pypi can be found [here](BUILD.md)

## Testing the Vcon Package
A suite of pytest unit tests exist for the Vcon package in: [tests](tests).
If you do not run the unit tests in this directory in a clone of the repo, you will need to copy the following directories from the repo in order to run the unit tests:

    mkdir  <your_test_directory>
    cp -r tests examples certs <your_test_directory>
    mkdir <your_test_directory>/py_vcon_server
    cp -r py_vcon_server/tests <your_test_directory>/py_vcon_server
    cp -r py_vcon_server/test_processors <your_test_directory>/py_vcon_server

These can be run using the following command in the current directory:

    cd  <your_test_directory>
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

