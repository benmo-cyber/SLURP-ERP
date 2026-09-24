from datetime import datetime
import re

from django.db import transaction
from django.db.models import Q
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_http_methods, require_POST

from erp_core.lot_display_quantities import compute_lot_quantity_breakdown
from erp_core.make_services import (
    MakeFlowError,
    adjust_batch_inputs,
    close_batch_ticket,
    create_batch_ticket,
    pack_units_for_mass,
    reverse_batch_ticket,
)
from erp_core.mass_quantity import LBS_PER_KG, convert_mass_uom, normalize_mass_quantity
from erp_core.models import (
    CriticalControlPoint,
    Formula,
    Item,
    ItemPreferredPackaging,
    Lot,
    ProductionBatch,
)
from erp_core.pack_display import format_pack_label, is_partial_lot, resolve_pack_size
from erp_core.packaging_suggest import suggested_containers_for_item
from erp_core.formula_ingredient import (
    lots_for_formula_ingredient,
    skus_for_formula_ingredient,
    skus_for_parent_code,
)
from erp_core.formula_resolve import formula_for_batch, formulas_for_fg, recipe_label
from erp_core.reversal_guard import build_batch_reversal_plan
from erp_core.sku_family import parse_sku_family

from ..nav import PRODUCTION_NAV

_FORMULA_BASELINE_RE = re.compile(r"\[FORMULA_BASELINE_QTY:([0-9]+(?:\.[0-9]+)?)\]")
_QUANTITY_TOLERANCE = 0.05


def _item_parent_code(item: Item | None) -> str:
    """Parent material code for cascade pickers (sku_parent_code or parsed from SKU)."""
    if item is None:
        return ""
    code = (item.sku_parent_code or "").strip().upper()
    if code:
        return code
    parent, _pack = parse_sku_family(
        item.sku or "",
        product_category=getattr(item, "product_category", None),
        item_type=getattr(item, "item_type", None),
    )
    if parent:
        return parent.strip().upper()
    return (item.sku or "").strip().upper()


def _formula_baseline_qty_lbs(batch: ProductionBatch) -> float:
    """Original ticket size (lbs) used for frozen formula targets on adjust."""
    m = _FORMULA_BASELINE_RE.search(batch.notes or "")
    if m:
        try:
            return normalize_mass_quantity(float(m.group(1)))
        except ValueError:
            pass
    return normalize_mass_quantity(float(batch.quantity_produced or 0))


def _ensure_formula_baseline(batch: ProductionBatch, qty_lbs: float | None = None) -> float:
    """Persist original ticket qty once so later QC adds don't rewrite formula targets."""
    existing = _FORMULA_BASELINE_RE.search(batch.notes or "")
    if existing:
        try:
            return normalize_mass_quantity(float(existing.group(1)))
        except ValueError:
            pass
    baseline = normalize_mass_quantity(
        float(qty_lbs if qty_lbs is not None else batch.quantity_produced or 0)
    )
    tag = f"[FORMULA_BASELINE_QTY:{baseline}]"
    notes = (batch.notes or "").strip()
    batch.notes = f"{notes}\n{tag}".strip() if notes else tag
    batch.save(update_fields=["notes", "updated_at"])
    return baseline


def _build_adjustment_summary(batch: ProductionBatch, formula: Formula | None, display_uom: str = "lbs"):
    """Per-ingredient formula target (frozen baseline) vs actual inputs for close/adjust UI."""
    if not formula or batch.batch_type != "production":
        return [], 0.0, 0.0
    baseline_lbs = _formula_baseline_qty_lbs(batch)
    # Sum actual usage by ingredient SKU set
    inputs = list(batch.inputs.select_related("lot__item", "item").all())
    rows = []
    total_delta_lbs = 0.0
    for ing in formula.ingredients.select_related("item").all():
        pct = float(ing.percentage or 0)
        target_lbs = normalize_mass_quantity(baseline_lbs * (pct / 100.0))
        skus = set(skus_for_formula_ingredient(ing))
        is_utility = bool(getattr(ing.item, "plant_utility", False))
        actual_lbs = 0.0
        for inp in inputs:
            item = inp.resolved_item() if hasattr(inp, "resolved_item") else None
            if item is None and inp.lot_id:
                item = inp.lot.item
            if not item:
                continue
            if is_utility:
                if item.id != ing.item_id:
                    continue
            elif (item.sku or "") not in skus:
                continue
            q = float(inp.quantity_used or 0)
            lu = (item.unit_of_measure or "lbs").lower()
            actual_lbs += _to_lbs(q, lu)
        actual_lbs = normalize_mass_quantity(actual_lbs)
        delta_lbs = normalize_mass_quantity(actual_lbs - target_lbs)
        total_delta_lbs = normalize_mass_quantity(total_delta_lbs + delta_lbs)
        target_disp = _native_to_display(target_lbs, "lbs", display_uom)
        actual_disp = _native_to_display(actual_lbs, "lbs", display_uom)
        delta_disp = _native_to_display(delta_lbs, "lbs", display_uom)
        rows.append(
            {
                "sku": ing.item.sku,
                "name": ing.item.name,
                "percentage": pct,
                "target": target_disp,
                "actual": actual_disp,
                "delta": delta_disp,
                "has_delta": abs(delta_lbs) > _QUANTITY_TOLERANCE,
            }
        )
    baseline_disp = _native_to_display(baseline_lbs, "lbs", display_uom)
    current_disp = _native_to_display(float(batch.quantity_produced or 0), "lbs", display_uom)
    return rows, baseline_disp, current_disp


def _prod_ctx(**extra):
    ctx = {
        "module": "production",
        "sidebar_nav": PRODUCTION_NAV,
        "active_tab": "batches",
        "page_css": ["Production.css", "ProductionBatchList.css", "CreateBatchTicket.css", "AdjustBatch.css", "BatchDetailView.css"],
    }
    ctx.update(extra)
    return ctx


def _batch_type(request: HttpRequest) -> str:
    bt = (request.GET.get("batch_type") or request.POST.get("batch_type") or "production").lower()
    return bt if bt in ("production", "repack") else "production"


def _to_lbs(qty: float, uom: str) -> float:
    u = (uom or "lbs").lower()
    if u in ("lb", "lbs"):
        return normalize_mass_quantity(qty)
    if u == "kg":
        return convert_mass_uom(qty, "kg", "lbs")
    return normalize_mass_quantity(qty)


def _display_to_native(qty_display: float, display_uom: str, native_uom: str) -> float:
    """Convert a quantity entered in ticket display unit into the lot/item native UoM."""
    d = (display_uom or "lbs").lower()
    n = (native_uom or "lbs").lower()
    if d in ("lb", "lbs"):
        d = "lbs"
    if n in ("lb", "lbs"):
        n = "lbs"
    if d == n or n not in ("lbs", "kg") or d not in ("lbs", "kg"):
        return normalize_mass_quantity(qty_display)
    return convert_mass_uom(qty_display, d, n)


def _close_storage_uom(batch: ProductionBatch) -> str:
    """Unit quantities are stored in on the batch row (production = lbs; repack = FG UoM)."""
    if batch.batch_type == "repack" and batch.finished_good_item_id:
        u = (batch.finished_good_item.unit_of_measure or "lbs").strip().lower() or "lbs"
        return "lbs" if u in ("lb", "lbs") else u
    return "lbs"


def _close_display_uom(batch: ProductionBatch) -> str:
    """Unit the ticket was entered in — spill/waste/actual on close use this."""
    saved = (getattr(batch, "batch_ticket_mass_unit", None) or "").strip().lower()
    if saved in ("lb", "lbs"):
        return "lbs"
    if saved == "kg":
        return "kg"
    if saved:
        return saved
    return _close_storage_uom(batch)


def _net_yield_native(batch: ProductionBatch) -> float | None:
    from erp_core.make_services import net_yield_native

    return net_yield_native(batch)


def _pack_breakout_for_item(item: Item | None, qty: float, qty_uom: str) -> dict | None:
    """Full packs + remainder for a quantity against the item's default pack size."""
    from erp_core.pack_display import pack_quantity_breakdown, resolve_pack_size

    if item is None or qty is None:
        return None
    try:
        q = float(qty)
    except (TypeError, ValueError):
        return None
    if q <= 0:
        return None
    pq, pu = resolve_pack_size(item=item)
    return pack_quantity_breakdown(q, qty_uom, pq, pu)


def _repack_item_choices():
    """Items with available lots suitable for repack (source SKUs)."""
    skus_with_lots = set(
        Lot.objects.filter(quantity_remaining__gt=0)
        .exclude(status="rejected")
        .values_list("item__sku", flat=True)
    )
    return list(
        Item.objects.filter(
            sku__in=skus_with_lots,
            item_type__in=["finished_good", "distributed_item", "raw_material"],
        ).order_by("sku")[:300]
    )


def _repack_target_choices(parent_code: str) -> list[Item]:
    """All pack variants under a parent (output SKUs), whether or not they have stock."""
    parent = (parent_code or "").strip().upper()
    if not parent:
        return []
    qs = Item.objects.filter(
        item_type__in=["finished_good", "distributed_item", "raw_material"]
    ).order_by("sku")
    # Prefer indexed parent code; also catch rows where parent equals full SKU
    by_code = list(qs.filter(sku_parent_code__iexact=parent)[:200])
    seen = {it.id for it in by_code}
    for it in qs.filter(sku__istartswith=parent)[:200]:
        if it.id in seen:
            continue
        if _item_parent_code(it) == parent:
            by_code.append(it)
            seen.add(it.id)
    return sorted(by_code, key=lambda it: (it.sku or "").upper())


def _packaging_lot_rows(limit: int = 80) -> list[dict]:
    """Available indirect-material (packaging) lots for repack/production pick lists."""
    lots = (
        Lot.objects.filter(
            item__item_type="indirect_material",
            quantity_remaining__gt=0,
        )
        .exclude(status="rejected")
        .select_related("item")
        .order_by("item__sku", "-received_date")[:limit]
    )
    rows = []
    for lot in lots:
        avail = float(compute_lot_quantity_breakdown(lot)["quantity_available_for_use"])
        if avail <= 0:
            continue
        rows.append(
            {
                "lot": lot,
                "available": avail,
                "sku": lot.item.sku,
                "name": lot.item.name or lot.item.description or lot.item.sku,
                "uom": (lot.item.unit_of_measure or "ea"),
            }
        )
    return rows


