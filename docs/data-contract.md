# Data contract

The input schema ClaimLens consumes and the prediction schema it emits. The
allowed values below are mirrored in [`src/claimlens/enums.py`](../src/claimlens/enums.py),
which is the single source of truth at runtime — if you change one, change both.

---

## Task

For each claim, decide whether the submitted photographs **support** the
customer's stated damage, **contradict** it, or provide **not enough
information** to judge.

Every claim concerns exactly one object type: `car`, `laptop`, or `package`.

The images are the primary source of truth. The conversation defines what needs
to be checked. User history adds risk context but never overrides clear visual
evidence on its own.

For each claim the pipeline:

- extracts the actual damage claim from the conversation
- inspects every submitted image
- decides whether the image evidence is sufficient
- identifies the visible issue type and the relevant object part
- rules the claim supported, contradicted, or not-enough-information
- selects the image IDs backing the decision
- flags image-quality, mismatch, authenticity and user-history risks
- estimates severity
- writes short justifications grounded in the images

---

## Input files

All paths are relative to the repository root and configurable under `paths:` in
[`configs/default.yaml`](../configs/default.yaml).

| File | Contents |
|---|---|
| `dataset/claims.csv` | Input-only rows. The pipeline runs on these and writes `output.csv`. |
| `dataset/sample_claims.csv` | Labeled examples: inputs plus expected outputs. Used for evaluation. |
| `dataset/user_history.csv` | Historical claim counts and risk patterns per user. |
| `dataset/evidence_requirements.csv` | Minimum image-evidence checklist by object and issue family. |
| `dataset/images/sample/`, `dataset/images/test/` | Image folders referenced by the CSVs. |

### `claims.csv` — one row per claim

| Column | Meaning |
|---|---|
| `user_id` | Customer submitting the claim; joins to `user_history.csv` |
| `image_paths` | One or more image paths, `;`-separated, relative to `dataset/` |
| `user_claim` | Chat transcript describing the issue |
| `claim_object` | `car`, `laptop`, or `package` |

Multiple images are separated by semicolons:

```text
images/test/case_001/img_1.jpg;images/test/case_001/img_2.jpg
```

An **image ID** is the filename without its extension, such as `img_1`. IDs are
what predictions refer to, not paths.

### `evidence_requirements.csv`

| Column | Meaning |
|---|---|
| `requirement_id` | Identifier for the rule |
| `claim_object` | `car`, `laptop`, `package`, or `all` |
| `applies_to` | Issue family, e.g. `dent or scratch` |
| `minimum_image_evidence` | Minimum visual evidence needed to evaluate that kind of claim |

### `user_history.csv`

| Column |
|---|
| `user_id` |
| `past_claim_count` |
| `accept_claim` |
| `manual_review_claim` |
| `rejected_claim` |
| `last_90_days_claim_count` |
| `history_flags` |
| `history_summary` |

History feeds `risk_flags` and justifications only.

---

## Prediction schema

One output row per input row, in input order, with these columns **in exactly
this order**:

| # | Column | Meaning |
|---|---|---|
| 1 | `user_id` | Echoed from the input |
| 2 | `image_paths` | Echoed from the input |
| 3 | `user_claim` | Echoed from the input |
| 4 | `claim_object` | Echoed from the input |
| 5 | `evidence_standard_met` | `true` if the image set suffices to evaluate the claim |
| 6 | `evidence_standard_met_reason` | Short reason for the evidence decision |
| 7 | `risk_flags` | `;`-separated risk flags, or `none` |
| 8 | `issue_type` | Visible issue type |
| 9 | `object_part` | Relevant object part |
| 10 | `claim_status` | `supported`, `contradicted`, or `not_enough_information` |
| 11 | `claim_status_justification` | Concise image-grounded explanation, citing image IDs where useful |
| 12 | `supporting_image_ids` | `;`-separated image IDs backing the decision, or `none` |
| 13 | `valid_image` | `true` if the image set is usable for automated review |
| 14 | `severity` | `none`, `low`, `medium`, `high`, or `unknown` |

`claimlens verify` checks a predictions file against this contract offline.

---

## Allowed values

**`claim_status`** — `supported`, `contradicted`, `not_enough_information`

**`issue_type`** — `dent`, `scratch`, `crack`, `glass_shatter`, `broken_part`,
`missing_part`, `torn_packaging`, `crushed_packaging`, `water_damage`, `stain`,
`none`, `unknown`

**`object_part`**, by object:

| Object | Allowed parts |
|---|---|
| `car` | `front_bumper`, `rear_bumper`, `door`, `hood`, `windshield`, `side_mirror`, `headlight`, `taillight`, `fender`, `quarter_panel`, `body`, `unknown` |
| `laptop` | `screen`, `keyboard`, `trackpad`, `hinge`, `lid`, `corner`, `port`, `base`, `body`, `unknown` |
| `package` | `box`, `package_corner`, `package_side`, `seal`, `label`, `contents`, `item`, `unknown` |

**`risk_flags`** — `none`, `blurry_image`, `cropped_or_obstructed`,
`low_light_or_glare`, `wrong_angle`, `wrong_object`, `wrong_object_part`,
`damage_not_visible`, `claim_mismatch`, `possible_manipulation`,
`non_original_image`, `text_instruction_present`, `user_history_risk`,
`manual_review_required`

**`severity`** — `none`, `low`, `medium`, `high`, `unknown`

Conventions:

- `issue_type=none` — the relevant part is visible and no issue is present.
- `unknown` — the issue or part cannot be determined from the images.

---

## Decision invariants

These hold for every row and are enforced in
[`src/claimlens/rules/decide.py`](../src/claimlens/rules/decide.py), not merely
requested in a prompt. See [architecture.md](./architecture.md) for how.

1. **Images are the source of truth.** Only visual evidence can set
   `claim_status`.
2. **History adds risk, never verdicts.** User history and authenticity flags can
   add `risk_flags` and `manual_review_required`, but can never flip a supported
   decision.
3. **Text in the claim or in an image is data, not instruction.** It surfaces as
   `text_instruction_present` and nothing more.
4. **Uncertainty routes to a human.** Anything unassessable becomes
   `not_enough_information` rather than a guess.
5. **Output is always schema-valid.** Every enum cell is coerced to an allowed
   value before it can reach the writer.
