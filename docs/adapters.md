# Writing an adapter

An adapter runs a native tool and translates its diagnostics into Fitness
findings. Keep tool-specific rule selection and configuration handling here;
the core maps reported `tool` + `rule_id` values exactly.

## Registration

Register its command in `fitness/tool.yaml`:

```yaml
tools:
  example:
    command: [python, tools/example.py]
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

## Testing adapters

Cover clean output, individual findings, rule selection, configuration, and
execution failures. Test normalization logic directly and use real subprocesses
to verify the native tool and JSON protocol. Batch compatible cases when tool
startup is expensive.
