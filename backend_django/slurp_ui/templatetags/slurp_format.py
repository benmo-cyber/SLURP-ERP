"""Display filters — thousands commas on money and report amounts."""

from __future__ import annotations

from django import template

from slurp_ui.money_format import format_money, format_number

register = template.Library()


@register.filter(name="money")
def money_filter(value, decimals=2):
    """{{ amount|money }} → $1,234.56 · {{ amount|money:0 }} → $1,235"""
    try:
        d = int(decimals)
    except (TypeError, ValueError):
        d = 2
    return format_money(value, d)


@register.filter(name="numcomma")
def numcomma_filter(value, decimals=2):
    """{{ amount|numcomma }} → 1,234.56 (no $; for GL / report columns)."""
    try:
        d = int(decimals)
    except (TypeError, ValueError):
        d = 2
    return format_number(value, d)