def _lots_for_packaging_item(packaging_item: Item, limit: int = 40) -> list[dict]:
    """Open lots for one preferred packaging SKU."""
    lots = (
        Lot.objects.filter(
            item=packaging_item,
            quantity_remaining__gt=0,
        )
        .exclude(status="rejected")
        .select_related("item")
        .order_by("-received_date")[:limit]
    )
    rows = []
    for lot in lots:
        avail = float(compute_lot_quantity_breakdown(lot)["quantity_available_for_use"])
        if avail <= 0:
            continue
        rows.append(
            {
                "lot": lot,
                "available": avail,
                "uom": (lot.item.unit_of_measure or "ea"),
            }
        )
    return rows


def _preferred_packaging_rows(fg: Item, display_uom: str, batch_qty: float = 0.0) -> list[dict]:
    """Preferred packaging lines with lots and optional suggested EA qty."""
    suggest = suggested_containers_for_item(fg, batch_qty, display_uom)
    suggested_n = suggest.get("suggested") if suggest.get("ok") else None
    prefs = list(
        ItemPreferredPackaging.objects.filter(finished_good=fg)
        .select_related("packaging_item")
        .order_by("sort_order", "id")
    )
    rows = []
    for pref in prefs:
        lots = _lots_for_packaging_item(pref.packaging_item)
        prefill = int(suggested_n) if pref.suggest_qty and suggested_n else None
        rows.append(
            {
                "pref": pref,
                "packaging_item": pref.packaging_item,
                "label": (pref.label or "").strip() or "Packaging",
                "suggest_qty": bool(pref.suggest_qty),
                "suggested": prefill,
                "lots": lots,
            }
        )
    return rows


def _parse_production_packaging_post(request: HttpRequest) -> list[dict]:
    """Build indirect_materials list from pkg_qty_* / pkg_other_qty_* fields."""
    out: list[dict] = []
    for key, raw_qty in request.POST.items():
        if not raw_qty:
            continue
        lot_id = None
        if key.startswith("pkg_qty_"):
            # pkg_qty_{prefId}_{lotId}
            parts = key.split("_")
            if len(parts) != 4:
                continue
            try:
                lot_id = int(parts[3])
                q = float(raw_qty)
            except (TypeError, ValueError):
                continue
        elif key.startswith("pkg_other_qty_"):
            # pkg_other_qty_{lotId}
            parts = key.split("_")
            if len(parts) != 4:
                continue
            try:
                lot_id = int(parts[3])
                q = float(raw_qty)
            except (TypeError, ValueError):
                continue
        else:
            continue
        if q <= 0 or lot_id is None:
            continue
        out.append({"lot_id": lot_id, "quantity_used": q})
    return out


def _repack_lot_rows(item: Item, display_uom: str):
    native = (item.unit_of_measure or "lbs").lower()
    lots = (
        Lot.objects.filter(item__sku=item.sku, quantity_remaining__gt=0)
        .exclude(status="rejected")
        .select_related("item")
        .order_by("-received_date")[:40]
    )
    rows = []
    for lot in lots:
        avail_native = float(compute_lot_quantity_breakdown(lot)["quantity_available_for_use"])
        if avail_native <= 0:
            continue
        try:
            avail_display = (
                convert_mass_uom(avail_native, native, display_uom)
                if native in ("lbs", "kg") and display_uom in ("lbs", "kg")
                else avail_native
            )
        except ValueError:
            avail_display = avail_native
        rows.append(
            {
                "lot": lot,
                "available_native": avail_native,
                "available_display": avail_display,
                "native_uom": native,
            }
        )
    return rows


def _production_date_local(batch: ProductionBatch):
    """Calendar date of batch.production_date in local time."""
    pd = getattr(batch, "production_date", None)
    if not pd:
        return None
    if timezone.is_aware(pd):
        return timezone.localtime(pd).date()
    return pd.date() if hasattr(pd, "date") else pd


def _god_mode_on(request: HttpRequest) -> bool:
    return bool(request.session.get("god_mode")) and bool(
        getattr(request.user, "is_authenticated", False) and request.user.is_staff
    )


def _close_before_production_blocked(batch: ProductionBatch, *, allow_early: bool) -> str | None:
    """
    Normally batches cannot close before production_date.
    Staff God mode overrides (allow_early=True).
    """
    if allow_early:
        return None
    pd = _production_date_local(batch)
    if pd is None:
        return None
    today = timezone.localdate()
    if pd > today:
        return (
            f"Cannot close before production date ({pd.isoformat()}). "
            "Enable God mode (staff) to close early, or wait until that date."
        )
    return None


def _dash_url_name(batch_type: str) -> str:
    return (
        "slurp_ui:production_repacks"
        if batch_type == "repack"
        else "slurp_ui:production"
    )


def _archive_url_name(batch_type: str) -> str:
    return (
        "slurp_ui:production_repack_archive"
        if batch_type == "repack"
        else "slurp_ui:production_archive"
    )


def _batch_list(request: HttpRequest, *, batch_type: str, active_tab: str) -> HttpResponse:
    batches = list(
        ProductionBatch.objects.filter(is_archived=False, batch_type=batch_type)
        .select_related("finished_good_item", "campaign")
        .prefetch_related("finished_good_item__pack_sizes")
        .order_by("-created_at")[:200]
    )
    allow_early = _god_mode_on(request)
    today = timezone.localdate()
    batch_rows = []
    for b in batches:
        storage = _close_storage_uom(b)
        display = _close_display_uom(b)
        actual_disp = None
        pack_breakout = ""
        campaign_code = ""
        if b.status == "closed" and b.quantity_actual is not None:
            yield_native = _net_yield_native(b)
            actual_disp = (
                _native_to_display(float(yield_native), storage, display)
                if yield_native is not None
                else None
            )
            if actual_disp is not None:
                brk = _pack_breakout_for_item(b.finished_good_item, actual_disp, display)
                if brk:
                    pack_breakout = brk["display"]
        if b.campaign_id and getattr(b, "campaign", None):
            campaign_code = b.campaign.campaign_code or ""
        prod_local = _production_date_local(b)
        early_blocked = bool(prod_local and prod_local > today and not allow_early)
        batch_rows.append(
            {
                "batch": b,
                "ticket_display": _native_to_display(
                    float(b.quantity_produced or 0), storage, display
                ),
                "actual_display": actual_disp,
                "display_uom": display,
                "pack_breakout": pack_breakout,
                "campaign_code": campaign_code,
                "can_close": not early_blocked,
                "close_blocked_reason": (
                    f"Production date is {prod_local.isoformat()}. Enable God mode to close early."
                    if early_blocked and prod_local
                    else ""
                ),
            }
        )
    return render(
        request,
        "slurp_ui/production/batches.html",
        _prod_ctx(
            active_tab=active_tab,
            batches=batches,
            batch_rows=batch_rows,
            list_batch_type=batch_type,
            port_status="full",
        ),
    )


@login_required
def production_batches(request: HttpRequest) -> HttpResponse:
    return _batch_list(request, batch_type="production", active_tab="batches")


@login_required
def production_repacks(request: HttpRequest) -> HttpResponse:
    return _batch_list(request, batch_type="repack", active_tab="repacks")


