---
name: rule-layer
description: Change the deterministic decision layer (src/claimlens/rules/, decide()) without breaking its invariants. Use when a claim gets the wrong verdict, when adding or reordering a decision branch, when changing risk flags, severity, evidence_standard_met or supporting_image_ids, or when writing tests for decision behaviour.
---

# Changing the rule layer

`decide(claim, observation) -> OutputRow` is the whole decision. It is a **pure
function** and must stay one: no network, no file I/O, no clock, no randomness
anywhere in `src/claimlens/rules/`. That purity is what makes verdicts
reproducible, unit-testable and re-scorable without paying to re-call the model.

## The workflow — test first, always

For a bug fix, write the failing test **before** the fix and watch it fail.
That is the repo convention, and here it is also the only proof the change did
what you think:

```bash
uv run pytest                    # 1. baseline: green, note the count
uv run claimlens validate        # 2. baseline: per-column accuracy on cached rows
# 3. add the failing test to tests/test_rules.py, run pytest, SEE IT FAIL
# 4. change rules/decide.py
uv run pytest                    # 5. green again
uv run claimlens validate        # 6. accuracy must not regress vs step 2
```

Step 6 is the one people skip. `validate` re-scores every cached observation
through your new logic for free — it catches the fix that repairs one case and
breaks four others. A local test passing is not evidence the rule layer improved.

`/rule-change` drives this loop end to end.

## Branch order IS precedence

`decide()` reads top to bottom and the first matching branch wins. Inserting a
branch in the wrong place silently changes unrelated verdicts.

1. **Provider failure** (`observation is None` or no images) →
   `not_enough_information`, `evidence_standard_met=false`, `valid_image=false`,
   always `manual_review_required`.
2. **Assessability gate** — no image shows the claimed part, shows damage, or
   shows a different object → `not_enough_information` + `damage_not_visible`.
3. **Support test** — an image supports the claim when it matches the claim
   object, shows damage, the issue type is compatible, and the damage is on a
   claimed part *or* on the visible claimed part the model left unnamed.
4. **Supported** — support exists and no exaggeration. Decisive image = most severe.
5. **Otherwise**, in order: exaggeration → contradicted (`claim_mismatch`);
   wrong object → contradicted (`wrong_object`); claimed part visible and
   undamaged → contradicted (`damage_not_visible`, `issue_type=none`); damage on
   an unclaimed part → contradicted (`wrong_object_part`); nothing decisive → NEI.

**Exaggeration** is: support exists, customer stated `high`, observed severity is
`none` or `low` → contradicted, not supported.

**Issue-type matching is deliberately lenient.** `unknown`/`none` on either side
counts as compatible, and these families count as matches — only a clearly
different known family blocks support:

```
dent/scratch   crack/glass_shatter   broken_part/missing_part
torn_packaging/crushed_packaging     water_damage/stain
```

## Invariants you must not break

**History never flips a verdict.** `claim_status` is assigned in exactly five
places and none of their conditions reference `hist_flags` or authenticity flags
— history enters only through the additive `risk` set. This is a *structural*
guarantee. If you find yourself reading history in a status branch, stop: the
answer is a risk flag plus `manual_review_required`, not a different status.

**The rule layer never reads `user_claim`.** That is what defuses prompt
injection: instruction text can only reach `text_instruction_present` via the
observation. Do not add a text check here.

**Severity is observed-only.** It comes from image severity, never from the
customer's adjectives. A supported row legitimately reads `severity=unknown`
when the model reported damage without a severity — that is not a bug to "fix".

**`valid_image` is a usability signal, never a decision input.** Do not branch on it.

**Never restate an enum.** Import from `src/claimlens/enums.py`. Use `coerce`,
`coerce_list`, `valid_parts_for`, `max_severity` rather than writing literals.
`_safe_part()` exists because `object_part` is object-specific — a `windshield`
on a `laptop` claim must collapse to `unknown`.

## Writing a test

Tests hand-craft the observation a well-behaved model would return, then assert
the output row. Use the `tests/conftest.py` helpers:

```python
from claimlens.observation import ImageObservation, VLMObservation
from claimlens.rules import decide
from .conftest import assert_row, mk_claim


def test_history_risk_never_flips_supported():
    """A flagged user with clear visual support stays supported, plus review."""
    row = decide(
        mk_claim("car", "rear bumper dent", "user_history_risk", ["img_1"]),
        VLMObservation(
            claim_summary="rear bumper dent",
            claimed_issue_type="dent",
            claimed_object_part="rear_bumper",
            claimed_parts=["rear_bumper"],
            stated_severity="medium",
            images=[
                ImageObservation(
                    image_id="img_1",
                    object_in_image="car",
                    matches_claim_object=True,
                    claimed_part_visible=True,
                    damage_present=True,
                    observed_issue_type="dent",
                    observed_object_part="rear_bumper",
                    observed_severity="medium",
                    supports_claim=True,
                )
            ],
        ),
    )
    assert row.claim_status == "supported"
    assert "user_history_risk" in row.risk_flags
    assert "manual_review_required" in row.risk_flags
```

Test the **invariant**, not the line you changed. A test that only pins the new
branch's output will pass while the property it was meant to protect rots.

## When the rule layer is the wrong fix

If the observation itself is wrong — the model saw damage that is not there,
missed a visible part, mislabelled the object — no rule change fixes it
honestly. That is a prompt problem: see the `prompt-and-cache` skill. Bending
`decide()` to compensate for a bad observation makes the next model swap worse.
