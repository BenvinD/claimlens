"""Evaluation harness: score the system on labeled sample rows and compare models."""

from .harness import EvalRun, run_model
from .metrics import Metrics, score

__all__ = ["Metrics", "score", "EvalRun", "run_model"]
