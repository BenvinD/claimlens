# CLAUDE.md

**Read [AGENTS.md](./AGENTS.md).** It is the single source of truth for how to
work in this repository — what ClaimLens is, the checks to run before and after
a change, and the rules about spend, secrets, prompts and the rule layer. This
file exists so Claude Code finds it; it deliberately does not restate it.

Two things worth having in context from the first line:

- **The model observes; the rules decide.** A vision model reports what is
  *visible*; a pure, unit-tested rule layer turns that into the verdict. Keep
  the split.
- **`claimlens smoke`, `run` and `evaluate` spend real money. Everything else is
  free.** Default to `dryrun`, `validate`, `verify` and `pytest`.

Supporting detail loads on demand from `.claude/skills/` — architecture, rule
layer, prompts and cache, data contract, cost and secrets — and the workflows
are `.claude/commands/` (`/baseline`, `/check`, `/rule-change`,
`/new-prompt-version`, `/add-model`, `/contract-audit`).