@login_required
def production_archive(
    request: HttpRequest, locked_batch_type: str | None = None
) -> HttpResponse:
    """Archived tickets: search + year/month or product folders.

    locked_batch_type: when set via URL kwargs, scopes the archive to that type
    (Batch Archive → production, Repack Archive → repack).
    """
    from calendar import month_name
    from django.db.models import Count
    from django.db.models.functions import Coalesce, TruncMonth, TruncYear

    q = (request.GET.get("q") or "").strip()
    if locked_batch_type in ("production", "repack"):
        batch_type = locked_batch_type
    else:
        batch_type = (request.GET.get("batch_type") or "all").strip().lower()
        if batch_type not in ("all", "production", "repack"):
            batch_type = "all"
    browse = (request.GET.get("browse") or "date").strip().lower()
    if browse not in ("date", "product"):
        browse = "date"
    archive_root_label = (
        "Repack archive"
        if batch_type == "repack"
        else "Batch archive"
        if batch_type == "production"
        else "Archive"
    )
    archive_url = (
        "slurp_ui:production_repack_archive"
        if locked_batch_type == "repack" or batch_type == "repack"
        else "slurp_ui:production_archive"
    )
    dash_url = _dash_url_name(
        "repack" if batch_type == "repack" else "production"
    )
    active_tab = (
        "repack-archive" if batch_type == "repack" else "archive"
    )

    year_raw = (request.GET.get("year") or "").strip()
    month_raw = (request.GET.get("month") or "").strip()
    product_id_raw = (request.GET.get("product") or "").strip()
    year = int(year_raw) if year_raw.isdigit() else None
    month = int(month_raw) if month_raw.isdigit() and 1 <= int(month_raw) <= 12 else None
    product_id = int(product_id_raw) if product_id_raw.isdigit() else None

    base = ProductionBatch.objects.filter(is_archived=True).select_related(
        "finished_good_item", "finished_good_item__product_family"
    )
    if batch_type in ("production", "repack"):
        base = base.filter(batch_type=batch_type)
    if q:
        base = base.filter(
            Q(batch_number__icontains=q)
            | Q(finished_good_item__sku__icontains=q)
            | Q(finished_good_item__name__icontains=q)
            | Q(notes__icontains=q)
        )

    # Prefer close date for filing; fall back to archive / production date.
    dated = base.annotate(
        folder_date=Coalesce("closed_date", "archived_at", "production_date")
    )

    folders = []
    batches = []
    folder_level = "list"  # years | months | products | list
    crumbs = [{"label": archive_root_label, "url_params": {"browse": browse}}]
    if batch_type != "all" and not locked_batch_type:
        crumbs[0]["url_params"]["batch_type"] = batch_type
    if q:
        crumbs[0]["url_params"]["q"] = q

    def _qp(**extra):
        params = {"browse": browse}
        if batch_type != "all" and not locked_batch_type:
            params["batch_type"] = batch_type
        if q:
            params["q"] = q
        params.update({k: v for k, v in extra.items() if v not in (None, "")})
        return params

    if q and not year and not month and not product_id:
        # Free search across archive — flat list, still respect browse filter chips.
        batches = list(dated.order_by("-folder_date", "-id")[:300])
        folder_level = "list"
        crumbs.append({"label": f'Search “{q}”', "url_params": None})
    elif browse == "product":
        if product_id:
            item = Item.objects.filter(pk=product_id).first()
            label = (
                f"{item.sku} — {item.name}" if item else f"Product #{product_id}"
            )
            crumbs.append(
                {
                    "label": "By product",
                    "url_params": _qp(browse="product"),
                }
            )
            crumbs.append({"label": label, "url_params": None})
            batches = list(
                dated.filter(finished_good_item_id=product_id).order_by(
                    "-folder_date", "-id"
                )[:300]
            )
            folder_level = "list"
        else:
            folder_level = "products"
            crumbs.append({"label": "By product", "url_params": None})
            rows = (
                dated.values(
                    "finished_good_item_id",
                    "finished_good_item__sku",
                    "finished_good_item__name",
                    "finished_good_item__product_family__code",
                )
                .annotate(n=Count("id"))
                .order_by("finished_good_item__sku")
            )
            for row in rows:
                fam = row.get("finished_good_item__product_family__code") or ""
                folders.append(
                    {
                        "kind": "product",
                        "label": row["finished_good_item__sku"] or "—",
                        "sublabel": row["finished_good_item__name"] or "",
                        "meta": fam,
                        "count": row["n"],
                        "url_params": _qp(
                            browse="product",
                            product=row["finished_good_item_id"],
                        ),
                    }
                )
    else:
        # Date browse: years → months → batches
        if year and month:
            crumbs.append(
                {
                    "label": "By date",
                    "url_params": _qp(browse="date"),
                }
            )
            crumbs.append(
                {
                    "label": str(year),
                    "url_params": _qp(browse="date", year=year),
                }
            )
            crumbs.append(
                {
                    "label": month_name[month],
                    "url_params": None,
                }
            )
            batches = list(
                dated.filter(
                    folder_date__year=year, folder_date__month=month
                ).order_by("-folder_date", "-id")[:300]
            )
            folder_level = "list"
        elif year:
            crumbs.append(
                {
                    "label": "By date",
                    "url_params": _qp(browse="date"),
                }
            )
            crumbs.append({"label": str(year), "url_params": None})
            folder_level = "months"
            rows = (
                dated.filter(folder_date__year=year)
                .annotate(m=TruncMonth("folder_date"))
                .values("m")
                .annotate(n=Count("id"))
                .order_by("-m")
            )
            for row in rows:
                mdt = row["m"]
                if not mdt:
                    continue
                folders.append(
                    {
                        "kind": "month",
                        "label": month_name[mdt.month],
                        "sublabel": str(mdt.year),
                        "meta": mdt.strftime("%Y-%m"),
                        "count": row["n"],
                        "url_params": _qp(
                            browse="date", year=mdt.year, month=mdt.month
                        ),
                    }
                )
        else:
            crumbs.append({"label": "By date", "url_params": None})
            folder_level = "years"
            rows = (
                dated.annotate(y=TruncYear("folder_date"))
                .values("y")
                .annotate(n=Count("id"))
                .order_by("-y")
            )
            for row in rows:
                ydt = row["y"]
                if not ydt:
                    continue
                folders.append(
                    {
                        "kind": "year",
                        "label": str(ydt.year),
                        "sublabel": "Year",
                        "meta": "",
                        "count": row["n"],
                        "url_params": _qp(browse="date", year=ydt.year),
                    }
                )

    # Preserve folder filters in restore-next links
    restore_params = _qp(
        year=year,
        month=month,
        product=product_id,
    )
    if folder_level == "list" and not batches and not folders and not q:
        # Empty archive root
        pass

    archive_batch_rows = []
    for b in batches:
        storage = _close_storage_uom(b)
        display = _close_display_uom(b)
        yield_native = _net_yield_native(b)
        archive_batch_rows.append(
            {
                "batch": b,
                "ticket_display": _native_to_display(
                    float(b.quantity_produced or 0), storage, display
                ),
                "yield_display": (
                    _native_to_display(float(yield_native), storage, display)
                    if yield_native is not None
                    else None
                ),
                "display_uom": display,
            }
        )

    return render(
        request,
        "slurp_ui/production/archive.html",
        _prod_ctx(
            active_tab=active_tab,
            batches=batches,
            archive_batch_rows=archive_batch_rows,
            folders=folders,
            folder_level=folder_level,
            crumbs=crumbs,
            browse=browse,
            q=q,
            batch_type=batch_type,
            locked_batch_type=locked_batch_type,
            archive_root_label=archive_root_label,
            archive_url_name=archive_url,
            dash_url_name=dash_url,
            year=year,
            month=month,
            product_id=product_id,
            restore_params=restore_params,
            result_count=len(batches) if folder_level == "list" else sum(
                f["count"] for f in folders
            ),
            port_status="full",
            page_css=[
                "Production.css",
                "ProductionBatchList.css",
                "ProductionArchive.css",
            ],
        ),
    )


@login_required
@require_POST
def production_archive_batch(request: HttpRequest, pk: int) -> HttpResponse:
    batch = get_object_or_404(ProductionBatch, pk=pk)
    next_url = (request.POST.get("next") or "").strip() or None
    dash = _dash_url_name(batch.batch_type)
    archive = _archive_url_name(batch.batch_type)
    archive_label = (
        "Repack Archive" if batch.batch_type == "repack" else "Batch Archive"
    )
    if batch.status != "closed":
        messages.error(
            request,
            "You must close the batch ticket before archiving.",
        )
        return redirect(next_url) if next_url else redirect(
            "slurp_ui:production_batch_detail", pk=pk
        )
    if batch.is_archived:
        messages.info(request, f"{batch.batch_number} is already archived.")
        return redirect(next_url) if next_url else redirect(archive)
    batch.is_archived = True
    batch.archived_at = timezone.now()
    batch.save(update_fields=["is_archived", "archived_at", "updated_at"])
    messages.success(
        request,
        f"Archived {batch.batch_number}. Find it under Production → {archive_label}.",
    )
    return redirect(next_url) if next_url else redirect(dash)


@login_required
@require_POST
def production_unarchive_batch(request: HttpRequest, pk: int) -> HttpResponse:
    batch = get_object_or_404(ProductionBatch, pk=pk)
    next_url = (request.POST.get("next") or "").strip() or None
    dash = _dash_url_name(batch.batch_type)
    dash_label = (
        "repacks dash" if batch.batch_type == "repack" else "batch tickets dash"
    )
    if not batch.is_archived:
        messages.info(request, f"{batch.batch_number} is not archived.")
        return redirect(next_url) if next_url else redirect(dash)
    batch.is_archived = False
    batch.archived_at = None
    batch.save(update_fields=["is_archived", "archived_at", "updated_at"])
    messages.success(request, f"Restored {batch.batch_number} to the {dash_label}.")
    return redirect(next_url) if next_url else redirect(dash)


@login_required
@require_http_methods(["GET", "POST"])
def production_batch_detail(request: HttpRequest, pk: int) -> HttpResponse:
    batch = get_object_or_404(
        ProductionBatch.objects.select_related(
            "finished_good_item", "formula", "campaign"
        ).prefetch_related("inputs__lot__item", "outputs__lot"),
        pk=pk,
    )
    can_edit_date = batch.status in ("draft", "scheduled", "in_progress")

    if request.method == "POST" and request.POST.get("action") == "set_production_date":
        if not can_edit_date:
            messages.error(request, f"Cannot change date on a {batch.status} batch.")
            return redirect("slurp_ui:production_batch_detail", pk=pk)
        new_date = parse_date((request.POST.get("production_date") or "").strip())
        if not new_date:
            messages.error(request, "Production date is required.")
        else:
            old = batch.production_date.date().isoformat() if batch.production_date else "—"
            batch.production_date = timezone.make_aware(datetime.combine(new_date, datetime.min.time()))
            batch.save(update_fields=["production_date", "updated_at"])
            messages.success(
                request,
                f"Production date for {batch.batch_number} moved {old} -> {new_date.isoformat()}.",
            )
        return redirect("slurp_ui:production_batch_detail", pk=pk)

    formula = None
    if batch.batch_type == "production":
        formula = formula_for_batch(batch)
        if formula is not None:
            formula = (
                Formula.objects.filter(pk=formula.pk)
                .prefetch_related("ingredients__item")
                .first()
            )
    can_adjust = batch.status not in ("closed", "cancelled") and not batch.is_archived
    early_msg = _close_before_production_blocked(
        batch, allow_early=_god_mode_on(request)
    )
    can_close = batch.status != "closed" and not batch.is_archived and not early_msg
    qc_parsed = None
    if batch.status == "closed":
        from erp_core.hold_services import parse_batch_qc_notes

        qc_parsed = parse_batch_qc_notes(batch.notes)
    mass_uom = _close_display_uom(batch)
    storage_uom = _close_storage_uom(batch)
    ticket_qty_display = _native_to_display(
        float(batch.quantity_produced or 0), storage_uom, mass_uom
    )
    yield_native = _net_yield_native(batch) if batch.status == "closed" else None
    actual_qty_display = (
        _native_to_display(float(yield_native), storage_uom, mass_uom)
        if yield_native is not None
        else None
    )
    wastes_display = _native_to_display(
        float(batch.wastes or 0), storage_uom, mass_uom
    )
    spills_display = _native_to_display(
        float(batch.spills or 0), storage_uom, mass_uom
    )
    variance_display = (
        _native_to_display(float(batch.variance), storage_uom, mass_uom)
        if batch.variance is not None
        else None
    )
    pack_breakout = None
    if actual_qty_display is not None:
        pack_breakout = _pack_breakout_for_item(
            batch.finished_good_item, actual_qty_display, mass_uom
        )
    return render(
        request,
        "slurp_ui/production/batch_detail.html",
        _prod_ctx(
            active_tab="repacks" if batch.batch_type == "repack" else "batches",
            batch=batch,
            formula=formula,
            recipe_label=recipe_label(formula),
            formula_label=recipe_label(formula),
            can_adjust=can_adjust,
            can_edit_date=can_edit_date,
            can_close=can_close,
            close_blocked_reason=early_msg or "",
            qc_parsed=qc_parsed,
            mass_uom=mass_uom,
            ticket_qty_display=ticket_qty_display,
            actual_qty_display=actual_qty_display,
            wastes_display=wastes_display,
            spills_display=spills_display,
            variance_display=variance_display,
            pack_breakout=pack_breakout,
            dash_url_name=_dash_url_name(batch.batch_type),
            archive_url_name=_archive_url_name(batch.batch_type),
            archive_label=(
                "Repack Archive"
                if batch.batch_type == "repack"
                else "Batch Archive"
            ),
            dash_label=(
                "repacks dash"
                if batch.batch_type == "repack"
                else "batch tickets dash"
            ),
            port_status="full",
        ),
    )


