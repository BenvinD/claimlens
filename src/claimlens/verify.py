"""Structural validation of a predictions CSV against the claims it answers.

Checks the header (exact names and order), the row count and ordering against
the source claims file, and every enum-valued cell. The allowed values are
imported from :mod:`claimlens.enums` rather than restated here, so the checker
cannot drift from the values the pipeline is allowed to emit.
"""

from __future__ import annotations

import csv
from pathlib import Path

from pydantic import BaseModel

from .enums import (
    ALL_OBJECT_PARTS,
    CLAIM_OBJECTS,
    CLAIM_STATUSES,
    ISSUE_TYPES,
    OUTPUT_COLUMNS,
    RISK_FLAGS,
    SEVERITIES,
)

BOOLEANS = frozenset({"true", "false"})
FREE_TEXT_COLUMNS = (
    "evidence_standard_met_reason",
    "claim_status_justification",
    "supporting_image_ids",
)

# column -> (allowed values, multi-valued?)
ENUM_COLUMNS: dict[str, tuple[frozenset[str], bool]] = {
    "claim_object": (CLAIM_OBJECTS, False),
    "evidence_standard_met": (BOOLEANS, False),
    "risk_flags": (RISK_FLAGS, True),
    "issue_type": (ISSUE_TYPES, False),
    "object_part": (ALL_OBJECT_PARTS, False),
    "claim_status": (CLAIM_STATUSES, False),
    "valid_image": (BOOLEANS, False),
    "severity": (SEVERITIES, False),
}


class VerifyResult(BaseModel):
    """Outcome of a verification run."""

    predictions: int
    claims: int
    errors: list[str] = []
    warnings: list[str] = []

    @property
    def ok(self) -> bool:
        return not self.errors


def verify(predictions_path: str | Path, claims_path: str | Path) -> VerifyResult:
    """Verify ``predictions_path`` answers ``claims_path`` with a valid schema."""
    errors: list[str] = []
    warnings: list[str] = []

    with open(claims_path, encoding="utf-8", newline="") as fh:
        claims = list(csv.DictReader(fh))
    with open(predictions_path, encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))

    if not rows:
        return VerifyResult(predictions=0, claims=len(claims), errors=["predictions file is empty"])

    header, data = rows[0], rows[1:]
    expected = list(OUTPUT_COLUMNS)
    if header != expected:
        errors.append(f"header mismatch\n    got:      {header}\n    expected: {expected}")
    if len(data) != len(claims):
        errors.append(
            f"row count: predictions have {len(data)} data rows, claims have {len(claims)}"
        )

    index = {name: i for i, name in enumerate(expected)}
    for n, row in enumerate(data, start=1):
        if len(row) != len(expected):
            errors.append(f"row {n}: has {len(row)} columns, expected {len(expected)}")
            continue

        for column, (allowed, multi) in ENUM_COLUMNS.items():
            value = row[index[column]].strip()
            if not value:
                errors.append(f"row {n}: empty {column}")
                continue
            candidates = [v.strip() for v in value.split(";")] if multi else [value]
            for candidate in candidates:
                if candidate not in allowed:
                    errors.append(f"row {n}: {column}={candidate!r} is not an allowed value")

        for column in FREE_TEXT_COLUMNS:
            if not row[index[column]].strip():
                warnings.append(f"row {n}: empty {column}")

        if n - 1 < len(claims):
            want_user = claims[n - 1].get("user_id", "")
            got_user = row[index["user_id"]]
            if got_user != want_user:
                warnings.append(
                    f"row {n}: user_id {got_user!r} != claims {want_user!r} (row order drift?)"
                )

    return VerifyResult(predictions=len(data), claims=len(claims), errors=errors, warnings=warnings)


def format_result(result: VerifyResult, max_warnings: int = 10) -> str:
    """Render a verification result as a short human-readable report."""
    lines = [
        f"predictions: {result.predictions} data rows | claims: {result.claims} rows",
        f"errors: {len(result.errors)} | warnings: {len(result.warnings)}",
        "",
    ]
    lines += [f"  ERROR: {e}" for e in result.errors]
    lines += [f"  warn : {w}" for w in result.warnings[:max_warnings]]
    if len(result.warnings) > max_warnings:
        lines.append(f"  ... +{len(result.warnings) - max_warnings} more warnings")
    lines.append("")
    lines.append("PASS - schema is valid" if result.ok else "FAIL - fix the errors above")
    return "\n".join(lines)
