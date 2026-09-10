---
description: Run the full offline check suite (make check) and report the real output
allowed-tools: Bash(make check:*), Bash(uv run pytest:*), Bash(uv run ruff:*), Bash(uv run claimlens dryrun:*), Bash(uv run claimlens verify:*)
---

Run the repository's complete offline gate. No API calls, no spend.

```bash
make check
```

That is lint → format check → tests → offline dryrun → CSV verification, the
same set CI runs on every push and pull request. A green `make check` locally
means a green build.

Report the actual output. If something fails:

1. Say which stage failed and show the real error.
2. Fix it, unless the fix is a judgement call the user should make — then
   describe the options and ask.
3. Re-run `make check` and confirm it is green before reporting done.

If you skipped a stage or a stage could not run, say so plainly rather than
describing what it was supposed to do.

Two reminders while fixing:

- `uv run ruff format .` applies formatting; `--check` only reports it.
- Do not "fix" a failing `claimlens verify` by editing `output.csv` by hand.
  `output.csv` is generated. A contract failure means either `enums.py` /
  `rules/output.py` is wrong, or the committed predictions are stale from a
  behaviour change — say which, and note it for the PR description.
