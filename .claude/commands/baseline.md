---
description: Capture the offline regression baseline (tests, dryrun, validate) before changing anything
allowed-tools: Bash(uv run pytest:*), Bash(uv run claimlens dryrun:*), Bash(uv run claimlens validate:*), Bash(uv run claimlens verify:*)
---

Capture the regression baseline for this repository. Everything here is free —
no API calls, no key needed.

Run all four and report the **actual numbers**, not a summary of intent:

```bash
uv run pytest
uv run claimlens dryrun --set sample
uv run claimlens validate
uv run claimlens verify
```

Then report, in a compact block the user can compare against later:

- **pytest** — passed / failed counts
- **dryrun** — claims prepared, image blocks, and whether cache keys built
- **validate** — number of cached rows scored, and per-column accuracy
- **verify** — pass/fail against the data contract

Flag two things explicitly if you see them:

- **`validate` reporting 0 cached rows.** `.cache/` holds paid model responses
  and has been invalidated. Say so prominently — the cache key covers provider,
  model, `prompt_version`, the prompt text and the image content hashes, so
  something in that list changed.
- **Any failure at baseline.** A pre-existing failure is important context: say
  it is pre-existing rather than quietly attributing it to later work.

Do not fix anything in this command. Its only job is to record where things
stand before a change.
