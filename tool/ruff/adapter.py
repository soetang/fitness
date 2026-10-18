"""Translate configured Ruff diagnostics into individual Fitness findings."""

import json
import subprocess
import sys

from pydantic import JsonValue


def overrides(config: dict[str, JsonValue], prefix: tuple[str, ...] = ()) -> dict[str, str]:
    """Encode native settings as Ruff's TOML key/value command-line overrides."""
    result: dict[str, str] = {}
    for key, value in config.items():
        path = (*prefix, key)
        if isinstance(value, dict):
            result.update(overrides(value, path))
        else:
            result[".".join(json.dumps(part) for part in path)] = json.dumps(value)
    return result


def main() -> None:
    request = json.load(sys.stdin)
    selections = request["selections"]
    settings = overrides(request["config"])
    for item in selections:
        for key, value in overrides(item["config"], ("lint",)).items():
            if key in settings and settings[key] != value:
                raise ValueError(
                    f"Conflicting Ruff settings for {key}; split incompatible selections"
                )
            settings[key] = value
    rules = sorted({rule for item in selections for rule in item["rules"] or []})
    flags: list[str] = []
    if rules:
        flag = (
            "--extend-select" if any(item["rules"] is None for item in selections) else "--select"
        )
        flags = [flag, ",".join(rules)]
    if settings:
        flags.extend(["--config", "\n".join(f"{key} = {value}" for key, value in settings.items())])
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
            "rule_id": max(
                (rule for rule in rules if rule == "ALL" or item["code"].startswith(rule)),
                key=lambda rule: 0 if rule == "ALL" else len(rule),
                default=item["code"],
            ),
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
