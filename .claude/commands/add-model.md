---
description: Add a model to configs/default.yaml and compare it against the production baseline
argument-hint: [provider/model, e.g. "openai gpt-4o-mini"]
---

Add a model configuration and compare it honestly.

**Model to add:** $ARGUMENTS

## 1. Check the adapter exists

The gateway ships adapters for **openai, anthropic and ollama only**. Gemini has
no adapter — which is why that entry in `configs/default.yaml` is commented out
rather than left silently unroutable. If the requested provider is not one of the
three, say so and stop; adding an unroutable entry is worse than not adding it.

## 2. Add the entry

Under `models:` in `configs/default.yaml`:

```yaml
  <name>:
    provider: <openai|anthropic|ollama>
    model: <model-id>
    api_key_env: <ENV_VAR_NAME>
    input_per_mtok: <price>
    output_per_mtok: <price>
```

Two rules:

- **`api_key_env` names an environment variable. It never holds a value.** Add
  the variable to `.env.example` (documentation only) if it is not there.
- **Pricing must be accurate.** Config pricing overrides the gateway's built-in
  table, and the cost numbers in `docs/evaluation-report.md` are computed from
  it. If you are not sure of current per-million-token pricing, say so rather
  than guessing — a wrong number here silently corrupts the report.

Comment the entry the way the existing ones are commented: what it is for.

## 3. Verify offline first

```bash
uv run claimlens dryrun --set sample --config configs/default.yaml
```

Free. Confirms the config parses and the routing table builds.

## 4. Compare — this costs money

```bash
uv run claimlens evaluate --models claude-haiku <name>
```

Ask the user before running it and say what it will cost: `evaluate` re-runs
every claim once per model, and a new model means a fresh cache key, so nothing
is served from `.cache/`.

Consider `uv run claimlens smoke --set sample --n 2` first (two claims) to
confirm the model returns parseable JSON at all before paying for a full sweep.

## 5. Report

Accuracy per column and cost per model, side by side. Recommend on **evidence**,
the way the current default was chosen — `claude-haiku-4-5` is production
because it led the labeled sample (`claim_status` 85% vs Sonnet 80%) at roughly a
third of the cost, not because it was cheapest.

Do not switch `active_model` unless the user asks. Say plainly what the
comparison could *not* establish — a small labeled sample supports a narrow
claim, and `docs/evaluation-report.md` is explicit about its own limits.
