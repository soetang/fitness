"""Batch selected functions into adapter requests and validate their findings."""

import json
from collections.abc import Callable

from pydantic import TypeAdapter, ValidationError

from fitness.contracts import Finding, FitnessError, FitnessFunction, Function, Tool

ExecuteAdapter = Callable[[list[str], str | None], str]


def encode_request(tool: Tool, functions: list[Function]) -> str | None:
    """Encode selected rules and configuration when the tool accepts input.

    Args:
        tool: Adapter configuration and input preference.
        functions: Selected functions evaluated by this adapter.
    """
    if not tool.send_input:
        return None
    return json.dumps(
        {
            "config": tool.config,
            "selections": [{"rules": f.rules, "config": f.config} for f in functions],
        }
    )


def run_selected_tool(
    name: str, tool: Tool, functions: list[Function], execute_adapter: ExecuteAdapter
) -> list[Finding]:
    """Execute one tool and reject malformed or incorrectly attributed findings.

    Args:
        name: Registered tool name expected on every returned finding.
        tool: Adapter command and configuration.
        functions: Selected functions to send in the request.
        execute_adapter: Transport accepting command and optional request text.

    Raises:
        FitnessError: Execution or validation fails, with the tool identified.
    """
    try:
        output = execute_adapter(tool.command, encode_request(tool, functions))
        findings = TypeAdapter(list[Finding]).validate_json(output)
        if any(f.tool != name for f in findings):
            raise FitnessError("finding tool does not match the invoked tool")
    except (ValidationError, FitnessError) as error:
        raise FitnessError(f"tool {name!r}: {error}") from error
    return findings


def collect_findings(
    tools: dict[str, Tool], selected: list[FitnessFunction], execute_adapter: ExecuteAdapter
) -> list[Finding]:
    """Invoke each selected adapter once, preserving tool and finding order.

    Args:
        tools: Registered adapters in invocation order.
        selected: Functions remaining after classification filtering.
        execute_adapter: Transport used to run each selected adapter.
    """
    findings = []
    for name, tool in tools.items():
        functions = [f.function for f in selected if f.function.tool == name]
        if functions:
            findings.extend(run_selected_tool(name, tool, functions, execute_adapter))
    return findings
