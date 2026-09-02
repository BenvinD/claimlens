# Contributing

Thanks for helping improve ClaimLens. This guide covers setup, the checks that
must pass, and the conventions that keep the decision layer trustworthy.

## Setup

```bash
uv sync                  # installs the package (editable) plus dev tools
cp .env.example .env     # only needed for commands that call a model
```

## The checks

Everything below runs offline, with no API key and no spend:

```bash
uv run pytest                            # rule-layer tests
uv run ruff check .                      # lint
uv run ruff format --check .             # formatting
uv run claimlens dryrun --set sample     # message building + observation schema
uv run claimlens verify                  # predictions CSV against the data contract
```

`make check` runs all of them. CI runs the same set on every push and pull
request, so a green `make check` locally means a green build.

Two commands need a real key and cost money — `claimlens smoke` and
`claimlens run`. Do not put them in CI.

## Conventions

**Enums live in one place.** `src/claimlens/enums.py` is the runtime source of
truth for every allowed output value. Never restate an allowed-value list
elsewhere — import it. If you change a value, update
[docs/data-contract.md](./docs/data-contract.md) in the same commit.

**The rule layer stays pure.** `src/claimlens/rules/` must have no network access,
no file I/O and no clock dependence. `decide()` is a pure function of
`(PreparedClaim, VLMObservation | None)`. This is what makes decisions
reproducible and testable, so keep it that way.

**Guard the invariants with tests.** The five invariants in the
[README](./README.md#the-design-in-one-sentence) are properties of the rule layer,
not of the prompt. Any change touching `decide()` needs a test that would fail if
the invariant broke. For a bug fix, write the failing test first.

**Prompts are versioned, not edited.** `prompt_version` is part of the cache key,
so editing an existing version silently invalidates cached observations and
changes results that the evaluation report describes. Add `v3` rather than
rewriting `v2`, and re-run `claimlens evaluate` if you want the report to reflect
it.

**Never commit secrets or model output caches.** `.env` and `.cache/` are
gitignored. If a key ever lands in a commit, rotate it — do not just amend.

## Adding a model

Add an entry to `models:` in `configs/default.yaml` with its `provider`, `model`,
`api_key_env` and per-million-token pricing, then compare it:

```bash
uv run claimlens evaluate --models claude-haiku your-new-model
```

Pricing in config overrides LiteLLM's built-in table, so keep it accurate — the
cost numbers in the evaluation report depend on it.

## Pull requests

- One logical change per PR, with a description of what changed and why.
- Include the output of any evaluation you ran if the change can affect
  predictions.
- Note explicitly if a change invalidates `.cache/` or the committed `output.csv`.
- Update the docs that your change makes stale.
