"""Layer 2: the vision-model provider.

One structured model call per claim behind a provider-agnostic interface, backed
by LiteLLM so the active model is chosen in ``configs/default.yaml``. The model
returns observations (see :mod:`claimlens.observation`); the rule layer decides.
"""

from .base import ProviderResult, VLMProvider
from .litellm_provider import LiteLLMProvider
from .messages import build_messages, cache_key
from .runner import analyze_claims

__all__ = [
    "ProviderResult",
    "VLMProvider",
    "build_messages",
    "cache_key",
    "LiteLLMProvider",
    "analyze_claims",
]
