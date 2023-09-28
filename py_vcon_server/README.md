# The py_vcon_server Python Package

Please pardon the lack of content here.  We are still under construction.

The first release and documentation comming soon.

## Table of Contents

  + [Testing the conserver](#testing-the-conserver)


## Overview of server

## Terms  - overlay states as appropriate
    job
    job queue
    queue job
    server job queue
    in progress jobs
    pipeline
    vCon processor
    pipeline server
    pipeline worker
    processor - vCon processor
    worker

    
## Architecture
    Components
      VconStorage
      ServerState
      Admin RESTful API
      vCon RESTful API
      Pipeline Server
      PipelineIO
      Pipeline
      Acl
      JobQueue

## Configuration

redis server docker

server in docker or from shell
## Admin RESTful API

iterate entry points and gen doc from a template

## VCON RESTful API

iterate entry points and gen doc from a template

## Pipeline processing

## Vcon Server Processor Plugins

    link to plugins dir README.md

    template for generated docs
      TOC
      iterate through processors and grab doc
      gather all init_options types and processor options types


## Access control

## Authentication and JWT

## Building

## Testing the Vcon Server

A suite of pytest unit tests exist for the server in: [tests](tests)

Running and testing the conserver requires a running instance of Redis.
Be sure to create and edit your server/.env file to reflect your redis server address and port.
It can be generated like the following command line:

    cat <<EOF>.env
    #!/usr/bin/sh
    export DEEPGRAM_KEY=ccccccccccccc
    export OPENAI_API_KEY=bbbbbbbbbbbbb
    export HOSTNAME=http://0.0.0.0:8000
    export REDIS_URL=redis://172.17.0.4:6379
    EOF

The unit tests for the conserver can be run using the following command in this directory:

    source .env
    pytest -v -rP tests

## Installing and configuring

## Extending the Vcon Server

## Support

