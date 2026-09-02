"""ClaimLens - multi-modal damage-claim evidence review.

A claim arrives as a chat transcript plus one or more photographs. ClaimLens
decides whether those photographs *support*, *contradict*, or are *insufficient
to judge* the claim, and returns a structured, fully enumerated row per claim.

Three layers, deliberately separated so the decision is reproducible:

1. ``preprocessing`` - pure Python. Loads the CSVs, joins user history, attaches
   the applicable evidence requirements, downscales and encodes the images.
2. ``provider`` - one structured vision-model call per claim behind a
   provider-agnostic interface. The model *observes* each image; it never rules.
3. ``rules`` - deterministic logic mapping observations to the output columns,
   where the invariants (images are the source of truth; history only adds risk)
   are enforced in tested code rather than requested in a prompt.
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]
