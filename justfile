default:
    @just --list

setup:
    uv sync --locked

test:
    uv run pytest

lint:
    uvx --from ./dist/self-check/fitness-0.1.0-py3-none-any.whl fitness lint --rules rules
    uv run ruff format --check .

fmt:
    uv run ruff check --fix .
    uv run ruff format .

typecheck:
    uv run pyrefly check

build:
    uv build --wheel

# Explicitly replace the retained runner only after the source tests pass.
update-runner: test
    uv build --wheel --out-dir dist/self-check
    uvx --refresh --from ./dist/self-check/fitness-0.1.0-py3-none-any.whl fitness --help

# uvx installs the wheel into an isolated tool environment, never the editable project.
self-check:
    @test -f ./dist/self-check/fitness-0.1.0-py3-none-any.whl || { echo 'Run just update-runner once to initialize the retained CLI.' >&2; exit 1; }
    uvx --from ./dist/self-check/fitness-0.1.0-py3-none-any.whl fitness lint --rules rules --verbose
    uvx --from ./dist/self-check/fitness-0.1.0-py3-none-any.whl fitness check --rules rules

check: test self-check
    uv run ruff format --check .
