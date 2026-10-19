# Contributing to Fitness

Project policies live in [fitness/functions](../fitness/functions/), with
integrations in [fitness/config.yaml](../fitness/config.yaml). Read those definitions
for the current rules and guidance.

## Development workflow

CLI output snapshots use Syrupy and live in `tests/__snapshots__/`.
Review output changes there. To intentionally update the context snapshot, run
`uv run pytest tests/test_context_cli.py -n 0 --no-cov --snapshot-update`.

Run `just setup`, then `just update-runner` to initialize the non-editable CLI at
`.fitness-runner/bin/fitness`. Normal checks reuse this snapshot; only
`just update-runner` replaces it after tests pass. See the [justfile](../justfile)
for individual commands.

`just check` runs source and adapter tests, definition/format validation, and fitness
evaluation. Pytest-xdist uses up to four workers; batched import cases share one
`xdist_group` with `loadgroup` scheduling. Pure adapter logic is tested directly;
native execution and JSON handling retain real subprocess tests. Fixtures are in
`fitness/tool/conftest.py`. Use `uv run pytest -n 0` for serial debugging.

## Repository adapter implementation

### Feature measurement

The layout adapter uses the encoding specified in the
[function configuration](../fitness/functions/codebase.yaml) and locked tiktoken
version. Tiktoken may populate its encoding cache on first use. Files are collected
recursively from each `src/fitness/features/<name>/` directory.

Eligible suffixes: `.py`, `.md`, `.yaml`, `.yml`, `.json`, `.toml`, `.txt`. Hidden
paths, `__pycache__`, and symlinks are excluded; eligible untracked files count.
Files are sorted, decoded as strict UTF-8 without newline
normalization, and encoded separately with special-token strings treated as text.
Counts are summed without filename or separator overhead.

Line counting includes blank lines and comments; a final newline does not create
an additional line. Feature-test attribution uses the shared import inventory;
fixture modules such as `conftest.py` are not treated as test modules.

### Import analysis

The layout adapter invokes `semgrep-core` once, sharing its import inventory between
contract access and dependency placement. Dependency-only selections scan `src/`;
contract checks add external callers to the same invocation. Python targets exclude
hidden directories, `__pycache__`, `build`, `dist`, and symlinks. Semgrep handles
import aliases and literal dynamic imports; the adapter resolves relative names.
Reflective and dynamically constructed names are not fully resolvable statically.

The engine is located through the installed distribution and receives an explicit
JSON target manifest. Its version is pinned because the native format is
version-specific. Native findings are not filtered by inline suppression. Parse
errors, incomplete scans, timeouts, and native failures are evaluation errors.
`imports.semgrep` contains fact-extraction patterns; its extension excludes it from
Fitness's recursive YAML-definition loader.

Dependency analysis includes conditional and `TYPE_CHECKING` imports in `src/`.
Runtime and optional requirements are checked regardless of environment markers.
`packaging` normalizes distribution names; explicit `module_mapping` entries map
them to top-level imports. Unknown mappings are errors. Build-system metadata is
inspected separately when formatting dependency findings.

### Commit analysis

The commit adapter uses `git diff --cached --no-renames -z`, including deletions and
both sides of renames. See the [commit policies](../fitness/functions/versioncontrol.yaml).

## Open prototype questions

- Generate native configuration versus reference existing tool configuration.
- File-level defaults for type/tool.
- Config merging, conflicting selections, and compatible adapter batching.
- Whether shared rule-ID budgets are sufficient for independent expectations.
- Richer completion/error reporting and partial failures.