@login_required
def production_batch_pdf(request: HttpRequest, pk: int) -> HttpResponse:
    batch = get_object_or_404(ProductionBatch.objects.select_related("finished_good_item"), pk=pk)
    try:
        from erp_core.batch_ticket_pdf_html import generate_batch_ticket_pdf_from_html

        mass_q = request.GET.get("mass_unit")
        pdf_bytes, filename = generate_batch_ticket_pdf_from_html(batch, mass_unit=mass_q)
    except Exception as e:
        messages.error(request, f"PDF generation failed: {e}")
        return redirect("slurp_ui:production_batch_detail", pk=pk)

    if not pdf_bytes:
        messages.error(request, "Failed to generate batch ticket PDF.")
        return redirect("slurp_ui:production_batch_detail", pk=pk)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    fname = filename or f"{batch.batch_number or pk}.pdf"
    disposition = "attachment" if request.GET.get("download") else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{fname}"'
    return response


@login_required
@require_http_methods(["GET", "POST"])
def production_create_batch(request: HttpRequest) -> HttpResponse:
    """Production or repack batch ticket create."""
    batch_type = _batch_type(request)
    formulas = (
        Formula.objects.select_related("finished_good")
        .prefetch_related("ingredients__item")
        .order_by("finished_good__sku", "-is_default", "name", "id")
    )
    repack_items = _repack_item_choices() if batch_type == "repack" else []

    # Parent → full SKU cascade (production also has formula step)
    parent_choices: list[str] = []
    fg_choices: list[Item] = []
    formula_choices: list[Formula] = []
    target_choices: list[Item] = []
    selected_parent = (request.GET.get("parent") or request.POST.get("parent") or "").strip().upper()
    selected_fg_id = request.GET.get("item") or request.POST.get("finished_good_id") or ""
    selected_formula = None
    selected_repack_item = None
    selected_repack_target = None
    selected_fg = None
    formula_id = request.GET.get("formula") or request.POST.get("formula_id")
    repack_item_id = request.GET.get("item") or request.POST.get("repack_item_id")

    if batch_type == "production":
        # Unique parent codes from FGs that have at least one formula
        parent_map: dict[str, dict[int, Item]] = {}
        for f in formulas:
            fg = f.finished_good
            if not fg:
                continue
            pcode = _item_parent_code(fg)
            if not pcode:
                continue
            parent_map.setdefault(pcode, {})[fg.id] = fg
        parent_choices = sorted(parent_map.keys())

        if selected_parent and selected_parent not in parent_map:
            selected_parent = ""

        if selected_parent:
            fg_choices = sorted(
                parent_map[selected_parent].values(),
                key=lambda it: (it.sku or "").upper(),
            )
            # Auto-select sole pack SKU under this parent
            if not selected_fg_id and len(fg_choices) == 1:
                selected_fg_id = str(fg_choices[0].id)

        if selected_fg_id:
            try:
                fg_pk = int(selected_fg_id)
            except (TypeError, ValueError):
                fg_pk = None
            if fg_pk and selected_parent:
                selected_fg = parent_map.get(selected_parent, {}).get(fg_pk)
            elif fg_pk:
                # parent missing from URL — recover from item
                for pcode, items in parent_map.items():
                    if fg_pk in items:
                        selected_fg = items[fg_pk]
                        selected_parent = pcode
                        fg_choices = sorted(
                            items.values(), key=lambda it: (it.sku or "").upper()
                        )
                        break
            if selected_fg is None:
                selected_fg_id = ""

        if selected_fg:
            from django.db.models import Count

            formula_choices = list(
                formulas_for_fg(selected_fg.id)
                .annotate(_ing_n=Count("ingredients"))
                .filter(_ing_n__gt=0)
            )
            if formula_id:
                selected_formula = next(
                    (f for f in formula_choices if str(f.id) == str(formula_id)), None
                )
            # Single usable formula: always lock it (no alternate picker)
            if len(formula_choices) == 1:
                selected_formula = formula_choices[0]
            elif selected_formula is None and len(formula_choices) > 1:
                # Prefer default among usable formulas
                selected_formula = next(
                    (f for f in formula_choices if f.is_default),
                    formula_choices[0],
                )
            if selected_formula is not None:
                selected_formula = (
                    Formula.objects.filter(pk=selected_formula.id)
                    .select_related("finished_good")
                    .prefetch_related("ingredients__item")
                    .first()
                )

    elif batch_type == "repack":
        parent_map: dict[str, dict[int, Item]] = {}
        for it in repack_items:
            pcode = _item_parent_code(it) or (it.sku or "").strip().upper()
            if not pcode:
                continue
            parent_map.setdefault(pcode, {})[it.id] = it
        parent_choices = sorted(parent_map.keys())

        if selected_parent and selected_parent not in parent_map:
            # Still allow parent if only targets exist under it with no source stock
            if not _repack_target_choices(selected_parent):
                selected_parent = ""

        if selected_parent:
            fg_choices = sorted(
                parent_map.get(selected_parent, {}).values(),
                key=lambda it: (it.sku or "").upper(),
            )
            target_choices = _repack_target_choices(selected_parent)
            if not repack_item_id and len(fg_choices) == 1:
                repack_item_id = str(fg_choices[0].id)

        if repack_item_id:
            try:
                item_pk = int(repack_item_id)
            except (TypeError, ValueError):
                item_pk = None
            if item_pk and selected_parent:
                selected_repack_item = parent_map.get(selected_parent, {}).get(item_pk)
            elif item_pk:
                for pcode, items in parent_map.items():
                    if item_pk in items:
                        selected_repack_item = items[item_pk]
                        selected_parent = pcode
                        fg_choices = sorted(
                            items.values(), key=lambda it: (it.sku or "").upper()
                        )
                        target_choices = _repack_target_choices(selected_parent)
                        break
            if selected_repack_item is None:
                selected_repack_item = Item.objects.filter(pk=repack_item_id).first()
                if selected_repack_item and not selected_parent:
                    selected_parent = _item_parent_code(selected_repack_item) or (
                        selected_repack_item.sku or ""
                    ).strip().upper()
                if selected_repack_item and selected_parent:
                    if selected_parent in parent_map:
                        fg_choices = sorted(
                            parent_map[selected_parent].values(),
                            key=lambda it: (it.sku or "").upper(),
                        )
                    target_choices = _repack_target_choices(selected_parent)

        if not target_choices and selected_parent:
            target_choices = _repack_target_choices(selected_parent)

        target_raw = request.GET.get("target") or request.POST.get("target_item_id") or ""
        if target_raw and target_choices:
            try:
                tid = int(target_raw)
            except (TypeError, ValueError):
                tid = None
            if tid:
                selected_repack_target = next(
                    (it for it in target_choices if it.id == tid), None
                )
        if selected_repack_target is None and selected_repack_item and target_choices:
            if len(target_choices) == 1:
                selected_repack_target = target_choices[0]
            else:
                selected_repack_target = next(
                    (it for it in target_choices if it.id == selected_repack_item.id),
                    None,
                )

    # Mass display unit: for repack default to *item native* (e.g. kg for J1410).
    # Honor explicit lbs/kg only when the user toggled (GET uom / POST batch_ticket_mass_unit).
    # Do not stick cascade forms at lbs when the SKU is kg.
    requested_uom = (
        request.POST.get("batch_ticket_mass_unit") or request.GET.get("uom") or ""
    ).strip().lower()
    if requested_uom in ("lb", "lbs"):
        requested_uom = "lbs"

    if batch_type == "repack":
        uom_item = selected_repack_target or selected_repack_item
        native = "lbs"
        if uom_item:
            native = (uom_item.unit_of_measure or "lbs").strip().lower() or "lbs"
            if native in ("lb", "lbs"):
                native = "lbs"
        if native in ("lbs", "kg"):
            display_uom = requested_uom if requested_uom in ("lbs", "kg") else native
        else:
            # Pack / count UoM — no lbs/kg conversion toggle
            display_uom = native
    else:
        display_uom = requested_uom if requested_uom in ("lbs", "kg") else "lbs"

    is_relabel = bool(
        batch_type == "repack"
        and selected_repack_item
        and selected_repack_target
        and selected_repack_item.id == selected_repack_target.id
    )

    ingredient_lot_choices = []
    repack_lot_rows = []
    work_in_partial_lots = []
    if selected_formula:
        fg = selected_formula.finished_good
        parent = _item_parent_code(fg)
        family_skus = skus_for_parent_code(parent) if parent else []
        if not family_skus and fg:
            family_skus = [(fg.sku or "").strip()]
        family_skus = [s for s in family_skus if s]
        fg_lots = (
            Lot.objects.filter(
                item__sku__in=family_skus,
                status="accepted",
                quantity_remaining__gt=0,
            )
            .select_related("item", "pack_size")
            .prefetch_related("item__pack_sizes")
            .order_by("-received_date")
        )
        for lot in fg_lots:
            if is_partial_lot(lot):
                avail = float(compute_lot_quantity_breakdown(lot)["quantity_available_for_use"])
                if avail <= 0:
                    continue
                pack_qty, pack_uom = resolve_pack_size(item=lot.item, lot=lot)
                work_in_partial_lots.append(
                    {
                        "lot": lot,
                        "available": avail,
                        "uom": (lot.item.unit_of_measure or "lbs"),
                        "pack_label": format_pack_label(item=lot.item, lot=lot),
                        "pack_qty": pack_qty,
                        "pack_uom": pack_uom,
                        "same_sku": bool(fg and lot.item_id == fg.id),
                    }
                )

        for ing in selected_formula.ingredients.all():
            native = (ing.item.unit_of_measure or "lbs").lower()
            is_utility = bool(getattr(ing.item, "plant_utility", False))
            lot_rows = []
            if not is_utility:
                lots = lots_for_formula_ingredient(ing, limit=80)
                for lot in lots:
                    avail_native = float(
                        compute_lot_quantity_breakdown(lot)["quantity_available_for_use"]
                    )
                    if avail_native <= 0:
                        continue
                    lot_native = (lot.item.unit_of_measure or native or "lbs").lower()
                    try:
                        avail_display = (
                            convert_mass_uom(avail_native, lot_native, display_uom)
                            if lot_native in ("lbs", "kg") and display_uom in ("lbs", "kg")
                            else avail_native
                        )
                    except ValueError:
                        avail_display = avail_native
                    partial = is_partial_lot(lot)
                    lot_rows.append(
                        {
                            "lot": lot,
                            "available_native": avail_native,
                            "available_display": avail_display,
                            "native_uom": lot_native,
                            "is_partial": partial,
                            "pack_label": format_pack_label(item=lot.item, lot=lot),
                        }
                    )
                # Prefer opened/partial packs first so they get used up
                lot_rows.sort(key=lambda r: (0 if r["is_partial"] else 1, -r["available_native"]))
            ingredient_lot_choices.append(
                {
                    "ingredient": ing,
                    "percentage": float(ing.percentage or 0),
                    "native_uom": native,
                    "plant_utility": is_utility,
                    "match_by_parent": bool(getattr(ing, "match_by_parent", False)),
                    "parent_code": (getattr(ing.item, "sku_parent_code", None) or "") if getattr(ing, "match_by_parent", False) else "",
                    "lots": lot_rows,
                }
            )
    elif selected_repack_item:
        repack_lot_rows = _repack_lot_rows(selected_repack_item, display_uom)

    packaging_lot_rows = []
    preferred_packaging_rows = []
    packaging_suggest = None
    target_pack_qty = None
    target_pack_uom = None
    target_pack_label = ""
    ccp_choices = []
    if batch_type == "repack" and selected_repack_item and selected_repack_target:
        if not is_relabel:
            packaging_lot_rows = _packaging_lot_rows()
            # Seed preferred packaging from target FPS when available
            preferred_packaging_rows = _preferred_packaging_rows(
                selected_repack_target, display_uom, batch_qty=0.0
            )
            ccp_choices = list(CriticalControlPoint.objects.all())
        target_pack_qty, target_pack_uom = resolve_pack_size(item=selected_repack_target)
        target_pack_label = format_pack_label(item=selected_repack_target)
    elif batch_type == "production" and selected_fg:
        packaging_lot_rows = _packaging_lot_rows()
        preferred_packaging_rows = _preferred_packaging_rows(
            selected_fg, display_uom, batch_qty=0.0
        )
        packaging_suggest = suggested_containers_for_item(selected_fg, 0.0, display_uom)

    if request.method == "POST":
        packaging_needs_confirm = False
        if batch_type == "repack" and selected_repack_item:
            target_item = selected_repack_target or selected_repack_item
            is_relabel_post = bool(
                target_item and selected_repack_item.id == target_item.id
            )
            try:
                qty_display = float(request.POST.get("quantity_produced") or 0)
            except ValueError:
                qty_display = 0
            target_native = (target_item.unit_of_measure or "lbs").lower()
            source_native = (selected_repack_item.unit_of_measure or "lbs").lower()
            # quantity_produced is entered in display_uom toward the *target* SKU
            qty_target = (
                _display_to_native(qty_display, display_uom, target_native)
                if qty_display > 0
                else 0.0
            )

            inputs = []
            for lot_row in repack_lot_rows:
                lot = lot_row["lot"]
                raw_qty = request.POST.get(f"repack_qty_{lot.id}")
                if not raw_qty:
                    continue
                try:
                    q_display = float(raw_qty)
                except ValueError:
                    continue
                if q_display <= 0:
                    continue
                # Lot qty entered in display_uom; convert to *source* native for inventory
                q_native = _display_to_native(q_display, display_uom, source_native)
                inputs.append({"lot_id": lot.id, "quantity_used": q_native})

            indirect_materials = []
            ccp_id = None
            if not is_relabel_post:
                for prow in packaging_lot_rows:
                    lot = prow["lot"]
                    raw_qty = request.POST.get(f"pack_qty_{lot.id}")
                    if not raw_qty:
                        continue
                    try:
                        q = float(raw_qty)
                    except ValueError:
                        continue
                    if q <= 0:
                        continue
                    indirect_materials.append({"lot_id": lot.id, "quantity_used": q})
                ccp_raw = (request.POST.get("critical_control_point_id") or "").strip()
                if ccp_raw.isdigit():
                    ccp_id = int(ccp_raw)

            if not inputs:
                messages.error(request, "Select at least one source lot with quantity.")
            elif not target_item:
                messages.error(request, "Select a target (output) SKU.")
            elif not is_relabel_post and not indirect_materials:
                messages.error(
                    request,
                    "Pack-change repacks require packaging (indirect materials). "
                    "Select at least one packaging lot.",
                )
            elif not is_relabel_post and not ccp_id:
                messages.error(
                    request,
                    "Pack-change repacks require a CCP (screen) selection.",
                )
            elif not is_relabel_post and ccp_id and not CriticalControlPoint.objects.filter(pk=ccp_id).exists():
                messages.error(request, "Selected CCP is invalid.")
            else:
                if qty_target <= 0:
                    # Derive target qty from converted source inputs
                    total_target = 0.0
                    for inp in inputs:
                        total_target += float(
                            convert_mass_uom(
                                inp["quantity_used"],
                                source_native if source_native in ("lbs", "kg") else "lbs",
                                target_native if target_native in ("lbs", "kg") else "lbs",
                            )
                            if source_native in ("lbs", "kg") and target_native in ("lbs", "kg")
                            and source_native != target_native
                            else inp["quantity_used"]
                        )
                    qty_target = normalize_mass_quantity(total_target)

                notes = (request.POST.get("notes") or "").strip()
                if is_relabel_post:
                    tag = "[RELABEL — same container; no packaging / CCP]"
                    notes = f"{notes}\n{tag}".strip() if notes else tag

                payload = {
                    "batch_type": "repack",
                    "finished_good_item_id": target_item.id,
                    "quantity_produced": qty_target,
                    "production_date": (
                        request.POST.get("production_date") or timezone.localdate().isoformat()
                    ),
                    "status": "in_progress",
                    "batch_ticket_mass_unit": display_uom,
                    "notes": notes,
                    "inputs": inputs,
                    "indirect_materials": indirect_materials,
                    "work_in_partials": [],
                }
                if ccp_id:
                    payload["critical_control_point"] = ccp_id
                try:
                    with transaction.atomic():
                        batch = create_batch_ticket(request.user, payload)
                        if is_relabel_post:
                            # Relabel never opens packs — close immediately so the
                            # output lot number exists for labels.
                            batch = close_batch_ticket(
                                batch,
                                request.user,
                                {
                                    "quantity_actual": float(
                                        batch.quantity_produced or 0
                                    ),
                                    "wastes": 0.0,
                                    "spills": 0.0,
                                    "notes": batch.notes,
                                    "allow_early_close": _god_mode_on(request),
                                },
                            )
                            out = (
                                batch.outputs.select_related("lot").first()
                            )
                            lot_num = (
                                out.lot.lot_number
                                if out is not None and out.lot_id
                                else "—"
                            )
                            messages.success(
                                request,
                                f"Relabeled {batch.batch_number} — output lot {lot_num}.",
                            )
                        else:
                            messages.success(
                                request,
                                f"Created repack batch {batch.batch_number}.",
                            )
                    return redirect("slurp_ui:production_batch_detail", pk=batch.id)
                except MakeFlowError as e:
                    messages.error(request, e.message)
                except Exception as e:
                    messages.error(request, str(e))

        elif batch_type == "production" and selected_formula:
            try:
                qty_display = float(request.POST.get("quantity_produced") or 0)
            except ValueError:
                qty_display = 0

            qty_lbs = _to_lbs(qty_display, display_uom) if qty_display > 0 else 0.0

            inputs = []
            # Parse multi-lot allocations: ing_qty_<ingredient_id>_<lot_id>
            for key, raw_qty in request.POST.items():
                if not key.startswith("ing_qty_") or not raw_qty:
                    continue
                parts = key.split("_")
                # ing_qty_{ingId}_{lotId}
                if len(parts) != 4:
                    continue
                try:
                    lot_id = int(parts[3])
                    q_display = float(raw_qty)
                except (TypeError, ValueError):
                    continue
                if q_display <= 0:
                    continue
                try:
                    lot = Lot.objects.select_related("item").get(pk=lot_id)
                except Lot.DoesNotExist:
                    continue
                native = (lot.item.unit_of_measure or "lbs").lower()
                q_native = _display_to_native(q_display, display_uom, native)
                inputs.append({"lot_id": lot_id, "quantity_used": q_native})

            # Plant utility qty: plant_utility_qty_<ingredient_id>
            for key, raw_qty in request.POST.items():
                if not key.startswith("plant_utility_qty_") or not raw_qty:
                    continue
                try:
                    ing_id = int(key.split("_")[-1])
                    q_display = float(raw_qty)
                except (TypeError, ValueError):
                    continue
                if q_display <= 0:
                    continue
                ing = next(
                    (r["ingredient"] for r in ingredient_lot_choices if r["ingredient"].id == ing_id),
                    None,
                )
                if not ing or not getattr(ing.item, "plant_utility", False):
                    continue
                native = (ing.item.unit_of_measure or "lbs").lower()
                q_native = _display_to_native(q_display, display_uom, native)
                inputs.append({"item_id": ing.item_id, "quantity_used": q_native})

            if not inputs:
                messages.error(request, "Allocate quantity on at least one ingredient.")
            else:
                if qty_lbs <= 0:
                    qty_lbs = 0.0
                    for row in inputs:
                        if row.get("lot_id"):
                            lot = Lot.objects.select_related("item").get(pk=row["lot_id"])
                            uom = lot.item.unit_of_measure or "lbs"
                        else:
                            item = Item.objects.get(pk=row["item_id"])
                            uom = item.unit_of_measure or "lbs"
                        qty_lbs += _to_lbs(float(row["quantity_used"]), uom)
                    qty_lbs = normalize_mass_quantity(qty_lbs)

                indirect_materials = _parse_production_packaging_post(request)
                packaging_warned = (request.POST.get("packaging_warned") or "").strip() == "1"
                if not indirect_materials and not packaging_warned:
                    messages.warning(
                        request,
                        "No packaging selected. Add packaging lots, or create again to confirm "
                        "a batch with no packaging.",
                    )
                    # Re-build preferred rows with suggest qty from this batch size
                    preferred_packaging_rows = _preferred_packaging_rows(
                        selected_formula.finished_good,
                        display_uom,
                        batch_qty=float(
                            convert_mass_uom(qty_lbs, "lbs", display_uom)
                            if display_uom in ("lbs", "kg")
                            else qty_lbs
                        ),
                    )
                    packaging_suggest = suggested_containers_for_item(
                        selected_formula.finished_good,
                        float(
                            convert_mass_uom(qty_lbs, "lbs", display_uom)
                            if display_uom in ("lbs", "kg")
                            else qty_lbs
                        ),
                        display_uom,
                    )
                    packaging_lot_rows = _packaging_lot_rows()
                    # Fall through to re-render with packaging_needs_confirm
                    packaging_needs_confirm = True
                else:
                    packaging_needs_confirm = False
                    prod_date = (request.POST.get("production_date") or "").strip()
                    status = "in_progress"
                    if prod_date:
                        try:
                            from datetime import date as date_cls

                            d = date_cls.fromisoformat(prod_date)
                            if d > timezone.localdate():
                                status = "scheduled"
                        except ValueError:
                            pass

                    work_in_partials = []
                    for pid in request.POST.getlist("work_in_partial"):
                        try:
                            work_in_partials.append({"lot_id": int(pid)})
                        except (TypeError, ValueError):
                            continue

                    payload = {
                        "batch_type": "production",
                        "finished_good_item_id": selected_formula.finished_good_id,
                        "formula_id": selected_formula.id,
                        "quantity_produced": qty_lbs,
                        "production_date": prod_date or timezone.localdate().isoformat(),
                        "status": status,
                        "batch_ticket_mass_unit": display_uom,
                        "notes": request.POST.get("notes") or "",
                        "inputs": inputs,
                        "indirect_materials": indirect_materials,
                        "work_in_partials": work_in_partials,
                    }
                    try:
                        batch = create_batch_ticket(request.user, payload)
                        messages.success(request, f"Created batch {batch.batch_number}.")
                        return redirect("slurp_ui:production_batch_detail", pk=batch.id)
                    except MakeFlowError as e:
                        messages.error(request, e.message)
                    except Exception as e:
                        messages.error(request, str(e))

    today = timezone.localdate().isoformat()
    if "packaging_needs_confirm" not in locals():
        packaging_needs_confirm = False
    return render(
        request,
        "slurp_ui/production/create_batch.html",
        _prod_ctx(
            batch_type=batch_type,
            formulas=formulas,
            parent_choices=parent_choices,
            fg_choices=fg_choices,
            formula_choices=formula_choices,
            target_choices=target_choices,
            selected_parent=selected_parent,
            selected_fg=selected_fg,
            selected_repack_target=selected_repack_target,
            packaging_lot_rows=packaging_lot_rows,
            preferred_packaging_rows=preferred_packaging_rows,
            packaging_suggest=packaging_suggest,
            packaging_needs_confirm=packaging_needs_confirm,
            target_pack_qty=target_pack_qty,
            target_pack_uom=target_pack_uom,
            target_pack_label=target_pack_label,
            lbs_per_kg=LBS_PER_KG,
            repack_items=repack_items,
            selected_formula=selected_formula,
            selected_repack_item=selected_repack_item,
            ingredient_lot_choices=ingredient_lot_choices,
            repack_lot_rows=repack_lot_rows,
            work_in_partial_lots=work_in_partial_lots,
            display_uom=display_uom,
            is_relabel=is_relabel,
            ccp_choices=ccp_choices,
            today=today,
            god_mode=bool(request.session.get("god_mode")) and request.user.is_staff,
            port_status="full",
        ),
    )


