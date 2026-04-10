"""US Central helpers — Django TIME_ZONE (America/Chicago), i.e. Central with DST, not a fixed offset."""
from __future__ import annotations

from datetime import date, datetime, time

from django.utils import timezone as dj_tz


def date_to_aware_central(d: date | datetime | None) -> datetime | None:
    """
    Store calendar dates and naïve datetimes as aware values in the active zone
    (settings.TIME_ZONE — America/Chicago, observes US DST).
    """
    if d is None:
        return None
    tz = dj_tz.get_current_timezone()
    if isinstance(d, datetime):
        if dj_tz.is_aware(d):
            return d.astimezone(tz)
        naive = d.replace(tzinfo=None)
    else:
        naive = datetime.combine(d, time.min)
    if dj_tz.is_naive(naive):
        return dj_tz.make_aware(naive, tz)
    return naive
