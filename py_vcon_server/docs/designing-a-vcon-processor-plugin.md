# Designing a VconProcessor Plugin: The jinja_report Example

## Introduction

This document captures the design discussion for the `jinja_report` VconProcessor
plugin.  It is intended as an example of the process for designing a new
VconProcessor plugin from requirements through to a complete, buildable design.

The `jinja_report` processor renders Jinja2 templates against the VconProcessorIO
(vCons and pipeline parameters) to produce text reports.  Output can be stored as
a pipeline parameter, as a new analysis object in the vCon, or both.

The discussion below is organized by design decision, showing the options
considered and the rationale for each choice.


## Starting Point: Choosing a Pattern

The py-vcon-server has two styles of VconProcessor:

  * **FilterPluginProcessor** — a thin wrapper that delegates to an underlying
    vCon FilterPlugin (e.g. `sign`, `verify`, `encrypt`, `deepgram`).  These use
    `FilterPluginProcessor.makeInitOptions()` and `makeOptions()` to dynamically
    build their options classes.

  * **Standalone VconProcessor** — implements the `process()` method directly
    without an underlying FilterPlugin (e.g. `jq`, `set_parameters`, `send_email`,
    `queue_job`).

The `jinja_report` processor is a standalone VconProcessor because it introduces
new functionality (Jinja2 template rendering) rather than wrapping an existing
FilterPlugin.  The `jq` processor was identified as the closest existing example
because it also:

  * Builds a dict representation of the VconProcessorIO
  * Queries/transforms that data
  * Stores results in pipeline parameters
  * Does not inherently modify vCons (though `jinja_report` optionally does)


## Design Decision: Template Source

**Options considered:**

  * **A:** Inline string in the processor options (like jq puts queries inline)
  * **B:** File path reference
  * **C:** Both inline and file path

**Decision:** Option A — inline template string, provided as a required processor
option field.  This matches the jq pattern and keeps pipeline definitions
self-contained.  File-based and Redis-stored templates were identified as future
enhancements.


## Design Decision: Template Context

Following the jq processor's approach, the Jinja2 template receives a context dict
with two top-level variables:

```python
{
    "vcons": [<dict form of each vCon in the VconProcessorIO>],
    "parameters": {<VconProcessorIO parameters dict>}
}
```

All vCons in the VconProcessorIO are exposed (not just the one at
`input_vcon_index`), so a template can reference any vCon.  The
`input_vcon_index` inherited option controls which vCon receives the analysis
object when analysis output is enabled.

Templates reference data using standard Jinja2 syntax:

```
{{ vcons[0].uuid }}
{{ vcons[0].parties[0].name | default("Unknown", true) }}
{{ parameters.summary }}
{% for p in vcons[0].parties %}...{% endfor %}
```

The context dict is built using the same loop pattern as the jq processor:
iterate `processor_input._vcons`, call `get_vcon(VconTypes.OBJECT)`, then
`dumpd(signed=False, deepcopy=False)`.


## Design Decision: Output Destinations

**Options considered:**

  * **A:** A single `output_mode` field choosing between parameter or analysis
  * **B:** Separate optional fields where presence indicates output type

**Decision:** Option B — the presence of `output_parameter_name` (which has a
default) or `analysis_type` (which defaults to None) determines output.  Both
can fire simultaneously.

  * `output_parameter_name` always has a default value of `"report_output"`, so
    parameter output always occurs.  This avoids the "zero output" misconfiguration
    problem — the pipeline editor sees a populated field and the processor always
    produces at least one output.

  * `analysis_type` is opt-in.  When set (e.g. `"report"`), the rendered output is
    added as a new analysis object to the vCon at `input_vcon_index`.

This means:

  * Parameter-only output: just provide a template (default behavior)
  * Analysis-only output: set `analysis_type` (parameter output still happens, but is
    harmless)
  * Both: set `analysis_type` and use the parameter too


## Design Decision: Analysis Object Fields

The `vcon.Vcon.add_analysis()` method accepts:

```python
add_analysis(
    dialog_index,    # Union[int, List[int]]
    analysis_type,   # str
    body,            # str (the rendered template)
    vendor,          # Optional[str]
    schema,          # Optional[str]
    encoding,        # str
    **optional_parameters
)
```

Key decisions for how jinja_report maps to this:

  * **encoding** — hardcoded to `"none"` since the rendered output is a plain string,
    not JSON.

  * **vendor** — defaults to `"jinja"`, overridable via `analysis_vendor` option.

  * **product** and **schema** — default to empty string (omitted from the analysis
    object when empty).
    These are primarily useful for non-text structured output where a consumer needs
    to identify the format.  The `add_analysis()` method already checks for
    None/empty and skips adding the field.

  * **mediatype** — passed via `**optional_parameters` as `media_type` option,
    defaulting to `"text/plain"`.  For HTML report templates, the user would set
    this to `"text/html"`.

**A note on pydantic defaults and the pipeline editor:** the initial design used
`typing.Union[str, None]` with `default = None` for optional fields like
`analysis_type`, `analysis_product`, and `analysis_schema`.  This produced correct
Python behavior, but pydantic omits `None` defaults from the generated JSON schema.
The pipeline editor uses the schema `default` key (not the `required` array) to
determine whether a field is mandatory, so these fields appeared as required in the
editor.  The fix was to change the type to `str` with `default = ""` and check for
empty string in the `process()` method.  The same pattern applies to
`analysis_dialog_index`, which uses `default = []` instead of `None`.


## Design Decision: Analysis Dialog Index

**Options considered:**

  * **A:** Default to `0`
  * **B:** Derive from template (parse AST to find referenced dialogs)
  * **C:** Default to all dialogs at runtime

