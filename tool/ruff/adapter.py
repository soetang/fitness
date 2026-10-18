"""Translate configured Ruff diagnostics into individual Fitness findings."""

import json
import subprocess
import sys


def main() -> None:
    request = json.load(sys.stdin)
    selections = request["selections"]
    if request["config"] or any(item["config"] for item in selections):
        raise ValueError("Ruff config mapping is not supported; use pyproject.toml")
    rules = sorted({rule for item in selections for rule in item["rules"] or []})
    flags: list[str] = []
    if rules:
        flag = (
            "--extend-select" if any(item["rules"] is None for item in selections) else "--select"
        )
        flags = [flag, ",".join(rules)]
    result = subprocess.run(
        ["ruff", "check", "--output-format", "json", *flags, *(sys.argv[1:] or ["."])],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    findings = [
        {
            "tool": "ruff",
            "rule_id": item["code"],
            "tool_message": f"{item['code']}: {item['message']}",
            "filename": item["filename"],
            "location": item["location"],
        }
        for item in json.loads(result.stdout)
    ]
    if result.returncode and not findings:
        sys.stderr.write(result.stderr or "Ruff failed without diagnostics\n")
        raise SystemExit(2)
    print(json.dumps(findings))


if __name__ == "__main__":
    main()
