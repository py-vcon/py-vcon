# The Home Repo for vCons and the Conserver

## Introduction
vCons are PDFs for human conversations, defining them so they can be shared, analyzed and secured. The Conserver is a domain specific data platform based on vCons, converting the raw materials of recorded conversations into self-serve data sources for any team. The Conserver represents the most modern set of tools for data engineers to responsibly and scalably use customer conversations in data pipelines. 

The Vcon library consists of two primary components:

  * The Python Vcon package for constructing and operating on Vcon objects
  * The Conserver for storing, managing and manipulating Vcon objects and operation streams on Vcon objects

## Table of Contents

  + [Introduction to the py-vcon Project](#introduction-to-the-py-vcon-project)
  + [What is a vCon?](#what-is_a_vcon)
  + [vCon Presentations, Whitepapers and Tutorials](#vcon-presentations-whitepapers-and-tutorials)
  + [Vcon Package Scope](#vcon-package-scope)
  + [Vcon Server Package Scope](#vcon-server-package-scope)
  + [Vcon Package Documentation](#vcon-package-documentation)
  + [Vcon Filter Plugins](#vcon-filter-plugins)
  + [Adding Vcon Filter Plugins](#adding-vcon-filter-plugins)
  + [Third Party API Keys](#third-party-api-keys)
  + [Vcon Package Building and Testing](#vcon-package-building-and-testing)
  + [Testing the Vcon Package](#testing-the-vcon-package)
  + [Support](#Support)
  + [Contributing](#contributing)



## Introduction to the py-vcon Project

merge with Indroduction above????
Not familiar with what a vCon is? see ..

 * The py-vcon Vcon package provides
   * python API
   * command line interface

 * The py-vcon-server package provides
   *  RESTful API
   *  Storage
   *  Job Queuing
   *  Batching
   *  Pipelining

## What is a vCon?


## vCon Presentations, Whitepapers and Tutorials

 * Read the [IETF Contact Center Requirements draft proposal](https://datatracker.ietf.org/doc/draft-rosenberg-vcon-cc-usecases/)
 * Read the [IETF draft proposal](https://datatracker.ietf.org/doc/html/draft-petrie-vcon-01)
 * Read the [white paper](https://docs.google.com/document/d/1TV8j29knVoOJcZvMHVFDaan0OVfraH_-nrS5gW4-DEA/edit?usp=sharing)
 * See the [Birds of a Feather session at IETF 116, Yokohama](https://youtu.be/EF2OMbo6Qj4)
 * See the [presentation at TADSummit](https://youtu.be/ZBRJ6FcVblc)
 * See the [presentation at IETF](https://youtu.be/dJsPzZITr_g?t=243)
 * See the [presentation at IIT](https://youtu.be/s-pjgpBOQqc)
 * See the [key note proposal for vCons](https://blog.tadsummit.com/2021/12/08/strolid-keynote-vcons/).


## Vcon Package Scope

    link to Vcon doc
    link to vcon commandline doc
    link to jq doc

## Vcon Server Package Scope

    link to Vcon Server Architecture
    link to Vcon Server doc

## Vcon Package Documentation

  * [vCon Library Quick Start for Python](https://github.com/vcon-dev/vcon/wiki/Library-Quick-Start)

## Vcon Filter Plugins

    link to vcon/filter_plugins/README.md

## Adding Vcon Filter Plugins

## Third Party API Keys
Some of the [Vcon Filter Plugins](#Vcon-filter-plugins) use third party provided functionality that require API keys to use or test the full functionality.
The current set of API keys are needed for:

  * Deepgram transcription ([Deepgram FilterPlugin](vcon/filter_plugins/README.md#vconfilter_pluginsimpldeepgramdeepgram)): DEEPGRAM__KEY
  <br>You can get a key at: https://platform.openai.com/account/api-keys

  * OpenAI Generative AI ([OpenAICompletion](vcon/filter_plugins/README.md#vconfilter_pluginsimplopenaiopenaicompletion) and [OpenAIChatCompletion](vcon/filter_plugins/README.md#vconfilter_pluginsimplopenaiopenaichatcompletion) FilterPlugins): OPENAI_API_KEY
  <br>You can get a key at: https://console.deepgram.com/signup?jump=keys

## Vcon Package Building and Testing

## Testing the Vcon Package
A suite of pytest unit tests exist for the Vcon package in: [tests](tests).


These can be run using the following command in the current directory:

    export OPENAI_API_KEY="your_openai_api_key_here"
    export DEEPGRAM_KEY="your_deepgram_key_here"
    pytest -v -rP tests


Please also run separately the following unit test as it will check for spurious stdout from the Vcon package that will likely cause the CLI to break:

    pytest -v -rP tests/test_vcon_cli.py

Note: These errors may not show up when you run test_vcon_cli.py with the rest of the unit tests as some stdout may only occur when the Vcon package is first imported and may not get trapped/detected by other unit tests.


##  Support

## Contributing

