# Writing an adapter

An adapter runs a native tool and translates its diagnostics into Fitness
findings. Keep tool-specific rule selection and configuration handling here;
the core maps reported `tool` + `rule_id` values exactly.

## Layout

Give each adapter its own folder, with colocated tests:

```text
fitness/tool/
  example/
    adapter.py
    test_adapter.py
  conftest.py
```

Register its command in `fitness/tool.yaml`:

```yaml
tools:
  example:
    command: [uv, run, --no-sync, python, fitness/tool/example/adapter.py]
    send_input: true
```

Use `send_input: true` when the adapter accepts configuration and rule selections
through JSON stdin. Otherwise stdin is closed. See the
[integration contract](reference.md#provisional-integration-contract) for request
and response schemas, timeouts, and error handling.

## Implementation checklist

1. Read the selected rules and configuration, when input is enabled.
2. Translate them into native arguments or settings. Reject unsupported or
   conflicting settings instead of silently ignoring them.
3. Run the native tool. Distinguish diagnostic exit codes from execution failures.
4. Emit one finding per offender as a flat JSON array on stdout. Send diagnostic
   logs to stderr. Exit zero for successful evaluation, including violations.
5. Preserve useful tool messages and any available filename/location.

An empty array means no violations. Nonzero exits or malformed output are errors;
the core discards partial results. A failed test does not automatically equal one
violation: report each actual offender.

## Ruff example

[`fitness/tool/ruff/adapter.py`](../fitness/tool/ruff/adapter.py) accepts native rule IDs and
families such as `F`, `UP`, and `SIM`. Across the selected invocation, the most
specific matching selector wins: `F401` before `F4` before `F`; `ALL` is least
specific. It emits that selector as `rule_id` and retains the concrete native
code in the message, such as `F401: Imported module is unused.`

Tool config becomes top-level Ruff settings; function config becomes settings
under `lint`. The adapter encodes these as TOML overrides. Compatible settings
are combined into one invocation; conflicting settings produce an error.

For example, the dataclass restriction in
[`fitness/functions/architecture.yaml`](../fitness/functions/architecture.yaml) selects `TID251` and
supplies `flake8-tidy-imports.banned-api` settings on the fitness function.

## Repository layout and commit adapters

The existing `layout` adapter also implements the architecture checks registered in
[`architecture.yaml`](../fitness/functions/architecture.yaml). It accepts explicit
rule selections using the existing JSON request. Unsupported settings and conflicting
settings for the same rule are execution errors. Its `architecture.py` sibling holds
policy evaluation, while `imports.py` collects a reusable import inventory. The
Pyrefly search path reflects those script-local imports.

Token counting uses the encoding named in the function config (`cl100k_base` in this
repository) and the locked tiktoken version. Tiktoken may populate its encoding cache
on first use. For each immediate feature directory under `src/fitness/features/`,
the adapter collects files recursively from that directory and matching
`tests/features/<name>/` and `docs/features/<name>/` directories, plus the configured
`associated_files` glob patterns. The current shared integration tests and fixtures
are explicitly associated with both features and counted in full for each.

Eligible suffixes are `.py`, `.md`, `.yaml`, `.yml`, `.json`, `.toml`, and `.txt`.
Hidden paths, `__pycache__`, and symlinks are excluded. Files are deduplicated within
each feature, sorted by path, decoded as strict UTF-8 without newline normalization,
and encoded separately with special-token strings treated as ordinary text. Counts
are summed without filename or separator overhead. Untracked eligible files count
too. Shared files outside these paths are not attributed implicitly. The adapter
reports one finding for each feature exceeding its configured combined budget;
Fitness's ordinary violation limit then evaluates these findings.

Import analysis invokes Semgrep **once** per layout evaluation, sharing its results
between contract access and dependency placement. If only dependency placement is
selected, targets are limited to `src/`; contract access adds external callers to
the same invocation. Semgrep's local `imports.semgrep` patterns collect facts;
they do not contain separate policy thresholds. The extension keeps this native
configuration out of Fitness's recursive YAML-definition loader.

Explicit targets include repository Python files, excluding hidden directories,
`__pycache__`, `build`, `dist`, and symlinks. Feature identity is determined by its
source directory; tests are external consumers. Semgrep recognizes imports,
aliases, attribute paths, and literal `importlib.import_module` and `__import__`
calls; the adapter resolves relative package names. Import facts cover alias-only
expressions; full dotted attribute matches supplement them. Scans disable metrics,
version checks, and inline suppression. Parse errors, incomplete target coverage,
timeouts, and unsuccessful native exits are evaluation errors. This is static
analysis; dynamically constructed names and reflective access cannot be fully
resolved.

Dependency analysis parses imports in `src/`, including `TYPE_CHECKING` blocks and
conditional imports. Those count as source usage. It checks runtime requirements
and optional runtime groups regardless of environment markers; development and
build-system requirements are not runtime declarations. Distribution names are
parsed with `packaging`, normalized, and mapped to top-level imports through the
explicit `module_mapping` config. Missing mappings are errors rather than guesses.
An unused runtime declaration also listed in `build-system.requires` is reported
with that build-only destination; other unused runtime declarations point to dev.

The `commits` adapter reads the Git index with `--cached --no-renames -z`. Both sides
of a rename therefore participate, as do deleted files. Ownership comes from
`src/fitness/features/<name>/`, `tests/features/<name>/`, and
`docs/features/<name>/`; files outside these directories are shared. See
[`versioncontrol.yaml`](../fitness/functions/versioncontrol.yaml) for the policies.

## Testing adapters

Use shared fixtures from [`fitness/tool/conftest.py`](../fitness/tool/conftest.py) and real
subprocesses, with no mocks. Cover clean output, individual findings, rule
selection, configuration, and execution failures. Run `just check` after changes.

`just check` includes adapter tests as well as the repository's fitness evaluation.
The import-boundary examples use one module-scoped, batched scan, retaining
separate assertions for each case. Native startup dominates small Semgrep scans;
batch compatible examples instead of launching a process per assertion. Distinct
selection and parse-error scenarios still run independently. Results are reused
within an evaluation or fixture, never cached across changing repository contents.
Pytest-xdist runs tests on up to four workers. The shared import-scan cases use one
`xdist_group` with `loadgroup` scheduling to avoid duplicating their fixture across
workers. Use `uv run pytest -n 0` for serial debugging.

Adapter changes may share a commit with definition changes, but not with changes
to `src/` or `tests/`. See the
[development reference](reference.md#checking-fitness-itself) for the retained
runner and staged-commit checks.
