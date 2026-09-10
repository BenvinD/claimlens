---
description: Change the rule layer test-first, with a before/after accuracy comparison
argument-hint: [what should change, e.g. "a blurry-only image set should not contradict"]
---

Make a rule-layer change, test-first, without breaking the invariants.

**The change requested:** $ARGUMENTS

Use the `rule-layer` skill for the invariants and branch precedence. Follow this
loop exactly — step 5 is the one that catches regressions, so do not skip it.

## 1. Baseline

```bash
uv run pytest
uv run claimlens validate
```

Note the pass count and the per-column accuracy. These are the numbers you must
beat or match. All free.

## 2. Locate the branch

Read `src/claimlens/rules/decide.py` and identify **which** of the ordered
branches produces the current behaviour: provider failure → assessability gate →
support test → supported → contradicted/NEI. Branch order *is* precedence, so
say where the change belongs and what it must not disturb above it.

## 3. Write the failing test first

Add it to `tests/test_rules.py` using the `mk_claim` / `assert_row` helpers from
`tests/conftest.py`. Run pytest and **watch it fail** — report the failure
output. A test that passes before the fix is testing the wrong thing.

Test the invariant, not just the line you are about to change.

## 4. Make the change

Keep `decide()` pure: no network, no file I/O, no clock, no randomness. Import
enum values from `src/claimlens/enums.py`; never restate them. If the change
requires reading `user_claim` or letting history set a status, stop — that
breaks a structural invariant, and the right answer is a risk flag plus
`manual_review_required`.

## 5. Verify — both halves

```bash
uv run pytest              # new test green, nothing else broken
uv run claimlens validate  # per-column accuracy vs step 1
make check                 # full offline gate
```

If `validate` accuracy dropped on any column, the fix repaired one case and
broke others. Report the drop and the trade honestly; do not bury it.

## 6. Report

- what changed and in which branch,
- the failing-then-passing test,
- baseline vs. final accuracy per column,
- whether the committed `output.csv` is now stale (it is, if verdicts moved).

Do not commit unless asked.
