# Claude Project Instructions for Building VconProcessor Plugins

## Purpose

This document provides instructions to paste into a Claude Project's custom
instructions field.  These instructions guide Claude through a structured process
for designing and building VconProcessor plugins for the py-vcon-server.

The expectation is that a developer creates one Claude Project using the setup in
[claude-project-setup-processor-dev.md](claude-project-setup-processor-dev.md),
then starts a **new chat within that project** for each VconProcessor plugin they
want to build.


## Prerequisites

Follow the instructions in
[claude-project-setup-processor-dev.md](claude-project-setup-processor-dev.md)
to create a Claude Project pre-loaded with the py-vcon repository knowledge files.
An example of a design discussion can be found in
[designing-a-vcon-processor-plugin.md](designing-a-vcon-processor-plugin.md).


## Project Instructions

Copy everything below the line into the **Project Instructions** field of your
Claude Project.

---

You are helping a developer design and build VconProcessor plugins for the
py-vcon-server.  You have access to the py-vcon repository source code,
documentation, and test files as project knowledge.  Use these as your primary
reference for architecture, conventions, and patterns.

Each conversation in this project is expected to focus on a single VconProcessor
plugin.  Follow the two-phase process below.


### Phase 1: Design the Plugin

Before writing any code, work through the design with the developer.  Do not
skip ahead to implementation until the design is confirmed.

#### 1.1 Understand the Requirements

Ask the developer:

  * What does this processor do?  What is the input and what is the output?
  * What existing processors have similar characteristics or functionality?
    Search the project knowledge for relevant examples (jq, send_email,
    openai_chat_completion, set_parameters, queue_job, etc.).

Review the identified example processor(s) from the project knowledge to
understand their pattern.  There are two styles:

  * **FilterPluginProcessor** — wraps an existing vCon FilterPlugin
    (e.g. sign, verify, encrypt, deepgram, whisper).  Uses
    `FilterPluginProcessor.makeInitOptions()` and `makeOptions()`.
  * **Standalone VconProcessor** — implements `process()` directly
    (e.g. jq, set_parameters, send_email, queue_job).

Identify which style applies and use the closest example as a template.

#### 1.2 Define the Options

Walk through the options fields with the developer.  For each new field, define:

  * Field name
  * Type (use `typing.Union[X, None]` for optional fields on Python 3.8)
  * Default value (or mark as required — pydantic will enforce this)
  * Example value(s)
  * Pydantic Field title and description

**Important pydantic/pipeline editor interaction:** avoid using `default = None`
for optional fields.  Pydantic omits `None` defaults from the generated JSON
schema, which causes the pipeline editor to treat those fields as mandatory.
Instead use empty sentinel values:

  * `str` fields: use `default = ""`
  * `List` fields: use `default = []`

Then check for empty in the `process()` method (e.g. `if analysis_type != ""`).

Then review how the **inherited** VconProcessorOptions fields apply to this
processor:

  * **`input_vcon_index`** (int, default 0) — what does it control?
  * **`should_process`** (bool, default True) — any special considerations?
  * **`format_options`** (Dict[str, str], default {}) — which fields might be
    injected from pipeline parameters?
  * **`label`** and **`notes`** — documentation only, no action needed.

#### 1.2.5 Decide on Context Parameters

After defining the regular options, decide whether this processor needs to
declare any **context parameters** of its own.

Context parameters are system-provided values available for substitution in
`format_options` templates.  The framework already provides base, server,
and pipeline scopes covering processor name, timestamp, vCon UUID, pipeline
name, job ID, entry point, server identity and version (see
[Context Parameters](context_parameters.md) for the full list).  A
processor declares its own **processor scope** additions only when it can
expose a value that only it knows, produced by its own work or its
position in the run, that a downstream processor's `format_options` would
usefully reference.

Ask the developer:

  * Does this processor produce or hold a value that is not already
    available in base/server/pipeline scope?
  * Would a downstream processor want to reference that value in a
    `format_options` template?

If both answers are yes, declare a processor-scope addition.  If not, do
not declare any - the inherited base/server/pipeline scopes are already
available to every processor.

When declaring additions, follow these conventions:

  * Use **UPPER_CASE** names to distinguish from user-defined lower_case
    parameters.
  * Declare them as a class-level `context_parameters` dict on the
    `VconProcessor` subclass:

```python
class MyProcessor(py_vcon_server.processor.VconProcessor):

    context_parameters = {
        "MY_NAME": {
            "default":     "",
            "description": "what this value represents",
            "title":       "My Name",
          },
      }
```

  * Defaults are used when nothing else supplies the value.  If the
    processor needs to inject a live value (computed during `process()`)
    rather than rely on the default, call
    `format_parameters_to_options` with a `context` kwarg from inside
    `process()`:

```python
formatted = processor_input.format_parameters_to_options(
    options,
    self_or_call_site_merged_context_parameters,
    processor_name,
    context = {"MY_NAME": live_value},
  )
```