def _native_to_display(qty_native: float, native_uom: str, display_uom: str) -> float:
    """Convert a lot-native quantity into the ticket display unit."""
    n = (native_uom or "lbs").lower()
    d = (display_uom or "lbs").lower()
    if n in ("lb", "lbs"):
        n = "lbs"
    if d in ("lb", "lbs"):
        d = "lbs"
    if n == d or n not in ("lbs", "kg") or d not in ("lbs", "kg"):
        return normalize_mass_quantity(qty_native)
    return convert_mass_uom(qty_native, n, d)


def _adjust_lot_row(
    lot: Lot,
    *,
    display_uom: str,
    existing_by_lot: dict,
    fallback_native: str = "lbs",
) -> dict | None:
    """Build one adjust-batch lot row; include reserved qty already on this batch."""
    avail_native = float(compute_lot_quantity_breakdown(lot)["quantity_available_for_use"])
    existing = existing_by_lot.get(lot.id)
    existing_qty = float(existing.quantity_used) if existing else 0.0
    if existing_qty > 0:
        avail_native += existing_qty
    if avail_native <= 0 and existing_qty <= 0:
        return None
    lot_native = (lot.item.unit_of_measure or fallback_native or "lbs").lower()
    avail_display = _native_to_display(avail_native, lot_native, display_uom)
    selected_display = (
        _native_to_display(existing_qty, lot_native, display_uom) if existing_qty > 0 else None
    )
    return {
        "lot": lot,
        "available_native": avail_native,
        "available_display": avail_display,
        "native_uom": lot_native,
        "is_partial": is_partial_lot(lot),
        "pack_label": format_pack_label(item=lot.item, lot=lot),
        "selected_qty_native": existing_qty if existing_qty > 0 else None,
        "selected_qty_display": selected_display,
    }


