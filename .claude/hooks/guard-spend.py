#!/usr/bin/env python3
"""PreToolUse guard: never spend money on model calls without being asked.

`claimlens smoke`, `run` and `evaluate` make real API calls; every other
command in this repository is free. This hook downgrades the paid three to an
explicit confirmation prompt, so an agent reaching for `run` when `dryrun`
would have done gets caught before the bill.

Approving the prompt is all it takes when spending really is the intent.
"""

from __future__ import annotations

import json
import re
import sys

PAID = {
    "smoke": "a live end-to-end check on the first N claims",
    "run": "a full pipeline run over the whole set",
    "evaluate": "a model comparison that re-runs every claim per model",
}

# `claimlens run`, `uv run claimlens run`, `python -m claimlens.cli run`, `make run`.
CLI = re.compile(r"\bclaimlens(?:\.cli)?\b[^;&|]*?\s(smoke|run|evaluate)\b")
MAKE = re.compile(r"\bmake\b[^;&|]*?\s(run|evaluate)\b")

FREE_ALTERNATIVE = (
    "Free alternatives: `claimlens dryrun --set sample` checks the model-call "
    "wiring offline, `claimlens validate` scores the rule layer on cached "
    "observations, and `claimlens verify` checks output.csv against the contract."
)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError, ValueError:
        return
    if payload.get("tool_name") != "Bash":
        return

    command = (payload.get("tool_input") or {}).get("command", "") or ""
    match = CLI.search(command) or MAKE.search(command)
    if not match:
        return

    subcommand = match.group(1)
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": (
                    f"`claimlens {subcommand}` makes real API calls - "
                    f"{PAID[subcommand]}. AGENTS.md: do not spend money without "
                    f"being asked. Confirm only if paid calls are actually "
                    f"intended here.\n\n{FREE_ALTERNATIVE}"
                ),
            }
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
