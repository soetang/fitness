# Technical reference

See the [README](../README.md) for a quick start and the
[adapter guide](adapters.md) for adding integrations.

## Development commands

Shared example definitions, findings, and an executable integration live in
`tests/fixtures/`.
`just setup`, `just test`, `just lint`, `just typecheck`, and `just fmt` support development.
Initialize the retained runner once with `just update-runner` before `just check`.
`just check` runs pytest, uses the retained wheel against this package's `fitness/`,
then checks formatting. Tests enforce **100% line and branch
coverage** of `src/fitness`; missing coverage fails the run. Without just, run:

```sh
uv run pytest
uvx --from ./dist/self-check/fitness-0.1.0-py3-none-any.whl fitness lint
uvx --from ./dist/self-check/fitness-0.1.0-py3-none-any.whl fitness check
uv run ruff format --check .
uv run pyrefly check
```

## Checking Fitness itself

`just check` tests the current source, executes Fitness lint/check from the retained
wheel in an isolated uv tool environment against the working tree, and checks
formatting. Normal checks never rebuild or refresh the wheel: a CLI change must not
silently replace the runner used to inspect that change. `just update-runner`
explicitly runs tests, builds and refreshes the retained wheel. Use this to
bootstrap a checkout or deliberately adopt a tested CLI version. `just build`
builds a separate candidate in `dist/` without replacing the retained runner.

`fitness/functions/` defines zero-limit lint, typing, and layout expectations.
Tool registrations live in `fitness/tool.yaml`. `fitness/tool/ruff/adapter.py`
and `fitness/tool/pyrefly/adapter.py` run the development tools using existing
`pyproject.toml` configuration. Run recipes from the project root after `just setup`.
Each adapter lives in `fitness/tool/<name>/adapter.py`, with its own `test_*.py` files.
Shared fixtures live in `fitness/tool/conftest.py`. Pytest collects these with importlib
mode so repeated test filenames work. Layout fitness functions flag adapters
without dedicated folders/tests, orphan adapter tests under `fitness/tool/`, and
`test_*adapter*.py` modules misplaced under `tests/`.
Adapters use `uv run --no-sync` to access the project's development environment;
they do not import Fitness. Ruff checks the repository, and Pyrefly checks
`src/`, `tests/`, and `fitness/tool/`.

Pyrefly findings use native rule IDs. Ruff findings use the most-specific requested
selector and retain the concrete native code in the message.
The general Ruff function uses `rules: [E, F, I, UP, SIM]` in
`fitness/functions/package.yaml`; `PGH004` and `TID251` live in dedicated functions. Ruff rule
selection is defined in YAML, not `pyproject.toml`. The Ruff adapter selects the
longest matching selector across the selected invocation: `F401` wins over `F4`,
which wins over `F` (`ALL` is least specific). It emits one finding with that
selector as `rule_id` and `F401: ...` in the message. A dedicated `F401` function
therefore receives that finding instead of the broader `F` function. When rules
are omitted and no explicit selector matches, the adapter reports the native ID.
The core always matches reported IDs exactly; there is no matching-mode field.
Lint warns about identical references and all-diagnostic functions, without
interpreting tool-specific selectors.
`just fmt` reads the package's Ruff rule IDs from that same YAML for automatic
lint fixes, then runs Ruff's formatter.
Their adapters receive selections over JSON stdin. Explicit IDs select native
checks; omitted `rules` uses configured checks and counts all returned diagnostics.
When combined, configured checks are extended with explicit selections. Native
configuration defaults remain in `pyproject.toml`. Ruff applies tool config as
native top-level overrides and function config under `lint`, using TOML key/value
CLI arguments. Conflicting settings across selections fail explicitly; compatible
settings are combined in one invocation. Pyrefly still rejects nonempty request
config rather than silently ignoring it. Native exit 1 with diagnostics becomes
successful adapter output; command failures remain errors.

Ruff's `PGH004` prohibits blanket noqa directives; rule-specific suppressions are
allowed. Pyrefly enables both `explicit-any` and `implicit-any` checks, including
tests and adapters. Pyrefly uses exact IDs in explicit selections. General Ruff
and Pyrefly functions omit guidance and rely on their native tool messages.

