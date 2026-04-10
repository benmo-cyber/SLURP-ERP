"""Calendar month arithmetic for lot expiration (no extra deps)."""
from __future__ import annotations

import calendar
from datetime import date, datetime, time

from django.utils import timezone


def add_calendar_months_to_date(d: date, months: int) -> date:
    """Add `months` to `d`, clamping day to last day of target month."""
    if months == 0:
        return d
    m0 = d.month - 1 + months
    y = d.year + m0 // 12
    m = m0 % 12 + 1
    last = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, last))


def add_calendar_months_to_datetime(dt: datetime, months: int) -> datetime:
    """Preserve time-of-day; use business timezone for naive datetimes."""
    if not isinstance(dt, datetime):
        raise TypeError("expected datetime")
    d = add_calendar_months_to_date(dt.date(), months)
    t = dt.time()
    out = datetime.combine(d, t)
    if timezone.is_aware(dt):
        return timezone.make_aware(out, timezone.get_current_timezone())
    return out
