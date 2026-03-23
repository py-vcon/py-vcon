# Setting Up a Claude Project for the py-vcon Repository

## Purpose

This document provides step-by-step instructions for setting up a Claude AI Project
pre-loaded with knowledge from the [py-vcon](https://github.com/py-vcon/py-vcon)
open source repository. This enables Claude to have deep context about the py-vcon
and py-vcon-server Python packages — their architecture, APIs, processors, pipelines,
filter plugins, and test patterns — so you can have productive development
conversations without repeatedly explaining the codebase.


## Prerequisites

- A Claude Pro, Team, or Enterprise account (Projects require a paid plan)


## Step 1: Create a New Claude Project

1. Go to [claude.ai](https://claude.ai)
2. In the left sidebar, click **Projects**
3. Click **Create Project**
4. Name it something descriptive (e.g. "py-vcon Development")
5. Optionally add a project description such as:
   > Development project for the py-vcon and py-vcon-server Python packages.
   > These implement the vCon standard for conversational data containers,
   > including a REST API server with pipeline processing, filter plugins,
   > and processor plugins.


## Step 2: Add Repository Files as Project Knowledge

1. In the project settings, click **Add Knowledge**
2. Select the option to add from a **GitHub repository**
3. Provide the repository URL: `https://github.com/py-vcon/py-vcon`
4. From the file browser, select the files listed below

The files are organized below by category. All paths are relative to the
repository root.


### Root Documentation

| File | Purpose |
|------|---------|
| `README.md` | Top-level project overview, installation, filter plugin docs, testing instructions |


### Core vcon Library (`vcon/`)

| File | Purpose |
|------|---------|
| `vcon/__init__.py` | Core Vcon class implementation — serialization, deserialization, state management |
| `vcon/README.md` | Auto-generated API documentation for all Vcon class methods |
| `vcon/filter_plugins/__init__.py` | FilterPlugin base classes, registry, and registration mechanism |
| `vcon/filter_plugins/README.md` | Auto-generated documentation for all filter plugins and their options |
| `vcon/filter_plugins/whisper.py` | Whisper transcription filter plugin registration and accessor |


### Server Package — Source (`py_vcon_server/`)

| File | Purpose |
|------|---------|
| `py_vcon_server/README.md` | Server architecture, configuration, RESTful APIs, pipeline processing, environment variables |
| `py_vcon_server/setup.py` | Package build configuration, dependencies, sub-packages |
| `py_vcon_server/py_vcon_server/pipeline.py` | Pipeline definitions, PipelineDb (Redis), pipeline server scheduling logic |
| `py_vcon_server/py_vcon_server/processor/__init__.py` | VconProcessor base classes, registry, FilterPluginProcessor wrapper |
| `py_vcon_server/py_vcon_server/processor/README.md` | Auto-generated documentation for all server processors and their options |
| `py_vcon_server/py_vcon_server/processor/whisper_base.py` | Whisper VconProcessor registration (base model) |
| `py_vcon_server/py_vcon_server/processor/builtin/deepgram.py` | Deepgram transcription VconProcessor binding |
| `py_vcon_server/py_vcon_server/processor/builtin/openai.py` | OpenAI chat completion VconProcessor binding |
| `py_vcon_server/py_vcon_server/processor/builtin/whisper.py` | Whisper transcription VconProcessor binding |


### Server Package — API Documentation (`py_vcon_server/docs/`)

| File | Purpose |
|------|---------|
| `py_vcon_server/docs/openapi.json` | Full OpenAPI 3.1 specification for all RESTful API endpoints |
| `py_vcon_server/docs/example_processor_addon/.gitignore` | Example processor addon package structure |

> **Note:** Do NOT include `py_vcon_server/docs/swagger-ui-bundle.js` — it is a
> large minified JavaScript file (the Swagger UI renderer) that provides no useful
> context for Claude and would waste knowledge capacity.


### Server Package — Tests (`py_vcon_server/tests/`)

| File | Purpose |
|------|---------|
| `py_vcon_server/tests/common_setup.py` | Shared test fixtures (party creation, inline audio vCon creation) |
| `py_vcon_server/tests/test_admin_api.py` | Tests for server state, queue config, job queue CRUD via REST API |
| `py_vcon_server/tests/test_encrypt_processor.py` | Tests for encrypt/decrypt/sign/verify processor pipeline |
| `py_vcon_server/tests/test_job_queue.py` | Tests for job queue operations, in-progress job management |
| `py_vcon_server/tests/test_pipeline.py` | Tests for pipeline object construction, pipeline DB operations |
| `py_vcon_server/tests/test_processor_jq.py` | Tests for the JQ query processor |
| `py_vcon_server/tests/test_redis_multiprocess.py` | Tests for Redis async connection behavior across forked processes |
| `py_vcon_server/tests/test_sign_processor.py` | Tests for JWS signing processor |
| `py_vcon_server/tests/test_vcon_conversions.py` | Tests for vCon format conversions (object, dict, JSON, UUID) |


## Step 3: Verify the Setup

After adding all files, you should have **24 files** loaded as Project Knowledge.
To verify the project is working:

1. Open a new conversation within the project
2. Ask a test question such as:
   - "What processors are available in the py-vcon-server?"
   - "How do I create a pipeline that transcribes audio and then summarizes it?"
   - "Explain the VconProcessor plugin architecture."
3. Claude should respond with specific, accurate details drawn from the project files


## Summary of Files

Below is the complete flat list of all 24 files for quick reference:

```
README.md
vcon/__init__.py
vcon/README.md
vcon/filter_plugins/__init__.py
vcon/filter_plugins/README.md
vcon/filter_plugins/whisper.py
py_vcon_server/README.md
py_vcon_server/setup.py
py_vcon_server/py_vcon_server/pipeline.py
py_vcon_server/py_vcon_server/processor/__init__.py
py_vcon_server/py_vcon_server/processor/README.md
py_vcon_server/py_vcon_server/processor/whisper_base.py
py_vcon_server/py_vcon_server/processor/builtin/deepgram.py
py_vcon_server/py_vcon_server/processor/builtin/openai.py
py_vcon_server/py_vcon_server/processor/builtin/whisper.py
py_vcon_server/docs/openapi.json
py_vcon_server/docs/example_processor_addon/.gitignore
py_vcon_server/tests/common_setup.py
py_vcon_server/tests/test_admin_api.py
py_vcon_server/tests/test_encrypt_processor.py
py_vcon_server/tests/test_job_queue.py
py_vcon_server/tests/test_pipeline.py
py_vcon_server/tests/test_processor_jq.py
py_vcon_server/tests/test_redis_multiprocess.py
py_vcon_server/tests/test_sign_processor.py
py_vcon_server/tests/test_vcon_conversions.py
```


## Notes

- The `openapi.json` file is large but very valuable — it gives Claude the complete
  API surface including all request/response schemas, endpoint descriptions, and
  processor option definitions.
- The test files provide Claude with concrete examples of how the code is exercised,
  which helps it generate accurate code suggestions and understand expected behavior.
- If you hit Project Knowledge size limits, prioritize the README files and
  `__init__.py` files first, then processor source, then tests, then `openapi.json`.
- Project Knowledge sourced from a GitHub repo is read-only context — Claude cannot
  modify these files, but it can reference them when answering questions or generating code.
