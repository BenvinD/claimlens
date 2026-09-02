# Dataset

Bundled sample data for development and evaluation. This is illustrative
material, not production claims, and is **not** covered by the repository's MIT
code license.

| File | Rows | Contents |
|---|---|---|
| `claims.csv` | 44 | Input-only claims. `claimlens run --set test` predicts these into `output.csv`. |
| `sample_claims.csv` | 20 | Labeled claims: inputs plus expected outputs, used by `claimlens evaluate` and `claimlens validate`. |
| `user_history.csv` | — | Per-user claim counts and risk context, joined on `user_id`. |
| `evidence_requirements.csv` | — | Minimum image evidence by object type and issue family. |
| `images/sample/` | — | Images referenced by `sample_claims.csv`. |
| `images/test/` | — | Images referenced by `claims.csv`. |

Image paths in the CSVs are relative to this directory, e.g.
`images/test/case_001/img_1.jpg`. Multiple images per claim are `;`-separated,
and an image's **ID** is its filename without the extension (`img_1`) — that is
what predictions reference.

Column-level definitions and allowed values are in
[../docs/data-contract.md](../docs/data-contract.md).

The sample set is small and deliberately adversarial: it includes blurred and
badly angled photographs, images of the wrong object, exaggerated severity
claims, instruction text planted in transcripts and burned into images, and users
with prior-claim risk history. Accuracy figures from 20 rows are noisy — see
[../docs/evaluation-report.md](../docs/evaluation-report.md), which says so
explicitly where it matters.
