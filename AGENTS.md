# Fitness

!fitness context startup

- Only edit this file when the user explicitly requests it. Keep it concise.
- Keep the prototype small. Use uv, dependency injection, and no mocks.
- Rules are defined in `fitness/`. Never repeat them in documentation or instructions; link to their definitions.
- Keep tool-specific behavior in adapters. Discuss data-model and integration-contract changes first.
- Keep README.md user-facing; put technical details in `docs/`.
- Keep user docs, including `docs/adapters.md` and `docs/reference.md`, user-facing; put repository implementation details in `docs/contributing.md`.
- Keep check output minimal: report only failures/errors, or just `success` when everything passes.
- Stage cohesive changes, run `just check`, and commit related work separately.

References: [glossary](docs/glossary.md), [adapters](docs/adapters.md),
[technical reference](docs/reference.md), [contributing](docs/contributing.md).