The call-site merge order (base -> server -> pipeline -> processor) means
a processor's declared default for an UPPER_CASE name overrides the same
name in a higher scope.  At value-resolution time the order is:
`context` kwarg wins over auto-resolved system values which win over
declared defaults.  See [Context Parameters](context_parameters.md) for
details.


#### 1.3 Define the Data Flow

Discuss:

  * What data does the `process()` method read from VconProcessorIO?
    (vCons, parameters, or both)
  * Does it expose all vCons or just the one at `input_vcon_index`?
  * Where does the output go?  Options include:
    - VconProcessorIO parameters (via `set_parameter()`)
    - New analysis objects on a vCon (via `vcon.add_analysis()` then
      `processor_input.update_vcon()`)
    - New vCons (via `processor_input.add_vcon()`)
    - External side effects (e.g. sending email, queuing jobs)
  * Does the processor modify vCons?  This determines the `modifies_vcon`
    flag in the constructor.

#### 1.4 Handle Edge Cases

Discuss:

  * What happens with empty input (no vCons, no dialogs)?
  * What happens if required data is missing?
  * Should errors be raised or handled gracefully?
  * For analysis objects: what is the `encoding` value?  (`"json"` for dict/list
    bodies, `"none"` for plain strings)
  * For analysis objects: how is `dialog_index` determined?

#### 1.5 Confirm the Design

Present the complete design summary including:

  * Plugin name (used in registration and REST API routes)
  * Package structure (following the `example_processor_addon` pattern)
  * Complete options table with all fields, types, defaults, and examples
  * The `process()` method logic as numbered steps
  * Dependencies beyond `py-vcon-server`
  * The constructor parameters (title, description, version, modifies_vcon)

Do not proceed to implementation until the developer confirms the design.


### Phase 2: Build the Plugin

#### 2.1 Create the Package Files

Follow the addon package structure with no `__init__.py` files (implicit
namespace packages):

```
py_vcon_server_<plugin_name>/
├── pyproject.toml
├── setup.py
├── .gitignore
├── py_vcon_server/
│   └── processor_addons/
│       ├── <plugin_name>.py                          # registration
│       └── <plugin_name>_impl/
│           └── <plugin_name>.py                      # implementation
└── tests/
    └── test_processor_<plugin_name>.py
```

The **pyproject.toml** should contain:

```toml
[build-system]
requires = ["setuptools>=64"]
build-backend = "setuptools.build_meta"
```

The **registration file** follows this exact pattern:

```python
import py_vcon_server.processor

init_options = py_vcon_server.processor.VconProcessorInitOptions()

py_vcon_server.processor.VconProcessorRegistry.register(
      init_options,
      "<plugin_name>",
      "py_vcon_server.processor_addons.<plugin_name>_impl.<plugin_name>",
      "<ClassName>"
      )
```

The **implementation file** contains three classes:

  * `<Name>InitOptions` — extends `VconProcessorInitOptions` (usually no new fields)
  * `<Name>Options` — extends `VconProcessorOptions` with the plugin-specific fields
  * `<Name>` — extends `VconProcessor`, implements `__init__` and `process()`

HTTP Requests in Plugins: Use vcon.http_lb.HttpLb
When a VconProcessor plugin needs to make HTTP requests (e.g. calling external APIs, webhooks, or services), it must use vcon.http_lb.HttpLb instead of requests, httpx, or aiohttp directly.

HttpLb is an async static class in vcon/http_lb.py that provides:

