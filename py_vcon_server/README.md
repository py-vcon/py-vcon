# The py_vcon_server Python Package

## Python Packages:
![vcon package name](https://img.shields.io/badge/pip_install-python__vcon-blue)
![python_vcon PyPI Version](https://img.shields.io/pypi/v/python_vcon.svg)
[![vcon unit tests](https://github.com/py-vcon/py-vcon/actions/workflows/python-test.yml/badge.svg?branch=main&python-version=3)](https://github.com/py-vcon/py-vcon/actions)

![vcon server package name](https://img.shields.io/badge/pip_install-py__vcon__server-blue)
![python_vcon PyPI Version](https://img.shields.io/pypi/v/py_vcon_server.svg)
[![vcon server unit tests](https://github.com/py-vcon/py-vcon/actions/workflows/python-server-test.yml/badge.svg?branch=main)](https://github.com/py-vcon/py-vcon/actions)

![Python 3.6](https://img.shields.io/badge/python-3.8-blue.svg)
![Python 3.6](https://img.shields.io/badge/python-3.9-blue.svg)
![Python 3.6](https://img.shields.io/badge/python-3.10-blue.svg)


The following is an overview of the Python vCon Server, architecture, components, configuration and use.
The documentation on this page assumes the reader has a rough understanding of what a vCon is and what you can do with them at least at a high level.
If that is not the case, you may want to start with [what is a vCon](../README.md#what-is-a-vcon).


## Table of Contents

  + [Overview of vCon Server](#overview-of-vcon-server)
  + [Terms](#terms)
  + [Architecture](#architecture)
  + [RESTful API Documentation](#restful-api-documentation)
    + [Admin RESTful API](#admin-restful-api)
    + [vCon RESTful API](#vcon-restful-api)
  + [Pipeline Processing](#pipeline-processing)
    + [Simple Pipeline Example](#simple-pipeline-example)
    + [Advanced Pipeline Example](#advanced-pipeline-example)
  + [vCon Processor Plugins](#vcon-processor-plugins)
  + [Access Control](#access-control)
  + [Building](#building)
  + [Environmental Variables](#environmental-variables)
  + [Installing and configuring](#installing-and-configuring)
  + [First Steps](#first-steps)
  + [Testing the vCon server](#testing-the-vcon-server)
  + [Future Release Features](#future-release-features)
  + [Extending the vCon Server](#extending-the-vcon-server)
  + [Support](#support)


## Overview of vCon Server

The Python vCon Server provides the ability to do the following:
  * Store, retrieve, modify and delete vCons
  * Perform operations on one or more vCons using a pluggable framework of **vCon processors**
  * Run a single **vCon processor** via a RESTful API, using provided or stored vCons
  * Group a sequence of vCon operations (**vCon processors** to execute) and associated configuration into a **Pipeline** definition
  * Run a **vCon pipeline**, via a RESTful API, using provide or stored vCons
  * Queue vCon jobs for the **pipeline server** to run through **vCon pipelines**
  * Administer and monitor the server and configuration via an Admin RESTful API


The Python vCon server an be thought of as the aggregation of the following high level components:
  * [vCon RESTful API](#vcon-restful-api)
  * vCon Pipeline Server
  * [vCon Processor Plugin Framework](#vcon-processor-plugins)
  * [Admin RESTful API](#admin-restful-api)
  * Plugable DB Interfaces


## Terms
 * **vCon processor** - a **VconProcessor** is an abstract interface for plugins to process or perform operations on one or more vCons.  A **VconProcessor** takes a **ProcessorIO** object and **ProcessorOptions** as input and returns a **VconProcessor** as output.  The **VconProcessor** contains or references the vCons for the input or output to the **VconProcessor**.
 * **pipeline** - a **VconPipeline** is an ordered set of operations or **VconProcessors** and their **ProcessorOptions** to be performed on the one or more vCons contained in a **ProcessorIO**.  The definition of a **VconProcessor** (its **PipelineOptions** and the list of names of **VconProcessors** and their input **ProcessorOptions**) is saved using a unique name in the **PipelineDB**.  A **ProcessorIO** is provided as input to the first **VconProcessor** in the **VconPipeline**, its output **ProcessorIO** is then passed as input to the next **VconProcessor** in the **VconPipeline**, continuing to the end of the list of **VconProcessors** in the **VconPipeline**.  A **VconPipeline** can be run either directly via the **vCon RESTful API** or in the **Pipeline Server**.
 * **pipeline server** - the pipeline server runs **VconPipeline**s in batch.  Jobs to be run through a **VconPipeline** are added to a **JobQueue** via the **vCon RESTful API**.  The pipeline server is configured with a set of queues to tend.   The pipeline server pulls jobs one at time from the **JobQueue**, retrieves the definition for the **VconPipeline** for that **JobQueue** and assigns the job and **VconPipeline** to a pipeline worker (OS process) to run the pipeline and its processors and optionally commit the result in the **VconStorage** after successfully running all of the pipeline processors.
 * **queue job** - a queue job is the definition of a job to run in a **Pipeline Server**.  It is typically a list of one or more references (vCon UUID) to vCon to be used as input to the beginning of the set of **VconProcessors** in a **VconPipeline**.
 * **job queue** - short for **pipeline job queue**
 * **pileline job queue** - a queue of jobs to be run on the **pipeline server**.  The job to be run, is defined by the **pipeline definition** having the same name as the **job queue**.
 * **in progress jobs** - the **pipeline server** pops a job out of the the **pipeline job queue** to dispatch it to a worker to process the **pipeline definition**.  While the worker is working on the pipeline, the job is put into the **in process jobs** list.  After the job is completed, the job is then removed from the **in process jobs** list.  If the job was canceled, the job is pushed back to the front of the job queue from which it was removed.  If the job failed, the job is added to the failure queue if provided in the pipeline definition.
 * **pipeline worker** - thread or process in which the pipeline job is run.
 * **job scheduler** - dispatcher that pulls jobs to be run on a server and assigns the job to a pipeline worker.
 * **job** - short for **pipeline queue job**
 * **processor** - short for vCon processor
 * **queue** - short for job queue
 * **worker** - short for pipeline worker

    
## Architecture
![Architecture Diagram](docs/Py_vCon_Server_Architecture.png)

The North facing interfaces provide the [vCon RESTful APIs](#vcon-restful-api) which are entry points that perform [vCon CRUD](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/vCon%3A%20Storage%20CRUD) and operations on vCons using **processor** plugins and configured **pipelines** of processor operations.

The West facing interfaces provide the [Admin RESTful API](#admin-restful-api) which are entry points for administration, configuration and monitoring of the vCon server.

The South facing interfaces are pluggable [vCon processors](#vcon-processor-plugins) which perform operations on one or more vCon either as standalone functions or as wrappers to externally provided services.

![VconProcessor Diagram](docs/VconProcessor.png)

The East facing interfaces are pluggable interfaces to database services for:
  * vCon storage
  * vCon server state and configuration
  * vCon Job Queues and Job State
  * Pipeline definitions and configuration

At the core is the **Pipeline Server** which runs queued vCon jobs through the named [Pipeline](#pipeline-processing)
![PipelineServer Flow Diagram](docs/PipelineServerFlow.png)

Currently Redis is used for all of these database services.
The RESTful APIs are all built on FastAPI.
This initial release does not provide vCon locking.
This means that nothing prevents multiple servers or jobs from modifying the same vCon at the same time, resulting in lost data.

#### Next Release Focus

In the next release we will focus on the following high level components:
  * vCon locking
  * [Access Control](#access-control) Lists


## RESTful API Documentation
The full swagger documentation for all of the RESTful APIs provided by the Python vCon Server are available here: 
[RESTful/Swagger docs](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html)

## Admin RESTful API
The Admin RESTful APIs are provided for getting information about running servers, modifying configuration and system definitions.
These APIs are intended for administration and DevOps of the server.
They are organized in the following sections:

 * [Admin: Servers](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/Admin:%20Servers) -
for getting and setting server configuration and state

 * [Admin: Job Queues](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/Admin:%20Job%20Queues) -
for getting, setting, deleting and adding to **job queues**

* [Admin: Pipelines](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/Admin:%20Pipelines) -
for getting, updating and deleting **pipeline** definitions and configuration

 * [Admin: In Progress Jobs](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/Admin:%20In%20Progress%20Jobs) -
for getting, requeuing and deleting **in progress jobs**

## vCon RESTful API
The vCon RESTful APIs are the high level interface to the Python vCon Server, providing the ability to create and perform operations on vCons.
This the primary interface for users of the server, as opposed to administrators or DevOps.
They are organized in the following sections:

 * [vCon: Storage CRUD](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/vCon:%20Storage%20CRUD) -
for creating, updating, deleting, querying vCons in **VconStorage** and queuing **Pipeline Jobs** for vCons

 * [vCon: Processors](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/vCon:%20Processors) -
for running **vCon Processors** on vCons in **VconStorage**

 * [vCon: Pipelines](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/vCon:%20Pipelines) -
for running **Pipelines** on the given vCon or indicated vCon in **VconStorage**

## Pipeline Processing

A pipeline provides the means to run a sequence of **VconProcessors**.
This is useful as often we want to perform the same sets of operations on many different vCons.
A processor is given a **VconProcessorIO** object and a set of **VconProcessorOptions** for the specific processor type.
The processor provides a **VconProcessorIO** object as output.
The **VconProcessorIO** object may contain zero or more vCons and a set of parameters.
The processor may modify the vCon(s) and parameters from the input **VconProcessorIO** to create the **VconProcessorIO** output object.
A pipeline is provided an input **VconProcessorIO** which is passed, along with the processor options for the first processor configured in the pipeline's **processors** list.
The output from the first processor is then passed to the second processor configured in the pipeline definition's **processors** list along with it's processor options.
This process is repeated through the sequence of processors configured in the pipeline definition's **processors** list.

![vCon Pipeline Processing Diagram](docs/PipelineProcessing.png)

A pipeline definition is divided up into two high level objects.
The **pipeline_options** object which sets general overall options for the pipeline.
The **processors** object list, which defines which processors are to be run, in the give order and with the given processor specific options.

Pipeline definitions can be created and modified using the [Admin: Pipeline RESTful APIs](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/Admin%3A%20Pipelines)

![vCon PipelineDefinition Diagram](docs/PipelineDefinition.png)

A pipeline can be run one time using the [vCon: Pipelines RESTful API](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/vCon%3A%20Pipelines) or many jobs can be queued for the pipeline server to run through any of the defined pipelines using the [Admin: Job Queues RESTful API](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/Admin%3A%20Job%20Queues/add_queue_job_queue__name__put).

The **Pipeline Server** will:
  * automatically check for jobs in it's configured set of **Job Queues**
  * pull one job out of a queue at a time and assign it a job ID
  * put the job in the **In Progress** queue while it is being processed
  * run the job through the pipeline
  * optionally commit modified or newly created vCons
  * queue the job in the success or failure **Job Queues** if provided
  * remove the job from the **In Progress** queue
  * repeat the process for other jobs in the **Job Queues** that the **Pipeline Server(s)** is(are) configured to process 

A couple of key points to make here are:

  * a **Pipeline Server** will only look at **Job Queue(s)** that it is(are) configured to process
  * a **Pipeline Server** can be configured to process multiple **Job Queues** with weighted priorities
  * multiple **Pipeline Servers** can be run at the same time on the same or different machines and they can be configured to process the same or different **Job Queues**
  * a **Job Queue's** name implies the name of the **Pipeline Definition** that will be used for jobs in that queue
  * **In Progress** jobs have a job ID assigned and can be referenced by the job ID in the **In Progress Queue**, which is used for all **Pipeline Server** instances running

To run vCons through pipelines using the **Pipeline Server**, you need to do the following:

  1) Define a pipeline ([create a pipeline definition](#create-and-use-a-pipeline))
  2) Create a **Job Queue** with the same name as the pipeline ([create a job queue](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/Admin%3A%20Job%20Queues/create_new_job_queue_queue__name__post))
  3) Configure the **Pipeline Server** to process the job queue ([set pipeline server queue properties](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/Admin%3A%20Servers/set_server_queue_properties_server_queue__name__post))
  4) Add one or more jobs to the **Job Queue** ([add a job to job queue](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/Admin%3A%20Job%20Queues/add_queue_job_queue__name__put))

![vCon Pipeline Server Flow Diagram](docs/PipelineServerFlow.png)

### Simple Pipeline Example

Here is an example of a [simple 2 processor pipeline](#create-and-use-a-pipeline) which uses the deepgram processor to transcribe a recording which is saved as an analysis object and the openai_chat_completion to create a summary of the transcript which is saved a a second analysis object in the vCon.

### Advanced Pipeline Example

A more advanced example of a pipeline definition can be found at the following link:
[Advanced pipeline definition example](docs/email_meeting_notes_pipeline.json)

This pipeline is defined to run 6 processors on the vCon input.
It does the following:

  * run the deepgram transcription processor (line 9)
  * run the openai_chat_completion processor with default summary prompt (line 16)
  * run the openai_chat_completion processor with action items prompt (line 21)
  * run the openai_chat_completion processor with notes prompt (line 29)
  * run the openai_jq processor with queries on vCon (line 37)
  * run the send_email processor with parameters message content (line 50)

## vCon Processor Plugins

  [Processor plugin framework and plugin instances README](py_vcon_server/processor/README.md)

![VconProcessor Diagram](docs/VconProcessor.png)


## Access Control
We realize Access Control is an important aspect of the vCon Server.  The ACL capabilities of the vCon Server has been planned out and designed.  It will be implemented in the next release.

## Authentication and JWT

[Guide to authentication with FastAPI](https://dev.to/spaceofmiah/implementing-authorization-in-fastapi-a-step-by-step-guide-for-securing-your-web-applications-3b1l#:~:text=FastAPI%20has%20built%2Din%20support,resources%20or%20perform%20certain%20actions.)

## Building

Instructions for building the vCon server package can be found [here](BUILD.md)

## Testing the vCon Server

A suite of pytest unit tests exist for the server in: [tests](tests)

Running and testing the server requires a running instance of Redis [see](#installing-and-configuring)
Be sure to create and edit your server/.env file to reflect your Redis server address and port.
It can be generated like the following command line:

    cat <<EOF>testenv
    #!/usr/bin/sh
    export DEEPGRAM_KEY=ccccccccccccc
    export OPENAI_API_KEY=bbbbbbbbbbbbb
    export HOSTNAME=http://0.0.0.0:8000
    export VCON_STORAGE_URL=redis://<redis_host_ip>:6379
    export PYTHONPATH=.
    EOF

The unit tests for the server can be run using the following command in this directory:

    source testenv
    pytest -v -rP tests

## Environmental Variables
  +  **VCON_STORAGE_URL** - DB URL for vCon storage database (defaults to:"redis://localhost" )
  +  **QUEUE_DB_URL** - DB URL for Job Queue and job status database (defaults to: same value as VCON_STORAGE_URL)
  + **PIPELINE_DB_URL** - DB URL for Pipeline definition database (defaults to: same value as VCON_STORAGE_URL)
  + **STATE_DB_URL** - DB URL for Server State database (defaults to: same value as VCON_STORAGE_URL )
  + **REST_URL** - host and port on which to bind RESTful APIs (defaults to: "http://localhost:8000")
  + **LOG_LEVEL** - server logging level (defaults to: "DEBUG")
  + **LOGGING_CONFIG_FILE** -  (defaults to: "<install path>/logging.config")
  + **LAUNCH_VCON_API** -  Enable vCon RESTful APIs True/False(defaults to: True)
  + **LAUNCH_ADMIN_API** - Enable Admin RESTful APIs True/False (defaults to: True)
  + **WORK_QUEUES** -  List of job queues the pipeline server is to pull jobs from.
If no queue names are specified, the pipeline server will not run any jobs.
This list of queue names can be [added](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/Admin%3A%20Servers/set_server_queue_properties_server_queue__name__post) and [removed](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/Admin%3A%20Servers/delete_server_queue_server_queue__name__delete) on a live server using the [Admin Server set of RESTful API](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/Admin%3A%20Servers).
The environmental variable has the format of comma separated queue names, each with an optional colon separated weight integer.
The weight specifies the number of jobs to pull from the queue before iterating to the next queue.
Example: "a:4,b"
(defaults to: "")
  + **PLUGIN_PATHS** - comma separated list of absolute or relative path names from which to load plugin registrations ([filter_plugins](../README.md#adding-vcon-filter-plugins) or [vCon Processor](#extending-the-vcon-server)).
(defaults to: "")

## Installing and Configuring

The following installation and configuration instructions are intended for development and testing purposes only.
This is by no means instructions for a secure install.
These instructions are intended for a setup where the developer is running a Docker server on a local host.
It is most convenient to run two Docker containers, one for the Redis server and a second for the vCon server.
The vCon server requires some of the JSON commands in the Redis stack server.
The following instructions are for running the configuration with two Docker containers: one for the Redis server, one for the vCon server.

The following docker command will retrieve the Redis stack server image and run the container:

    docker run -d --name redis-stack-server -p 6379:6379 redis/redis-stack-server:latest

For developers, it may be useful to create a shell on the Redis server to use the Redis CLI.
The following will start a shell in the Docker container and start the Redis CLI:

    docker exec -it redis-stack-server /bin/bash
    redis-cli -h localhost -p 6379

The Redis server will be bound to to the Docker server host's network on the default Redis port (6379).

If you do not setup your Redis server in the above configuration, you will need to setup your environmental variables to indicate other wise with something like the following:

    VCON_STORAGE_URL=redis://<your_host>:<your_port>

For example:

    echo VCON_STORAGE_URL=redis://192.168.0.1:8765 >> testenv

The py_vcon_server can be run in another container or directly on the Docker server host.
This is a personal choice.
If you want to be able to run all of the unit tests and be able to take advantage of all of the vCon operations supported by the Python vCon and py_vcon_server packages, you will want to get API keys to use OpenAI and Deepgram services.
You can find [instructions on getting third party API keys here](../README.md#third-party-api-keys).

The network interface and port, upon which the vCon server Admin and vCon RESTful APIs, are exposed is configured with the REST_URL environment variable.

We run unit tests on Python 3.8, 3.9 and 3.10.
Other Python platforms are untested.

### Run py_vcon_server Package
Install the py_vcon_server package:

    pip3 install py_vcon_server

If you are running the vCon server directly from the package, setup your environment like the following:

    cat << EOF >> testenv
    export REST_URL="http://<your_host_ip>:8000"
    export OPENAI_API_KEY="your_openai_key_here"
    export DEEPGRAM_KEY="your_deepgram_api_key_here"
    EOF

To start the vCon server use the following commands:

    source testenv
    python3 -m py_vcon_server

### Run py_vcon_server From Cloned Repo
If you which to run the vCon server in a development mode, directly from the git clone, from the [py_vcon_server](.) directory, setup your environment variables using the following:

    cat << EOF >> testenv
    export PYTHONPATH="."
    export REST_URL="http://<your_host_ip>:8000"
    export OPENAI_API_KEY="your_openai_key_here"
    export DEEPGRAM_KEY="your_deepgram_api_key_here"
    EOF


To start the vCon server use the following commands:

    source testenv
    python3 -m py_vcon_server

The live swagger documentation for the RESTful APIs along with developer test UI is available at the following once the server is started:

    http://<your_host_ip>:8000/docs

Note: a static image of the swagger documentation (without developer test UI) can be viewed [here](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html).

## First Steps
   * [1. Installing and Configuring](#installing-and-configuring)
   * [2. Build a vCon](#build-a-vcon)
   * [3  Store a vCon on the server](#store-a-vcon-on-the-server)
   * [4. Process a vCon](#process-a-vcon)
   * [5. Create and Use a Pipeline](#create-and-use-a-pipeline)
   * [6. Create a Job Queue and Queue a Job](#create-a-job-queue-and-queue-a-job)

### Build a vCon

There are a number of ways that you can build a vCon:

  * Use the [Python vCon](../README.md#installing-py-vcon) package [Command Line Interface (CLI)](../vcon/bin/README.md) in a Linux shell

  For example to create a vCon with a single audio recording dialog with an external reference to the audio file:`

    wget https://github.com/py-vcon/py-vcon/blob/main/examples/agent_sample.wav?raw=true -O agent_sample.wav
    vcon -i b.vcon add ex-recording agent_sample.wav "2023-03-06T20:07:43+00:00" "[0,1]"  https://github.com/py-vcon/py-vcon/blob/main/examples/agent_sample.wav?raw=true


  * Use the [Python vCon](../README.md#installing-py-vcon) package [library](../vcon/README.md) and write some Python code to create your own vCon

  * Create your own JSON vCon by hand or using other tools

  * Use an [existing vCon](../tests/hello.vcon)

### Store a vCon on the server

There are a number of ways to put your vCon on the server and store it.
vCons are stored using it's UUID as the key.
To perform an operation on a stored vCon you will want to remember its UUID.
The following examples assume that your vcon is contained locally in a file call hello.vcon, your vCon server is configured to run the vCon RESTful API on the IP address: 192.168.0.2 and is bound to port 8000.
You will have to change the examples to your specifics.

* Use the **vcon** CLI:

      vcon -i hello.vcon -p 192.168.0.2 8000

* Use vCon server [POST /vcon entry point](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/Admin%3A%20Pipelines).
For test purposes, you can use the swagger documentation test interface:

    1) Go to http://192.168.0.2:8000/docs#/vCon%3A%20Storage%20CRUD/post_vcon_vcon_post
    2) Click the **Try it out** button
    3) Copy and paste your vCon into the **Request Body** field
    4) Click the **Execute** button

* Use **wget**:

      wget --method POST --header="Content-Type: application/json" --body-file=hello.vcon http://192.168.0.100:8000/vcon

* Use **curl**:

      curl -i -X POST http://192.168.0.100:8000/vcon -H "Content-Type: application/json" --data-binary "@hello.vcon"

Note: If you do not know the UUID for your vCon you can look at it in a text editor.
Alternatively, you can query the JSON vCon using the jq command:

    jq ".uuid" hello.vcon

### Process a vCon

Now that you have a vCon you can do something with it.
The py_vcon_server comes with a built in set of VconProcessor plugins that operate on vCons.
The processors are exposed via the vCon RESTful API.
The vCon Processor RESTful APIs require the vCon to be stored in in VconStorage in the server.
You can put your vCon in VconStorage by [posting it via the vCon RESTful API](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/vCon%3A%20Storage%20CRUD/post_vcon_vcon_post).
If your vCon contains or references a audio or video dialog, you might try the Whisper or Deepgram (requires API key from Deepgram) transcription processors as a first step.
If your vCon contains only text from email or messages, you might try the openai_chat_completion (requires API key from OpenAI) processor to produce a summary of the text.
Have a look at the [vCon Processor RESTful API Swagger documentation](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/vCon%3A%20Processors)

### Create and Use a Pipeline

In the prior step you performed a single operation or process on a vCon.
You can define a sequence of operations or processes to be performed on a vCon in what we call a Pipeline.
When we define a Pipeline, we name each of the Processors, in the order that they are to be performed, along with the options for each of the Processors in the sequence.
Here is a simple Pipeline definition.

    {
      "pipeline_options": {
        "save_vcons": true,
        "timeout": 10,
        "failure_queue": null,
        "success_queue": null
      },
      "processors": [
        {
          "processor_name": "deepgram",
          "processor_options": {
            "input_vcon_index": 0
          }
        },
        {
          "processor_name": "openai_chat_completion",
          "processor_options": {
            "input_vcon_index": 0
          }
        }
      ]
    }

It has two parts at the top level.
The pipeline_options and the processors sequence or list.
The pipeline_options apply to the whole Pileline.
The processors list defines the order of the processors to be run with the name of the processor and an optional set of options to provide when running that processor.
Pipelines are stored and modified using the [Admin RESTful API for Pilelines](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/Admin%3A%20Pipelines)
When you create a Pipeline, you assign it a unique name or key, that you use to refer to your Pipeline.
Now that you have created a Pipeline, you can test it out or push a single vCon through it using the [vCon Pipeline RESTful APIs](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/vCon%3A%20Pipelines)
You can use these RESTful APIs to run your vCon in VconStorage or provided as the body of your HTTP POST request through the Pipeline.

### Create a Job Queue and Queue a Job

Once you have tested your Pipeline line and are happy with its configuration, you may then want to run a bunch of vCons through it.
The py_vcon_server provides a job queuing capability for the Pipeline Server.
If you create a job queue with the same name as the Pipeline, jobs will be pulled from the queue one at a time and run through the Pipeline having the same name.
You create job queues using the [Admin Job Queue RESTful APIs](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/Admin%3A%20Job%20Queues).
You add jobs to the queue using the [PUT queue vCon Storage CRUD API](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/vCon%3A%20Storage%20CRUD/add_queue_job_queue__name__put).
The py_vcon_server Pipeline Server will not start processing the jobs in you queue, until you configure the server to look at your queue.
The Pipeline Server only looks at the queue names which you configure using the [Admin Server Queue RESTful APIs](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/Admin%3A%20Servers).

## Future Release Features

The following features are next to be implemented for the vCon server.
[Sponsor us](https://github.com/sponsors/py-vcon) if you would like this development to be sped up or have different priorities.

  * Transactional vCon locking to prevent multiple processors from modifying a vCon at the same time
  * vCon access control lists
  * Slack notification vCon processors
  * Resolution of the Python multiprocessing, asyncio and Redis bug
  * More vCon processor plugins

## Extending the Vcon Server

TODO:  Overview of extendable frameworks in the vCon server

![VconProcessor Diagram](docs/VconProcessor.png)

How to create new vCon processor plugins
  + [Example VconProcessor wrapper for Deepgram vCon FilterPlugin](py_vcon_server/processor/builtin/deepgram.py)
  + [Example registration for Deepgram VconProcessor](py_vcon_server/processor/deepgram.py)
  + [Abstract VconProcessor interface documentation](py_vcon_server/processor#py_vcon_serverprocessorvconprocessor)

Note: to load your proprietary vCon plugins, you need to add the path to your plugin registration to the [PLUGIN_PATHS environmental variable](#environmental-variables).
Plugins are only loaded upon startup.


![FilterPlugin Diagram](../docs/FilterPlugin.png)

[How to create new vCon filter plugins](../README.md#adding-vcon-filter-plugins)

Note: to load your proprietary filter_plugins, you need to add the path to your plugin registration to the [PLUGIN_PATHS environmental variable](#environmental-variables).
Plugins are only loaded upon startup.

How to bind a different backend DB
  + [Example Redis binding for VconStorage](py_vcon_server/db/redis/__init__.py)
  + [Example registration of Redis binding for VconStorage](py_vcon_server/db/redis_registration.py)

## Support

Commercial support for the py_vcon_server is available from [SIPez](http://www.sipez.com)

