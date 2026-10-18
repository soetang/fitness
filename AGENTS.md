# Fitness prototype

Small Python CLI built with Typer and managed with uv. Keep changes small and
consistent with the prototype's scope: `fitness lint` and `fitness check`.

## Development

- Use uv for dependencies and Python commands.
- Use dependency injection at external boundaries; do not use mocks in tests.
- Reuse shared fixtures in `tests/fixtures/` and `tests/conftest.py`.
- Give every adapter its own `tool/<name>/` folder containing `adapter.py` and
  `test_*.py` modules. Keep shared adapter fixtures in `tool/conftest.py`.
  Layout fitness functions enforce colocated tests and detect adapter-named
  tests misplaced under `tests/`.
- Keep tool-specific behavior in integrations, not in the core.
- Use Pydantic models instead of dataclasses. The `TID251` function in
  `rules/architecture.yaml` supplies the banned-api settings to Ruff.
- `rules/architecture.yaml` may contain only fitness functions with
  `type: architecture`; the layout adapter enforces this project-specific rule.
- Reference native diagnostic IDs or supported selectors in `rules`. Omit `rules` to count every
  diagnostic from a tool's configured checks; an empty list is invalid.
- Keep this project's Ruff selection in the YAML fitness functions, not in
  `pyproject.toml`. Ruff opts into `rule_matching: prefix` so `E`, `F`, and `I`
  select entire rule families. Other tools default to exact matching.
  The general lint function uses selectors without duplicating
  rules assigned to dedicated functions.
- Omit guidance for general Ruff and Pyrefly functions; native messages suffice.
- Do not use blanket `# noqa` suppressions. Rule-specific `# noqa: <rule>`
  directives are allowed. Enforce this through Ruff's native `PGH004` rule.
- Disallow explicit and implicit `Any` using Pyrefly's configured checks.
- Preserve unsettled design choices as open questions in the README.
- Run `just check` after changes. It runs pytest with required 100% line and
  branch coverage, Fitness lint/check using the retained wheel, and formatting checks.
- For self-checking this package, always use `just self-check` or `just check`.
  Never run the self-check CLI from the editable source tree or automatically
  rebuild/refresh its wheel during normal checks. Keep a retained runner snapshot.
  Use `just update-runner` explicitly to initialize or replace it after tests pass;
  `just build` builds a candidate separately without changing the runner.
  The adapters in `tool/` inspect the current working tree
  with the project's locked development tools and native configuration.
- Use `just fmt` to fix lint/formatting issues, then rerun `just check`.
- Stage and commit cohesive units of work separately; avoid accumulating unrelated
  changes into one large commit.
- A commit may change `rules/` and `tool/` together, or `src/` and `tests/`
  together, but must not mix these groups. Other paths are neutral. Stage the
  intended commit, then run `just check` before committing; the commit fitness
  function checks the Git index, including additions, modifications, and deletions.

## Glossary

Terminology agreed in the fitness-format design session:

- **Fitness function**: an expectation defined by the user. Prefer this term over
  calling our definitions “rules.” Each function requires a short title.
- **Type**: one user-defined classification per function, such as architecture,
  security, maintainability, or problem. Not a fixed enum or multiple labels.
- **Tool**: a named command definition referenced by functions. Integrations
  interpret native configuration and translate results into common findings.
- **Tool rule / rule ID**: an identifier understood by a tool, such as Ruff's
  `TID251`. A fitness function can reference multiple IDs through `rules`.
- **Guidance**: optional plain-text advice that supplements tool messages,
  explaining the expectation and helping with prevention or correction.
- **Finding**: an individual reported offender, with required `tool`, `rule_id`,
  and `tool_message`, plus optional `filename` and `location`. Tools return a flat
  JSON array; the core maps findings to functions by tool and rule ID.
- **Violation count**: the number of findings mapped to a function. A finding
  counts toward every matching function when references overlap.
- **Violation limit**: a fixed nonnegative integer in the definition, defaulting
  to zero. One shared limit covers all referenced rule IDs. A function passes
  when its count is at or below its limit. Lowering the limit is an explicit edit;
  there is no automatic baseline or ratchet.
- **Not automated**: a valid function that omits `tool`. It is not evaluated or
  reported as passed.
- **Error**: invalid configuration or inability to evaluate, distinct from
  violations. The current completion/error protocol is provisional.
- **Lint**: offline validation of definition shape and references. Never invokes
  tools to validate native rule IDs or settings. Overlapping references are
  allowed and produce a warning.
- **Check**: execute integrations for selected automated functions, map findings,
  and compare counts with limits. Nonautomated functions remain explicitly marked.
- **Config**: tool-specific settings interpreted by the integration. Tool config
  is invocation-wide; function config describes function-specific native settings.
  Native thresholds determine what is a finding; `limit` determines how many
  findings are acceptable.

Functions have no explicit IDs; identify them by their source definition file and
line. Tool output contains no function references or titles. A failed test does
not inherently equal one violation: integrations must report individual offenders.

See `README.md` for the current YAML format, provisional execution contract, and
open prototype questions.
