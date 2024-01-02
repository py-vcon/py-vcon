# The py_vcon_server Python Package

Please pardon the lack of content here.  We are still under construction.

The first release and documentation comming soon.

## Table of Contents

  + [Testing the vCon server](#testing-the-vcon-server)


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

## RESTful API Documentation
[RESTful/Swagger docs](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html)

## Admin RESTful API

[Admin: Servers](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/Admin:%20Servers)

[Admin: Job Queues](https://raw.githack.com/py-vcon/py-vcon/main/py_vcon_server/docs/swagger.html#/Admin:%20Job%20Queues)

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

## Testing the vCon Server

A suite of pytest unit tests exist for the server in: [tests](tests)

Running and testing the server requires a running instance of Redis.
Be sure to create and edit your server/.env file to reflect your redis server address and port.
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

## Extending the Vcon Server

## Support

