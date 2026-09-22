"""
Material activity aggregates for Inventory → Material activity.

Summarizes lot movement over a date range by flow (brought in / made / shipped / returned),
with optional parent-SKU expansion, vendor filter, and a single breakdown dimension.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable

from django.db.models import Q
from django.utils import timezone

from .models import Item, LotTransactionLog

FLOW_BROUGHT_IN = "brought_in"
FLOW_MADE = "made"
FLOW_SHIPPED = "shipped"
FLOW_RETURNED = "returned"

FLOW_LABELS = {
    FLOW_BROUGHT_IN: "Brought in",
    FLOW_MADE: "Made",
    FLOW_SHIPPED: "Shipped",
    FLOW_RETURNED: "Returned",
}

ALL_FLOWS = (FLOW_BROUGHT_IN, FLOW_MADE, FLOW_SHIPPED, FLOW_RETURNED)

BREAKDOWNS = ("none", "month", "vendor", "sku", "flow")


def _return_q() -> Q:
    return Q(transaction_type="return") | (
        Q(transaction_type="receipt")
        & (
            Q(notes__icontains="Restock from customer return")
            | Q(notes__icontains="customer return")
            | Q(reference_type="customer_return")
        )
    )


def _brought_in_q() -> Q:
    return Q(transaction_type="receipt") & ~(
        Q(notes__icontains="Restock from customer return")
        | Q(notes__icontains="customer return")
        | Q(reference_type="customer_return")
    )


def _made_q() -> Q:
    return Q(transaction_type__in=("production_output", "repack_output"))


def _shipped_q() -> Q:
    return Q(transaction_type="sale")


FLOW_Q = {
    FLOW_BROUGHT_IN: _brought_in_q,
    FLOW_MADE: _made_q,
    FLOW_SHIPPED: _shipped_q,
    FLOW_RETURNED: _return_q,
}


def resolve_skus(subject: str, *, scope: str) -> list[str]:
    """
    scope=sku → exact SKU match (case-insensitive).
    scope=parent → all items with sku_parent_code == subject, plus subject itself.
    """
    s = (subject or "").strip().upper()
    if not s:
        return []
    if scope == "parent":
        skus = set(
            Item.objects.filter(sku_parent_code__iexact=s).values_list("sku", flat=True)
        )
        skus.add(s)
        # Parent-only item row if present
        parent_item = Item.objects.filter(sku__iexact=s).values_list("sku", flat=True).first()
        if parent_item:
            skus.add(parent_item)
        return sorted({(x or "").strip().upper() for x in skus if x})
    # exact
    hit = Item.objects.filter(sku__iexact=s).values_list("sku", flat=True).first()
    return [(hit or s).upper()]


def _parse_day(value: str | date | None, *, end: bool = False) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, time.max if end else time.min)
    else:
        raw = str(value).strip()[:10]
        try:
            d = date.fromisoformat(raw)
        except ValueError:
            return None
        dt = datetime.combine(d, time.max if end else time.min)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def default_date_range() -> tuple[date, date]:
    today = timezone.localdate()
    return today - timedelta(days=365), today


def classify_flow(row: LotTransactionLog) -> str | None:
    t = (row.transaction_type or "").lower()
    notes = (row.notes or "").lower()
    ref_t = (row.reference_type or "").lower()
    if t == "return" or ref_t == "customer_return":
        return FLOW_RETURNED
    if t == "receipt":
        if "restock from customer return" in notes or "customer return" in notes:
            return FLOW_RETURNED
        return FLOW_BROUGHT_IN
    if t in ("production_output", "repack_output"):
        return FLOW_MADE
    if t == "sale":
        return FLOW_SHIPPED
    return None


def query_material_activity(
    *,
    subject: str,
    scope: str = "sku",
    date_from: str | date | None = None,
    date_to: str | date | None = None,
    vendor: str | None = None,
    flows: Iterable[str] | None = None,
    breakdown: str = "none",
) -> dict[str, Any]:
    """
    Returns:
      subject, scope, skus, date_from, date_to, vendor,
      flows_selected, breakdown,
      totals: {flow: {qty, uoms: {uom: qty}}},
      rows: [{key, label, flow?, sku?, vendor?, month?, qty, uom, ...}],
      mixed_uom: bool,
      event_count: int,
    """
    scope = scope if scope in ("sku", "parent") else "sku"
    breakdown = breakdown if breakdown in BREAKDOWNS else "none"
    selected = [f for f in (flows or ALL_FLOWS) if f in ALL_FLOWS]
    if not selected:
        selected = list(ALL_FLOWS)

    d0, d1 = default_date_range()
    df = _parse_day(date_from) or _parse_day(d0)
    dt = _parse_day(date_to, end=True) or _parse_day(d1, end=True)

    skus = resolve_skus(subject, scope=scope)
    empty = {
        "subject": (subject or "").strip().upper(),
        "scope": scope,
        "skus": skus,
        "date_from": (df.date() if df else d0).isoformat(),
        "date_to": (dt.date() if dt else d1).isoformat(),
        "vendor": (vendor or "").strip(),
        "flows_selected": selected,
        "breakdown": breakdown,
        "totals": {f: {"qty": 0.0, "uoms": {}} for f in ALL_FLOWS},
        "rows": [],
        "mixed_uom": False,
        "event_count": 0,
        "has_subject": bool(skus),
    }
    if not skus:
        return empty

    flow_q = Q()
    for f in selected:
        flow_q |= FLOW_Q[f]()

    qs = LotTransactionLog.objects.filter(item_sku__in=skus).filter(flow_q)
    if df:
        qs = qs.filter(logged_at__gte=df)
    if dt:
        qs = qs.filter(logged_at__lte=dt)
    vendor_s = (vendor or "").strip()
    if vendor_s:
        qs = qs.filter(vendor__icontains=vendor_s)

    # Pull rows for classification + breakdown (cap large scans reasonably)
    logs = list(
        qs.only(
            "item_sku",
            "vendor",
            "transaction_type",
            "quantity_change",
            "unit_of_measure",
            "notes",
            "reference_type",
            "logged_at",
        ).order_by("logged_at")[:20000]
    )

    totals: dict[str, dict[str, Any]] = {
        f: {"qty": 0.0, "uoms": defaultdict(float)} for f in ALL_FLOWS
    }
    # breakdown accumulators: key -> {label, flow, sku, vendor, month, uoms: defaultdict}
    buckets: dict[str, dict[str, Any]] = {}

    def add_bucket(key: str, *, label: str, flow: str, sku: str, vend: str, month: str, qty: float, uom: str):
        b = buckets.get(key)
        if not b:
            b = {
                "key": key,
                "label": label,
                "flow": flow,
                "sku": sku,
                "vendor": vend or "—",
                "month": month,
                "uoms": defaultdict(float),
            }
            buckets[key] = b
        b["uoms"][uom] += qty

    for row in logs:
        flow = classify_flow(row)
        if flow is None or flow not in selected:
            continue
        qty = abs(float(row.quantity_change or 0))
        if qty <= 0:
            continue
        uom = (row.unit_of_measure or "lbs").lower()
        if uom in ("lb",):
            uom = "lbs"
        totals[flow]["qty"] += qty
        totals[flow]["uoms"][uom] += qty

        vend = (row.vendor or "").strip() or "—"
        sku = (row.item_sku or "").strip().upper()
        month = row.logged_at.strftime("%Y-%m") if row.logged_at else ""

        if breakdown == "none":
            continue
        if breakdown == "month":
            add_bucket(
                f"m:{month}:{flow}",
                label=month or "—",
                flow=flow,
                sku="",
                vend="",
                month=month,
                qty=qty,
                uom=uom,
            )
        elif breakdown == "vendor":
            add_bucket(
                f"v:{vend.lower()}:{flow}",
                label=vend,
                flow=flow,
                sku="",
                vend=vend,
                month="",
                qty=qty,
                uom=uom,
            )
        elif breakdown == "sku":
            add_bucket(
                f"s:{sku}:{flow}",
                label=sku,
                flow=flow,
                sku=sku,
                vend="",
                month="",
                qty=qty,
                uom=uom,
            )
        elif breakdown == "flow":
            add_bucket(
                f"f:{flow}",
                label=FLOW_LABELS.get(flow, flow),
                flow=flow,
                sku="",
                vend="",
                month="",
                qty=qty,
                uom=uom,
            )

    # Normalize totals uoms to plain dicts; detect mixed
    all_uoms = set()
    for f in ALL_FLOWS:
        uoms = dict(totals[f]["uoms"])
        totals[f]["uoms"] = uoms
        all_uoms.update(uoms.keys())
        # Prefer primary uom label = largest share
        if uoms:
            primary = max(uoms.items(), key=lambda kv: kv[1])[0]
            totals[f]["primary_uom"] = primary
        else:
            totals[f]["primary_uom"] = "lbs"

    rows_out = []
    for b in buckets.values():
        uoms = dict(b["uoms"])
        primary = max(uoms.items(), key=lambda kv: kv[1])[0] if uoms else "lbs"
        rows_out.append(
            {
                "key": b["key"],
                "label": b["label"],
                "flow": b["flow"],
                "flow_label": FLOW_LABELS.get(b["flow"], b["flow"]),
                "sku": b["sku"],
                "vendor": b["vendor"],
                "month": b["month"],
                "qty": round(sum(uoms.values()), 4),
                "uom": primary,
                "uoms": uoms,
                "mixed_uom": len(uoms) > 1,
            }
        )

    # Sort rows sensibly
    if breakdown == "month":
        rows_out.sort(key=lambda r: (r["month"], r["flow"]))
    elif breakdown == "vendor":
        rows_out.sort(key=lambda r: (r["vendor"], r["flow"]))
    elif breakdown == "sku":
        rows_out.sort(key=lambda r: (r["sku"], r["flow"]))
    elif breakdown == "flow":
        rows_out.sort(key=lambda r: r["flow"])

    return {
        "subject": (subject or "").strip().upper(),
        "scope": scope,
        "skus": skus,
        "date_from": (df.date() if df else d0).isoformat(),
        "date_to": (dt.date() if dt else d1).isoformat(),
        "vendor": vendor_s,
        "flows_selected": selected,
        "breakdown": breakdown,
        "totals": totals,
        "rows": rows_out,
        "mixed_uom": len(all_uoms) > 1,
        "event_count": len(logs),
        "has_subject": True,
        "flow_labels": FLOW_LABELS,
    }
