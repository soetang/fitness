"""Executable fixture implementing the prototype tool contract."""

import json
import sys
from pathlib import Path

request = json.load(sys.stdin)
assert request["config"] == {"preview": True}
assert all(item["rules"] == ["API001"] for item in request["selections"])
print(Path(__file__).with_name("findings.json").read_text())
