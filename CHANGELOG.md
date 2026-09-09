# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Replaced LiteLLM with `vortex-ai-gateway` as the model-calling dependency.
  `provider/litellm_provider.py` → `provider/vortex_provider.py`; the gateway is
  driven in-process over ASGI, so calls pass through its authentication, Redis
  rate limiter, response cache, routing table, per-provider circuit breaker and
  usage ledger. See `docs/migration-litellm-to-vortex.md`.
- Transport retries moved to the gateway; ClaimLens retains only the JSON-repair
  re-ask and a wait on the gateway's own `429`.
- `runtime.max_output_tokens` (4096) is now explicit rather than inherited from
  a dependency's default.
- **Breaking:** Python floor raised from 3.11 to 3.14, required by
  `vortex-ai-gateway`. 3.11-3.13 dropped from classifiers and the CI matrix.
- Gemini is commented out in `configs/default.yaml`: the gateway ships adapters
  for OpenAI, Anthropic and Ollama only.

## [1.0.0] - 2026-09-02

First public release.

### Added

- `claimlens` console script with `preprocess`, `dryrun`, `validate`, `verify`,
  `smoke`, `run` and `evaluate` subcommands.
- Three-layer pipeline: pure-Python preprocessing, a provider-agnostic
  vision-model observation call via LiteLLM, and a deterministic rule layer.
- Content-hash disk cache so identical inputs are never re-billed.
- Evaluation harness with per-column accuracy, `claim_status` confusion,
  `manual_review_required` recall and an operational cost/latency analysis.
- Offline predictions-CSV verification (`claimlens verify`) that imports its
  allowed values from `claimlens.enums` rather than restating them.
- Documentation set: architecture, data contract and evaluation report.
- CI running tests, lint, format check, offline dryrun and CSV verification.

### Changed

- Restructured to a `src/` layout installable package with `pyproject.toml`
  metadata, a `[project.scripts]` entry point and pinned dev tooling.
- Rule-layer tests converted from a script with a hand-rolled comparator to
  pytest, one test per decision path.
- Configuration moved to `configs/default.yaml`; paths resolve against the
  repository root so behaviour is identical from any working directory.
- Row-alignment `zip()` calls now pass `strict=True`, so a length mismatch
  between claims and results raises instead of silently truncating the output.
