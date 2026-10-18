runner_dir := justfile_directory() / ".fitness-runner"
fitness_cli := runner_dir / "bin/fitness"
quiet := "bash tool/quiet.sh"

default:
    @just --list

setup:
    uv sync --locked

test:
    @{{quiet}} uv run pytest

lint: _runner-ready
    @{{quiet}} "{{fitness_cli}}" lint ::: just _format --check

fitness: _runner-ready
    @"{{fitness_cli}}" check

check:
    @{{quiet}} just test ::: just lint ::: just fitness

fmt:
    @{{quiet}} just _format

_format *args:
    @config=$(uv run python fitness/tool/ruff/format_config.py) && uv run ruff format --config "$config" {{args}} .

typecheck: _runner-ready
    @"{{fitness_cli}}" check --type typing

build:
    uv build --wheel

# uv installs a built, non-editable snapshot in a dedicated environment.
update-runner:
    @{{quiet}} just test ::: uv venv --allow-existing "{{runner_dir}}" ::: uv pip install --python "{{runner_dir}}/bin/python" --reinstall-package fitness . > /dev/null
    @"{{fitness_cli}}" --help

# Normal checks reuse this installation without rebuilding it.
_runner-ready:
    @test -x "{{fitness_cli}}" || { echo 'Run just update-runner once to initialize the retained CLI.' >&2; exit 1; }
