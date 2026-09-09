# Migrating ClaimLens from LiteLLM to vortex-ai-gateway

Status: **done**, with four gaps listed at the bottom. Migrated 2026-09-09.

## What changed

`litellm` was a pip dependency this repository imported and called.
`vortex-ai-gateway` now occupies exactly that slot — same position in
`pyproject.toml`, same import-and-call shape from `provider/`. Nothing about
the pipeline's structure moved: preprocessing, the one-observation-call-per-claim
contract, the disk cache, the batch runner and the deterministic rule layer are
untouched.

| | before | after |
|---|---|---|
| dependency | `litellm>=1.89.2` | `vortex-ai-gateway>=0.0.1a1` |
| module | `provider/litellm_provider.py` | `provider/vortex_provider.py` |
| class | `LiteLLMProvider` | `VortexProvider` |
| call | `litellm.completion(model="anthropic/claude-haiku-4-5", ...)` | `POST /v1/chat/completions` with `model="claude-haiku-4-5"` |
| model selection | `provider/model` string | routing table derived from `models` in `configs/default.yaml` |
| pricing fallback | `litellm.completion_cost` | `vortex_ai_gateway.pricing.PriceTable` |
| Python floor | `>=3.11` | `>=3.14` |

## Why the gateway runs in-process

The gateway is a FastAPI application, and everything that makes it a *gateway*
rather than a client library — authentication, the Redis rate limiter, the
response cache, the usage ledger — lives in its route layer. Importing
`AnthropicAdapter` directly would have skipped all of it and delivered little
more than LiteLLM already did.

So `VortexProvider` drives the real application over ASGI
(`httpx.ASGITransport`), on a single event loop pinned to a daemon thread. Every
call goes through the whole stack, with no socket and no second process to
supervise. Moving the gateway onto its own host later is a transport swap: drop
the `ASGITransport` and give the client a `base_url`.

One `GatewayRuntime` is shared per settings fingerprint. Two providers built for
a model comparison must not open two Redis pools, and must share one set of
circuit breakers — a breaker per caller is not a breaker.

## Configuration

`configs/default.yaml` stays the source of truth for *what to call*. The routing
table is derived from its `models` block, one `<model>=<provider>` rule each, and
only for models whose provider has an adapter **and** whose key is present — a
provider named without its key stops the gateway at startup, which would
otherwise turn "I have no OpenAI key" into "ClaimLens will not start".

Everything about *how this deployment runs* is `VORTEX_*` in `.env`, which is
where the gateway already reads it from. See `.env.example`.

## Production setup performed

- Redis: already running natively on `localhost:6379`.
- Client key minted into a hashed, revocable SQLite store:
  `vortex-keys create --name claimlens-batch --rpm 240 --tpm 400000`
  → key id `1b7240bc546a`, token in `.env` as `VORTEX_CLIENT_API_KEY`.
  `.vortex/` is git-ignored.
- `VORTEX_METERING_ENABLED=true` — Redis token-bucket limiter + usage ledger.
- `VORTEX_CACHE_ENABLED=true`, 1h TTL, per-key scope.

The 240 rpm allowance sits well above `runtime.max_concurrency: 4`, so the
limiter is a backstop rather than the thing pacing a run.

### Verified

| check | result |
|---|---|
| Anthropic translation of a real claim | system hoisted to top level (2640 chars); `['text', 'image']` blocks; image as `base64`/`image/jpeg`, 64916 chars |
| auth — no key | `401 missing_api_key` |
| auth — unknown key | `401 invalid_api_key` |
| auth — minted key | `200` |
| rate limit headers | `limit-requests: 240`, `remaining-requests: 239`, `limit-tokens: 400000` |
| response cache | second identical request → `X-Cache: HIT` |
| usage ledger | `/v1/usage` reports requests, tokens, priced cost, `unpriced_models: []` |
| probes | `/healthz` ok, `/readyz` ready |
| routing to the live vendor | reaches Anthropic; a bogus key returns `authentication_error: anthropic returned 401` in 0.57s, **unretried** |
| offline commands | `dryrun`, `preprocess`, `verify`, `pytest` (9 passed) all pass without constructing a gateway |

A billed end-to-end call was **not** made: `ANTHROPIC_API_KEY` in `.env` is
empty. Fill it in and `make check && uv run claimlens smoke --set sample --n 2`
completes the verification.

