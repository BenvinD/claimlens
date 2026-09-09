"""Layer 2: the vision-model provider.

One structured model call per claim behind a provider-agnostic interface, backed
by vortex-ai-gateway so the active model is chosen in ``configs/default.yaml``.
The model
returns observations (see :mod:`claimlens.observation`); the rule layer decides.
"""

from .base import ProviderResult, VLMProvider
from .messages import build_messages, cache_key
from .runner import analyze_claims
from .vortex_provider import VortexProvider

__all__ = [
    "ProviderResult",
    "VLMProvider",
    "build_messages",
    "cache_key",
    "VortexProvider",
    "analyze_claims",
]
