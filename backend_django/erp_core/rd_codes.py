"""Allocate permanent R&D formula codes: {family_letter}-R### (per letter, never reused)."""
from __future__ import annotations

import re

from django.db import transaction

from erp_core.models import RDFormula, RDFormulaCodeSequence

_RD_CODE_RE = re.compile(r"^([A-Z])-R(\d+)$")


def normalize_family_letter(raw: str | None) -> str:
    letter = (raw or "").strip().upper()
    if len(letter) != 1 or not letter.isalpha():
        raise ValueError("Family letter must be a single A–Z letter (matches commercial SKU family).")
    return letter


def format_rd_code(family_letter: str, sequence_number: int) -> str:
    return f"{family_letter}-R{sequence_number:03d}"


@transaction.atomic
def allocate_rd_code(family_letter: str) -> tuple[str, str]:
    """
    Reserve the next R&D code for this family letter.
    Returns (family_letter, rd_code). Safe under concurrent creates.
    """
    letter = normalize_family_letter(family_letter)
    seq, _ = RDFormulaCodeSequence.objects.select_for_update().get_or_create(
        family_letter=letter,
        defaults={"sequence_number": 0},
    )
    # Also never collide with historical rows (e.g. after restore / manual inserts).
    next_n = int(seq.sequence_number or 0) + 1
    while RDFormula.objects.filter(rd_code=format_rd_code(letter, next_n)).exists():
        next_n += 1
    seq.sequence_number = next_n
    seq.save(update_fields=["sequence_number", "last_updated"])
    return letter, format_rd_code(letter, next_n)


def parse_rd_code(rd_code: str) -> tuple[str, int] | None:
    m = _RD_CODE_RE.match((rd_code or "").strip().upper())
    if not m:
        return None
    return m.group(1), int(m.group(2))
