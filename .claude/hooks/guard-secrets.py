#!/usr/bin/env python3
"""PreToolUse guard: keep `.env` and the paid model cache out of harm's way.

Two rules from AGENTS.md, enforced by the harness rather than by remembering:

  1. `.env` holds a real API key. Never read, print, copy or edit it.
     `.env.example` is fine - it only names variables.
  2. `.cache/` holds paid model responses. Deleting it is expensive and is
     almost never what was actually asked for.

Reads a PreToolUse payload on stdin, writes a permission decision on stdout.
"""

from __future__ import annotations

import json
import re
import sys

# `.env`, `.env.local`, ... but never `.env.example`. `.venv` does not contain
# the literal substring `.env`, so virtualenv paths are unaffected.
DOTENV = re.compile(r"(?<![\w.-])\.env(?!\.example)(?:\.[\w-]+)?(?![\w.-])")

# `rm`/`shred`/`trash` aimed at the model-response cache.
CACHE_RM = re.compile(r"\b(?:rm|shred|trash|trash-put)\b[^;&|]*?(?<![\w./-])\.?/?\.cache(?![\w-])")

READS_FILE = re.compile(
    r"\b(?:cat|bat|less|more|head|tail|nl|od|xxd|strings|grep|rg|ag|awk|sed|cp|mv|"
    r"source|scp|rsync|base64|tee|dotenv)\b"
)

# A heredoc body is data being written, not a path being read. Writing a script
# or a doc that merely mentions the secret file is fine, so strip those bodies
# before pattern-matching or every heredoc about `.env` trips the guard.
HEREDOC_START = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def strip_heredocs(command: str) -> str:
    """Return ``command`` with the body of every heredoc removed."""
    lines = command.split("\n")
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        out.append(line)
        delimiters = [m.group(2) for m in HEREDOC_START.finditer(line)]
        index += 1
        for delimiter in delimiters:
            while index < len(lines) and lines[index].strip() != delimiter:
                index += 1
            if index < len(lines):
                index += 1  # consume the closing delimiter
    return "\n".join(out)


def deny(reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.exit(0)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError, ValueError:
        return

    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}

    if tool == "Bash":
        command = strip_heredocs(tool_input.get("command", "") or "")
        if DOTENV.search(command) and READS_FILE.search(command):
            deny(
                "Blocked: this command reads or copies `.env`, which holds a real "
                "API key (AGENTS.md: 'Never touch secrets'). Use `.env.example` to "
                "see which variables exist, or ask the user to confirm a value "
                "themselves. Config files may name an env var, never hold its value."
            )
        if CACHE_RM.search(command):
            deny(
                "Blocked: `.cache/` holds paid model responses keyed by provider, "
                "model, prompt_version and image hashes. Deleting it throws away "
                "money and wipes the `claimlens validate` baseline. If the cache "
                "genuinely needs clearing, ask the user first."
            )
        return

    path = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("notebook_path")
    if isinstance(path, str) and DOTENV.search(path):
        deny(
            f"Blocked: `{path}` holds a real API key (AGENTS.md: 'Never touch "
            "secrets'). Read `.env.example` instead - it documents every variable "
            "without exposing a value."
        )


if __name__ == "__main__":
    main()
