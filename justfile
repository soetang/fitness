runner_dir := justfile_directory() / ".fitness-runner"
fitness_cli := runner_dir / "bin/fitness"

default:
    @just --list

setup:
    uv sync --locked

test:
    @if output="$(uv run pytest 2>&1)"; then echo success; else status=$?; printf '%s\n' "$output"; exit "$status"; fi

lint: _runner-ready
    "{{fitness_cli}}" lint
    uv run ruff format --config "$(uv run python fitness/tool/ruff/format_config.py)" --check .

fitness: _runner-ready
    "{{fitness_cli}}" check

check: test lint fitness

fmt:
    uv run ruff format --config "$(uv run python fitness/tool/ruff/format_config.py)" .

typecheck:
    uv run pyrefly check

build:
    uv build --wheel

# uv installs a built, non-editable snapshot in a dedicated environment.
update-runner: test
    uv venv --allow-existing "{{runner_dir}}"
    uv pip install --python "{{runner_dir}}/bin/python" --reinstall-package fitness .
    "{{fitness_cli}}" --help

# Normal checks reuse this installation without rebuilding it.
_runner-ready:
    @test -x "{{fitness_cli}}" || { echo 'Run just update-runner once to initialize the retained CLI.' >&2; exit 1; }
