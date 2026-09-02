# Architecture

ClaimLens is three layers with one deliberate constraint between them: **the
model observes, the rules decide.**

```
dataset/*.csv + images
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. preprocessing            pure Python, no model calls     │
│    load CSVs → join user history → attach evidence          │
│    requirements → EXIF-correct, downscale, JPEG-encode,     │
│    base64 and content-hash every image                      │
└─────────────────────────────────────────────────────────────┘
        │ PreparedClaim
        ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. provider                 one structured call per claim   │
│    LiteLLM → any vision model. Returns a factual            │
│    VLMObservation ("what is in each image"), never a         │
│    verdict. Content-hash disk cache, bounded concurrency,    │
│    retries, one JSON-repair re-ask, Pydantic enum coercion   │
└─────────────────────────────────────────────────────────────┘
        │ VLMObservation
        ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. rules                    deterministic, unit-tested      │
│    Maps observations to the 14 output columns under fixed    │
│    invariants. No model involved; no network; pure function  │
└─────────────────────────────────────────────────────────────┘
        │ OutputRow
        ▼
    output.csv
```

## Why observe-then-decide

The obvious alternative is to ask the model for the 14 output columns directly.
This design refuses that, and pays for it in code, for three reasons:

- **The invariants become enforceable.** "User history never flips a supported
  claim" is a property of a pure function you can unit-test, not a sentence in a
  prompt you hope the model honours.
- **Decisions are reproducible and debuggable.** Given a cached observation, the
  same input always yields the same row. You can change decision logic and re-score
  without paying to re-call the model — that is what `claimlens validate` does.
- **Prompt injection loses its target.** The rule layer never reads `user_claim`
  at all. Instruction text in a conversation or burned into an image can only ever
  set `text_instruction_present`.

The cost: a hand-written rule layer that must track label semantics, and which can
lag real-world variety. That is the trade made knowingly.

## Layout

```text
.
├── configs/default.yaml         # provider-agnostic config; secrets via env only
├── dataset/                     # bundled sample data + images
├── docs/
│   ├── architecture.md          # you are here
│   ├── data-contract.md         # input/output schema and allowed values
│   └── evaluation-report.md     # accuracy, ops analysis, model selection
├── src/claimlens/
│   ├── cli.py                   # `claimlens` console script
│   ├── config.py                # typed config loader + repo-root path resolution
│   ├── enums.py                 # allowed output values (runtime source of truth)
│   ├── schema.py                # typed input / prepared records
│   ├── observation.py           # structured model-observation schema
│   ├── prompts.py               # versioned system/user prompts (v1, v2)
│   ├── verify.py                # offline predictions-CSV validation
│   ├── preprocessing/           # CSV loaders, image encoding, join pipeline
│   ├── provider/                # provider interface, LiteLLM impl, cache, runner
│   ├── rules/                   # decision engine + CSV writer
│   └── evaluation/              # scoring harness, metrics, report renderer
└── tests/                       # offline rule-layer tests (zero API spend)
```

## Layer 1 — preprocessing

`prepare_dataset(which, cfg)` returns a list of `PreparedClaim`, each carrying
everything the model call needs so no further disk access is required.

- **CSV loading** uses the stdlib `csv` module so multi-line, comma-bearing quoted
  `user_claim` cells parse as a single field.
- **History join** is `history_map.get(user_id)` — a missing user yields `None`,
  never an exception.
- **Evidence requirements** are filtered to rows whose `claim_object` matches the
  claim or is `all`.
- **Image encoding** applies `ImageOps.exif_transpose` (honouring camera
  rotation), converts to RGB, downscales with LANCZOS so the long side is at most
  `image.max_long_side`, saves JPEG at `image.jpeg_quality`, then computes a
  SHA-256 of the encoded bytes and a `data:` URL. A missing or undecodable file
  becomes an `EncodedImage` with `exists=False` / `error=...` — it never raises,
  so one bad file cannot take down a batch.

Downscaling is the primary cost lever: image tokens dominate vision-model spend,
and most claim damage is assessable at 1024px. Very fine damage — a hairline
scratch — is the known casualty.

## Layer 2 — the provider

One call per claim, all of that claim's images batched as content blocks in that
single call.

- **Provider-agnostic.** Every call goes through `litellm.completion` with a model
  id built from config as `provider/model`. One OpenAI-style message format works
  across Anthropic, OpenAI and Gemini, so comparing two models is a config change
  rather than a code change. Pricing is overridden in config so cost accounting
  stays authoritative rather than depending on a third-party table.
- **Untrusted input is fenced.** The system prompt declares the conversation and
  any in-image text to be data, to be flagged and never obeyed; the user message
  fences the transcript in a delimited block. Fencing is defence in depth, not the
  defence — the rule layer's indifference to claim text is.
