# Technical reference

Fitness's configuration format, adapter protocol, and Python API. For work on
Fitness itself, see [Contributing](contributing.md).

## Definitions

`--rules` defaults to `fitness` and accepts a YAML file or recursive directory.
`--type` filters check execution by function type.

```yaml
description: Expectations for the quality of documentation links.
tools:
  links:
    command: [python, integrations/links.py]
    send_input: true
functions:
  - title: Keep documentation links working
    type: documentation
    tool: links
    rules: [broken-link]
    limit: 0
    guidance: Update or remove broken links.
```

Every YAML document requires a nonempty `description` explaining its scope,
including documents that only define tools. Files may group functions by subject
and contain multiple types. Descriptions are metadata; they do not affect selection
or execution and are not sent to adapters.

Functions require `title` and `type`. Omit `tool` for manual expectations; omit
`rules` to count all findings from a tool. `limit` defaults to zero. Optional
guidance supplements tool messages. See the [glossary](glossary.md) for terminology.
Lint validates definitions offline, including references and unknown fields.

## Provisional integration contract

Each selected tool runs once, without a shell, in the caller's working directory.
Commands have a 60-second timeout. With `send_input: false` (default), stdin is closed.
With `send_input: true`, stdin receives JSON:

```json
{"config": {}, "selections": [{"rules": ["broken-link"], "config": {}}]}
```

Top-level config is invocation-wide; selections hold function settings. Omitted
rules become `null`. Adapters interpret configuration and selectors; see the
[adapter guide](adapters.md). Config is not sent when input is disabled.

Successful integrations exit **0**, even when findings exist, and emit only a flat
JSON array on stdout. Send diagnostics to stderr. An empty array means zero
violations. Nonzero exits, timeouts, and malformed output are evaluation errors;
partial results are discarded. Wrappers must normalize native tool exit codes.

```json
[
  {
    "tool": "links",
    "rule_id": "broken-link",
    "tool_message": "Link target was not found.",
    "filename": "docs/guide.md",
    "location": {"row": 12, "column": 5}
  }
]
```

Filename/location are optional; coordinates are one-based. The tool name must
match the invoked tool. The core maps exact reported rule IDs to functions and
passes when count <= limit.

CLI exit codes: **0** valid/passing, **1** violations, **2** configuration/execution
error. Check prints only failures or `success`. No matching or automated functions
also yields `success`; this does not imply manual expectations were evaluated.

## Python API

`fitness.features.lint.contract.lint_fitness_functions(path)` loads and validates
fitness functions offline, returning shared `FitnessFunctions` data including
source locations and overlap warnings. The check contract exposes
`check_fitness_functions(fitness_functions, execute_adapter=..., type_=...)`,
returning `CheckResult` objects. Both APIs raise `FitnessError` for errors;
neither prints output nor exits the process.

`execute_adapter` accepts a command and optional JSON stdin and returns stdout;
its default process transport is also available through the check contract.
Tool remains the YAML command definition; adapter describes the executable
integration capability. Shared domain models live in `fitness.contracts`.
