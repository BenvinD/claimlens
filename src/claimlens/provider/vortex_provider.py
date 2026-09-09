"""Vortex-AI-Gateway-backed VLMProvider.

One structured vision call per claim, sent in the gateway's OpenAI-compatible
``/v1/chat/completions`` shape. The model name comes from config
(``models.<name>.model``) and the routing table is derived from the same block,
so swapping Anthropic / OpenAI / Ollama stays a config change. API keys are
read from the environment variable named in config, never stored.

The gateway runs **in this process, over ASGI** rather than across a socket. It
occupies exactly the slot LiteLLM held — an installed dependency this module
imports and calls — while still being the real FastAPI application, so every
request passes through authentication, the Redis rate limiter, the response
cache, the routing table, the per-provider retry loop and circuit breaker, and
the usage ledger. All of those live in the route layer; importing
``AnthropicAdapter`` directly would skip every one of them.

Moving the gateway onto its own host later is a transport swap and nothing
else: drop the ``ASGITransport`` and give the client a ``base_url``.

Retry duties are split rather than stacked. The gateway owns transport retries
— it classifies vendor failures, retries the transient ones with full jitter
inside a wall-clock deadline, waits exactly as long as a vendor ``429`` asks,
and trips a breaker — so this module does not retry them a second time. What it
does retry is the one failure the gateway hands back on purpose: a
``gateway_rate_limit_exceeded`` ``429``, which means ClaimLens outran its own
key's allowance and should wait for ``Retry-After``. The single in-call JSON
repair stays here, because only this layer knows the reply was meant to be JSON.
"""

from __future__ import annotations

import asyncio
import atexit
import json
import os
import re
import threading
import time
from typing import Any

import httpx
from vortex_ai_gateway.config import Settings
from vortex_ai_gateway.pricing import PriceTable
from vortex_ai_gateway.routing import ADAPTERS

from ..config import REPO_ROOT, Config
from ..observation import VLMObservation
from ..schema import PreparedClaim
from .base import ProviderResult, VLMProvider
from .cache import DiskCache
from .messages import build_messages, cache_key

_FENCE_RE = re.compile(r"^```[a-zA-Z0-9]*\n?|\n?```$")

#: The gateway authenticates every ``/v1`` route, so a call needs a client key.
#: Minted with ``vortex-keys create``; the value here is the token, not a vendor
#: key, and it is what a rate limit and the usage ledger hang off.
CLIENT_KEY_ENV = "VORTEX_CLIENT_API_KEY"

#: Sent when the deployment has no key store, where any well-formed token is
#: accepted but a *missing* one is still a 401. Named so it is obvious in a log.
_DEV_CLIENT_KEY = "claimlens-local-dev"

#: ASGI has no host, but httpx still wants an absolute URL to build one.
_ASGI_BASE_URL = "http://vortex.internal"


def extract_json(text: str) -> dict | None:
    """Best-effort extraction of a single JSON object from model text."""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = _FENCE_RE.sub("", t).strip()
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = t.find("{"), t.rfind("}")
    if 0 <= start < end:
        try:
            obj = json.loads(t[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


class GatewayRuntime:
    """A gateway application and the event loop it is pinned to.

    ``analyze`` is synchronous because the batch runner drives it from a thread
    pool, but the gateway, its httpx client and its Redis pool are async and all
    bound to a single event loop. So one loop is created on a daemon thread and
    every call is submitted to it, rather than each call opening its own with
    ``asyncio.run`` and stranding those connection pools on a loop that then
    closes.

    One runtime is shared per settings fingerprint: two providers built for a
    model comparison must not each open a Redis pool, and — more importantly —
    must share one set of circuit breakers, since a breaker per caller is not a
    breaker.
    """

    _instances: dict[str, GatewayRuntime] = {}
    _instances_lock = threading.Lock()

    @classmethod
    def shared(cls, settings: Settings, fingerprint: str) -> GatewayRuntime:
        with cls._instances_lock:
            runtime = cls._instances.get(fingerprint)
            if runtime is None:
                runtime = cls(settings)
                cls._instances[fingerprint] = runtime
            return runtime

    @classmethod
    def close_all(cls) -> None:
        """Shut every runtime down, releasing Redis and httpx pools."""
        with cls._instances_lock:
            runtimes = list(cls._instances.values())
            cls._instances.clear()
        for runtime in runtimes:
            runtime.close()

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="vortex-gateway", daemon=True)
        self._thread.start()
        self._closed = False
        self._submit(self._startup()).result()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    async def _startup(self) -> None:
        # Imported here, not at module scope: `vortex_ai_gateway.gateway` ends
        # with `app = create_app()`, so importing that module builds a second
        # gateway out of the ambient environment -- one with no routing table,
        # which logs "serving canned replies" on every offline ClaimLens
        # command. Deferring it means only a command that actually calls a
        # model pays that cost.
        from vortex_ai_gateway.gateway import create_app

        self.app = create_app(self.settings)
        # Drive the lifespan by hand: ASGITransport does not run one, and
        # skipping it would leak the Redis pool the factory opened.
        self._lifespan = self.app.router.lifespan_context(self.app)
        await self._lifespan.__aenter__()
        # The client budget must clear the gateway's own retry deadline, or
        # httpx would cancel a call the gateway is still legitimately retrying.
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url=_ASGI_BASE_URL,
            timeout=self.settings.retry_deadline_seconds + 30.0,
        )

    async def _post(self, path: str, payload: dict, headers: dict) -> httpx.Response:
        return await self._client.post(path, json=payload, headers=headers)

    def post(self, path: str, payload: dict, headers: dict) -> httpx.Response:
        """Make one gateway request from a worker thread."""
        return self._submit(self._post(path, payload, headers)).result()

    async def _shutdown(self) -> None:
        await self._client.aclose()
        await self._lifespan.__aexit__(None, None, None)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._submit(self._shutdown()).result(timeout=30)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)


