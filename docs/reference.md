# Technical reference

Project expectations live in [fitness/functions](../fitness/functions/), with
integrations in [fitness/tool.yaml](../fitness/tool.yaml). Read those definitions
for the current rules and guidance.

## Checking Fitness itself

Run `just setup`, then `just update-runner` once to initialize the non-editable
CLI at `.fitness-runner/bin/fitness`. Run `just check` for validation. Normal checks
reuse the installed snapshot; only `just update-runner` replaces it after tests
pass. See the [justfile](../justfile) for individual commands.

## Definitions

`--rules` defaults to `fitness` and accepts a YAML file or recursive directory.
`--type` filters check execution by function type.

```yaml
tools:
  architecture:
    command: [python, integrations/architecture.py]
    send_input: true
functions:
  - title: Keep features independent
    type: architecture
    tool: architecture
    rules: [private-import]
    limit: 0
    guidance: Communicate through public interfaces.
```

Functions require `title` and `type`. Omit `tool` for manual expectations; omit
`rules` to count all findings from a tool. `limit` defaults to zero. Optional
guidance supplements tool messages. See the [glossary](glossary.md) for terminology.
Lint validates definitions offline, including references and unknown fields.

## Provisional integration contract

Each selected tool runs once, without a shell, in the caller's working directory.
Commands have a 60-second timeout. With `send_input: false` (default), stdin is closed.
With `send_input: true`, stdin receives JSON:

```json
{"config": {}, "selections": [{"rules": ["private-import"], "config": {}}]}
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
    "tool": "architecture",
    "rule_id": "private-import",
    "tool_message": "Import the public interface instead.",
    "filename": "src/orders/client.py",
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

## Architecture and open questions

### Python API

`fitness.features.lint.contract.lint_fitness_functions(path)` loads and validates
fitness functions offline, returning shared `FitnessFunctions` data including
source locations and overlap warnings. The check contract exposes
`check_fitness_functions(fitness_functions, execute_adapter=..., type_=...)`,
returning `CheckResult` objects. Both APIs raise `FitnessError` for errors and
leave presentation and exit codes to `fitness.cli`.

`execute_adapter` accepts a command and optional JSON stdin and returns stdout;
its default process transport is also available through the check contract.
Tool remains the YAML command definition; adapter describes the executable
integration capability. Shared domain models live in `fitness.contracts`.
Feature-specific loading and process transport stay inside their features.

The initial migration introduces the feature directories before activating the
staged feature-boundary policy. Subsequent changes use the new directory ownership.

The prototype still leaves these decisions open:

- Generate native configuration versus reference existing tool configuration.
- File-level defaults for type/tool.
- Config merging, conflicting selections, and compatible adapter batching.
- Whether shared rule-ID budgets are sufficient for independent expectations.
- Richer completion/error reporting and partial failures.