- **Content-hash cache.** The key is a SHA-256 over provider, model, prompt
  version, system prompt, user text and the sorted image content hashes. Identical
  inputs are never re-billed, across reruns and across model comparisons. Note the
  key does *not* include runtime parameters or an observation-schema version, so
  changing those requires clearing `.cache/`.
- **Bounded concurrency.** A `ThreadPoolExecutor` sized by
  `runtime.max_concurrency` overlaps blocking network I/O while capping RPM/TPM
  pressure. Results are stored by original index, so ordering is preserved and a
  worker exception becomes an error result rather than aborting the batch.
- **Structured output, then validation.** The prompt asks for a single JSON
  object; extraction strips code fences and falls back to the outermost `{...}`
  slice; one repair turn re-asks for JSON only; then Pydantic validates, coercing
  every enum field to a legal value or `unknown`. A hallucinated enum cannot reach
  the rule layer, and total failure degrades to a safe
  `not_enough_information` row rather than a crash.

## Layer 3 — the rules

`decide(claim, observation)` is a pure function. Branch order *is* precedence:

1. **Provider failure** (no observation) → `not_enough_information`,
   `evidence_standard_met=false`, `valid_image=false`, always
   `manual_review_required`. No visual evidence exists, so no verdict is possible.
2. **Assessability gate** — if no image shows the claimed part, shows damage, or
   shows a different object, nothing about the claim can be seen →
   `not_enough_information`, `damage_not_visible`.
3. **Support test** — an image supports the claim if it matches the claim object,
   shows damage, the issue type is compatible (same value or same issue family:
   dent/scratch, crack/glass_shatter, broken/missing part, torn/crushed packaging,
   water_damage/stain), and the damage is on a claimed part *or* on the visible
   claimed part that the model left unnamed. **Exaggeration** — support exists, the
   customer stated high severity, but observed severity is none or low.
4. **Supported** — support and no exaggeration. The decisive image is the most
   severe one.
5. **Otherwise contradicted or NEI**, in order: exaggeration → contradicted
   (`claim_mismatch`); wrong object → contradicted (`wrong_object`); claimed part
   visible and undamaged → contradicted (`damage_not_visible`, `issue_type=none`);
   damage on an unclaimed part → contradicted (`wrong_object_part`); nothing
   decisive → `not_enough_information`.

Cross-cutting:

- **`risk_flags`** accumulate from image quality flags, authenticity flags,
  injection detection, contradiction cues and user history, then render in a
  stable canonical order.
- **`manual_review_required`** is added when history flags risk, an authenticity
  flag lands on the decisive image, or `wrong_object` / `possible_manipulation` is
  present.
- **`valid_image`** is a usability signal, never a decision input.
- **`severity`** comes only from observed image severity — never from the
  customer's adjectives. A supported row can therefore read `severity=unknown`
  when the model reported damage without a severity.

### Why history can never flip a verdict

`claim_status` is assigned in exactly five places: the provider-failure branch,
the assessability gate, the support/exaggeration test, and the four visual
branches of the contradiction path. None of those conditions reference history or
authenticity flags — those enter only through the additive risk set. The guarantee
is structural, not stylistic.

## Configuration

Everything tunable lives in [`configs/default.yaml`](../configs/default.yaml):

| Key | Effect |
|---|---|
| `active_model` | Which entry in `models:` to use |
| `models.<name>` | `provider`, `model`, `api_key_env`, per-million-token pricing |
| `prompt_version` | System/user prompt version (`v2` is current) |
| `image.max_long_side`, `image.jpeg_quality` | Downscaling — the main cost lever |
| `runtime.*` | Temperature, concurrency, retries, timeout |
| `cache.*` | Content-hash cache location and on/off |
| `paths.*` | Dataset and output locations, resolved against the repo root |

API keys are read from environment variables only, named — never held — by the
config file. `prompt_version` and the model are part of the cache key, so changing
either invalidates cached observations by design.

## Known limitations

Tracked honestly rather than hidden:

- **`evidence_standard_met` does not read the requirement text.** Evidence
  requirements are loaded, joined and placed in the prompt, but the deterministic
  gate only checks visibility and damage presence. Requirement satisfaction is
  effectively delegated to the model's visibility judgement. This is the first
  thing worth fixing.
- **`supporting_image_ids` reports one image.** The decisive-image selector
  returns only the most severe match, though the contract allows several.
- **Severity is the weakest column.** Models over-read severity; the rule layer
  passes observed severity through, so calibration belongs in the prompt.
- **NEI paths add history-driven manual review but not authenticity-driven.** A
  manipulated-but-indeterminate claim can land in NEI without
  `manual_review_required`.
- **Paths resolve relative to a source checkout.** `REPO_ROOT` is derived from the
  package location, so `configs/` and `dataset/` are found when running from a
  clone (including an editable install). A non-editable install into
  `site-packages` would need `--config` and absolute `paths:` entries.