## Behavioural differences worth knowing

**Retries are split, not stacked.** The gateway owns transport retries — it
classifies vendor failures, retries transient ones with full jitter inside a
wall-clock deadline, waits exactly as long as a vendor `429` asks, and trips a
per-provider circuit breaker. `VortexProvider` therefore does *not* retry those
again. It retries exactly one thing: a `gateway_rate_limit_exceeded` `429`,
which means ClaimLens outran its own key's allowance. The single in-call JSON
repair stays in ClaimLens, because only that layer knows the reply was meant to
be JSON.

**`max_output_tokens` is now explicit** (`runtime.max_output_tokens`, 4096).
Anthropic requires an output cap. LiteLLM sent none and let the vendor default
apply; the gateway's adapter would otherwise impose its own 4096. Naming it in
config means the cap is ours, not a dependency's.

**Two caches, in series.** ClaimLens's `DiskCache` answers first and stores the
parsed `ProviderResult`. The gateway's Redis cache sits behind it and only
catches repeats `DiskCache` missed. Harmless, and the gateway's is what a second
consumer of the same gateway would benefit from.

---

## Gaps — features LiteLLM had that the gateway does not

### 1. No Gemini adapter (blocking, if you want Gemini)

`routing.ADAPTERS` covers `openai`, `anthropic` and `ollama` only. LiteLLM
reached Gemini, Bedrock, Vertex, Azure, Groq, Mistral and ~100 others through
one interface; this is a three-vendor gateway.

The `gemini` entry in `configs/default.yaml` is **commented out** rather than
left silently unroutable. `VortexProvider.__init__` raises a clear `KeyError`
if you select a model whose provider has no adapter, instead of failing on the
first request.

Fix: the gateway repo ships an `add-provider` skill describing the eight files a
vendor adapter touches. A Gemini adapter is the natural next one.

### 2. No structured-output support on the Anthropic path

The Anthropic adapter rejects `response_format` unless it is `text`, pointing
you at tool-calling instead. ClaimLens does not use `response_format` today — it
prompts for JSON and parses with `extract_json` — so nothing broke. But the
cleaner fix for JSON reliability (`json_schema` response format, which would
retire the repair round-trip) is unavailable on Anthropic. Ollama supports it;
OpenAI passes it through.

### 3. No per-request cost in the response

LiteLLM's `completion_cost()` priced a single response. The gateway returns
`usage` only; cost is aggregate, per key, at `GET /v1/usage`. ClaimLens is
unaffected because `configs/default.yaml` already carried authoritative
per-model pricing and `ModelConfig.cost_for` is preferred anyway — the fallback
just changed from LiteLLM's table to `PriceTable`. Note the two tables disagree:
the gateway prices `claude-*-haiku*` at $0.80/$4.00 per Mtok against config's
$1.00/$5.00. Config wins, so this only shows up for a model with no configured
pricing.

### 4. `vortex_ai_gateway.gateway` builds an app on import

`gateway.py` ends with a module-level `app = create_app()`, so importing it
constructs a second gateway from the ambient environment — one with no routing
table, which logged `"no provider configured; serving canned replies"` on every
offline ClaimLens command. Worked around by importing `create_app` lazily inside
`GatewayRuntime._startup`, so only a command that actually calls a model pays
for it. Worth fixing upstream: the module-level `app` exists for
`uvicorn vortex_ai_gateway.gateway:app`, and a factory (`--factory`) would serve
that without the import side effect.

### Not gaps, but note

- **Python 3.14 floor.** The gateway pins `requires-python = ">=3.14"`.
  ClaimLens followed, dropping 3.11/3.12/3.13 from its classifiers and CI matrix.
  Nothing in ClaimLens needed that; it came entirely from the dependency.
- **CI tracks the gateway's `main`.** The workflow checks out
  `BenvinD/vortex-ai-gateway` as a sibling so the path source resolves. Your
  local checkout is **ahead of that remote** — `cache.py` (the response cache) is
  unpushed, along with the streaming-usage and resilience-wrapper commits. Remote
  `main` is self-consistent and will install, but CI is testing an older gateway
  than your machine runs until those commits are pushed.
- **Not on PyPI.** `[tool.uv.sources]` resolves the dependency from
  `../vortex-ai-gateway`. Once it is published, delete that block and the
  version constraint alone is enough.
