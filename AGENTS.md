# AGENTS.md

Repository conventions for AI coding agents (Claude Code, Codex, Cursor, Gemini
CLI, Aider, Copilot, and any other AGENTS.md-aware tool). Human contributors
should read [CONTRIBUTING.md](./CONTRIBUTING.md), which this file does not
replace.

## What this repository is

ClaimLens decides whether submitted photographs support, contradict, or fail to
substantiate a damage claim about a car, laptop, or package. Three layers:
pure-Python preprocessing → one structured vision-model call per claim (via
vortex-ai-gateway, run in-process over ASGI) → a deterministic rule layer that
produces the output row.

The design constraint that everything else follows from: **the model observes,
the rules decide.** Read [docs/architecture.md](./docs/architecture.md) before
changing anything in `src/claimlens/rules/` or `src/claimlens/prompts.py`.

## Before you change code

Run the offline checks and note the numbers — they are your regression baseline:

```bash
uv run pytest
uv run claimlens dryrun --set sample     # claim count, image blocks, cache keys
uv run claimlens validate                # per-column accuracy on cached rows
```

If `claimlens validate` reports **0 cached rows** after your change, you
invalidated `.cache/` — which holds paid model responses. That is almost always a
mistake. The cache key covers provider, model, `prompt_version`, the prompt text
and the image content hashes, so touching prompt strings or model config
invalidates it.

## Rules

**Do not spend money without being asked.** `claimlens smoke`, `claimlens run` and
`claimlens evaluate` make real API calls. Every other command is free. Default to
the free ones.

**Do not edit prompts in place.** `prompt_version` is part of the cache key and
the evaluation report describes specific versions. Add a new version; do not
rewrite `v2`.

**Keep the rule layer pure.** No network, no file I/O, no clock in
`src/claimlens/rules/`. `decide()` must stay a pure function of its two arguments.

**Never restate an enum.** `src/claimlens/enums.py` is the runtime source of truth
for allowed values. Import from it. If you change a value there, update
[docs/data-contract.md](./docs/data-contract.md) in the same change.

**Test the invariant, not just the line.** The five invariants in the
[README](./README.md) are properties of `decide()`. Any change to it needs a test
that fails if the invariant breaks. For bug fixes, write that test first and watch
it fail.

**Never touch secrets.** `.env` holds a real API key. Do not read it, print it,
copy it into code, or include it in any output. `configs/default.yaml` may only
ever name an environment variable, never hold a value.

**Do not commit or push unless asked.**

## Before you report done

```bash
make check
```

That runs tests, lint, format check, the offline dryrun and CSV verification.
Report the actual output. If something fails or you skipped a step, say so
plainly rather than describing the intent.
