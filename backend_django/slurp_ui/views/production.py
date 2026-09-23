from datetime import datetime
import re

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
    reverse_batch_ticket,
)
from erp_core.mass_quantity import LBS_PER_KG, convert_mass_uom, normalize_mass_quantity
from erp_core.models import Formula, Item, Lot, ProductionBatch
from erp_core.pack_display import format_pack_label, is_partial_lot, resolve_pack_size
from erp_core.formula_ingredient import lots_for_formula_ingredient, skus_for_formula_ingredient
from erp_core.formula_resolve import formula_for_batch, recipe_label
from erp_core.reversal_guard import build_batch_reversal_plan

from ..nav import PRODUCTION_NAV

_FORMULA_BASELINE_RE = re.compile(r"\[FORMULA_BASELINE_QTY:([0-9]+(?:\.[0-9]+)?)\]")
_QUANTITY_TOLERANCE = 0.05


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
    inputs = list(batch.inputs.select_related("lot__item").all())
    rows = []
    total_delta_lbs = 0.0
    for ing in formula.ingredients.select_related("item").all():
        pct = float(ing.percentage or 0)
        target_lbs = normalize_mass_quantity(baseline_lbs * (pct / 100.0))
        skus = set(skus_for_formula_ingredient(ing))
        actual_lbs = 0.0
        for inp in inputs:
            lot = inp.lot
            if not lot or not lot.item:
                continue
            if (lot.item.sku or "") not in skus:
                continue
            q = float(inp.quantity_used or 0)
            lu = (lot.item.unit_of_measure or "lbs").lower()
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


def _repack_item_choices():
    """Items with available lots suitable for repack (same SKU lots)."""
    skus_with_lots = set(
        Lot.objects.filter(quantity_remaining__gt=0)
        .exclude(status="rejected")
        .values_list("item__sku", flat=True)
    )
    return (
        Item.objects.filter(
            sku__in=skus_with_lots,
            item_type__in=["finished_good", "distributed_item", "raw_material"],
        )
        .order_by("sku")[:300]
    )


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


@login_required
def production_batches(request: HttpRequest) -> HttpResponse:
    batches = (
        ProductionBatch.objects.filter(is_archived=False)
        .select_related("finished_good_item")
        .order_by("-created_at")[:200]
    )
    return render(
        request,
        "slurp_ui/production/batches.html",
        _prod_ctx(batches=batches, port_status="full"),
    )


