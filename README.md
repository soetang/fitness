# Fitness

A small CLI prototype for defining and checking fitness functions: expectations
for your codebase, with configurable violation limits.

- `fitness lint` validates definitions offline.
- `fitness check` runs tools and reports whether expectations pass.

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked
uv run fitness lint --rules tests/fixtures/definitions --verbose
uv run fitness check --rules tests/fixtures/definitions --type migration
```

Remove `--type migration` to check all example functions; the example deliberately
includes a failing expectation. Use `--rules` to point to your own YAML file or
directory.

## Development

With [just](https://just.systems/) installed:

```sh
just setup
just update-runner  # Initialize once; rerun only to deliberately update the runner.
just check
```

## TODO

Potential features, pending further design discussion:

- [ ] Select fitness functions for agent context by importance or relevant files.
- [ ] Package a skill for using Fitness and adding functions and adapters.
- [ ] Support shared and package-specific functions across multiple codebases.
- [ ] Opt into reusable fitness functions from remote Git collections.

## Documentation

- [Glossary](docs/glossary.md)
- [Definitions and CLI behavior](docs/reference.md#definitions)
- [Writing an adapter](docs/adapters.md)
- [Technical reference](docs/reference.md)
- [Contributing](docs/contributing.md)
