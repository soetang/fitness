"""Translate configured Pyrefly diagnostics into individual Fitness findings."""

import json
import subprocess
import sys


def main() -> None:
    request = json.load(sys.stdin)
    selections = request["selections"]
    if request["config"] or any(item["config"] for item in selections):
        raise ValueError("Pyrefly config mapping is not supported; use pyproject.toml")
    rules = sorted({rule for item in selections for rule in item["rules"] or []})
    flags = [f"--error={rule}" for rule in rules]
    if rules and all(item["rules"] is not None for item in selections):
        flags.extend(f"--only={rule}" for rule in rules)
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
    print(json.dumps(findings))


if __name__ == "__main__":
    main()