Architecture functions live in `fitness/functions/architecture.yaml`. Functions about the
definitions themselves live in `fitness/functions/meta.yaml` with `type: meta`.
The layout adapter's
`architecture-function-type` rule reports every function there whose type is not
`architecture`. Other definition files may contain other types.
The Pydantic-model function uses Ruff `TID251` with its `banned-api` configuration
in YAML to prohibit standard-library and Pydantic dataclasses.

The `type: versioncontrol` function in `fitness/functions/versioncontrol.yaml` checks staged
paths: functions, tool registrations, and adapters under `fitness/` may change
together, as may `src/` and `tests/`, but one commit cannot mix the two groups.
Other paths are neutral. Stage a cohesive change, then run `just check` before
committing. Unstaged changes are ignored; an empty index passes. This checks the
prospective commit only; no Git hook or historical-commit CI check is installed.

## Definitions

`--rules` defaults to `fitness`. It accepts a YAML file or recursively
loads `.yaml`/`.yml` files in a directory. Tools may be defined in a separate file.

```yaml
tools:
  architecture:
    command: [python, integrations/architecture.py]
    send_input: true
    config: {}
functions:
  - title: Keep features independent
    type: architecture
    tool: architecture
    rules: [private-import]
    limit: 0
    guidance: Communicate through public interfaces.
    config: {}
```

A fitness function requires a title and one user-defined type. Omit `tool` for
nonautomated expectations; these are reported as **NOT AUTOMATED**, never passed.
Automated functions may omit `rules` to count all findings from that tool's
configured checks. An explicit list must contain at least one rule ID or selector.
`limit` defaults to zero and is a shared
nonnegative integer budget across those IDs. Guidance supplements tool messages.
Source file/line identifies definitions; no explicit function IDs are needed.

Lint is offline: it validates shape, unknown/duplicate fields, tool references,
and limits, and warns about overlapping tool/rule references. It does not validate
native rule IDs or tool-specific settings. The core has no tool-specific knowledge.

## Provisional integration contract

Each selected tool runs once, without a shell, in the caller's working directory.
Commands have a 60-second timeout. With `send_input: false` (default), stdin is closed.
With `send_input: true`, stdin receives JSON:

```json
{"config": {}, "selections": [{"rules": ["private-import"], "config": {}}]}
```

Top-level config is invocation-wide; each selection preserves function-specific
settings. Omitted rules are transmitted as `"rules": null`. Explicit lists filter
findings by exact reported rule ID. All-diagnostic functions overlap with every
explicit selection for the same tool, so lint warns about shared counts.
Integrations own native configuration interpretation, conflict detection,
and compatible batching. No function metadata is sent. Config is ignored when
input is disabled.

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

`filename` and `location` are optional. Location coordinates are positive,
one-based integers. The reported tool must match the invoked tool. Unselected
rule IDs are ignored. Every finding counts toward every matching function;
pass means count <= limit. Multiple offenders must be emitted as individual
findings; a failed pytest test is not inherently one violation.

CLI exit codes: **0** valid/passing, **1** violations, **2** configuration/execution
error. No matching functions is a successful check with an explicit message.

## Architecture and open questions

Three modules: strict models, loading/evaluation, and Typer presentation.
`evaluate(suite, runner)` and `create_app(runner)` inject the command boundary.
Tests use ordinary injected functions and real subprocess fixtures, with no mocks.

This prototype chooses `--rules`, `send_input`, and the completion protocol above
for experimentation. Still open:

- Generate native configuration versus reference existing tool configuration.
- File-level defaults for type/tool.
- Config merging, conflicting selections, and compatible adapter batching.
- Whether a shared rule-ID budget is sufficient: Ruff's TID251 cannot distinguish
  independent banned APIs by ID alone.
- Richer completion/error reporting and partial failures.

For Ruff experiments, `preview` and `explicit-preview-rules` belong in tool config;
`pylint.max-bool-expr` belongs in function config. The repository's minimal Ruff
adapter supports rule selection and native configuration overrides; incompatible
function settings currently produce an error rather than separate batches.
There is no automatic baseline, ratchet, or agent integration.
