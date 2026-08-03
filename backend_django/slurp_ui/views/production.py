from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
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
from erp_core.reversal_guard import build_batch_reversal_plan

from ..nav import PRODUCTION_NAV


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
    batches = ProductionBatch.objects.select_related("finished_good_item").order_by(
        "-created_at"
    )[:200]
    return render(
        request,
        "slurp_ui/production/batches.html",
        _prod_ctx(batches=batches, port_status="full"),
    )


@login_required
def production_batch_detail(request: HttpRequest, pk: int) -> HttpResponse:
    batch = get_object_or_404(
        ProductionBatch.objects.select_related("finished_good_item").prefetch_related(
            "inputs__lot__item", "outputs__lot"
        ),
        pk=pk,
    )
    formula = None
    if batch.batch_type == "production" and batch.finished_good_item_id:
        formula = (
            Formula.objects.filter(finished_good_id=batch.finished_good_item_id)
            .prefetch_related("ingredients__item")
            .first()
        )
    can_adjust = batch.status not in ("closed", "cancelled")
    return render(
        request,
        "slurp_ui/production/batch_detail.html",
        _prod_ctx(
            batch=batch,
            formula=formula,
            can_adjust=can_adjust,
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
        .order_by("finished_good__sku")
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
    if selected_formula:
        for ing in selected_formula.ingredients.all():
            sku = ing.item.sku
            native = (ing.item.unit_of_measure or "lbs").lower()
            lots = (
                Lot.objects.filter(item__sku=sku, quantity_remaining__gt=0)
                .exclude(status="rejected")
                .select_related("item")
                .order_by("-received_date")[:40]
            )
            lot_rows = []
            for lot in lots:
                avail_native = float(
                    compute_lot_quantity_breakdown(lot)["quantity_available_for_use"]
                )
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
                lot_rows.append(
                    {
                        "lot": lot,
                        "available_native": avail_native,
                        "available_display": avail_display,
                        "native_uom": native,
                    }
                )
            ingredient_lot_choices.append(
                {
                    "ingredient": ing,
                    "percentage": float(ing.percentage or 0),
                    "native_uom": native,
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
            for ing in selected_formula.ingredients.all():
                lot_id = request.POST.get(f"lot_id_{ing.id}")
                raw_qty = request.POST.get(f"qty_{ing.id}")
                if not lot_id or not raw_qty:
                    continue
                try:
                    q_display = float(raw_qty)
                except ValueError:
                    continue
                if q_display <= 0:
                    continue
                lot = Lot.objects.select_related("item").get(pk=int(lot_id))
                native = (lot.item.unit_of_measure or "lbs").lower()
                q_native = _display_to_native(q_display, display_uom, native)
                inputs.append({"lot_id": int(lot_id), "quantity_used": q_native})

            if qty_lbs <= 0 and inputs:
                qty_lbs = 0.0
                for row in inputs:
                    lot = Lot.objects.select_related("item").get(pk=row["lot_id"])
                    qty_lbs += _to_lbs(float(row["quantity_used"]), lot.item.unit_of_measure or "lbs")
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

            payload = {
                "batch_type": "production",
                "finished_good_item_id": selected_formula.finished_good_id,
                "quantity_produced": qty_lbs,
                "production_date": prod_date or timezone.localdate().isoformat(),
                "status": status,
                "batch_ticket_mass_unit": display_uom,
                "notes": request.POST.get("notes") or "",
                "inputs": inputs,
                "indirect_materials": [],
                "work_in_partials": [],
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
            display_uom=display_uom,
            lbs_per_kg=LBS_PER_KG,
            today=today,
            god_mode=bool(request.session.get("god_mode")) and request.user.is_staff,
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def production_adjust_batch(request: HttpRequest, pk: int) -> HttpResponse:
    batch = get_object_or_404(
        ProductionBatch.objects.select_related("finished_good_item").prefetch_related(
            "inputs__lot__item"
        ),
        pk=pk,
    )
    if batch.status == "closed":
        messages.warning(request, f"Batch {batch.batch_number} is closed and cannot be adjusted.")
        return redirect("slurp_ui:production_batch_detail", pk=pk)

    formula = None
    if batch.batch_type == "production":
        formula = (
            Formula.objects.filter(finished_good_id=batch.finished_good_item_id)
            .prefetch_related("ingredients__item")
            .first()
        )

    native_uom = (batch.finished_good_item.unit_of_measure or "lbs").lower()
    display_uom = (batch.batch_ticket_mass_unit or native_uom or "lbs").lower()
    if display_uom not in ("lbs", "kg"):
        display_uom = native_uom if native_uom in ("lbs", "kg") else "lbs"

    existing_by_lot = {inp.lot_id: inp for inp in batch.inputs.all()}

    available_lots = []
    if batch.batch_type == "repack":
        sku = batch.finished_good_item.sku
        lots = (
            Lot.objects.filter(item__sku=sku, quantity_remaining__gt=0)
            .exclude(status="rejected")
            .select_related("item")
            .order_by("-received_date")[:50]
        )
        for lot in lots:
            avail = float(compute_lot_quantity_breakdown(lot)["quantity_available_for_use"])
            if lot.id in existing_by_lot:
                avail += float(existing_by_lot[lot.id].quantity_used)
            if avail <= 0 and lot.id not in existing_by_lot:
                continue
            existing_qty = existing_by_lot.get(lot.id)
            available_lots.append(
                {
                    "lot": lot,
                    "available": avail,
                    "selected_qty": float(existing_qty.quantity_used) if existing_qty else None,
                }
            )
    elif formula:
        required_skus = {ing.item.sku for ing in formula.ingredients.all()}
        lots = (
            Lot.objects.filter(item__sku__in=required_skus, quantity_remaining__gt=0)
            .exclude(status="rejected")
            .select_related("item")
            .order_by("-received_date")[:80]
        )
        for lot in lots:
            avail = float(compute_lot_quantity_breakdown(lot)["quantity_available_for_use"])
            if lot.id in existing_by_lot:
                avail += float(existing_by_lot[lot.id].quantity_used)
            if avail <= 0 and lot.id not in existing_by_lot:
                continue
            existing_qty = existing_by_lot.get(lot.id)
            available_lots.append(
                {
                    "lot": lot,
                    "available": avail,
                    "selected_qty": float(existing_qty.quantity_used) if existing_qty else None,
                }
            )

    if request.method == "POST":
        try:
            qty_produced = float(request.POST.get("quantity_produced") or batch.quantity_produced)
        except ValueError:
            messages.error(request, "Invalid quantity to produce.")
            return redirect("slurp_ui:production_adjust_batch", pk=pk)

        inputs = []
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
            if batch.batch_type == "production":
                target_qty = _to_lbs(qty_produced, display_uom)
            else:
                target_qty = _display_to_native(qty_produced, display_uom, native_uom)

            payload = {"quantity_produced": target_qty, "inputs": inputs}
            try:
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

    return render(
        request,
        "slurp_ui/production/adjust_batch.html",
        _prod_ctx(
            batch=batch,
            formula=formula,
            available_lots=available_lots,
            display_uom=display_uom,
            qty_display=qty_display,
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def production_close_batch(request: HttpRequest, pk: int) -> HttpResponse:
    batch = get_object_or_404(
        ProductionBatch.objects.select_related("finished_good_item").prefetch_related(
            "inputs__lot__item"
        ),
        pk=pk,
    )
    if batch.status == "closed":
        messages.warning(request, f"Batch {batch.batch_number} is already closed.")
        return redirect("slurp_ui:production")

    if request.method == "POST":
        try:
            actual = float(request.POST.get("quantity_actual") or batch.quantity_produced)
            wastes = float(request.POST.get("wastes") or 0)
            spills = float(request.POST.get("spills") or 0)
        except ValueError:
            messages.error(request, "Invalid quantity / waste / spill values.")
            return redirect("slurp_ui:production_close_batch", pk=pk)

        qc_param = (request.POST.get("qc_parameter") or "").strip()
        qc_actual = (request.POST.get("qc_actual") or "").strip()
        qc_initials = (request.POST.get("qc_initials") or "").strip()
        notes_bits = []
        if batch.notes:
            notes_bits.append(batch.notes)
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
        _prod_ctx(batch=batch, port_status="full"),
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
