runner_dir := justfile_directory() / ".fitness-runner"
fitness_cli := runner_dir / "bin/fitness"
quiet := "sh tool/quiet.sh"

default:
    @just --list

setup:
    uv sync --locked

test: _test
    @echo success

_test:
    @{{quiet}} uv run pytest

lint: _lint
    @echo success

_lint: _runner-ready
    @{{quiet}} "{{fitness_cli}}" lint
    @{{quiet}} just _format --check

fitness: _fitness
    @echo success

_fitness: _runner-ready
    @{{quiet}} "{{fitness_cli}}" check

check: _test _lint _fitness
    @echo success

fmt:
    @{{quiet}} just _format
    @echo success

_format *args:
    @config=$(uv run python fitness/tool/ruff/format_config.py) && uv run ruff format --config "$config" {{args}} .

typecheck: _runner-ready
    @{{quiet}} "{{fitness_cli}}" check --type typing
    @echo success

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
