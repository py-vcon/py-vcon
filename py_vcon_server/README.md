# The py_vcon_server Python Package

Please pardon the roughness of content here.  We are still under construction.

The first release and documentation coming soon.

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
  + [vCon Processor Plugins](#vcon-processor-plugins)
  + [Access Control](#access-control)
  + [Building](#building)
  + [Installing and configuring](#installing-and-configuring)
  + [Testing the vCon server](#testing-the-vcon-server)
  + [Extending the vCon Server](#extending-the-vcon-server)
  + [Support](#support)


## Overview of vCon Server

The Python vCon Server provides the ability to do the following:
  * Store, retrieve, modify and delete vCons
  * Perform operations on one or more vCons using a plugable framework of **vCon processors**
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


    Components
      vCon RESTful API built on FASTapi
      Admin RESTful API built on FASTapi
      Pipeline Server

      Pluggable DB Interfaces
        VconStorage
        ServerState
        JobQueue
        PipelineDB
        
        PipelineIO
        Pipeline
        
      Processor Plugin Framework
        vCon Processor
  
      Concepts
        vCon locking
        ACL


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

## vCon Processor Plugins

    link to plugins directory README.md

    template for generated docs
      TOC
      iterate through processors and grab doc
      gather all init_options types and processor options types


## Access Control
We realize Access Control is an important aspect of the vCon Server.  The ACL capabilities of the vCon Server has been planned out and designed.  It will be implemented in the next release.

## Authentication and JWT

[Guide to authentication with fastAPI](https://dev.to/spaceofmiah/implementing-authorization-in-fastapi-a-step-by-step-guide-for-securing-your-web-applications-3b1l#:~:text=FastAPI%20has%20built%2Din%20support,resources%20or%20perform%20certain%20actions.)

## Building

## Testing the vCon Server

A suite of pytest unit tests exist for the server in: [tests](tests)

Running and testing the server requires a running instance of Redis.
Be sure to create and edit your server/.env file to reflect your Redis server address and port.
It can be generated like the following command line:

    cat <<EOF>.env
    #!/usr/bin/sh
    export DEEPGRAM_KEY=ccccccccccccc
    export OPENAI_API_KEY=bbbbbbbbbbbbb
    export HOSTNAME=http://0.0.0.0:8000
    export REDIS_URL=redis://172.17.0.4:6379
    EOF

The unit tests for the server can be run using the following command in this directory:

    source .env
    pytest -v -rP tests

## Installing and configuring
Redis server docker

server in docker or from shell
## Extending the Vcon Server

## Support

