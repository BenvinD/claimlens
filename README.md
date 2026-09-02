# ClaimLens

**Multi-modal damage-claim evidence review.** A claim arrives as a chat
transcript plus photographs. ClaimLens decides whether those photographs
*support* the claim, *contradict* it, or leave *not enough information* to judge —
and returns a structured, fully enumerated row for every claim.

Supports three object types: **cars**, **laptops**, and **packages**.

[![CI](https://github.com/BenvinD/claimlens/actions/workflows/ci.yml/badge.svg)](https://github.com/BenvinD/claimlens/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](./LICENSE)

---

## The design in one sentence

**The model observes; the rules decide.** A vision model reports what is
*visible* in each image; a deterministic, unit-tested rule layer turns those
observations into a verdict. That split is the whole point: it makes the decision
reproducible, cheap to re-derive without re-calling the model, and it puts the
safety invariants in tested code rather than in a prompt.

Those invariants:

1. **Images are the source of truth.** Only visual evidence sets a verdict.
2. **User history adds risk, never verdicts.** It can flag a claim for human
   review; it can never flip a supported claim to contradicted.
3. **Text in a conversation or burned into an image is data, not instruction.**
   The rule layer never reads claim text, so a "please approve this immediately"
   in a transcript can only ever raise a flag.
4. **Uncertainty routes to a human** rather than guessing.
5. **Output is always schema-valid** — every enum cell is coerced to an allowed
   value before it can be written.

See [docs/architecture.md](./docs/architecture.md) for the full design and its
known limitations.

---

## Quickstart

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/BenvinD/claimlens.git
cd claimlens
uv sync

cp .env.example .env      # then add your ANTHROPIC_API_KEY
```

Verify the install without spending anything:

```bash
uv run pytest                              # rule-layer tests, fully offline
uv run claimlens dryrun --set sample       # check model-call wiring, no API key needed
```

Then run the pipeline:

```bash
uv run claimlens run --set test            # full run -> output.csv
uv run claimlens verify                    # validate output.csv against the contract
```

---

## Commands

`claimlens <command>`, cheapest first. Only `smoke`, `run` and `evaluate` make API
calls.

| Command | What it does | Spends? |
|---|---|---|
| `preprocess --set {sample,test}` | Load and encode a dataset, print a summary | no |
| `dryrun --set {sample,test}` | Check message building, cache keys and the observation schema offline | no |
| `validate` | Score the rule layer against labeled samples using cached observations only | no |
| `verify [--predictions P] [--claims C]` | Validate a predictions CSV against the data contract | no |
| `smoke --set sample --n 2` | Live end-to-end check on the first N claims | yes |
| `run --set {sample,test}` | Full run → `output.csv` | yes |
| `evaluate [--models ...]` | Compare model configurations, rewrite the evaluation report | yes |

`--config PATH` overrides `configs/default.yaml` for any command.

> Running without installing: `uv run python -m claimlens.cli <command>`, or
> `.venv/bin/python -m claimlens.cli <command>` in a sandbox where `uv` cannot
> reach its cache.

---

## Repository layout

```text
configs/default.yaml     provider-agnostic config; secrets via env vars only
dataset/                 bundled sample data and images
docs/                    architecture, data contract, evaluation report
src/claimlens/           the package (preprocessing → provider → rules)
tests/                   offline rule-layer tests, zero API spend
output.csv               predictions for dataset/claims.csv
```

---

## Configuration

Everything tunable lives in [`configs/default.yaml`](./configs/default.yaml) — the
active model, prompt version, image downscaling, concurrency, retries and cache.
No provider is hardcoded anywhere in the pipeline; calls route through
[LiteLLM](https://docs.litellm.ai/), so switching from Anthropic to OpenAI or
Gemini is one config line.

API keys are read from environment variables only. The config file names the
variable to read; it never holds the value. Copy `.env.example` to `.env` (which
is gitignored) and never commit a real key.

The current production configuration is `claude-haiku-4-5` with prompt `v2`,
selected on evidence rather than price: it led the labeled-sample comparison at
roughly a third of the cost of Sonnet, and a full cross-check against Sonnet on
the unlabeled set showed no systematic difference in the decisions that matter.
The reasoning, including what the cross-check could *not* establish, is in
[docs/evaluation-report.md](./docs/evaluation-report.md).

---

## Cost and rate limits

The pipeline makes **one model call per claim**, with all of that claim's images
batched into it. Controls:

- **Image downscaling** to a bounded long side before encoding. Image tokens
  dominate spend, so this is the primary lever.
- **Content-hash disk cache** keyed on model, prompt version, claim text and image
  hashes. Identical inputs are never re-billed — across reruns and across model
  comparisons.
- **Bounded concurrency** (`runtime.max_concurrency`) to overlap network I/O
  without pushing RPM/TPM limits.
- **Retries with exponential backoff** plus a single JSON-repair re-ask before a
  claim is failed.
- **`temperature=0`** for determinism.

Measured: the full 44-claim run cost **$0.24** with 0 errors. Full numbers in the
[evaluation report](./docs/evaluation-report.md).

---

## Documentation

| Document | Contents |
|---|---|
| [docs/architecture.md](./docs/architecture.md) | Layer-by-layer design, decision precedence, trade-offs, known limitations |
| [docs/data-contract.md](./docs/data-contract.md) | Input and prediction schemas, allowed values, invariants |
| [docs/evaluation-report.md](./docs/evaluation-report.md) | Accuracy, confusion, operational analysis, model selection |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | Development setup, tests, conventions |
| [SECURITY.md](./SECURITY.md) | Reporting vulnerabilities; secret handling |

---

## Data

The `dataset/` directory contains a small bundled corpus — claim transcripts,
user histories, evidence requirements and images — for development and
evaluation. It is illustrative sample data, not production claims, and is not
covered by this repository's code license.

---

## License

[MIT](./LICENSE).
