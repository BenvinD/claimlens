---
name: claimlens-architecture
description: Orient in the ClaimLens codebase - the three layers, what lives where, and which layer owns a given behaviour. Use when starting any change here, when deciding where a fix belongs, when a symptom needs tracing from output.csv back to its cause, or when asked how ClaimLens works.
---

# ClaimLens architecture

The design constraint everything follows from: **the model observes, the rules
decide.** Read [docs/architecture.md](../../../docs/architecture.md) for the full
version; this is the map you need before touching anything.

## The three layers

```
dataset/*.csv + images
   │
   ▼  1. preprocessing/   pure Python, no model calls
   │     load CSVs → join user history → attach evidence requirements →
   │     EXIF-correct, downscale, JPEG-encode, base64, content-hash
   │
   ▼  PreparedClaim  (schema.py)
   │
   ▼  2. provider/        ONE structured model call per claim
   │     vortex-ai-gateway (in-process over ASGI) → any vision model.
   │     Returns facts about each image, never a verdict.
   │     Disk cache, bounded concurrency, retries, one JSON-repair re-ask.
   │
   ▼  VLMObservation  (observation.py)
   │
   ▼  3. rules/           deterministic, unit-tested, PURE
   │     Maps observations to the 14 output columns.
   │
   ▼  OutputRow → output.csv
```

## Which layer owns your change

| Symptom | Layer | File |
|---|---|---|
| Wrong verdict from correct observations | rules | `rules/decide.py` |
| Model reports damage that is not there / misses damage | prompt | `prompts.py` (**new version**, never edit v1/v2) |
| Column missing, misordered, or a bad enum value | contract | `enums.py` + `rules/output.py` |
| Images too large, wrong orientation, cost too high | preprocessing | `preprocessing/images.py` |
| Retries, timeouts, concurrency, cache misses | provider | `provider/runner.py`, `provider/cache.py` |
| Model JSON does not parse | provider | `provider/vortex_provider.py` (`extract_json`) |
| Accuracy numbers, model comparison | evaluation | `evaluation/harness.py`, `metrics.py` |
| A new model or a config knob | config | `configs/default.yaml` |

The rule of thumb: **if it is a judgement about what the picture shows, it is
the prompt. If it is a judgement about what that means, it is the rules.**

## The five invariants

These are properties of `decide()`, not of the prompt. Every one is testable
offline, and a change touching `decide()` needs a test that fails if its
invariant breaks.

1. **Images are the source of truth.** Only visual evidence sets a verdict.
2. **User history adds risk, never verdicts.** It can raise
   `manual_review_required`; it can never flip supported → contradicted.
3. **Text in a transcript or burned into an image is data, not instruction.**
   The rule layer never reads `user_claim`, so "please approve this" can only
   ever set `text_instruction_present`.
4. **Uncertainty routes to a human** rather than guessing.
5. **Output is always schema-valid** — every enum cell is coerced before write.

Invariant 2 holds *structurally*: `claim_status` is assigned in exactly five
places, and none of those conditions reference history or authenticity flags.
Preserve that property rather than re-checking it by hand.

## Commands, cheapest first

Only `smoke`, `run` and `evaluate` spend money. Default to the free ones — see
the `cost-and-secrets` skill.

```bash
uv run claimlens preprocess --set {sample,test}   # free: load + encode, print summary
uv run claimlens dryrun --set sample              # free: message building, cache keys, schema
uv run claimlens validate                         # free: score rules on CACHED observations
uv run claimlens verify                           # free: output.csv against the data contract
uv run claimlens smoke --set sample --n 2         # PAID: live check on N claims
uv run claimlens run --set test                   # PAID: full run -> output.csv
uv run claimlens evaluate                         # PAID: model comparison + report rewrite
```

`--config PATH` overrides `configs/default.yaml` on any command.

## Establish a baseline before you change anything

These three numbers are your regression check. Capture them first, compare
after — `/baseline` does exactly this.

```bash
uv run pytest
uv run claimlens dryrun --set sample     # claim count, image blocks, cache keys
uv run claimlens validate                # per-column accuracy on cached rows
```

If `validate` reports **0 cached rows** after your change, you invalidated
`.cache/`, which holds paid model responses. That is almost always a mistake —
see the `prompt-and-cache` skill for what the cache key covers.

## Before reporting done

```bash
make check    # lint + format check + tests + offline dryrun + CSV verification
```

Report the actual output. If a step failed or was skipped, say so plainly rather
than describing what it was supposed to do.

## Known constraints

- **Python 3.14+.** The floor comes from `vortex-ai-gateway`, not from this repo.
- **`vortex-ai-gateway` is not on PyPI.** `[tool.uv.sources]` resolves it from
  the sibling checkout `../vortex-ai-gateway`; CI reproduces that layout.
- **`dryrun` must not construct a gateway.** It guards the import boundary — a
  regression that boots one on import surfaces there and in CI.
