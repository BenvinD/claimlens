"""Shared fixtures and helpers for the rule-layer test suite.

Every helper here is synthetic: no dataset files are read and no model calls are
made, so the whole suite runs offline with zero API spend.
"""

from __future__ import annotations

from claimlens.rules.output import OutputRow
from claimlens.schema import ClaimInput, EncodedImage, PreparedClaim, UserHistory

# Output columns whose CSV rendering is a ";"-joined set rather than a scalar.
SET_COLUMNS = ("risk_flags", "supporting_image_ids")


def mk_img(image_id: str, **kw) -> EncodedImage:
    """A minimal usable ``EncodedImage`` (already resolved, encoded and hashed)."""
    return EncodedImage(
        image_id=image_id,
        rel_path=f"images/x/{image_id}.jpg",
        abs_path=f"/x/{image_id}.jpg",
        exists=True,
        data_url="data:image/jpeg;base64,AAAA",
        content_hash="hash_" + image_id,
        **kw,
    )


def mk_claim(obj: str, user_claim: str, history_flags: str, image_ids: list[str]) -> PreparedClaim:
    """A ``PreparedClaim`` as the preprocessing layer would emit it."""
    return PreparedClaim(
        claim_input=ClaimInput(
            user_id="u",
            image_paths=";".join(f"images/x/{i}.jpg" for i in image_ids),
            user_claim=user_claim,
            claim_object=obj,
        ),
        user_history=UserHistory(user_id="u", history_flags=history_flags),
        evidence_requirements=[],
        images=[mk_img(i) for i in image_ids],
    )


def assert_row(row: OutputRow, expected: dict) -> None:
    """Assert the rendered CSV row matches ``expected``.

    Set-valued columns are compared order-insensitively; ``none`` is treated as
    the empty set so an expectation of ``[]`` matches the rendered ``"none"``.
    """
    rendered = row.to_csv_dict()
    for column, want in expected.items():
        got = rendered[column]
        if column in SET_COLUMNS:
            got_set = set(filter(None, got.split(";"))) - {"none"}
            assert got_set == set(want), f"{column}: got {sorted(got_set)}, want {sorted(want)}"
        else:
            assert got == want, f"{column}: got {got!r}, want {want!r}"
