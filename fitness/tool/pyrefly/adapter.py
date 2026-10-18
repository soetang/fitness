"""Translate configured Pyrefly diagnostics into individual Fitness findings."""

import json
import subprocess
import sys

from pydantic import JsonValue


def _selection_flags(selections: list[list[str] | None]) -> list[str]:
    """Restrict diagnostics only when every function selects explicit rules."""
    rules = sorted({rule for selection in selections for rule in selection or []})
    flags = [f"--error={rule}" for rule in rules]
    if rules and None not in selections:
        flags.extend(f"--only={rule}" for rule in rules)
    return flags


def _normalize_findings(result: subprocess.CompletedProcess[str]) -> list[dict[str, JsonValue]]:
    """Translate native diagnostics without treating process errors as violations."""
    if result.returncode not in (0, 1):
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    findings = [
        {
            "tool": "pyrefly",
            "rule_id": item["name"],
            "tool_message": f"{item['name']}: {item['description']}",
            "filename": item["path"],
            "location": {"row": item["line"], "column": item["column"]},
        }
        for item in json.loads(result.stdout)["errors"]
    ]
    if result.returncode and not findings:
        sys.stderr.write(result.stderr or "Pyrefly failed without diagnostics\n")
        raise SystemExit(2)
    return findings


def main() -> None:
    request = json.load(sys.stdin)
    selections = request["selections"]
    if request["config"] or any(item["config"] for item in selections):
        raise ValueError("Pyrefly config mapping is not supported; use pyproject.toml")
    flags = _selection_flags([item["rules"] for item in selections])
    result = subprocess.run(
        [
            "pyrefly",
            "check",
            "--config",
            "pyproject.toml",
            "--output-format",
            "json",
            *flags,
            *sys.argv[1:],
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    print(json.dumps(_normalize_findings(result)))


if __name__ == "__main__":
    main()
