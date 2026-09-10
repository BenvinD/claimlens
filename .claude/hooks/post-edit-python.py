#!/usr/bin/env python3
"""PostToolUse: format every edited Python file and surface the repo invariant
that the edited path is governed by.

Formatting runs `ruff format` on just the touched file, so `make check`'s
format gate never fails on a file this session wrote. Lint findings on that
file are reported back as feedback rather than silently auto-fixed - a `--fix`
could quietly change the rule layer's behaviour.

The reminders are path-triggered, from AGENTS.md and CONTRIBUTING.md: they fire
exactly when the corresponding rule is about to be broken, instead of sitting
unread at the top of a context window.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REMINDERS: list[tuple[str, str]] = [
    (
        "src/claimlens/rules/",
        "You edited the rule layer. `decide()` must stay a PURE function of "
        "(PreparedClaim, VLMObservation | None) - no network, no file I/O, no "
        "clock. Any change here needs a test in tests/test_rules.py that fails "
        "if the invariant breaks; for a bug fix, write that test first and watch "
        "it fail. Re-run `uv run pytest` and `uv run claimlens validate` and "
        "compare the per-column accuracy against your baseline.",
    ),
    (
        "src/claimlens/prompts.py",
        "You edited prompts.py. `prompt_version` is part of the cache key, so "
        "editing an existing version invalidates paid cached responses in "
        "`.cache/` and silently contradicts docs/evaluation-report.md. Add a NEW "
        "version key (v3) and switch `prompt_version` in configs/default.yaml - "
        "do not rewrite v1 or v2 in place. If you only added a new key, this is "
        "fine; if you changed an existing string, revert it.",
    ),
    (
        "src/claimlens/enums.py",
        "You edited enums.py, the runtime source of truth for allowed output "
        "values. Update docs/data-contract.md in the SAME change, and check "
        "nothing restates these values literally: "
        '`grep -rn "supported\\|contradicted\\|not_enough_information" src/ '
        "--include='*.py' | grep -v enums.py`. Then run `uv run claimlens verify`.",
    ),
    (
        "src/claimlens/observation.py",
        "You edited the observation schema. It is the contract between the model "
        "call and the rule layer - `uv run claimlens dryrun --set sample` "
        "validates it offline. Cached observations in `.cache/` were written "
        "against the old shape, so run `uv run claimlens validate` to confirm "
        "they still parse.",
    ),
]

CONFIG_REMINDER = (
    "You edited configs/default.yaml. It may only ever NAME an environment "
    "variable (`api_key_env`), never hold a value. Changing `active_model` or "
    "`prompt_version` changes the cache key, so `claimlens validate` will report "
    "0 cached rows until those calls are paid for again."
)


def ruff(project_dir: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    local = project_dir / ".venv" / "bin" / "ruff"
    cmd = [str(local), *args] if local.exists() else ["uv", "run", "ruff", *args]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=project_dir, timeout=90)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError, ValueError:
        return

    tool_input = payload.get("tool_input") or {}
    raw_path = tool_input.get("file_path") or tool_input.get("path")
    if not isinstance(raw_path, str):
        return

    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()
    path = Path(raw_path).resolve()
    try:
        rel = path.relative_to(project_dir).as_posix()
    except ValueError:
        return  # edited outside the repository

    notes: list[str] = []
    problems: list[str] = []

    if path.suffix == ".py" and path.exists():
        try:
            ruff(project_dir, ["format", "--quiet", str(path)])
            check = ruff(project_dir, ["check", "--output-format=concise", str(path)])
            if check.returncode != 0 and check.stdout.strip():
                problems.append(f"ruff check on {rel}:\n{check.stdout.strip()}")
        except OSError, subprocess.SubprocessError:
            pass  # a missing toolchain must not block the edit

    for prefix, note in REMINDERS:
        if rel.startswith(prefix):
            notes.append(note)
    if rel == "configs/default.yaml":
        notes.append(CONFIG_REMINDER)

    if problems:
        print("\n\n".join(problems), file=sys.stderr)
        if notes:
            print("\n\n" + "\n\n".join(notes), file=sys.stderr)
        sys.exit(2)  # feed back to the model so it fixes the lint now

    if notes:
        json.dump(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": "\n\n".join(notes),
                }
            },
            sys.stdout,
        )


if __name__ == "__main__":
    main()