@login_required
def production_archive(request: HttpRequest) -> HttpResponse:
    """Archived batch tickets: search + year/month or product folders."""
    from calendar import month_name
    from django.db.models import Count
    from django.db.models.functions import Coalesce, TruncMonth, TruncYear

    q = (request.GET.get("q") or "").strip()
    batch_type = (request.GET.get("batch_type") or "all").strip().lower()
    if batch_type not in ("all", "production", "repack"):
        batch_type = "all"
    browse = (request.GET.get("browse") or "date").strip().lower()
    if browse not in ("date", "product"):
        browse = "date"

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
    crumbs = [{"label": "Archive", "url_params": {"browse": browse}}]
    if batch_type != "all":
        crumbs[0]["url_params"]["batch_type"] = batch_type
    if q:
        crumbs[0]["url_params"]["q"] = q

    def _qp(**extra):
        params = {"browse": browse}
        if batch_type != "all":
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

    return render(
        request,
        "slurp_ui/production/archive.html",
        _prod_ctx(
            active_tab="archive",
            batches=batches,
            folders=folders,
            folder_level=folder_level,
            crumbs=crumbs,
            browse=browse,
            q=q,
            batch_type=batch_type,
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
    if batch.status != "closed":
        messages.error(request, "Only closed batches can be archived.")
        return redirect(next_url) if next_url else redirect(
            "slurp_ui:production_batch_detail", pk=pk
        )
    if batch.is_archived:
        messages.info(request, f"{batch.batch_number} is already archived.")
        return redirect(next_url) if next_url else redirect("slurp_ui:production_archive")
    batch.is_archived = True
    batch.archived_at = timezone.now()
    batch.save(update_fields=["is_archived", "archived_at", "updated_at"])
    messages.success(
        request,
        f"Archived {batch.batch_number}. Find it under Production → Archive.",
    )
    return redirect(next_url) if next_url else redirect("slurp_ui:production")


@login_required
@require_POST
def production_unarchive_batch(request: HttpRequest, pk: int) -> HttpResponse:
    batch = get_object_or_404(ProductionBatch, pk=pk)
    next_url = (request.POST.get("next") or "").strip() or None
    if not batch.is_archived:
        messages.info(request, f"{batch.batch_number} is not archived.")
        return redirect(next_url) if next_url else redirect("slurp_ui:production")
    batch.is_archived = False
    batch.archived_at = None
    batch.save(update_fields=["is_archived", "archived_at", "updated_at"])
    messages.success(request, f"Restored {batch.batch_number} to the batch tickets dash.")
    return redirect(next_url) if next_url else redirect("slurp_ui:production")


@login_required
@require_http_methods(["GET", "POST"])
def production_batch_detail(request: HttpRequest, pk: int) -> HttpResponse:
    batch = get_object_or_404(
        ProductionBatch.objects.select_related(
            "finished_good_item", "formula"
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
    return render(
        request,
        "slurp_ui/production/batch_detail.html",
        _prod_ctx(
            batch=batch,
            formula=formula,
            recipe_label=recipe_label(formula),
            can_adjust=can_adjust,
            can_edit_date=can_edit_date,
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

    selected_formula = None
    selected_repack_item = None
    formula_id = request.GET.get("formula") or request.POST.get("formula_id")
    repack_item_id = request.GET.get("item") or request.POST.get("repack_item_id")

    if batch_type == "production" and formula_id:
        selected_formula = (
            Formula.objects.filter(pk=formula_id)
            .select_related("finished_good")
            .prefetch_related("ingredients__item")
            .first()
        )
    elif batch_type == "repack" and repack_item_id:
        selected_repack_item = Item.objects.filter(pk=repack_item_id).first()

    display_uom = (request.POST.get("batch_ticket_mass_unit") or request.GET.get("uom") or "lbs").lower()
    if batch_type == "repack" and selected_repack_item:
        native = (selected_repack_item.unit_of_measure or "lbs").lower()
        if native in ("lbs", "kg"):
            display_uom = native if display_uom not in ("lbs", "kg") else display_uom
    if display_uom not in ("lbs", "kg"):
        display_uom = "lbs"

    ingredient_lot_choices = []
    repack_lot_rows = []
    work_in_partial_lots = []
    if selected_formula:
        fg = selected_formula.finished_good
        fg_lots = (
            Lot.objects.filter(
                item=fg,
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
                    }
                )

        for ing in selected_formula.ingredients.all():
            native = (ing.item.unit_of_measure or "lbs").lower()
            lots = lots_for_formula_ingredient(ing, limit=80)
            lot_rows = []
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
                    "match_by_parent": bool(getattr(ing, "match_by_parent", False)),
                    "parent_code": (getattr(ing.item, "sku_parent_code", None) or "") if getattr(ing, "match_by_parent", False) else "",
                    "lots": lot_rows,
                }
            )
    elif selected_repack_item:
        repack_lot_rows = _repack_lot_rows(selected_repack_item, display_uom)

    if request.method == "POST":
        if batch_type == "repack" and selected_repack_item:
            try:
                qty_display = float(request.POST.get("quantity_produced") or 0)
            except ValueError:
                qty_display = 0
            native = (selected_repack_item.unit_of_measure or "lbs").lower()
            qty_native = _display_to_native(qty_display, display_uom, native) if qty_display > 0 else 0.0

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
                q_native = _display_to_native(q_display, display_uom, native)
                inputs.append({"lot_id": lot.id, "quantity_used": q_native})

            if not inputs:
                messages.error(request, "Select at least one lot with quantity.")
            else:
                if qty_native <= 0:
                    qty_native = normalize_mass_quantity(sum(i["quantity_used"] for i in inputs))

                payload = {
                    "batch_type": "repack",
                    "quantity_produced": qty_native,
                    "production_date": (request.POST.get("production_date") or timezone.localdate().isoformat()),
                    "status": "in_progress",
                    "batch_ticket_mass_unit": display_uom,
                    "notes": request.POST.get("notes") or "",
                    "inputs": inputs,
                    "indirect_materials": [],
                    "work_in_partials": [],
                }
                try:
                    batch = create_batch_ticket(request.user, payload)
                    messages.success(request, f"Created repack batch {batch.batch_number}.")
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

            if not inputs:
                messages.error(request, "Allocate quantity on at least one lot.")
            else:
                if qty_lbs <= 0:
                    qty_lbs = 0.0
                    for row in inputs:
                        lot = Lot.objects.select_related("item").get(pk=row["lot_id"])
                        qty_lbs += _to_lbs(
                            float(row["quantity_used"]), lot.item.unit_of_measure or "lbs"
                        )
                    qty_lbs = normalize_mass_quantity(qty_lbs)

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
                    "indirect_materials": [],
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
    return render(
        request,
        "slurp_ui/production/create_batch.html",
        _prod_ctx(
            batch_type=batch_type,
            formulas=formulas,
            repack_items=repack_items,
            selected_formula=selected_formula,
            selected_repack_item=selected_repack_item,
            ingredient_lot_choices=ingredient_lot_choices,
            repack_lot_rows=repack_lot_rows,
            work_in_partial_lots=work_in_partial_lots,
            display_uom=display_uom,
            lbs_per_kg=LBS_PER_KG,
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

    existing_by_lot = {inp.lot_id: inp for inp in batch.inputs.all()}
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
        for ing in formula.ingredients.select_related("item").all():
            native = (ing.item.unit_of_measure or "lbs").lower()
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
            messages.error(request, "Select at least one lot with quantity.")
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
                    lot = Lot.objects.select_related("item").get(pk=inp["lot_id"])
                    q = float(inp["quantity_used"])
                    lu = (lot.item.unit_of_measure or "lbs").lower()
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
        return redirect("slurp_ui:production")
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
    qc_ctx = _formula_qc_context(formula)
    display_uom = (batch.batch_ticket_mass_unit or "lbs").lower()
    if display_uom not in ("lbs", "kg"):
        display_uom = "lbs"
    if formula:
        _ensure_formula_baseline(batch)
    adjustment_rows, baseline_qty_display, current_qty_display = _build_adjustment_summary(
        batch, formula, display_uom
    )
    has_adjustments = any(r["has_delta"] for r in adjustment_rows)

    if request.method == "POST":
        try:
            actual = float(request.POST.get("quantity_actual") or batch.quantity_produced)
            wastes = float(request.POST.get("wastes") or 0)
            spills = float(request.POST.get("spills") or 0)
        except ValueError:
            messages.error(request, "Invalid quantity / waste / spill values.")
            return redirect("slurp_ui:production_close_batch", pk=pk)

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
            qc_parameter_value=qc_ctx["formula_qc_label"],
            port_status="full",
            **qc_ctx,
        ),
    )


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
    return redirect("slurp_ui:production")