@login_required
@require_http_methods(["GET", "POST"])
def production_adjust_batch(request: HttpRequest, pk: int) -> HttpResponse:
    batch = get_object_or_404(
        ProductionBatch.objects.select_related(
            "finished_good_item", "formula"
        ).prefetch_related("inputs__lot__item"),
        pk=pk,
    )
    if batch.status == "closed":
        messages.warning(request, f"Batch {batch.batch_number} is closed and cannot be adjusted.")
        return redirect("slurp_ui:production_batch_detail", pk=pk)
    if batch.is_archived:
        messages.warning(request, f"Batch {batch.batch_number} is archived.")
        return redirect("slurp_ui:production_batch_detail", pk=pk)

    formula = None
    if batch.batch_type == "production":
        formula = formula_for_batch(batch)
        if formula is not None:
            formula = (
                Formula.objects.filter(pk=formula.pk)
                .prefetch_related("ingredients__item")
                .first()
            )

    native_uom = (batch.finished_good_item.unit_of_measure or "lbs").lower()
    display_uom = (batch.batch_ticket_mass_unit or native_uom or "lbs").lower()
    if display_uom not in ("lbs", "kg"):
        display_uom = native_uom if native_uom in ("lbs", "kg") else "lbs"

    existing_by_lot = {
        inp.lot_id: inp for inp in batch.inputs.all() if inp.lot_id
    }
    existing_by_item = {
        inp.item_id: inp
        for inp in batch.inputs.select_related("item").all()
        if inp.lot_id is None and inp.item_id
    }
    ingredient_lot_choices = []
    available_lots = []  # flat list for repack / POST fallback

    if batch.batch_type == "repack":
        sku = batch.finished_good_item.sku
        lot_ids = set(
            Lot.objects.filter(item__sku=sku, quantity_remaining__gt=0)
            .exclude(status="rejected")
            .values_list("id", flat=True)[:50]
        )
        lot_ids.update(existing_by_lot.keys())
        lots = (
            Lot.objects.filter(id__in=lot_ids)
            .select_related("item", "pack_size")
            .prefetch_related("item__pack_sizes")
            .order_by("-received_date")
        )
        for lot in lots:
            row = _adjust_lot_row(
                lot,
                display_uom=display_uom,
                existing_by_lot=existing_by_lot,
                fallback_native=native_uom,
            )
            if row:
                available_lots.append(row)
    elif formula:
        claimed_lot_ids: set[int] = set()
        claimed_utility_item_ids: set[int] = set()
        for ing in formula.ingredients.select_related("item").all():
            native = (ing.item.unit_of_measure or "lbs").lower()
            is_utility = bool(getattr(ing.item, "plant_utility", False))
            if is_utility:
                existing = existing_by_item.get(ing.item_id)
                utility_qty_native = float(existing.quantity_used) if existing else 0.0
                try:
                    utility_qty_display = (
                        convert_mass_uom(utility_qty_native, native, display_uom)
                        if native in ("lbs", "kg") and display_uom in ("lbs", "kg")
                        else utility_qty_native
                    )
                except ValueError:
                    utility_qty_display = utility_qty_native
                claimed_utility_item_ids.add(ing.item_id)
                ingredient_lot_choices.append(
                    {
                        "ingredient": ing,
                        "percentage": float(ing.percentage or 0),
                        "native_uom": native,
                        "plant_utility": True,
                        "utility_qty_display": utility_qty_display,
                        "match_by_parent": False,
                        "parent_code": "",
                        "lots": [],
                    }
                )
                continue
            skus = set(skus_for_formula_ingredient(ing))
            lot_qs = lots_for_formula_ingredient(ing, limit=80)
            lot_by_id = {lot.id: lot for lot in lot_qs}
            # Keep lots already on this batch under the matching ingredient.
            for lot_id, inp in existing_by_lot.items():
                lot = inp.lot
                if lot and (lot.item.sku or "") in skus and lot_id not in lot_by_id:
                    lot_by_id[lot_id] = lot
            lot_rows = []
            for lot in lot_by_id.values():
                row = _adjust_lot_row(
                    lot,
                    display_uom=display_uom,
                    existing_by_lot=existing_by_lot,
                    fallback_native=native,
                )
                if not row:
                    continue
                if lot.id in claimed_lot_ids:
                    continue
                claimed_lot_ids.add(lot.id)
                lot_rows.append(row)
                available_lots.append(row)
            lot_rows.sort(
                key=lambda r: (
                    0 if r.get("selected_qty_display") else 1,
                    0 if r["is_partial"] else 1,
                    -r["available_native"],
                )
            )
            ingredient_lot_choices.append(
                {
                    "ingredient": ing,
                    "percentage": float(ing.percentage or 0),
                    "native_uom": native,
                    "plant_utility": False,
                    "match_by_parent": bool(getattr(ing, "match_by_parent", False)),
                    "parent_code": (
                        (getattr(ing.item, "sku_parent_code", None) or "")
                        if getattr(ing, "match_by_parent", False)
                        else ""
                    ),
                    "lots": lot_rows,
                }
            )
        # Orphan inputs (SKU no longer on formula) — still editable
        orphan_rows = []
        for lot_id, inp in existing_by_lot.items():
            if lot_id in claimed_lot_ids:
                continue
            lot = inp.lot
            if not lot:
                continue
            row = _adjust_lot_row(
                lot,
                display_uom=display_uom,
                existing_by_lot=existing_by_lot,
                fallback_native=(lot.item.unit_of_measure or "lbs"),
            )
            if row:
                orphan_rows.append(row)
                available_lots.append(row)
                claimed_lot_ids.add(lot_id)
        if orphan_rows:
            ingredient_lot_choices.append(
                {
                    "ingredient": None,
                    "ingredient_label": "Other lots on this batch",
                    "percentage": 0,
                    "native_uom": display_uom,
                    "plant_utility": False,
                    "match_by_parent": False,
                    "parent_code": "",
                    "lots": orphan_rows,
                    "orphan": True,
                }
            )

    if request.method == "POST":
        inputs = []
        seen_lots: set[int] = set()

        if formula and ingredient_lot_choices:
            for group in ingredient_lot_choices:
                ing = group.get("ingredient")
                ing_key = ing.id if ing is not None else "orphan"
                if group.get("plant_utility") and ing is not None:
                    raw = request.POST.get(f"plant_utility_qty_{ing.id}")
                    if not raw:
                        continue
                    try:
                        q = float(raw)
                    except ValueError:
                        continue
                    if q <= 0:
                        continue
                    lot_native = (ing.item.unit_of_measure or "lbs").lower()
                    q_native = _display_to_native(q, display_uom, lot_native)
                    inputs.append({"item_id": ing.item_id, "quantity_used": q_native})
                    continue
                for lot_row in group.get("lots") or []:
                    lot = lot_row["lot"]
                    raw = request.POST.get(f"ing_qty_{ing_key}_{lot.id}")
                    if raw is None or raw == "":
                        # Flat fallback name used by repack-style cards
                        raw = request.POST.get(f"qty_{lot.id}")
                    if not raw:
                        continue
                    try:
                        q = float(raw)
                    except ValueError:
                        continue
                    if q <= 0:
                        continue
                    if lot.id in seen_lots:
                        continue
                    seen_lots.add(lot.id)
                    lot_native = (lot.item.unit_of_measure or "lbs").lower()
                    q_native = _display_to_native(q, display_uom, lot_native)
                    inputs.append({"lot_id": lot.id, "quantity_used": q_native})
        else:
            for lot_row in available_lots:
                lot = lot_row["lot"]
                raw = request.POST.get(f"qty_{lot.id}")
                if not raw:
                    continue
                try:
                    q = float(raw)
                except ValueError:
                    continue
                if q <= 0:
                    continue
                lot_native = (lot.item.unit_of_measure or "lbs").lower()
                q_native = _display_to_native(q, display_uom, lot_native)
                inputs.append({"lot_id": lot.id, "quantity_used": q_native})

        if not inputs:
            messages.error(request, "Select at least one ingredient with quantity.")
        else:
            # Prefer posted quantity; if blank/invalid, sync from total inputs (QC add/remove).
            raw_qty = (request.POST.get("quantity_produced") or "").strip()
            qty_produced = None
            if raw_qty:
                try:
                    qty_produced = float(raw_qty)
                except ValueError:
                    qty_produced = None

            if batch.batch_type == "production":
                total_lbs = 0.0
                for inp in inputs:
                    if inp.get("lot_id"):
                        lot = Lot.objects.select_related("item").get(pk=inp["lot_id"])
                        lu = (lot.item.unit_of_measure or "lbs").lower()
                    else:
                        item = Item.objects.get(pk=inp["item_id"])
                        lu = (item.unit_of_measure or "lbs").lower()
                    q = float(inp["quantity_used"])
                    total_lbs += _to_lbs(q, lu)
                total_lbs = normalize_mass_quantity(total_lbs)
                if qty_produced is None or qty_produced <= 0:
                    target_qty = total_lbs
                else:
                    target_qty = _to_lbs(qty_produced, display_uom)
                # Auto-accept small drift by preferring input sum when user strengthened/weakened
                if abs(total_lbs - target_qty) > 0.05:
                    target_qty = total_lbs
            else:
                total_native = normalize_mass_quantity(sum(float(i["quantity_used"]) for i in inputs))
                if qty_produced is None or qty_produced <= 0:
                    target_qty = total_native
                else:
                    target_qty = _display_to_native(qty_produced, display_uom, native_uom)
                if abs(total_native - target_qty) > 0.05:
                    target_qty = total_native

            payload = {"quantity_produced": target_qty, "inputs": inputs}
            try:
                if batch.batch_type == "production" and formula:
                    _ensure_formula_baseline(batch)
                adjust_batch_inputs(batch, payload)
                messages.success(request, f"Adjusted batch {batch.batch_number}.")
                return redirect("slurp_ui:production_batch_detail", pk=pk)
            except MakeFlowError as e:
                messages.error(request, e.message)
            except Exception as e:
                messages.error(request, str(e))

    qty_display = float(batch.quantity_produced)
    if batch.batch_type == "production" and display_uom == "kg":
        qty_display = convert_mass_uom(qty_display, "lbs", "kg")
    elif batch.batch_type == "repack" and native_uom in ("lbs", "kg") and display_uom in ("lbs", "kg"):
        qty_display = convert_mass_uom(qty_display, native_uom, display_uom)

    # Freeze formula targets to the original ticket size (first visit pins baseline).
    baseline_lbs = (
        _ensure_formula_baseline(batch, float(batch.quantity_produced or 0))
        if batch.batch_type == "production" and formula
        else float(batch.quantity_produced or 0)
    )
    baseline_display = _native_to_display(baseline_lbs, "lbs", display_uom)
    if batch.batch_type == "repack":
        baseline_display = qty_display

    adjustment_rows, _, _ = _build_adjustment_summary(batch, formula, display_uom)

    return render(
        request,
        "slurp_ui/production/adjust_batch.html",
        _prod_ctx(
            batch=batch,
            formula=formula,
            available_lots=available_lots,
            ingredient_lot_choices=ingredient_lot_choices,
            display_uom=display_uom,
            qty_display=qty_display,
            baseline_qty_display=baseline_display,
            adjustment_rows=adjustment_rows,
            lbs_per_kg=LBS_PER_KG,
            port_status="full",
        ),
    )