atexit.register(GatewayRuntime.close_all)


def _load_env() -> None:
    """Load ``.env`` from the repo root, wherever the process was started.

    The gateway reads ``VORTEX_*`` from the environment and its own ``.env``
    lookup is relative to the working directory, so a ``claimlens validate``
    run from a subdirectory would otherwise get a gateway with no Redis and no
    key store. Loading here means every entry point is covered, not just the
    two commands that already did it for the vendor key.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
    except Exception:  # noqa: BLE001 - env may legitimately be set already
        pass


def build_gateway_settings(config: Config) -> tuple[Settings, str]:
    """Derive gateway settings from ClaimLens config, and a cache fingerprint.

    ``configs/default.yaml`` stays the single source of truth for *what to call*
    — the routing table and the vendor keys are built from its ``models`` block,
    and the timeouts from its ``runtime`` block. Everything about *how this
    deployment runs* — Redis, metering, the key store, the response cache — is
    left to ``VORTEX_*`` in the environment, which is where the gateway already
    expects to read it from.

    Only models whose provider has an adapter **and** whose key is present are
    routed. A provider named in the table without its key stops the gateway at
    startup, which would turn "I have no OpenAI key" into "ClaimLens will not
    start" even for an Anthropic-only run.
    """
    _load_env()
    routes: list[str] = []
    keys: dict[str, Any] = {}
    for model_cfg in config.models.values():
        if model_cfg.provider not in ADAPTERS:
            continue  # no adapter for this vendor; see the migration notes
        api_key = os.environ.get(model_cfg.api_key_env or "")
        if not api_key:
            continue
        keys[f"{model_cfg.provider}_api_key"] = api_key
        route = f"{model_cfg.model}={model_cfg.provider}"
        if route not in routes:
            routes.append(route)

    rt = config.runtime
    settings = Settings(
        model_routes=",".join(routes),
        request_timeout_seconds=float(rt.request_timeout_s),
        # The gateway owns transport retries now, so ClaimLens's retry budget
        # is spent here rather than in a loop wrapped around it.
        retry_max_attempts=rt.max_retries + 1,
        **keys,
    )
    # Resolved against the repo root for the same reason paths in Config are:
    # a relative key store would follow the working directory and quietly
    # create an empty, keyless database next to wherever the CLI was invoked.
    if settings.key_db_path:
        settings.key_db_path = str(config.resolve(settings.key_db_path))
    # Keys are deliberately absent from the fingerprint: two runs differing only
    # by a rotated key still want one runtime, and the value must not sit in a
    # dict key that could end up in a log or a traceback.
    fingerprint = "|".join(
        [
            settings.model_routes,
            str(settings.request_timeout_seconds),
            str(settings.retry_max_attempts),
            settings.redis_url,
            str(settings.metering_enabled),
            str(settings.cache_enabled),
            settings.key_db_path,
        ]
    )
    return settings, fingerprint


class VortexProvider(VLMProvider):
    def __init__(self, config: Config, model_name: str | None = None) -> None:
        self.config = config
        self.model_name = model_name or config.active_model
        if self.model_name not in config.models:
            raise KeyError(
                f"model '{self.model_name}' not in config.models: {sorted(config.models)}"
            )
        self.model_cfg = config.models[self.model_name]
        if self.model_cfg.provider not in ADAPTERS:
            raise KeyError(
                f"provider '{self.model_cfg.provider}' has no gateway adapter; "
                f"available: {sorted(ADAPTERS)}"
            )
        # The gateway routes on the bare model name, not 'provider/model'.
        self.gateway_model = self.model_cfg.model
        self.cache = DiskCache(config.resolve(config.cache.dir), enabled=config.cache.enabled)

        settings, fingerprint = build_gateway_settings(config)
        self.settings = settings
        self.runtime = GatewayRuntime.shared(settings, fingerprint)
        self.prices = PriceTable.from_settings(settings)
        self._client_key = os.environ.get(CLIENT_KEY_ENV) or _DEV_CLIENT_KEY

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._client_key}"}

    def _payload(self, messages: list[dict]) -> dict:
        rt = self.config.runtime
        return {
            "model": self.gateway_model,
            "messages": messages,
            "temperature": rt.temperature,
            # Anthropic requires an output cap and the adapter would otherwise
            # apply its own default, so it is named here instead of inherited.
            "max_completion_tokens": rt.max_output_tokens,
        }

    def _call(self, messages: list[dict]) -> httpx.Response:
        return self.runtime.post("/v1/chat/completions", self._payload(messages), self._headers())

    @staticmethod
    def _error_of(resp: httpx.Response) -> tuple[str, str]:
        """The gateway's error envelope as ``(code, message)``."""
        try:
            body = resp.json().get("error", {})
        except ValueError:
            return "invalid_error_body", resp.text[:200]
        return str(body.get("code") or "unknown"), str(body.get("message") or resp.text[:200])

    def _usage_and_cost(self, body: dict) -> tuple[int, int, int, float]:
        usage = body.get("usage") or {}
        pt = int(usage.get("prompt_tokens") or 0)
        ct = int(usage.get("completion_tokens") or 0)
        tt = int(usage.get("total_tokens") or (pt + ct))

        # Prefer authoritative config pricing; fall back to the gateway's table.
        cfg_cost = self.model_cfg.cost_for(pt, ct)
        if cfg_cost is not None:
            return pt, ct, tt, cfg_cost
        priced = self.prices.cost(self.gateway_model, pt, ct)
        return pt, ct, tt, float(priced) if priced is not None else 0.0

    def analyze(self, claim: PreparedClaim) -> ProviderResult:
        uid = claim.claim_input.user_id
        key = cache_key(claim, self.model_cfg, self.config.prompt_version)

        cached = self.cache.get(key)
        if cached is not None:
            try:
                res = ProviderResult.model_validate(cached)
                res.cached = True
                res.cost_usd = 0.0  # cache hit = no new spend
                return res
            except Exception:  # noqa: BLE001 - ignore a corrupt cache entry
                pass

        messages = build_messages(claim, self.config.prompt_version, self.model_cfg.provider)
        rt = self.config.runtime
        start = time.time()
        last_err: str | None = None
        # Accumulate usage/cost across every billable call (throttle waits +
        # JSON repair) so reported tokens/cost reflect real spend, not just the
        # final response.
        acc_pt = acc_ct = acc_tt = 0
        acc_cost = 0.0

        for attempt in range(rt.max_retries + 1):
            resp = self._call(messages)

            if resp.status_code != 200:
                code, message = self._error_of(resp)
                last_err = f"{code}: {message}"
                # The gateway already exhausted its own retries on anything
                # transient. The exception is its *own* limiter saying this
                # client is sending too fast, which is worth waiting out.
                if code == "gateway_rate_limit_exceeded" and attempt < rt.max_retries:
                    time.sleep(float(resp.headers.get("Retry-After") or min(2**attempt, 8)))
                    continue
                break

            body = resp.json()
            pt, ct, tt, cost = self._usage_and_cost(body)
            acc_pt += pt
            acc_ct += ct
            acc_tt += tt
            acc_cost += cost
            text = (body["choices"][0]["message"].get("content")) or ""
            data = extract_json(text)

            if data is None:  # one in-call repair before counting it a failure
                repair = messages + [
                    {"role": "assistant", "content": text},
                    {
                        "role": "user",
                        "content": (
                            "Your previous reply was not valid JSON. Reply again "
                            "with ONLY the JSON object, no prose or code fences."
                        ),
                    },
                ]
                resp = self._call(repair)
                if resp.status_code != 200:
                    code, message = self._error_of(resp)
                    last_err = f"{code}: {message}"
                    break
                body = resp.json()
                pt, ct, tt, cost = self._usage_and_cost(body)
                acc_pt += pt
                acc_ct += ct
                acc_tt += tt
                acc_cost += cost
                text = (body["choices"][0]["message"].get("content")) or ""
                data = extract_json(text)
                if data is None:
                    last_err = "json_parse_failed"
                    continue

            obs = VLMObservation.model_validate(data)
            served_by = (body.get("vortex") or {}).get("provider") or self.model_cfg.provider
            result = ProviderResult(
                user_id=uid,
                observation=obs,
                model=self.model_cfg.model,
                provider=served_by,
                prompt_tokens=acc_pt,
                completion_tokens=acc_ct,
                total_tokens=acc_tt,
                cost_usd=acc_cost,
                cached=False,
                latency_s=time.time() - start,
                raw_text=text,
            )
            self.cache.set(key, result.model_dump())
            return result

        return ProviderResult(
            user_id=uid,
            observation=None,
            model=self.model_cfg.model,
            provider=self.model_cfg.provider,
            cached=False,
            latency_s=time.time() - start,
            error=last_err or "unknown_error",
        )
