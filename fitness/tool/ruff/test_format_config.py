import subprocess
import sys
import tomllib
from pathlib import Path


def test_renders_shared_runtime_controls(tmp_path: Path):
    folder = tmp_path / "fitness"
    folder.mkdir()
    (folder / "tool.yaml").write_text("""
tools:
  ruff:
    config:
      line-length: 100
      preview: true
      extend-exclude: [.fitness-runner]
""")
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("format_config.py"))],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert tomllib.loads(result.stdout) == {
        "line-length": 100,
        "preview": True,
        "extend-exclude": [".fitness-runner"],
    }