def _formula_qc_context(formula: Formula | None) -> dict:
    """Build close-batch QC display fields from the FG formula."""
    empty = {
        "formula_qc_parameter": "",
        "formula_qc_min": None,
        "formula_qc_max": None,
        "formula_qc_label": "",
        "formula_has_qc": False,
    }
    if not formula:
        return empty
    name = (getattr(formula, "qc_parameter_name", None) or "").strip()
    qc_min = getattr(formula, "qc_spec_min", None)
    qc_max = getattr(formula, "qc_spec_max", None)
    if not name and qc_min is None and qc_max is None:
        return empty
    range_bits = []
    if qc_min is not None:
        range_bits.append(f"min {qc_min:g}")
    if qc_max is not None:
        range_bits.append(f"max {qc_max:g}")
    label = name or "QC"
    if range_bits:
        label = f"{label} ({', '.join(range_bits)})"
    return {
        "formula_qc_parameter": name,
        "formula_qc_min": qc_min,
        "formula_qc_max": qc_max,
        "formula_qc_label": label,
        "formula_has_qc": True,
    }


@login_required
@require_http_methods(["GET", "POST"])
def production_close_batch(request: HttpRequest, pk: int) -> HttpResponse:
    batch = get_object_or_404(
        ProductionBatch.objects.select_related(
            "finished_good_item", "formula"
        ).prefetch_related("inputs__lot__item"),
        pk=pk,
    )
    if batch.status == "closed":
        messages.warning(request, f"Batch {batch.batch_number} is already closed.")
        return redirect(_dash_url_name(batch.batch_type))
    if batch.is_archived:
        messages.warning(request, f"Batch {batch.batch_number} is archived.")
        return redirect("slurp_ui:production_batch_detail", pk=pk)

    early_msg = _close_before_production_blocked(
        batch, allow_early=_god_mode_on(request)
    )
    if early_msg:
        messages.error(request, early_msg)
        return redirect("slurp_ui:production_batch_detail", pk=pk)

    formula = None
    if batch.batch_type == "production":
        formula = formula_for_batch(batch)
        if formula is not None:
            formula = (
                Formula.objects.filter(pk=formula.pk)
                .prefetch_related("ingredients__item")
                .first()
            )
    qc_ctx = _formula_qc_context(formula)
    display_uom = _close_display_uom(batch)
    storage_uom = _close_storage_uom(batch)
    if formula:
        _ensure_formula_baseline(batch)
    adjustment_rows, baseline_qty_display, current_qty_display = _build_adjustment_summary(
        batch, formula, display_uom
    )
    has_adjustments = any(r["has_delta"] for r in adjustment_rows)
    ticket_display = _native_to_display(
        float(batch.quantity_produced or 0), storage_uom, display_uom
    )
    from erp_core.pack_display import resolve_pack_size

    pack_qty, pack_uom = resolve_pack_size(item=batch.finished_good_item)
    pack_breakout = _pack_breakout_for_item(
        batch.finished_good_item, ticket_display, display_uom
    )
    campaign_preview = ""
    if batch.batch_type == "production" and batch.campaign_id:
        from erp_core.campaign_lots import preview_campaign_code

        campaign_preview = preview_campaign_code(batch)

    if request.method == "POST":
        try:
            actual_display = float(
                request.POST.get("quantity_actual") or ticket_display
            )
            wastes_display = float(request.POST.get("wastes") or 0)
            spills_display = float(request.POST.get("spills") or 0)
        except ValueError:
            messages.error(request, "Invalid quantity / waste / spill values.")
            return redirect("slurp_ui:production_close_batch", pk=pk)

        actual = _display_to_native(actual_display, display_uom, storage_uom)
        wastes = _display_to_native(wastes_display, display_uom, storage_uom)
        spills = _display_to_native(spills_display, display_uom, storage_uom)

        # Always prefer formula QC identity when present (do not trust free-text override).
        if qc_ctx["formula_has_qc"]:
            qc_param = qc_ctx["formula_qc_label"]
        else:
            qc_param = (request.POST.get("qc_parameter") or "").strip()
        qc_actual = (request.POST.get("qc_actual") or "").strip()
        qc_initials = (request.POST.get("qc_initials") or "").strip()
        notes_bits = []
        if batch.notes:
            notes_bits.append(batch.notes)
        if has_adjustments:
            adj_lines = [
                "Batch adjustments vs original formula ticket "
                f"(baseline {baseline_qty_display} {display_uom} → current {current_qty_display} {display_uom}):"
            ]
            for row in adjustment_rows:
                if not row["has_delta"]:
                    continue
                sign = "+" if row["delta"] > 0 else ""
                adj_lines.append(
                    f"  {row['sku']}: target {row['target']} → actual {row['actual']} "
                    f"({sign}{row['delta']} {display_uom})"
                )
            notes_bits.append("\n".join(adj_lines))
        if qc_param or qc_actual or qc_initials:
            notes_bits.append(
                f"QC Parameters: {qc_param}\nQC Actual: {qc_actual}\nQC Initials: {qc_initials}"
            )
        extra_notes = (request.POST.get("notes") or "").strip()
        if extra_notes:
            notes_bits.append(extra_notes)

        payload = {
            "status": "closed",
            "quantity_actual": actual,
            "wastes": wastes,
            "spills": spills,
            "notes": "\n".join(notes_bits),
            "qc_parameter": qc_param,
            "qc_actual": qc_actual,
            "qc_initials": qc_initials,
            "allow_early_close": _god_mode_on(request),
        }
        try:
            close_batch_ticket(batch, request.user, payload)
            messages.success(request, f"Closed batch {batch.batch_number}.")
            return redirect("slurp_ui:production_batch_detail", pk=pk)
        except MakeFlowError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "slurp_ui/production/close_batch.html",
        _prod_ctx(
            batch=batch,
            formula=formula,
            adjustment_rows=adjustment_rows,
            has_adjustments=has_adjustments,
            baseline_qty_display=baseline_qty_display,
            current_qty_display=current_qty_display,
            display_uom=display_uom,
            ticket_qty_display=ticket_display,
            pack_qty=pack_qty,
            pack_uom=pack_uom or "",
            pack_breakout=pack_breakout,
            campaign_preview=campaign_preview,
            lbs_per_kg=LBS_PER_KG,
            qc_parameter_value=qc_ctx["formula_qc_label"],
            port_status="full",
            **qc_ctx,
        ),
    )


