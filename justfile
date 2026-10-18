runner_dir := justfile_directory() / ".fitness-runner"
fitness_cli := runner_dir / "bin/fitness"
quiet := "sh tool/quiet.sh"

default:
    @just --list

setup:
    uv sync --locked

test:
    @{{quiet}} just _test

_test:
    @{{quiet}} --silent uv run pytest

lint:
    @{{quiet}} just _lint

_lint: _runner-ready
    @{{quiet}} --silent "{{fitness_cli}}" lint
    @{{quiet}} --silent just _format --check

fitness:
    @{{quiet}} just _fitness

_fitness: _runner-ready
    @{{quiet}} --silent "{{fitness_cli}}" check

check:
    @{{quiet}} just _test _lint _fitness

fmt:
    @{{quiet}} just _format

_format *args:
    @config=$(uv run python fitness/tool/ruff/format_config.py) && uv run ruff format --config "$config" {{args}} .

typecheck: _runner-ready
    @{{quiet}} "{{fitness_cli}}" check --type typing

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