**Decision:** Option C — when `analysis_dialog_index` is None (the default), the
processor computes the list at runtime:

```python
num_dialogs = len(in_vcon.dialog) if in_vcon.dialog else 0
if num_dialogs > 1:
    dialog_index = list(range(num_dialogs))
elif num_dialogs == 1:
    dialog_index = 0
else:
    dialog_index = 0
```

Option B (template AST analysis) was rejected as too complex and fragile — it
would need to handle loops, conditionals, variable indirection, and macro calls.
A report template typically summarizes the entire conversation, so defaulting to
all dialogs is correct in spirit.

With a single dialog, the index is an int (`0`), matching the convention used by
other processors.  With multiple dialogs, it's a list (`[0, 1, 2]`), which the
`add_analysis()` method supports.


## Design Decision: Inherited Options

The `VconProcessorOptions` base class provides these fields, and each applies
to jinja_report as follows:

  * **`input_vcon_index`** (int, default 0) — controls which vCon receives the
    analysis object.  All vCons are still exposed in the template context regardless.

  * **`should_process`** (bool, default True) — conditional skip, handled by the
    pipeline runner before `process()` is called.  Useful with `format_options` to
    conditionally skip the jinja step based on a prior processor's output.

  * **`format_options`** (Dict[str, str], default {}) — injects VconProcessorIO
    parameters into option field values using Python `.format()` syntax.  For
    example, `{"template": "{my_template_param}"}` pulls the template string from
    a parameter set by a prior pipeline step.

  * **`label`** and **`notes`** — documentation-only fields with no runtime impact.

The `format_parameters_to_options()` call at the top of `process()` (same pattern
as jq) handles `format_options` automatically.


## Design Decision: Constructor `modifies_vcon` Flag

The `VconProcessor.__init__()` constructor takes a boolean indicating whether the
processor may modify a vCon.  Since jinja_report can add analysis objects (when
`analysis_type` is set), this is `True`.  The same approach is used by the openai
processor, which always declares `True` even though it only sometimes adds analysis.


## Design Decision: Jinja2 Environment

  * **`StrictUndefined`** — the Jinja2 environment uses `jinja2.StrictUndefined`
    so that referencing a nonexistent variable raises an immediate error rather
    than silently rendering as empty string.  This catches template bugs early.

  * **No autoescape** — the output could be plain text, markdown, or HTML, so
    autoescape is not enabled by default.

  * **No custom filters** — standard Jinja2 does not include date formatting
    filters.  Dates from the vCon (RFC3339 strings like
    `2024-03-06T20:07:43.000+00:00`) pass through as-is.  Custom filters can
    be added as a future enhancement.


## Design Decision: Package Structure

The processor is built as an independent pip package following the
`example_processor_addon` pattern in `py_vcon_server/docs/`:

```
py_vcon_server_jinja_report/
├── pyproject.toml
├── setup.py
├── .gitignore
├── py_vcon_server/
│   └── processor_addons/
│       ├── jinja_report.py                          # registration
│       └── jinja_report_impl/
│           └── jinja_report.py                      # implementation
└── tests/
    └── test_processor_jinja_report.py
```

No `__init__.py` files — the package uses implicit namespace packages so pip can
merge `py_vcon_server.processor_addons` across the main py-vcon-server package and
addon packages.

Dependencies: `py-vcon-server` and `jinja2`.


## Final Options Summary

### Inherited from VconProcessorOptions

| Field | Type | Default |
|-------|------|---------|
| `input_vcon_index` | int | 0 |
| `should_process` | bool | True |
| `format_options` | Dict[str,str] | {} |
| `label` | str | "" |
| `notes` | str | "" |

Note: `format_options` accepts both user-defined `lower_case` parameter names and system-provided `UPPER_CASE` context parameter names.  See [Context Parameters](context_parameters.md) for the complete list of context parameters available across all scopes.

### New fields on JinjaReportOptions

| Field | Type | Default | Example |
|-------|------|---------|---------|
| `template` | str | *required* | (see below) |
| `output_parameter_name` | str | "report_output" | "report_output" |
| `analysis_type` | Optional[str] | None | "report" |
| `analysis_vendor` | Optional[str] | "jinja" | "jinja" |
| `analysis_product` | Optional[str] | None | None |
| `analysis_schema` | Optional[str] | None | None |
| `media_type` | str | "text/plain" | "text/plain" |
| `analysis_dialog_index` | Optional[Union[int, List[int]]] | None | [0, 1] |


## Example Template

```
Conversation Report
===================
UUID: {{ vcons[0].uuid }}
Subject: {{ vcons[0].subject | default("N/A", true) }}
Date: {{ vcons[0].dialog[0].start | default("N/A", true) }}
Duration: {{ vcons[0].dialog[0].duration | default("N/A", true) }} seconds

Parties:
{% for p in vcons[0].parties -%}
  - {{ p.name | default("Unknown", true) }}
{% endfor %}
```

## Loading the Plugin

Install the addon pip package:
```bash
pip install py_vcon_server.processor_addons.jinja-report
```

The py-vcon-server automatically discovers and loads processor addons installed
under the `py_vcon_server.processor_addons` namespace package.  No changes to
the `PLUGIN_PATHS` environment variable are needed.

In a development environment where py-vcon-server is loaded via `PYTHONPATH`
rather than pip install, namespace package merging does not occur automatically.
In that case you can either use `pip install --no-deps -e .` from the addon
project directory, or add the registration module path to `PLUGIN_PATHS`:
```bash
export PLUGIN_PATHS="py_vcon_server.processor_addons.jinja_report"
```

