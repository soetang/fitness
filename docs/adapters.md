# Writing an adapter

An adapter runs a native tool and translates its diagnostics into Fitness
findings. Keep tool-specific rule selection and configuration handling here;
the core maps reported `tool` + `rule_id` values exactly.

## Layout

Give each adapter its own folder, with colocated tests:

```text
tool/
  example/
    adapter.py
    test_adapter.py
  conftest.py
```

Register its command in `fitnessfunctions/tools.yaml`:

```yaml
tools:
  example:
    command: [uv, run, --no-sync, python, tool/example/adapter.py]
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

[`tool/ruff/adapter.py`](../tool/ruff/adapter.py) accepts native rule IDs and
families such as `F`, `UP`, and `SIM`. Across the selected invocation, the most
specific matching selector wins: `F401` before `F4` before `F`; `ALL` is least
specific. It emits that selector as `rule_id` and retains the concrete native
code in the message, such as `F401: Imported module is unused.`

Tool config becomes top-level Ruff settings; function config becomes settings
under `lint`. The adapter encodes these as TOML overrides. Compatible settings
are combined into one invocation; conflicting settings produce an error.

For example, the dataclass restriction in
[`fitnessfunctions/architecture.yaml`](../fitnessfunctions/architecture.yaml) selects `TID251` and
supplies `flake8-tidy-imports.banned-api` settings on the fitness function.

## Testing

Use shared fixtures from [`tool/conftest.py`](../tool/conftest.py) and real
subprocesses, with no mocks. Cover clean output, individual findings, rule
selection, configuration, and execution failures. Run `just check` after changes.

Adapter changes may share a commit with definition changes, but not with changes
to `src/` or `tests/`. See the
[development reference](reference.md#checking-fitness-itself) for the retained
runner and staged-commit checks.
