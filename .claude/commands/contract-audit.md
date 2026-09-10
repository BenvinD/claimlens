---
description: Check that enums.py, docs/data-contract.md and output.csv still agree
allowed-tools: Bash(uv run claimlens verify:*), Bash(uv run pytest:*), Bash(grep:*), Bash(rg:*), Read, Glob
---

Audit the data contract for drift. `src/claimlens/enums.py` is the runtime
source of truth; `docs/data-contract.md` mirrors it; `output.csv` must satisfy
both. All checks here are free.

## 1. Enums restated elsewhere

Nothing outside `enums.py` may hard-code an allowed value. Search for leaks:

```bash
grep -rn "supported\|contradicted\|not_enough_information" src/ --include='*.py' | grep -v enums.py
grep -rn "front_bumper\|glass_shatter\|crushed_packaging" src/ --include='*.py' | grep -v enums.py
```

Matches in `rules/decide.py` need judgement: comparing against a value is fine
(`status == "supported"`), but rebuilding a *set* of allowed values is drift.
Prompt strings must get their enum lists from `enums.py` via the builders, never
inline. Report any list that duplicates one in `enums.py`.

## 2. Docs vs. runtime

Compare `docs/data-contract.md` against `enums.py`, in both directions:

- every value in `CLAIM_OBJECTS`, `CLAIM_STATUSES`, `ISSUE_TYPES`, `SEVERITIES`,
  `RISK_FLAGS` and each object's `OBJECT_PARTS` appears in the doc;
- the doc lists nothing that no longer exists in the code;
- `OUTPUT_COLUMNS` matches the doc's 14-row table **in order** — order is part
  of the contract, not a presentation detail.

## 3. The committed predictions

```bash
uv run claimlens verify
uv run pytest
```

`verify` checks `output.csv` against the contract offline.

## 4. Report

A short table: **agree / drifted**, per check, with the specific values or line
numbers that differ. If nothing drifted, say so in one line — do not pad it.

For anything drifted, name which side is wrong. `enums.py` is the source of
truth, so the usual fix is updating `docs/data-contract.md`; but if the code
gained a value that was never meant to be allowed, the code is the bug.

Do not fix anything without saying what you are changing and why — a contract
edit is exactly the kind of change that needs to be visible in a diff.
