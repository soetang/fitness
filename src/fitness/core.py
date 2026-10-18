import json
import subprocess
from collections.abc import Callable
from itertools import combinations
from pathlib import Path
from typing import cast

import yaml
from pydantic import TypeAdapter, ValidationError

from fitness.models import Document, Finding, Function, Model, Tool


class FitnessError(Exception):
    pass


class UniqueLoader(yaml.SafeLoader):
    """Reject duplicate YAML keys instead of silently overwriting definitions."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False):
        keys = [self.construct_object(key, deep=deep) for key, _ in node.value]
        try:
            if len(keys) != len(set(keys)):
                raise FitnessError(f"duplicate YAML key at line {node.start_mark.line + 1}")
        except TypeError as error:
            raise FitnessError("YAML mapping keys must be scalar") from error
        return super().construct_mapping(node, deep=deep)


class Definition(Model):
    function: Function
    source: str


class Suite(Model):
    tools: dict[str, Tool]
    definitions: list[Definition]
    warnings: list[str]


def load(path: Path) -> Suite:
    files = (
        sorted(p for p in path.rglob("*") if p.suffix in {".yaml", ".yml"} and p.is_file())
        if path.is_dir()
        else [path]
    )
    if not files:
        raise FitnessError(f"{path}: no YAML definitions found")
    tools = {}
    definitions = []
    for file in files:
        try:
            text = file.read_text()
            document = Document.model_validate(yaml.load(text, Loader=UniqueLoader))
            node = cast(yaml.MappingNode, yaml.compose(text))
            lines: list[int] = []
            for key, value in node.value:
                if key.value == "functions":
                    lines = [item.start_mark.line + 1 for item in value.value]
            for name, tool in document.tools.items():
                if name in tools:
                    raise FitnessError(f"duplicate tool {name!r}")
                tools[name] = tool
            definitions.extend(
                Definition(function=function, source=f"{file}:{line}")
                for function, line in zip(document.functions, lines, strict=True)
            )
        except (OSError, ValueError, yaml.YAMLError, FitnessError) as error:
            raise FitnessError(f"{file}: {error}") from error
    for definition in definitions:
        function = definition.function
        if function.tool and function.tool not in tools:
            raise FitnessError(f"{definition.source}: unknown tool {function.tool!r}")
    warnings = []
    for name in tools:
        automated = [d for d in definitions if d.function.tool == name]
        for left, right in combinations(automated, 2):
            a, b = left.function.rules, right.function.rules
            if a is None or b is None or set(a).intersection(b):
                warnings.append(
                    f"{name}: {left.source} and {right.source} overlap; "
                    "shared findings count toward each function"
                )
    return Suite(tools=tools, definitions=definitions, warnings=warnings)


# Inject this boundary directly; the CLI uses the real process implementation.
Runner = Callable[[list[str], str | None], str]


def run_command(command: list[str], stdin: str | None) -> str:
    try:
        result = subprocess.run(
            command,
            input=stdin,
            stdin=subprocess.DEVNULL if stdin is None else None,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise FitnessError(str(error)) from error
    if result.returncode:
        raise FitnessError(f"exit {result.returncode}: {result.stderr.strip()}")
    return result.stdout


class Result(Model):
    definition: Definition
    findings: list[Finding]

    @property
    def status(self) -> str:
        if not self.definition.function.tool:
            return "NOT AUTOMATED"
        return "PASS" if len(self.findings) <= self.definition.function.limit else "FAIL"


def evaluate(suite: Suite, runner: Runner, type_: str | None = None) -> list[Result]:
    selected = [d for d in suite.definitions if type_ is None or d.function.type == type_]
    findings = []
    for name, tool in suite.tools.items():
        functions = [d.function for d in selected if d.function.tool == name]
        if not functions:
            continue
        payload = None
        if tool.send_input:
            payload = json.dumps(
                {
                    "config": tool.config,
                    "selections": [{"rules": f.rules, "config": f.config} for f in functions],
                }
            )
        try:
            output = runner(tool.command, payload)
            batch = TypeAdapter(list[Finding]).validate_json(output)
            if any(f.tool != name for f in batch):
                raise FitnessError("finding tool does not match the invoked tool")
        except (ValidationError, FitnessError) as error:
            raise FitnessError(f"tool {name!r}: {error}") from error
        findings.extend(batch)
    return [
        Result(
            definition=d,
            findings=[
                f
                for f in findings
                if f.tool == d.function.tool
                and (d.function.rules is None or f.rule_id in d.function.rules)
            ],
        )
        for d in selected
    ]