@login_required
@require_POST
def production_campaign_link(request: HttpRequest) -> HttpResponse:
    """Link selected production batches into one campaign (parent + ISO week)."""
    from erp_core.campaign_lots import link_batches_to_campaign

    raw_ids = request.POST.getlist("batch_ids")
    try:
        batch_ids = [int(x) for x in raw_ids if str(x).isdigit()]
    except (TypeError, ValueError):
        batch_ids = []
    try:
        campaign, linked = link_batches_to_campaign(batch_ids)
        messages.success(
            request,
            f"Linked {len(linked)} ticket(s) to campaign {campaign.campaign_code}.",
        )
    except ValueError as e:
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, str(e))
    return redirect("slurp_ui:production")


@login_required
@require_POST
def production_campaign_unlink(request: HttpRequest) -> HttpResponse:
    """Clear campaign on selected production batches."""
    from erp_core.campaign_lots import unlink_batches_from_campaign

    raw_ids = request.POST.getlist("batch_ids")
    try:
        batch_ids = [int(x) for x in raw_ids if str(x).isdigit()]
    except (TypeError, ValueError):
        batch_ids = []
    try:
        unlinked = unlink_batches_from_campaign(batch_ids)
        messages.success(
            request,
            f"Unlinked {len(unlinked)} ticket(s) from campaign.",
        )
    except ValueError as e:
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, str(e))
    return redirect("slurp_ui:production")


@login_required
@require_POST
def production_reverse_batch(request: HttpRequest, pk: int) -> HttpResponse:
    batch = get_object_or_404(ProductionBatch, pk=pk)
    try:
        info = reverse_batch_ticket(batch)
        messages.success(
            request,
            f"Reversed batch {info.get('batch_number') or batch.batch_number}.",
        )
    except MakeFlowError as e:
        plan = e.extra.get("reversal_plan") if e.extra else None
        if not plan:
            try:
                plan = build_batch_reversal_plan(batch)
            except Exception:
                plan = None
        detail = e.message
        if plan and plan.get("blockers"):
            bits = [b.get("message") or str(b) for b in plan["blockers"]]
            detail = detail + " — " + "; ".join(bits)
        messages.error(request, detail)
    except Exception as e:
        messages.error(request, str(e))
    return redirect(_dash_url_name(batch.batch_type))


@login_required
@require_http_methods(["GET", "POST"])
def production_rework(request: HttpRequest) -> HttpResponse:
    """Blend parent-family FG partials (+ optional RM strength adjust) into a new on-hold lot."""
    from erp_core.formula_ingredient import parent_code_for_item
    from erp_core.pack_display import format_pack_label, resolve_pack_size
    from erp_core.rework_services import (
        ReworkError,
        execute_rework,
        partial_lots_for_parent,
    )

    fg_choices = list(
        Item.objects.filter(item_type="finished_good").order_by("sku")[:500]
    )
    target_id = request.GET.get("item") or request.POST.get("target_item_id")
    target = None
    if target_id:
        target = Item.objects.filter(
            pk=target_id, item_type__in=("finished_good", "distributed_item")
        ).first()

    parent = parent_code_for_item(target) if target else ""
    partial_rows = []
    if parent:
        for lot in partial_lots_for_parent(parent):
            avail = float(compute_lot_quantity_breakdown(lot)["quantity_available_for_use"])
            partial_rows.append(
                {
                    "lot": lot,
                    "available": avail,
                    "uom": lot.item.unit_of_measure or "lbs",
                    "pack_label": format_pack_label(item=lot.item, lot=lot),
                    "same_sku": bool(target and lot.item_id == target.id),
                }
            )

    adjust_lots = []
    if target:
        rms = (
            Lot.objects.filter(
                item__item_type="raw_material",
                status="accepted",
                quantity_remaining__gt=0,
            )
            .select_related("item")
            .order_by("item__sku", "-received_date")[:80]
        )
        for lot in rms:
            avail = float(compute_lot_quantity_breakdown(lot)["quantity_available_for_use"])
            if avail > 1e-6:
                adjust_lots.append({"lot": lot, "available": avail})

    if request.method == "POST" and target:
        try:
            partial_lines = []
            for row in partial_rows:
                lid = row["lot"].id
                if request.POST.get(f"use_partial_{lid}"):
                    raw_qty = (request.POST.get(f"partial_qty_{lid}") or "").strip()
                    partial_lines.append(
                        {
                            "lot_id": lid,
                            "quantity": float(raw_qty) if raw_qty else row["available"],
                        }
                    )
            adjust_lines = []
            for key, val in request.POST.items():
                if not key.startswith("adjust_qty_"):
                    continue
                raw = (val or "").strip()
                if not raw:
                    continue
                try:
                    lid = int(key[len("adjust_qty_") :])
                    qty = float(raw)
                except ValueError:
                    continue
                if qty > 0:
                    adjust_lines.append({"lot_id": lid, "quantity": qty})
            result = execute_rework(
                target_item=target,
                partial_lines=partial_lines,
                adjust_lines=adjust_lines,
                notes=(request.POST.get("notes") or "").strip(),
                user=request.user,
            )
            out = result["output_lot"]
            messages.success(
                request,
                f"Rework {result['batch'].batch_number}: {result['quantity']:.2f} "
                f"→ lot {out.lot_number} on hold awaiting micro.",
            )
            return redirect("slurp_ui:inventory_lot_detail", pk=out.id)
        except ReworkError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "slurp_ui/production/rework.html",
        {
            "module": "production",
            "sidebar_nav": PRODUCTION_NAV,
            "active_tab": "rework",
            "fg_choices": fg_choices,
            "target": target,
            "parent": parent,
            "partial_rows": partial_rows,
            "adjust_lots": adjust_lots,
            "port_status": "full",
        },
    )
