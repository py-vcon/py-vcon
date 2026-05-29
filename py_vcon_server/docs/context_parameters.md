# Context Parameters

Context parameters are system-provided values available for substitution in a
processor's `format_options` templates.  They complement user-defined
parameters (set via `set_parameters`, `jq`, or any other processor that writes
to `VconProcessorIO`) by providing values about the execution environment that
the user did not explicitly set: the processor name, the current time, the
vCon UUID, the pipeline name, the server identity, and so on.


## Case Convention

To avoid name collisions between user-defined parameters and system-provided
context parameters, the project follows a case convention:

  * **`UPPER_CASE`** names are reserved for system-provided context parameters
    (e.g. `PROCESSOR_NAME`, `VCON_UUID`, `PIPELINE_NAME`).
  * **`lower_case`** names are used for user-defined parameters (e.g.
    `attendees`, `summary`, `action_items`).

The convention is a guideline, not enforced by the framework.  If a
user-defined parameter happens to share a name with a context parameter, the
context parameter's value wins.


## Scopes

Context parameters are organized into four scopes that are merged in order
when a processor's `format_options` are substituted:

  1. **Base** scope - always available, values resolved per call.
  2. **Server** scope - always available, values resolved once per process.
  3. **Pipeline** scope - available in any processor run, sourced from the
     `VconProcessorIO` run context.
  4. **Processor** scope - additions declared by individual processor classes.

When a name appears in more than one scope, the later scope's definition wins
at the definition-merge level.  At the value-resolution level, a per-call
`context` override (when a processor passes one explicitly) wins over the
auto-resolved values, which win over declared defaults.


## Base Scope

| Name | Default | Description |
|------|---------|-------------|
| `PROCESSOR_NAME` | `""` | Registered name of the processor currently executing |
| `TIMESTAMP` | `""` | ISO 8601 UTC timestamp captured at substitution time |
| `NDATE` | `""` | UTC date in `yyyymmdd` form captured at substitution time |
| `VCON_UUID` | `""` | UUID of the vCon at `input_vcon_index`, or empty string if not resolvable |


## Server Scope

Server scope values are resolved from `py_vcon_server.settings` and the
`py_vcon_server` and `vcon` package versions on first substitution and
cached for the life of the process.

| Name | Default | Description |
|------|---------|-------------|
| `INSTANCE_ID` | `""` | Identifier for this server instance, sourced from `py_vcon_server.settings.INSTANCE_ID` |
| `REST_SCHEME` | `""` | Scheme parsed from `py_vcon_server.settings.REST_URL` (e.g. `http`, `https`) |
| `REST_HOST` | `""` | Host parsed from `py_vcon_server.settings.REST_URL` |
| `REST_PORT` | `""` | Port parsed from `py_vcon_server.settings.REST_URL`, as a string |
| `SERVER_VERSION` | `""` | `py_vcon_server` package `__version__` |
| `VCON_VERSION` | `""` | `vcon` package `__version__` |

If `REST_URL` is malformed (cannot be parsed), the `REST_*` values fall back
to empty strings and an ERROR is logged at server start.


## Pipeline Scope

Pipeline scope values are sourced from the `VconProcessorIO` run context,
which is set by whichever entry point started the run.

| Name | Default | Description |
|------|---------|-------------|
| `PIPELINE_NAME` | `""` | Name of the pipeline currently running |
| `PIPELINE_JOB_ID` | `""` | Job ID assigned when this run was queued (empty for direct REST calls) |
| `ENTRY_POINT` | `""` | How this run was started; see values below |

`ENTRY_POINT` resolves to one of the following strings:

| Value | Set by |
|-------|--------|
| `/process` | `POST /process/{uuid}/{processor_name}` |
| `/processIO` | `POST /processIO/{processor_name}` |
| `/pipeline/run` | `POST /pipeline/{name}/run` (vCon in request body) |
| `/pipeline/run/uuid` | `POST /pipeline/{name}/run/{uuid}` (vCon in storage) |
| `background` | Background worker via `PipelineJobHandler.do_job` |


## Processor Scope

A `VconProcessor` subclass may declare additional context parameters by
setting a class-level `context_parameters` dict.  The names declared there
are merged into the substitution dict for that processor only, and the
processor may inject live values for them via the `context` argument to
`format_parameters_to_options` from inside its `process()` method.

```python
class MyProcessor(VconProcessor):
    context_parameters = {
        "MY_NAME": {
            "default":     "",
            "description": "what this value represents",
            "title":       "My Name",
        },
    }
```

No built-in processor currently declares its own `context_parameters`.  When
processor-scope additions are introduced, they will be documented alongside
the processor that provides them.


## Using Context Parameters

A processor's `format_options` is a dict of option field names to template
strings.  Inside a template string, `{name}` placeholders are substituted
from the merged set of user-defined parameters and context parameters.

The following pipeline fragment uses context parameters (`{PIPELINE_NAME}`,
UPPER_CASE) alongside user-defined parameters (`{date}`, `{summary}`,
lower_case) to set the subject and body of an email:

```json
{
  "processor_name": "send_email",
  "processor_options": {
    "format_options": {
      "subject":   "Meeting notes from pipeline {PIPELINE_NAME}, {date}",
      "text_body": "Summary:\n{summary}\n\nAttendees:\n{attendees}\n"
    },
    "to":              ["you@yourdomain.com"],
    "client_hostname": "vcon_server.yourdomain.com",
    "from_address":    "py_vcon_server@yourdomain.com",
    "smtp_host":       "mail.yourdomain.com"
  }
}
```

`PIPELINE_NAME` is provided by the framework when the pipeline runs.  The
lower_case parameters (`date`, `summary`, `attendees`) would have been set
earlier in the same pipeline, typically by a `jq` processor extracting
values from the vCon.  See
[Advanced Pipeline Example](../README.md#advanced-pipeline-example) for a
complete pipeline that demonstrates this pattern.