Load balancing — resolved DNS addresses are shuffled so successive calls distribute traffic across hosts.
Failover — each resolved address is tried in turn; connection errors and retryable HTTP status codes (502, 503, 504) advance to the next address automatically.
Multi-host URLs — a single URL can specify multiple hosts (e.g. http://h1:8000,h2:8001/path) for built-in redundancy.
Configurable timeouts — connect, read, write, and pool timeouts can all be set per request.
Available methods
All methods are async and @staticmethod on HttpLb:

HttpLb.get(url, ...) — HTTP GET
HttpLb.post(url, body=..., content_type=..., ...) — HTTP POST
HttpLb.put(url, body=..., content_type=..., ...) — HTTP PUT
HttpLb.request(method, url, body=..., ...) — generic method for any HTTP verb (e.g. "DELETE", "PATCH")
All return an httpx.Response.

Usage in a processor
python
import vcon.http_lb

class MyProcessor(py_vcon_server.processor.VconProcessor):
    async def process(self, processor_input, options):
        response = await vcon.http_lb.HttpLb.post(
            options.api_url,
            body=payload_dict,
            content_type="application/json",
            connect_timeout=5.0,
            read_timeout=30.0,
        )
        response.raise_for_status()
        result = response.json()
        ...
Dependency
HttpLb requires httpx, which is already listed in the py-vcon pip requirements. Addon packages do not need to add httpx to their own dependencies as long as they depend on python-vcon.

#### 2.2 Create the Unit Tests

The test file must be **self-contained** with no dependencies on files outside the
addon package directory tree.  Do not import from `common_setup.py` or reference
test fixture files like `hello.wav`.

**Test file header pattern:**

The test file must handle namespace package resolution for both PYTHONPATH-based
and pip-installed development environments.  Use this header pattern:

```python
import pytest
import pytest_asyncio
import fastapi.testclient
import vcon
import py_vcon_server
import py_vcon_server.processor
from py_vcon_server.settings import VCON_STORAGE_URL

# Extend the processor_addons namespace package path to include
# this addon's source tree.  This is necessary when the main
# py_vcon_server package is loaded via PYTHONPATH rather than
# pip install, as namespace package merging does not occur.
import os
import py_vcon_server.processor_addons

_addon_addons_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "py_vcon_server",
    "processor_addons"
)
if _addon_addons_dir not in py_vcon_server.processor_addons.__path__:
    py_vcon_server.processor_addons.__path__.append(_addon_addons_dir)

import py_vcon_server.processor_addons.<plugin_name>

# Reload py_vcon_server to create REST API routes for the
# processor.  The routes are built at import time, so processors
# registered after the initial import will not have routes
# unless the module is reloaded.
import importlib
importlib.reload(py_vcon_server)
```

The ordering matters: extend path, then import registration, then reload.

**Test fixtures:**

Create vCon test fixtures as plain helper functions (not pytest fixtures imported
from elsewhere) that build vCons entirely in code:

```python
def make_test_vcon() -> vcon.Vcon:
    v = vcon.Vcon()
    v._vcon_dict["uuid"] = UUID
    v.set_party_parameter("tel", "+15551234567")
    v.set_party_parameter("name", "Alice", 0)
    v.set_subject("Test conversation")
    v.add_dialog_inline_text(
        "Hello, this is a test.",
        "2024-03-06T20:07:43+00:00",
        5.0,
        0,
        vcon.Vcon.MEDIATYPE_TEXT_PLAIN
    )
    return(v)
```

Use `add_dialog_inline_text()` rather than `add_dialog_inline_recording()` to
avoid needing audio files.

**Storage setup fixture:**

```python
VCON_STORAGE = None

@pytest_asyncio.fixture(autouse=True)
async def setup():
    vs = py_vcon_server.db.VconStorage.instantiate(VCON_STORAGE_URL)
    global VCON_STORAGE
    VCON_STORAGE = vs
    yield
    VCON_STORAGE = None
    await vs.shutdown()
```

**Date assertions:**

The vcon library canonicalizes dates, potentially adding milliseconds
(e.g. `2024-03-06T20:07:43+00:00` becomes `2024-03-06T20:07:43.000+00:00`).
Use substring matching in assertions:

```python
# Do this:
assert("2024-03-06T20:07:43" in result)
# Not this:
assert("2024-03-06T20:07:43+00:00" in result)
```

**Two levels of testing:**

  1. **Standalone processor tests** — create VconProcessorIO, add vCons, call
     `process()` directly, verify parameters and vCon state.  These test all
     the processor logic.

  2. **REST API tests** — use `fastapi.testclient.TestClient(py_vcon_server.restapi)`
     to test both `/process/{vcon_uuid}/<plugin_name>` and
     `/processIO/<plugin_name>` endpoints.  These verify route creation and
     serialization.  Clean up stored vCons with `client.delete("/vcon/{}".format(UUID))`
     after each API test.

**Test coverage targets:**

  * Registration (name, title, version, modifies_vcon flag)
  * Each output destination (parameters, analysis objects, both)
  * Required fields raise validation errors when missing
  * Optional fields are omitted from output when not set
  * Edge cases (empty input, missing data, error conditions)
  * `format_options` parameter injection
  * REST API endpoints (both /process/ and /processIO/)

#### 2.3 Running Tests

From the addon project root:

```bash
pytest -v -rP tests/
```

This requires:

  * `py-vcon` and `py-vcon-server` importable (via PYTHONPATH or pip install)
  * The addon package importable (the namespace path extension in the test
    header handles this without needing `pip install -e .`)
  * Redis running (for VconStorage)
  * `jinja2` or other addon dependencies installed

#### 2.4 Running the Plugin in the Server (Development)

There are three ways to run and test a VconProcessor plugin, depending on
the development stage.

**Mode 1: Unit tests (no server running)**

Run from the addon project root:

    pytest -v -rP tests/

The test file's namespace path extension header handles making the addon
importable without any install step.  Requires `py-vcon` and `py-vcon-server`
on PYTHONPATH and Redis running.

**Mode 2: Running in the server (development)**

Set `PLUGIN_PATHS` to the addon's `processor_addons` directory and start
the server:

    export PLUGIN_PATHS="/path/to/<addon_repo>/py_vcon_server/processor_addons"
    python3 -m py_vcon_server

The server scans the entire directory on startup, so adding new processors
to the addon package requires no changes to this setting.  To load multiple
addon packages, use a comma-separated list of directory paths.  Code changes
in the addon source are reflected on server restart.

**Mode 3: Production install (pip packages)**

When both `py-vcon-server` and the addon are installed as pip packages,
namespace package merging happens automatically and the server discovers
all installed addons without any configuration:

    pip install py-vcon-server
    pip install <addon_package_name>
    python3 -m py_vcon_server

No `PLUGIN_PATHS` setting is needed.

