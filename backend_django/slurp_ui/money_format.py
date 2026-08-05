"""Shared USD / number display helpers (thousands commas)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        if isinstance(value, Decimal):
            return float(value)
        return float(value)
    except (TypeError, ValueError, InvalidOperation):
        return None


def format_number(value: Any, decimals: int = 2, blank: str = "—") -> str:
    """Format a number with thousands separators, no currency symbol."""
    n = _as_float(value)
    if n is None:
        return blank
    d = max(0, int(decimals))
    return f"{n:,.{d}f}"


def format_money(value: Any, decimals: int = 2, blank: str = "—") -> str:
    """Format a USD amount with $ and thousands separators."""
    n = _as_float(value)
    if n is None:
        return blank
    d = max(0, int(decimals))
    return f"${n:,.{d}f}"
