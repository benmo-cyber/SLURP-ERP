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


def add_calendar_months_to_datetime(dt: datetime | date, months: int) -> datetime:
    """Preserve time-of-day; use business timezone for naive datetimes.

    Accepts ``date`` (treated as midnight in the current timezone) so callers
    that only have a calendar manufacture date still compute expiration.
    """
    if isinstance(dt, datetime):
        base = dt
    elif isinstance(dt, date):
        base = timezone.make_aware(
            datetime.combine(dt, time.min), timezone.get_current_timezone()
        )
    else:
        raise TypeError("expected datetime or date")
    d = add_calendar_months_to_date(base.date(), months)
    t = base.time()
    out = datetime.combine(d, t)
    if timezone.is_aware(base):
        return timezone.make_aware(out, timezone.get_current_timezone())
    return out
