from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F, Min, Prefetch, Q, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from django.urls import reverse
from urllib.parse import urlencode

from erp_core.buy_services import (
    BuyFlowError,
    assert_po_is_current_version,
    cancel_purchase_order,
    check_in_lot,
    check_in_lots_batch,
    create_purchase_order,
    create_revision_purchase_order,
    issue_purchase_order,
    po_line_open_on_order_native,
    po_line_ordered_native,
    reverse_check_in,
)
from erp_core.inventory_count_services import (
    InventoryCountError,
    add_new_lot_line,
    cancel_count_session,
    create_count_session,
    mark_session_review,
    post_count_session,
    refresh_snapshot_missing_lots,
    reopen_session_draft,
    update_count_line,
    variance_summary,
)
from erp_core.inventory_table_data import (
    fetch_inventory_details,
    fetch_lots_by_sku_vendor,
    format_qty_for_display,
)
from erp_core.lot_display_quantities import compute_lot_quantity_breakdown
from erp_core.lot_services import (
    LotFlowError,
    checkout_indirect_material,
    coa_release_preview,
    put_on_hold,
    reconcile_lot,
    release_from_hold,
)
from erp_core.models import (
    CheckInLog,
    InventoryCountSession,
    Item,
    ItemPackSize,
    Lot,
    LotAttributeChangeLog,
    LotDepletionLog,
    LotHoldCase,
    LotTransactionLog,
    ProductionLog,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderLog,
    RDFormulaFamily,
    Vendor,
    VendorPricing,
)
from erp_core.rd_codes import normalize_family_letter
from erp_core.serializers import ItemSerializer

from ..nav import INVENTORY_NAV


def _inventory_return_url(request: HttpRequest) -> str:
    """Preserve expanded inventory table state after lot actions."""
    tab = request.GET.get("tab") or request.POST.get("tab") or "finished_good"
    uom = request.GET.get("uom") or request.POST.get("uom") or "lbs"
    sku = request.GET.get("sku") or request.POST.get("sku") or ""
    vendor = request.GET.get("vendor") if "vendor" in request.GET else request.POST.get("vendor")
    deeper = request.GET.get("deeper") or request.POST.get("deeper") or ""
    params = {"tab": tab, "uom": uom}
    if sku:
        params["sku"] = sku
    if vendor is not None and vendor != "":
        params["vendor"] = vendor
    elif vendor == "":
        params["vendor"] = ""
    if deeper:
        params["deeper"] = deeper
    return reverse("slurp_ui:inventory") + "?" + urlencode(params)


def _inventory_ctx(**extra):
    ctx = {
        "module": "inventory",
        "sidebar_nav": INVENTORY_NAV,
        "page_css": ["Inventory.css", "InventoryTable.css", "ItemsList.css", "CreateItemForm.css", "Logs.css"],
    }
    ctx.update(extra)
    return ctx


def _approved_vendors():
    return Vendor.objects.filter(approval_status="approved").order_by("name")


def _map_pack_unit_to_item_uom(pack_unit: str) -> str:
    """Inventory/order UoM follows pack unit; map pack-only units onto Item.UNIT_CHOICES."""
    u = (pack_unit or "lbs").strip().lower()
    if u in ("lbs", "kg", "ea"):
        return u
    if u in ("pcs", "gal"):
        return "ea"
    return "lbs"


def _parse_optional_float(raw, *, label: str, errors: list) -> float | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        errors.append(f"{label} must be a number.")
        return None


def _normalize_create_prices(pack_size, pack_unit, price, price_uom):
    """
    Return (item_price_per_inventory_uom, pack_price).
    price_uom: 'pack' or a unit matching pack/inventory measure.
    """
    if price is None:
        return None, None
    pu = (price_uom or "pack").strip().lower()
    if pu == "pack" or not pack_size:
        pack_price = price
        item_price = (price / pack_size) if pack_size else price
        return item_price, pack_price
    # Per unit of measure (lb/kg/ea/gal/pcs)
    item_price = price
    pack_price = price * pack_size if pack_size else price
    return item_price, pack_price


def _item_from_post(post, *, item=None):
    """Build item field dict from POST; returns (data_dict, errors list)."""
    errors = []
    sku = (post.get("sku") or "").strip().upper()
    name = (post.get("name") or post.get("description") or "").strip()
    vendor = (post.get("vendor") or "").strip() or None
    if not sku:
        errors.append("SKU is required.")
    if not name:
        errors.append("Name is required.")
    if vendor and Item.objects.filter(sku=sku, vendor=vendor).exclude(pk=getattr(item, "pk", None)).exists():
        errors.append(f'Item "{sku}" already exists for vendor {vendor}.')

    pack_unit = (post.get("pack_size_unit") or "").strip().lower()
    # Create form no longer collects item UoM — derive from pack unit when provided.
    posted_uom = (post.get("unit_of_measure") or "").strip().lower()
    if posted_uom in dict(Item.UNIT_CHOICES):
        uom = posted_uom
    elif pack_unit:
        uom = _map_pack_unit_to_item_uom(pack_unit)
    else:
        uom = getattr(item, "unit_of_measure", None) or "lbs"

    data = {
        "sku": sku,
        "name": name,
        "description": (post.get("description") or name).strip() or None,
        "vendor_item_name": (post.get("vendor_item_name") or "").strip() or None,
        "vendor_item_number": (post.get("vendor_item_number") or "").strip() or None,
        "item_type": post.get("item_type") or getattr(item, "item_type", "raw_material"),
        "unit_of_measure": uom,
        "vendor": vendor,
        "product_category": (post.get("product_category") or "").strip() or None,
        "hts_code": (post.get("hts_code") or "").strip() or None,
        "country_of_origin": (post.get("country_of_origin") or "").strip() or None,
        "on_order": float(getattr(item, "on_order", 0) or 0),
    }
    parent_id = post.get("sku_parent_item")
    if parent_id:
        try:
            data["sku_parent_item"] = int(parent_id)
        except (TypeError, ValueError):
            pass

    family_id = (post.get("product_family") or "").strip()
    if "product_family" in post:
        if family_id:
            try:
                data["product_family"] = int(family_id)
            except (TypeError, ValueError):
                errors.append("Invalid family letter selection.")
        else:
            data["product_family"] = None

    pack_f = _parse_optional_float(post.get("pack_size"), label="Pack size", errors=errors)
    if pack_f is not None:
        data["pack_size"] = pack_f

    price_f = _parse_optional_float(post.get("price"), label="Price", errors=errors)
    price_uom = (post.get("price_uom") or "pack").strip().lower()
    item_price, _pack_price = _normalize_create_prices(pack_f, pack_unit, price_f, price_uom)
    if item_price is not None:
        data["price"] = item_price
    return data, errors


def _maybe_create_default_pack_size(item, post):
    """Create ItemPackSize from create form when pack_size + unit provided."""
    pack_val = (post.get("pack_size") or "").strip()
    pack_unit = (post.get("pack_size_unit") or "lbs").strip().lower()
    if not pack_val:
        return
    try:
        pack_f = float(pack_val)
    except ValueError:
        return
    price_raw = (post.get("price") or "").strip()
    price_f = None
    if price_raw:
        try:
            price_f = float(price_raw)
        except ValueError:
            price_f = None
    price_uom = (post.get("price_uom") or "pack").strip().lower()
    _item_price, pack_price = _normalize_create_prices(pack_f, pack_unit, price_f, price_uom)

    allowed = {c[0] for c in ItemPackSize.PACK_SIZE_UNIT_CHOICES}
    if pack_unit not in allowed:
        pack_unit = "lbs"

    if item.pack_sizes.filter(is_active=True).exists():
        return
    ItemPackSize.objects.create(
        item=item,
        pack_size=pack_f,
        pack_size_unit=pack_unit,
        price=pack_price,
        description=(post.get("pack_size_description") or "").strip() or f"{pack_f} {pack_unit}",
        is_default=True,
        is_active=True,
    )


def _display_uom(request: HttpRequest) -> str:
    u = (request.GET.get("uom") or "lbs").lower()
    return u if u in ("lbs", "kg") else "lbs"


def _inventory_tab(request: HttpRequest) -> str:
    t = (request.GET.get("tab") or "finished_good").lower()
    if t in ("finished_good", "raw_material", "indirect_material"):
        return t
    return "finished_good"


@login_required
def inventory_table(request: HttpRequest) -> HttpResponse:
    """SKU rollup table matching React InventoryTable columns / tabs / expand."""
    tab = _inventory_tab(request)
    display_uom = _display_uom(request)
    expand_sku = (request.GET.get("sku") or "").strip()
    expand_vendor = request.GET.get("vendor")  # may be '' meaning Unknown
    deeper = str(request.GET.get("deeper") or "").lower() in ("1", "true", "yes")

    raw_rows = fetch_inventory_details(request.user, tab)
    rows = []
    for master in raw_rows:
        uom = master.get("pack_size_unit") or "lbs"
        sku = master.get("item_sku") or ""
        is_expanded = bool(expand_sku) and sku == expand_sku
        vendors_out = []
        vendor_names = []
        for v in master.get("vendors") or []:
            vname = v.get("vendor")
            item_type = v.get("item_type") or master.get("item_type")
            if vname not in (None, ""):
                key = (
                    "MFG"
                    if vname == "Unknown"
                    and (v.get("item_type") or master.get("item_type")) == "finished_good"
                    else vname
                )
            else:
                key = "MFG" if item_type == "finished_good" else "Unknown"
            if key not in vendor_names:
                vendor_names.append(key)
            if is_expanded:
                v_expanded = expand_vendor is not None and (
                    (expand_vendor in ("Unknown", "MFG") and key == expand_vendor)
                    or (expand_vendor == key)
                )
                vendors_out.append(
                    {
                        "vendor": key,
                        "raw_vendor": vname,
                        "description": v.get("description") or master.get("description"),
                        "item_type": v.get("item_type") or master.get("item_type"),
                        "product_category": v.get("product_category")
                        or master.get("product_category")
                        or "",
                        "pack_size_unit": v.get("pack_size_unit") or uom,
                        "available": format_qty_for_display(v.get("available"), uom, display_uom),
                        "on_order": format_qty_for_display(v.get("on_order"), uom, display_uom),
                        "allocated_to_sales": format_qty_for_display(
                            v.get("allocated_to_sales"), uom, display_uom
                        ),
                        "allocated_to_production": format_qty_for_display(
                            v.get("allocated_to_production"), uom, display_uom
                        ),
                        "on_hold": format_qty_for_display(v.get("on_hold"), uom, display_uom),
                        "lot_count": v.get("lot_count") or 0,
                        "expanded": v_expanded,
                    }
                )

        rows.append(
            {
                "sku": sku,
                "description": master.get("description") or "",
                "item_type": master.get("item_type") or "",
                "product_category": master.get("product_category") or "",
                "vendors_label": ", ".join(vendor_names) if vendor_names else "—",
                "pack_size_unit": uom,
                "available": format_qty_for_display(master.get("available"), uom, display_uom),
                "on_order": format_qty_for_display(master.get("on_order"), uom, display_uom),
                "allocated_to_sales": format_qty_for_display(
                    master.get("allocated_to_sales"), uom, display_uom
                ),
                "allocated_to_production": format_qty_for_display(
                    master.get("allocated_to_production"), uom, display_uom
                ),
                "on_hold": format_qty_for_display(master.get("on_hold"), uom, display_uom),
                "lot_count": master.get("lot_count") or 0,
                "vendor_count": master.get("vendor_count") or len(vendor_names),
                "expanded": is_expanded,
                "vendors": vendors_out,
                "on_hold_flag": float(master.get("on_hold") or 0) > 0,
            }
        )

    lot_rows = []
    if expand_sku and expand_vendor is not None:
        vendor_param = expand_vendor
        raw_lots = fetch_lots_by_sku_vendor(
            request.user,
            sku=expand_sku,
            vendor=vendor_param,
            inventory_table=tab,
            deeper=deeper,
        )
        for lot in raw_lots:
            lu = (lot.get("item") or {}).get("unit_of_measure") if isinstance(lot.get("item"), dict) else None
            if not lu:
                # serializer may flatten item fields differently
                lu = lot.get("unit_of_measure") or "lbs"
            # Prefer breakdown fields from API
            avail = lot.get("quantity_available_for_use")
            if avail is None:
                avail = lot.get("quantity_remaining")
            lot_rows.append(
                {
                    "id": lot.get("id"),
                    "lot_number": lot.get("lot_number") or "—",
                    "vendor_lot_number": lot.get("vendor_lot_number") or "—",
                    "po_number": lot.get("po_number") or "—",
                    "tracking": lot.get("po_tracking_number") or "—",
                    "received_date": lot.get("received_date"),
                    "manufacture_date": lot.get("manufacture_date"),
                    "expiration_date": lot.get("expiration_date"),
                    "quantity": format_qty_for_display(lot.get("quantity_remaining"), lu, display_uom),
                    "available": format_qty_for_display(avail, lu, display_uom),
                    "on_hold": format_qty_for_display(
                        lot.get("quantity_on_hold") or 0, lu, display_uom
                    ),
                    "status": lot.get("status") or "",
                    "committed_sales": format_qty_for_display(
                        lot.get("committed_to_sales_qty") or 0, lu, display_uom
                    ),
                    "committed_prod": format_qty_for_display(
                        lot.get("committed_to_production_qty") or 0, lu, display_uom
                    ),
                    "uom": display_uom if (lu or "").lower() in ("lbs", "kg", "lb") else (lu or display_uom),
                    "avail_native": float(avail or 0),
                    "hold_native": float(lot.get("quantity_on_hold") or 0),
                    "remaining_native": float(lot.get("quantity_remaining") or 0),
                }
            )

    show_on_order = tab != "finished_good"
    return render(
        request,
        "slurp_ui/inventory/table.html",
        _inventory_ctx(
            active_tab="inventory",
            rows=rows,
            lot_rows=lot_rows,
            tab=tab,
            display_uom=display_uom,
            expand_sku=expand_sku,
            expand_vendor=expand_vendor,
            deeper=deeper,
            show_on_order=show_on_order,
            port_status="full",
        ),
    )


@login_required
def inventory_items(request: HttpRequest) -> HttpResponse:
    q = (request.GET.get("q") or "").strip()
    item_type = (request.GET.get("type") or "").strip()
    family = (request.GET.get("family") or "").strip().upper()
    items = Item.objects.select_related("product_family").prefetch_related("pack_sizes")
    if q:
        items = items.filter(Q(sku__icontains=q) | Q(name__icontains=q) | Q(vendor__icontains=q))
    if item_type:
        items = items.filter(item_type=item_type)
    if family:
        items = items.filter(product_family__code__iexact=family)
    items = items.order_by(
        F("product_family__code").asc(nulls_last=True),
        "sku",
        "vendor",
    )[:500]
    return render(
        request,
        "slurp_ui/inventory/items.html",
        _inventory_ctx(
            active_tab="items",
            items=items,
            q=q,
            item_type=item_type,
            family=family,
            product_families=list(
                RDFormulaFamily.objects.filter(is_active=True).order_by("code")
            ),
            item_type_choices=Item.ITEM_TYPE_CHOICES,
            port_status="full",
        ),
    )


def _enrich_po_rows(pos: list) -> list:
    for po in pos:
        lines = list(po.items.all())
        po.line_count = len(lines)
        ordered = 0.0
        received = 0.0
        skus = []
        for li in lines:
            ordered += float(li.quantity_ordered or 0)
            received += float(li.quantity_received or 0)
            li.line_ext = float(li.quantity_ordered or 0) * float(li.unit_price or 0)
            if li.item_id and li.item:
                skus.append(li.item.sku)
        po.qty_ordered = ordered
        po.qty_received = received
        po.receive_pct = (100.0 * received / ordered) if ordered > 0 else 0.0
        po.lines_detail = lines
        if not skus:
            po.line_summary = "No lines"
        elif len(skus) == 1:
            po.line_summary = skus[0]
        else:
            po.line_summary = f"{skus[0]} +{len(skus) - 1} more"
    return pos


@login_required
@require_http_methods(["GET"])
def inventory_purchase_orders(request: HttpRequest) -> HttpResponse:
    q = (request.GET.get("q") or "").strip()
    queue = (request.GET.get("queue") or "open").strip().lower()
    layout = (request.GET.get("layout") or "cards").strip().lower()
    if queue not in ("open", "draft", "issued", "receive", "done", "cancelled", "all"):
        queue = "open"
    if layout not in ("cards", "split", "board"):
        layout = "cards"

    base = PurchaseOrder.objects.all()
    counts = {
        "open": base.exclude(status__in=["completed", "cancelled", "superseded"]).count(),
        "draft": base.filter(status="draft").count(),
        "issued": base.filter(status="issued").count(),
        "receive": base.filter(status="issued", drop_ship=False).count(),
        "done": base.filter(status__in=["received", "completed"]).count(),
        "cancelled": base.filter(status="cancelled").count(),
        "all": base.count(),
    }

    qs = PurchaseOrder.objects.prefetch_related(
        Prefetch("items", queryset=PurchaseOrderItem.objects.select_related("item"))
    )
    if queue == "open":
        qs = qs.exclude(status__in=["completed", "cancelled", "superseded"])
    elif queue == "draft":
        qs = qs.filter(status="draft")
    elif queue == "issued":
        qs = qs.filter(status="issued")
    elif queue == "receive":
        qs = qs.filter(status="issued", drop_ship=False)
    elif queue == "done":
        qs = qs.filter(status__in=["received", "completed"])
    elif queue == "cancelled":
        qs = qs.filter(status="cancelled")

    if q:
        qs = qs.filter(
            Q(po_number__icontains=q)
            | Q(vendor_customer_name__icontains=q)
            | Q(notes__icontains=q)
        )

    pos = _enrich_po_rows(list(qs.order_by("-created_at")[:200]))

    selected = None
    selected_id = request.GET.get("po")
    if selected_id:
        try:
            sid = int(selected_id)
        except (TypeError, ValueError):
            sid = None
        if sid:
            selected = next((p for p in pos if p.id == sid), None)
            if selected is None:
                selected = (
                    PurchaseOrder.objects.prefetch_related(
                        Prefetch(
                            "items",
                            queryset=PurchaseOrderItem.objects.select_related("item"),
                        )
                    )
                    .filter(pk=sid)
                    .first()
                )
                if selected:
                    _enrich_po_rows([selected])
    if selected is None and pos and layout == "split":
        selected = pos[0]

    open_value = (
        PurchaseOrder.objects.exclude(status__in=["completed", "cancelled", "superseded"]).aggregate(
            s=Sum("total")
        )["s"]
        or 0.0
    )

    return render(
        request,
        "slurp_ui/inventory/purchase_orders.html",
        _inventory_ctx(
            active_tab="purchase-orders",
            purchase_orders=pos,
            selected_po=selected,
            q=q,
            queue=queue,
            layout=layout,
            counts=counts,
            open_value=float(open_value or 0),
            shipment_mode_choices=PurchaseOrder.SHIPMENT_MODE_CHOICES,
            page_css=[
                "Inventory.css",
                "SalesWorkspace.css",
                "InventoryTable.css",
                "ItemsList.css",
                "CreateItemForm.css",
                "Logs.css",
            ],
            port_status="full",
        ),
    )


@login_required
@require_POST
def inventory_issue_po(request: HttpRequest, pk: int) -> HttpResponse:
    po = get_object_or_404(PurchaseOrder, pk=pk)
    issue_date = (request.POST.get("issue_date") or "").strip() or None
    try:
        issue_purchase_order(po, request.user, issue_date=issue_date)
        messages.success(request, f"Issued PO {po.po_number}.")
        _flash_po_email_outcome(request, po)
    except BuyFlowError as e:
        messages.error(request, e.message)
    return redirect("slurp_ui:inventory_purchase_orders")


def _flash_po_email_outcome(request: HttpRequest, po: PurchaseOrder) -> None:
    if getattr(po, "_email_sent", None) is False:
        messages.warning(
            request,
            getattr(po, "_email_error", None)
            or "PO issued, but the vendor email could not be sent.",
        )
    elif getattr(po, "_email_sent", None) is True:
        messages.info(request, f"Vendor email sent for PO {po.po_number}.")


@login_required
@require_POST
def inventory_cancel_po(request: HttpRequest, pk: int) -> HttpResponse:
    po = get_object_or_404(PurchaseOrder, pk=pk)
    try:
        cancel_purchase_order(po)
        messages.success(request, f"Cancelled PO {po.po_number}.")
    except BuyFlowError as e:
        messages.error(request, e.message)
    except Exception as e:
        messages.error(request, str(e))
    return redirect("slurp_ui:inventory_purchase_orders")


@login_required
@require_POST
def inventory_update_po_tracking(request: HttpRequest, pk: int) -> HttpResponse:
    """Manual inbound shipment tracking fields (automation can fill these later)."""
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if po.status in ("cancelled", "superseded"):
        messages.error(request, f"Cannot update tracking on a {po.status} PO.")
        return redirect(reverse("slurp_ui:inventory_purchase_orders") + f"?po={po.id}&layout=split")

    mode = (request.POST.get("shipment_mode") or "").strip()
    allowed_modes = {c[0] for c in PurchaseOrder.SHIPMENT_MODE_CHOICES}
    if mode not in allowed_modes:
        mode = ""

    eta_raw = (request.POST.get("inbound_eta_date") or "").strip()
    eta = None
    if eta_raw:
        try:
            from datetime import date as date_cls

            eta = date_cls.fromisoformat(eta_raw)
        except ValueError:
            messages.error(request, "Inbound ETA must be a valid date.")
            return redirect(
                reverse("slurp_ui:inventory_purchase_orders")
                + f"?queue={request.POST.get('queue') or 'open'}&layout=split&po={po.id}"
            )

    dest = (request.POST.get("destination_place") or "").strip()
    if not dest:
        dest = "Wildwood Ingredients — Washington, MO"

    po.shipment_mode = mode
    po.carrier = (request.POST.get("carrier") or "").strip() or None
    po.tracking_number = (request.POST.get("tracking_number") or "").strip() or None
    po.bill_of_lading = (request.POST.get("bill_of_lading") or "").strip()
    po.vessel_name = (request.POST.get("vessel_name") or "").strip()
    po.destination_place = dest
    po.inbound_eta_date = eta
    po.tracking_notes = (request.POST.get("tracking_notes") or "").strip()
    po.save(
        update_fields=[
            "shipment_mode",
            "carrier",
            "tracking_number",
            "bill_of_lading",
            "vessel_name",
            "destination_place",
            "inbound_eta_date",
            "tracking_notes",
            "updated_at",
        ]
    )
    messages.success(request, f"Saved tracking for {po.po_number}.")
    queue = (request.POST.get("queue") or "open").strip()
    layout = (request.POST.get("layout") or "split").strip()
    return redirect(
        reverse("slurp_ui:inventory_purchase_orders")
        + f"?queue={queue}&layout={layout}&po={po.id}"
    )


@login_required
@require_http_methods(["GET"])
def inventory_revise_po(request: HttpRequest, pk: int) -> HttpResponse:
    """Open the create-PO form prefilled for revising an existing PO."""
    po = get_object_or_404(PurchaseOrder, pk=pk)
    try:
        assert_po_is_current_version(po)
    except BuyFlowError as e:
        messages.error(request, e.message)
        return redirect("slurp_ui:inventory_purchase_orders")
    return redirect(reverse("slurp_ui:inventory_create_po") + f"?revise={po.id}")


def _po_revise_form_payload(po: PurchaseOrder) -> dict:
    """JSON payload used to prefill create_po.html when revising."""
    lines = []
    for li in po.items.select_related("item").all():
        lines.append(
            {
                "item_id": li.item_id,
                "quantity": li.quantity_ordered,
                "unit_cost": li.unit_price or 0,
                "order_uom": getattr(li, "order_uom", None) or "",
                "notes": li.notes or "",
            }
        )
    required = po.required_date or po.expected_delivery_date
    vendor_id = None
    try:
        vendor_id = int(po.vendor_customer_id) if po.vendor_customer_id else None
    except (TypeError, ValueError):
        vendor_id = None
    if vendor_id is None:
        vendor = Vendor.objects.filter(name__iexact=(po.vendor_customer_name or "").strip()).first()
        vendor_id = vendor.id if vendor else None
    return {
        "source_id": po.id,
        "source_number": po.po_number,
        "vendor_id": vendor_id,
        "required_date": required.isoformat() if required else "",
        "payment_terms": po.shipping_terms or "",
        "shipping_method": po.shipping_method or "",
        "coa_sds_email": po.coa_sds_email or "",
        "discount": po.discount or 0,
        "shipping_cost": po.shipping_cost or 0,
        "notes": po.notes or "",
        "drop_ship": bool(po.drop_ship),
        "ship_to_name": po.ship_to_name or "Wildwood Ingredients, LLC",
        "ship_to_address": po.ship_to_address or "6431 Michels Dr.",
        "ship_to_city": po.ship_to_city or "Washington",
        "ship_to_state": po.ship_to_state or "MO",
        "ship_to_zip": po.ship_to_zip or "63090",
        "ship_to_country": po.ship_to_country or "USA",
        "lines": lines,
    }


@login_required
def inventory_po_pdf(request: HttpRequest, pk: int) -> HttpResponse:
    po = get_object_or_404(PurchaseOrder.objects.prefetch_related("items__item"), pk=pk)
    try:
        from erp_core.po_pdf_html import generate_po_pdf_from_html

        pdf_bytes = generate_po_pdf_from_html(po)
    except Exception as e:
        messages.error(request, f"PO PDF failed: {e}")
        return redirect("slurp_ui:inventory_purchase_orders")
    if not pdf_bytes:
        messages.error(request, "PO PDF generation failed.")
        return redirect("slurp_ui:inventory_purchase_orders")
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    fname = f"{po.po_number or f'po-{pk}'}.pdf"
    disposition = "attachment" if request.GET.get("download") else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{fname}"'
    return response


@login_required
def inventory_logs(request: HttpRequest) -> HttpResponse:
    log_type = request.GET.get("type") or "transactions"
    if log_type not in (
        "transactions",
        "depletion",
        "purchase-orders",
        "production",
        "check-ins",
        "lot-attribute-changes",
    ):
        log_type = "transactions"

    limit = 200
    rows = []
    filters = {k: (request.GET.get(k) or "").strip() for k in request.GET if k != "type"}

    if log_type == "transactions":
        qs = LotTransactionLog.objects.select_related("lot", "lot__item").all()
        if filters.get("lot_number"):
            qs = qs.filter(lot_number__icontains=filters["lot_number"])
        if filters.get("sku"):
            qs = qs.filter(item_sku__icontains=filters["sku"])
        if filters.get("transaction_type"):
            qs = qs.filter(transaction_type=filters["transaction_type"])
        if filters.get("reference_number"):
            qs = qs.filter(reference_number__icontains=filters["reference_number"])
        if filters.get("date_from"):
            qs = qs.filter(logged_at__gte=filters["date_from"])
        if filters.get("date_to"):
            qs = qs.filter(logged_at__lte=filters["date_to"])
        rows = list(qs.order_by("-logged_at")[:limit])

    elif log_type == "depletion":
        qs = LotDepletionLog.objects.select_related("lot", "lot__item").all()
        if filters.get("lot_number"):
            qs = qs.filter(lot_number=filters["lot_number"])
        if filters.get("sku"):
            qs = qs.filter(item_sku=filters["sku"])
        if filters.get("method"):
            qs = qs.filter(depletion_method=filters["method"])
        if filters.get("date_from"):
            qs = qs.filter(depleted_at__gte=filters["date_from"])
        if filters.get("date_to"):
            qs = qs.filter(depleted_at__lte=filters["date_to"])
        rows = list(qs.order_by("-depleted_at")[:limit])

    elif log_type == "purchase-orders":
        qs = PurchaseOrderLog.objects.select_related("purchase_order").all()
        if filters.get("po_number"):
            qs = qs.filter(po_number=filters["po_number"])
        if filters.get("vendor"):
            qs = qs.filter(vendor_name=filters["vendor"])
        if filters.get("action"):
            qs = qs.filter(action=filters["action"])
        if filters.get("lot_number"):
            qs = qs.filter(lot_number=filters["lot_number"])
        if filters.get("date_from"):
            qs = qs.filter(logged_at__gte=filters["date_from"])
        if filters.get("date_to"):
            qs = qs.filter(logged_at__lte=filters["date_to"])
        rows = list(qs.order_by("-logged_at")[:limit])

    elif log_type == "production":
        qs = ProductionLog.objects.select_related("batch", "batch__finished_good_item").all()
        if filters.get("batch_number"):
            qs = qs.filter(batch_number=filters["batch_number"])
        if filters.get("sku"):
            qs = qs.filter(finished_good_sku=filters["sku"])
        if filters.get("batch_type"):
            qs = qs.filter(batch_type=filters["batch_type"])
        if filters.get("date_from"):
            qs = qs.filter(closed_date__gte=filters["date_from"])
        if filters.get("date_to"):
            qs = qs.filter(closed_date__lte=filters["date_to"])
        rows = list(qs.order_by("-logged_at")[:limit])

    elif log_type == "check-ins":
        qs = CheckInLog.objects.select_related("lot", "lot__item").all()
        if filters.get("item_sku"):
            qs = qs.filter(item_sku=filters["item_sku"])
        if filters.get("po_number"):
            qs = qs.filter(po_number=filters["po_number"])
        if filters.get("date_from"):
            qs = qs.filter(checked_in_at__gte=filters["date_from"])
        if filters.get("date_to"):
            qs = qs.filter(checked_in_at__lte=filters["date_to"])
        rows = list(qs.order_by("-checked_in_at")[:limit])

    elif log_type == "lot-attribute-changes":
        qs = LotAttributeChangeLog.objects.select_related("lot", "lot__item").all()
        if filters.get("lot_number"):
            qs = qs.filter(lot__lot_number__icontains=filters["lot_number"])
        if filters.get("sku"):
            qs = qs.filter(lot__item__sku__icontains=filters["sku"])
        if filters.get("field_name"):
            qs = qs.filter(field_name=filters["field_name"])
        if filters.get("date_from"):
            qs = qs.filter(changed_at__gte=filters["date_from"])
        if filters.get("date_to"):
            qs = qs.filter(changed_at__lte=filters["date_to"])
        rows = list(qs.order_by("-changed_at")[:limit])

    log_types = [
        ("transactions", "Lot transactions"),
        ("depletion", "Lot depletion"),
        ("purchase-orders", "Purchase orders"),
        ("production", "Production"),
        ("check-ins", "Check-ins"),
        ("lot-attribute-changes", "Lot attribute changes"),
    ]
    return render(
        request,
        "slurp_ui/inventory/logs.html",
        _inventory_ctx(
            active_tab="logs",
            log_type=log_type,
            log_types=log_types,
            rows=rows,
            filters=filters,
            port_status="full",
        ),
    )


def _parse_check_in_lines(post) -> list[dict]:
    """Parse indexed check-in lines: line-0-item_id, line-1-quantity, …"""
    indices: set[int] = set()
    for key in post.keys():
        if not key.startswith("line-"):
            continue
        parts = key.split("-", 2)
        if len(parts) >= 2 and parts[1].isdigit():
            indices.add(int(parts[1]))
    lines: list[dict] = []
    for i in sorted(indices):
        item_id = (post.get(f"line-{i}-item_id") or "").strip()
        qty = (post.get(f"line-{i}-quantity") or "").strip()
        if not item_id and not qty:
            continue
        lines.append(
            {
                "item_id": item_id,
                "quantity": qty,
                "entry_uom": post.get(f"line-{i}-entry_uom") or "",
                "status": post.get(f"line-{i}-lot_status") or "accepted",
                "vendor_lot_number": post.get(f"line-{i}-vendor_lot_number") or "",
                "expiration_date": post.get(f"line-{i}-expiration_date") or None,
                "manufacture_date": post.get(f"line-{i}-manufacture_date") or None,
                "freight_actual": post.get(f"line-{i}-freight_actual") or None,
                "lot_number": post.get(f"line-{i}-lot_number") or "",
                "notes": post.get(f"line-{i}-notes") or "",
            }
        )
    return lines


@login_required
@require_http_methods(["GET", "POST"])
def inventory_check_in(request: HttpRequest) -> HttpResponse:
    issued_pos = (
        PurchaseOrder.objects.filter(status="issued", drop_ship=False)
        .prefetch_related(
            Prefetch("items", queryset=PurchaseOrderItem.objects.select_related("item"))
        )
        .order_by("-order_date")[:100]
    )
    selected_po = None
    po_id = request.GET.get("po") or request.POST.get("po_id")
    if po_id:
        selected_po = (
            PurchaseOrder.objects.filter(pk=po_id, status="issued", drop_ship=False)
            .prefetch_related(
                Prefetch("items", queryset=PurchaseOrderItem.objects.select_related("item"))
            )
            .first()
        )

    if request.method == "POST":
        try:
            po = get_object_or_404(PurchaseOrder, pk=request.POST.get("po_id"), status="issued")
            shared = {
                "po_number": po.po_number,
                "received_date": request.POST.get("received_date") or "",
                "short_reason": request.POST.get("short_reason") or "",
                "carrier": request.POST.get("carrier") or (po.carrier or ""),
                "coa": request.POST.get("coa") == "on",
                "prod_free_pests": request.POST.get("prod_free_pests") == "on",
                "carrier_free_pests": request.POST.get("carrier_free_pests") == "on",
                "shipment_accepted": request.POST.get("shipment_accepted") == "on",
                "initials": request.POST.get("initials") or "",
                "notes": request.POST.get("notes") or "",
            }
            lines = _parse_check_in_lines(request.POST)
            # Backward compatible: single-line form fields if no indexed lines posted.
            if not lines and request.POST.get("item_id"):
                lines = [
                    {
                        "item_id": request.POST.get("item_id"),
                        "quantity": request.POST.get("quantity"),
                        "entry_uom": request.POST.get("entry_uom") or "",
                        "status": request.POST.get("lot_status") or "accepted",
                        "vendor_lot_number": request.POST.get("vendor_lot_number") or "",
                        "expiration_date": request.POST.get("expiration_date") or None,
                        "manufacture_date": request.POST.get("manufacture_date") or None,
                        "freight_actual": request.POST.get("freight_actual") or None,
                        "lot_number": request.POST.get("lot_number") or "",
                        "notes": request.POST.get("line_notes") or "",
                    }
                ]
            lots = check_in_lots_batch(request.user, shared, lines)
            if len(lots) == 1:
                lot = lots[0]
                messages.success(
                    request,
                    f"Checked in lot {lot.lot_number} — {lot.quantity} "
                    f"{lot.item.unit_of_measure} ({lot.status}).",
                )
            else:
                parts = [
                    f"{lot.lot_number} ({lot.status}: {lot.quantity} {lot.item.unit_of_measure})"
                    for lot in lots
                ]
                messages.success(
                    request,
                    f"Checked in {len(lots)} lots: " + "; ".join(parts) + ".",
                )
            return redirect(f"{request.path}?po={po.id}")
        except BuyFlowError as e:
            messages.error(request, e.message)
            selected_po = PurchaseOrder.objects.filter(pk=request.POST.get("po_id")).first()
        except Exception as e:
            messages.error(request, str(e))

    today = timezone.localdate().isoformat()
    check_in_lines = []
    if selected_po:
        for li in selected_po.items.all():
            if not li.item_id:
                continue
            native_uom = (li.item.unit_of_measure or "lbs").strip()
            order_uom = (li.order_uom or native_uom or "lbs").strip()
            ordered_native = po_line_ordered_native(li)
            remaining = po_line_open_on_order_native(li)
            check_in_lines.append(
                {
                    "item_id": li.item_id,
                    "sku": li.item.sku,
                    "name": li.item.name or "",
                    "native_uom": native_uom,
                    "order_uom": order_uom,
                    "ordered": float(li.quantity_ordered or 0),
                    "ordered_native": float(ordered_native),
                    "received": float(li.quantity_received or 0),
                    "remaining": float(remaining),
                    "fully_received": remaining <= 0.01,
                }
            )

    return render(
        request,
        "slurp_ui/inventory/check_in.html",
        _inventory_ctx(
            active_tab="inventory",
            issued_pos=issued_pos,
            selected_po=selected_po,
            check_in_lines=check_in_lines,
            today=today,
            god_mode=bool(request.session.get("god_mode")) and request.user.is_staff,
            port_status="full",
        ),
    )


def _resolve_or_create_product_family(post) -> tuple[RDFormulaFamily | None, list[str]]:
    """Use selected product_family, or create from new_family_code + new_family_name when checkbox is on."""
    errors: list[str] = []
    adding_new = (post.get("add_new_family") or "").strip() in ("1", "on", "true", "yes")
    new_code = (post.get("new_family_code") or "").strip()
    new_name = (post.get("new_family_name") or "").strip()
    if adding_new:
        if not new_code and not new_name:
            errors.append("Check “Add a new family letter” only when providing Code and Name.")
            return None, errors
        try:
            code = normalize_family_letter(new_code)
        except ValueError as exc:
            errors.append(str(exc) or "Family code must be 1–4 letters.")
            return None, errors
        if not new_name:
            errors.append("New family needs a name (e.g. Natural Green).")
            return None, errors
        existing = RDFormulaFamily.objects.filter(code__iexact=code).first()
        if existing:
            if new_name and existing.name != new_name:
                existing.name = new_name
                existing.is_active = True
                existing.save(update_fields=["name", "is_active", "updated_at"])
            return existing, errors
        fam = RDFormulaFamily.objects.create(code=code, name=new_name, is_active=True)
        return fam, errors

    fam_id = (post.get("product_family") or "").strip()
    if not fam_id:
        return None, errors
    try:
        pk = int(fam_id)
    except (TypeError, ValueError):
        errors.append("Invalid family letter selection.")
        return None, errors
    fam = RDFormulaFamily.objects.filter(pk=pk).first()
    if not fam:
        errors.append("Selected family was not found.")
    return fam, errors


def _maybe_set_product_family_from_sku(item) -> None:
    """If product_family is empty, link from the longest family prefix on the parsed parent stem."""
    if getattr(item, "product_family_id", None):
        return
    from erp_core.sku_family import all_family_prefixes, match_family_prefix

    stem = (getattr(item, "sku_parent_code", None) or item.sku or "").strip().upper()
    if not stem:
        return
    # Use full prefix set (incl. composed LH) so we do not mis-tag blends as the first letter only.
    code = match_family_prefix(stem, all_family_prefixes())
    if not code:
        return
    fam = RDFormulaFamily.objects.filter(code__iexact=code, is_active=True).first()
    if not fam:
        # Composed blend with no registry row yet — leave unset; user can add via checkbox.
        return
    item.product_family = fam
    item.save(update_fields=["product_family", "updated_at"])


@login_required
@require_http_methods(["GET", "POST"])
def inventory_create_item(request: HttpRequest) -> HttpResponse:
    vendors = _approved_vendors()
    # One picker row per material family — prefer a true master (no pack suffix), else any row.
    family_qs = (
        Item.objects.exclude(item_type="indirect_material")
        .exclude(sku_parent_code__isnull=True)
        .exclude(sku_parent_code="")
    )
    # Prefer master rows (no pack suffix) when choosing the representative id per family.
    master_ids = (
        family_qs.filter(Q(sku_pack_suffix__isnull=True) | Q(sku_pack_suffix=""))
        .values("sku_parent_code")
        .annotate(min_id=Min("id"))
        .values_list("min_id", flat=True)
    )
    covered = set(
        family_qs.filter(pk__in=master_ids).values_list("sku_parent_code", flat=True)
    )
    fallback_ids = (
        family_qs.exclude(sku_parent_code__in=covered)
        .values("sku_parent_code")
        .annotate(min_id=Min("id"))
        .values_list("min_id", flat=True)
    )
    master_items = list(
        Item.objects.filter(pk__in=list(master_ids) + list(fallback_ids)).order_by(
            "sku_parent_code", "sku"
        )[:400]
    )
    existing_skus = list(
        Item.objects.order_by("sku").values_list("sku", flat=True).distinct()[:800]
    )
    product_families = list(
        RDFormulaFamily.objects.filter(is_active=True).order_by("code", "name")
    )
    mode = request.POST.get("mode") or request.GET.get("mode") or "new"
    selected_parent = None
    parent_id = request.POST.get("sku_parent_item") or request.GET.get("parent")
    if parent_id:
        selected_parent = Item.objects.filter(pk=parent_id).first()

    if request.method == "POST":
        action = request.POST.get("action") or "create"
        if action == "create":
            post = request.POST.copy()
            fam, fam_errors = _resolve_or_create_product_family(post)
            for e in fam_errors:
                messages.error(request, e)
            if fam:
                post["product_family"] = str(fam.pk)

            data, errors = _item_from_post(post)
            if mode == "add-vendor":
                existing_sku = (post.get("existing_sku") or "").strip().upper()
                if existing_sku:
                    data["sku"] = existing_sku
                    ref = Item.objects.filter(sku=existing_sku).first()
                    if ref and not data.get("name"):
                        data["name"] = ref.name
            if fam_errors or errors:
                for e in errors:
                    messages.error(request, e)
            else:
                serializer = ItemSerializer(data=data)
                if serializer.is_valid():
                    item = serializer.save()
                    _maybe_create_default_pack_size(item, post)
                    if not fam:
                        _maybe_set_product_family_from_sku(item)
                    from erp_core.cost_master_sync import sync_item_to_cost_master

                    sync_item_to_cost_master(
                        item,
                        changed_by=getattr(request.user, "username", None) or "system",
                        history_note=f"Created from catalog item {item.sku}",
                    )
                    messages.success(request, f"Created item {item.sku}.")
                    return redirect("slurp_ui:inventory_edit_item", pk=item.pk)
                for field, errs in serializer.errors.items():
                    for err in errs:
                        messages.error(request, f"{field}: {err}")

    return render(
        request,
        "slurp_ui/inventory/create_item.html",
        _inventory_ctx(
            active_tab="items",
            vendors=vendors,
            master_items=master_items,
            existing_skus=existing_skus,
            product_families=product_families,
            mode=mode,
            selected_parent=selected_parent,
            item_type_choices=Item.ITEM_TYPE_CHOICES,
            product_category_choices=Item.PRODUCT_CATEGORY_CHOICES,
            pack_unit_choices=ItemPackSize.PACK_SIZE_UNIT_CHOICES,
            price_uom_choices=[
                ("pack", "Per pack"),
                ("lbs", "Per lb"),
                ("kg", "Per kg"),
                ("gal", "Per gallon"),
                ("ea", "Per each"),
                ("pcs", "Per piece"),
            ],
            port_status="full",
            # Lean CSS — inventory table styles force min-widths / overflow-x on this bare form page.
            page_css=["CreateItemForm.css"],
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def inventory_edit_item(request: HttpRequest, pk: int) -> HttpResponse:
    item = get_object_or_404(Item.objects.prefetch_related("pack_sizes"), pk=pk)
    pack_sizes = list(item.pack_sizes.order_by("-is_default", "pack_size"))

    if request.method == "POST":
        action = request.POST.get("action") or "save"
        if action == "save":
            data, errors = _item_from_post(request.POST, item=item)
            if errors:
                for e in errors:
                    messages.error(request, e)
            else:
                serializer = ItemSerializer(item, data=data, partial=False)
                if serializer.is_valid():
                    serializer.save()
                    from erp_core.cost_master_sync import sync_item_to_cost_master

                    item.refresh_from_db()
                    sync_item_to_cost_master(
                        item,
                        changed_by=getattr(request.user, "username", None) or "system",
                        history_note=f"Updated from catalog item {item.sku}",
                    )
                    messages.success(request, f"Updated {item.sku}.")
                    return redirect("slurp_ui:inventory_edit_item", pk=pk)
                for field, errs in serializer.errors.items():
                    for err in errs:
                        messages.error(request, f"{field}: {err}")
        elif action == "add_pack_size":
            try:
                ps = float(request.POST.get("pack_size") or 0)
            except ValueError:
                ps = 0
            unit = request.POST.get("pack_size_unit") or "lbs"
            if ps <= 0:
                messages.error(request, "Pack size must be positive.")
            else:
                is_default = bool(request.POST.get("is_default"))
                if is_default:
                    item.pack_sizes.update(is_default=False)
                price = None
                pr = (request.POST.get("pack_price") or "").strip()
                if pr:
                    try:
                        price = float(pr)
                    except ValueError:
                        pass
                ItemPackSize.objects.create(
                    item=item,
                    pack_size=ps,
                    pack_size_unit=unit,
                    price=price,
                    description=(request.POST.get("pack_description") or "").strip() or f"{ps} {unit}",
                    is_default=is_default,
                    is_active=True,
                )
                messages.success(request, "Pack size added.")
                return redirect("slurp_ui:inventory_edit_item", pk=pk)
        elif action == "delete_pack_size":
            ps_id = request.POST.get("pack_size_id")
            ps = item.pack_sizes.filter(pk=ps_id).first()
            if ps:
                ps.delete()
                messages.success(request, "Pack size removed.")
            return redirect("slurp_ui:inventory_edit_item", pk=pk)
        elif action == "toggle_pack_size":
            ps_id = request.POST.get("pack_size_id")
            ps = item.pack_sizes.filter(pk=ps_id).first()
            if ps:
                field = request.POST.get("toggle_field")
                if field == "is_default":
                    item.pack_sizes.update(is_default=False)
                    ps.is_default = True
                    ps.save(update_fields=["is_default"])
                elif field == "is_active":
                    ps.is_active = not ps.is_active
                    ps.save(update_fields=["is_active"])
            return redirect("slurp_ui:inventory_edit_item", pk=pk)

    return render(
        request,
        "slurp_ui/inventory/edit_item.html",
        _inventory_ctx(
            active_tab="items",
            item=item,
            pack_sizes=pack_sizes,
            product_families=list(
                RDFormulaFamily.objects.filter(is_active=True).order_by("code", "name")
            ),
            item_type_choices=Item.ITEM_TYPE_CHOICES,
            product_category_choices=Item.PRODUCT_CATEGORY_CHOICES,
            pack_unit_choices=ItemPackSize.PACK_SIZE_UNIT_CHOICES,
            uom_choices=Item.UNIT_CHOICES,
            port_status="full",
            page_css=["CreateItemForm.css"],
        ),
    )


def _vendor_po_catalog_payload(vendors) -> dict:
    """Per-vendor catalog for create-PO: payment terms + approved items with price/UoM/pack."""
    today = timezone.localdate()
    vendor_list = list(vendors)
    name_by_lower = {(v.name or "").strip().lower(): v for v in vendor_list if (v.name or "").strip()}

    items = list(
        Item.objects.exclude(item_type="finished_good")
        .exclude(Q(vendor__isnull=True) | Q(vendor=""))
        .prefetch_related(
            Prefetch(
                "pack_sizes",
                queryset=ItemPackSize.objects.filter(is_active=True).order_by(
                    "-is_default", "pack_size", "pack_size_unit"
                ),
            )
        )
        .order_by("sku")
    )
    items = [it for it in items if (it.vendor or "").strip().lower() in name_by_lower]

    pricing_best: dict[tuple[str, int], VendorPricing] = {}
    item_ids = [it.id for it in items]
    if item_ids:
        for vp in (
            VendorPricing.objects.filter(is_active=True, item_id__in=item_ids)
            .order_by("-effective_date", "-id")
        ):
            vkey = (vp.vendor_name or "").strip().lower()
            if vkey not in name_by_lower:
                continue
            if vp.effective_date and vp.effective_date > today:
                continue
            if vp.expiry_date and vp.expiry_date < today:
                continue
            key = (vkey, int(vp.item_id))
            if key not in pricing_best:
                pricing_best[key] = vp

    items_by_vendor: dict[str, list] = {str(v.id): [] for v in vendor_list}
    for it in items:
        v = name_by_lower.get((it.vendor or "").strip().lower())
        if not v:
            continue
        vkey = (v.name or "").strip().lower()
        vp = pricing_best.get((vkey, it.id))
        # Order UoM always follows the item master (SKU) default — not vendor-pricing UoM.
        uom = (it.unit_of_measure or "lbs").strip() or "lbs"
        packs = []
        default_pack_id = None
        for ps in it.pack_sizes.all():
            label = (ps.description or "").strip() or f"{ps.pack_size:g} {ps.pack_size_unit}"
            packs.append({"id": str(ps.id), "label": label})
            if default_pack_id is None and ps.is_default:
                default_pack_id = str(ps.id)
        if not packs and it.pack_size is not None and float(it.pack_size) > 0:
            # Legacy Item.pack_size (no ItemPackSize rows in this DB yet)
            legacy_id = f"legacy:{float(it.pack_size):g}:{uom}"
            packs.append({"id": legacy_id, "label": f"{float(it.pack_size):g} {uom}"})
            default_pack_id = legacy_id
        if default_pack_id is None and packs:
            default_pack_id = packs[0]["id"]
        unit_price = float(vp.unit_price) if vp and vp.unit_price is not None else float(it.price or 0)
        items_by_vendor[str(v.id)].append(
            {
                "id": it.id,
                "sku": it.sku,
                "name": it.name,
                "vendor_item_name": it.vendor_item_name or it.name,
                "vendor_item_number": it.vendor_item_number or "",
                "unit_of_measure": uom,
                "unit_price": unit_price,
                "pack_sizes": packs,
                "default_pack_size_id": default_pack_id,
            }
        )

    catalog = {}
    for v in vendor_list:
        catalog[str(v.id)] = {
            "payment_terms": (v.payment_terms or "").strip(),
            "name": v.name,
            "items": items_by_vendor.get(str(v.id), []),
        }
    return catalog


@login_required
@require_http_methods(["GET", "POST"])
def inventory_create_po(request: HttpRequest) -> HttpResponse:
    vendors = list(_approved_vendors())
    vendor_catalog = _vendor_po_catalog_payload(vendors)
    revise_source = None
    revise_prefill = None

    revise_raw = (request.POST.get("revise_source_id") or request.GET.get("revise") or "").strip()
    if revise_raw:
        try:
            revise_source = PurchaseOrder.objects.prefetch_related(
                Prefetch("items", queryset=PurchaseOrderItem.objects.select_related("item"))
            ).get(pk=int(revise_raw))
        except (PurchaseOrder.DoesNotExist, ValueError, TypeError):
            messages.error(request, "Purchase order to revise was not found.")
            return redirect("slurp_ui:inventory_purchase_orders")
        if revise_source.status in ("cancelled", "superseded", "completed"):
            messages.error(request, f"Cannot revise a {revise_source.status} PO.")
            return redirect("slurp_ui:inventory_purchase_orders")
        try:
            assert_po_is_current_version(revise_source)
        except BuyFlowError as e:
            messages.error(request, e.message)
            return redirect("slurp_ui:inventory_purchase_orders")
        revise_prefill = _po_revise_form_payload(revise_source)

    if request.method == "POST":
        try:
            line_count = int(request.POST.get("line_count") or 0)
        except ValueError:
            line_count = 0

        vendor = None
        try:
            vendor = Vendor.objects.get(pk=int(request.POST.get("vendor_id")))
        except (Vendor.DoesNotExist, ValueError, TypeError):
            messages.error(request, "Select a valid vendor.")

        lines = []
        had_item_error = False
        if vendor:
            vendor_name_key = (vendor.name or "").strip().lower()
            allowed_item_ids = {
                int(row["id"])
                for row in (vendor_catalog.get(str(vendor.id), {}) or {}).get("items", [])
            }
            pack_labels = {
                int(ps.id): ((ps.description or "").strip() or f"{ps.pack_size:g} {ps.pack_size_unit}")
                for ps in ItemPackSize.objects.filter(is_active=True)
            }
            for i in range(line_count):
                item_id = request.POST.get(f"item_id_{i}")
                qty = request.POST.get(f"quantity_{i}")
                if not item_id or not qty:
                    continue
                try:
                    item_id_int = int(item_id)
                    q = float(qty)
                except ValueError:
                    continue
                if q <= 0:
                    continue
                if item_id_int not in allowed_item_ids:
                    messages.error(
                        request,
                        f"Item id {item_id_int} is not an approved item for {vendor.name}.",
                    )
                    had_item_error = True
                    lines = []
                    break
                item = Item.objects.filter(pk=item_id_int).first()
                if not item or (item.vendor or "").strip().lower() != vendor_name_key:
                    messages.error(
                        request,
                        f"Item {getattr(item, 'sku', item_id_int)} is not approved for {vendor.name}.",
                    )
                    had_item_error = True
                    lines = []
                    break
                notes = (request.POST.get(f"notes_{i}") or "").strip()
                pack_raw = (request.POST.get(f"pack_size_id_{i}") or "").strip()
                if pack_raw:
                    pack_tag = None
                    if pack_raw.startswith("legacy:"):
                        # legacy:{qty}:{uom}
                        parts = pack_raw.split(":", 2)
                        if len(parts) == 3:
                            pack_tag = f"[Pack: {parts[1]} {parts[2]}]"
                    else:
                        try:
                            pack_id = int(pack_raw)
                        except ValueError:
                            pack_id = None
                        if pack_id and pack_id in pack_labels:
                            pack_tag = f"[Pack: {pack_labels[pack_id]}]"
                    if pack_tag and pack_tag not in notes:
                        notes = f"{pack_tag} {notes}".strip() if notes else pack_tag
                lines.append(
                    {
                        "item_id": item_id_int,
                        "quantity": q,
                        "unit_cost": float(request.POST.get(f"unit_cost_{i}") or 0),
                        "order_uom": (request.POST.get(f"order_uom_{i}") or "").strip() or None,
                        "notes": notes,
                    }
                )

        if vendor and lines:
            payment_terms = (request.POST.get("payment_terms") or "").strip()
            payload = {
                "vendor_id": vendor.id,
                "required_date": request.POST.get("required_date") or None,
                "expected_delivery_date": request.POST.get("required_date") or None,
                # PO.shipping_terms stores this PO's payment-terms override (PDF Payment Terms).
                "shipping_terms": payment_terms,
                "shipping_method": request.POST.get("shipping_method") or "",
                "coa_sds_email": request.POST.get("coa_sds_email") or "",
                "discount": float(request.POST.get("discount") or 0),
                "shipping_cost": float(request.POST.get("shipping_cost") or 0),
                "notes": request.POST.get("notes") or "",
                "drop_ship": request.POST.get("drop_ship") == "on",
                "ship_to_name": request.POST.get("ship_to_name") or "Wildwood Ingredients, LLC",
                "ship_to_address": request.POST.get("ship_to_address") or "6431 Michels Dr.",
                "ship_to_city": request.POST.get("ship_to_city") or "Washington",
                "ship_to_state": request.POST.get("ship_to_state") or "MO",
                "ship_to_zip": request.POST.get("ship_to_zip") or "63090",
                "ship_to_country": request.POST.get("ship_to_country") or "USA",
                "items": lines,
                "status": "draft",
                "po_type": "vendor",
            }
            if request.user.is_staff and request.session.get("god_mode"):
                od = (request.POST.get("order_date") or "").strip()
                if od:
                    payload["order_date"] = od

            payload["vendor_address"] = vendor.street_address or vendor.address or ""
            payload["vendor_city"] = vendor.city or ""
            payload["vendor_state"] = vendor.state or ""
            payload["vendor_zip"] = vendor.zip_code or ""
            payload["vendor_country"] = vendor.country or ""

            try:
                want_issue = (request.POST.get("submit_action") or "draft").strip().lower() == "issue"
                if revise_source:
                    po = create_revision_purchase_order(request.user, revise_source, payload)
                    if want_issue:
                        issue_purchase_order(po, request.user)
                        messages.success(
                            request,
                            f"Saved and issued revision {po.po_number} "
                            f"(closed prior open version of that PO only).",
                        )
                        _flash_po_email_outcome(request, po)
                        return redirect(
                            reverse("slurp_ui:inventory_purchase_orders")
                            + f"?queue=open&po={po.id}"
                        )
                    messages.success(
                        request,
                        f"Saved revision draft {po.po_number} "
                        f"(closed prior open version of that PO only). Use Issue PO when ready.",
                    )
                    return redirect(
                        reverse("slurp_ui:inventory_purchase_orders")
                        + f"?queue=open&po={po.id}"
                    )
                po = create_purchase_order(request.user, payload)
                if want_issue:
                    issue_purchase_order(po, request.user)
                    messages.success(request, f"Created and issued PO {po.po_number}.")
                    _flash_po_email_outcome(request, po)
                    return redirect("slurp_ui:inventory_purchase_orders")
                messages.success(
                    request,
                    f"Created draft PO {po.po_number}. Use Issue PO on the list when ready.",
                )
                return redirect(reverse("slurp_ui:inventory_purchase_orders") + "?queue=draft")
            except BuyFlowError as e:
                messages.error(request, e.message)
            except Exception as e:
                messages.error(request, str(e))
        elif vendor and not lines and not had_item_error:
            messages.error(request, "Add at least one valid line item.")

    return render(
        request,
        "slurp_ui/inventory/create_po.html",
        _inventory_ctx(
            active_tab="purchase-orders",
            vendors=vendors,
            vendor_catalog=vendor_catalog,
            god_mode=bool(request.session.get("god_mode")) and request.user.is_staff,
            today=timezone.localdate().isoformat(),
            revise_source=revise_source,
            revise_prefill=revise_prefill,
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def inventory_indirect_checkout(request: HttpRequest) -> HttpResponse:
    lots_qs = (
        Lot.objects.select_related("item")
        .filter(item__item_type="indirect_material", quantity_remaining__gt=0)
        .exclude(status="rejected")
        .order_by("item__sku", "-received_date")[:300]
    )
    lot_choices = []
    for lot in lots_qs:
        avail = float(compute_lot_quantity_breakdown(lot)["quantity_available_for_use"])
        if avail <= 0:
            continue
        if lot.status and lot.status not in ("accepted", "on_hold"):
            continue
        lot_choices.append({"lot": lot, "available": avail})

    if request.method == "POST":
        lot_id = request.POST.get("lot_id")
        try:
            lot = get_object_or_404(Lot.objects.select_related("item"), pk=lot_id)
            qty = float(request.POST.get("quantity") or 0)
            checkout_indirect_material(
                request.user,
                lot,
                qty,
                notes=(request.POST.get("notes") or "").strip(),
                reference_number=(request.POST.get("reference_number") or "").strip(),
            )
            messages.success(
                request,
                f"Checked out {qty} {lot.item.unit_of_measure} from lot {lot.lot_number}.",
            )
            return redirect("slurp_ui:inventory_indirect_checkout")
        except LotFlowError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "slurp_ui/inventory/indirect_checkout.html",
        _inventory_ctx(
            active_tab="inventory",
            lot_choices=lot_choices,
            page_css=["Inventory.css", "IndirectMaterialCheckout.css"],
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def inventory_lot_hold(request: HttpRequest, pk: int) -> HttpResponse:
    lot = get_object_or_404(Lot.objects.select_related("item"), pk=pk)
    avail = float(compute_lot_quantity_breakdown(lot)["quantity_available_for_use"])
    next_url = _inventory_return_url(request)

    if request.method == "POST":
        try:
            qty = float(request.POST.get("quantity") or 0)
            reason = (request.POST.get("reason") or "").strip()
            put_on_hold(lot, qty, user=request.user, reason=reason)
            messages.success(request, f"Put {qty} on hold for lot {lot.lot_number}.")
            case = (
                LotHoldCase.objects.filter(lot=lot, status="open")
                .order_by("-opened_at")
                .first()
            )
            if case:
                return redirect("slurp_ui:inventory_hold_case", pk=case.pk)
            return redirect(next_url)
        except LotFlowError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "slurp_ui/inventory/lot_hold.html",
        _inventory_ctx(
            active_tab="inventory",
            lot=lot,
            available=avail,
            next_url=next_url,
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def inventory_lot_release(request: HttpRequest, pk: int) -> HttpResponse:
    lot = get_object_or_404(Lot.objects.select_related("item"), pk=pk)
    hold_qty = float(getattr(lot, "quantity_on_hold", 0) or 0)
    next_url = _inventory_return_url(request)
    preview = None
    release_qty = hold_qty

    if request.method == "GET":
        raw = (request.GET.get("quantity") or "").strip()
        if raw:
            try:
                release_qty = float(raw)
            except ValueError:
                release_qty = hold_qty
        try:
            preview = coa_release_preview(lot, release_qty)
        except LotFlowError as e:
            messages.error(request, e.message)
            return redirect(next_url)

    if request.method == "POST":
        try:
            release_qty = float(request.POST.get("quantity") or 0)
            preview = coa_release_preview(lot, release_qty)
            coa_payload = None
            if preview.get("coa_required"):
                line_results = []
                for line in preview.get("template_lines") or []:
                    lid = line.get("id")
                    line_results.append(
                        {
                            "item_line_id": lid,
                            "result_text": (request.POST.get(f"line_{lid}") or "").strip(),
                        }
                    )
                coa_payload = {"line_results": line_results}
                if preview.get("formula_qc"):
                    coa_payload["qc_result_value"] = request.POST.get("qc_result_value")
            release_from_hold(request.user, lot, release_qty, coa_payload=coa_payload)
            messages.success(request, f"Released {release_qty} from hold on lot {lot.lot_number}.")
            return redirect(next_url)
        except LotFlowError as e:
            messages.error(request, e.message)
            try:
                preview = coa_release_preview(lot, float(request.POST.get("quantity") or hold_qty))
            except LotFlowError:
                preview = None
        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "slurp_ui/inventory/lot_release.html",
        _inventory_ctx(
            active_tab="inventory",
            lot=lot,
            hold_qty=hold_qty,
            release_qty=release_qty,
            preview=preview,
            next_url=next_url,
            page_css=["Inventory.css", "ReleaseFromHoldCoaModal.css"],
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET"])
def inventory_holds(request: HttpRequest) -> HttpResponse:
    """Open (and optionally recent resolved) hold investigation cases."""
    show = (request.GET.get("show") or "open").strip().lower()
    qs = LotHoldCase.objects.select_related("lot", "lot__item").prefetch_related("notes")
    open_count = qs.filter(status="open").count()
    resolved_count = qs.filter(status="resolved").count()
    if show == "resolved":
        cases = qs.filter(status="resolved").order_by("-resolved_at", "-opened_at")[:100]
    elif show == "all":
        cases = qs.order_by("-opened_at")[:150]
    else:
        cases = qs.filter(status="open").order_by("-opened_at")[:100]
        show = "open"

    rows = []
    for case in cases:
        lot = case.lot
        hold_qty = float(getattr(lot, "quantity_on_hold", 0) or 0)
        last_note = case.notes.order_by("-created_at").first()
        rows.append(
            {
                "case": case,
                "lot": lot,
                "hold_qty": hold_qty,
                "note_count": case.notes.count(),
                "last_note": last_note,
                "last_note_preview": (
                    (last_note.body or "").strip()[:120] if last_note else ""
                ),
                "last_note_truncated": bool(
                    last_note and len((last_note.body or "").strip()) > 120
                ),
            }
        )

    return render(
        request,
        "slurp_ui/inventory/holds.html",
        _inventory_ctx(
            active_tab="holds",
            rows=rows,
            show=show,
            open_count=open_count,
            resolved_count=resolved_count,
            page_css=[
                "Inventory.css",
                "SalesWorkspace.css",
                "HoldLog.css",
            ],
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def inventory_hold_case(request: HttpRequest, pk: int) -> HttpResponse:
    """Hold log detail: notes/photos + resolve accept / return / discard."""
    from erp_core.hold_services import add_hold_note, open_hold_qty, resolve_hold_case
    from erp_core.lot_services import coa_release_preview

    case = get_object_or_404(
        LotHoldCase.objects.select_related("lot", "lot__item").prefetch_related("notes"),
        pk=pk,
    )
    lot = case.lot
    hold_qty = open_hold_qty(lot)
    preview = None
    if case.status == "open" and hold_qty > 0:
        try:
            preview = coa_release_preview(lot, hold_qty)
        except LotFlowError:
            preview = None

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip().lower()
        try:
            if action == "add_note":
                photo = request.FILES.get("photo")
                add_hold_note(
                    case,
                    user=request.user,
                    body=request.POST.get("body") or "",
                    photo=photo,
                )
                messages.success(request, "Note added to hold log.")
            elif action == "resolve":
                resolution = (request.POST.get("resolution") or "").strip().lower()
                qty = float(request.POST.get("quantity") or 0)
                coa_payload = None
                if resolution == "accept" and preview and preview.get("coa_required"):
                    line_results = []
                    for line in preview.get("template_lines") or []:
                        lid = line.get("id")
                        line_results.append(
                            {
                                "item_line_id": lid,
                                "result_text": (request.POST.get(f"line_{lid}") or "").strip(),
                            }
                        )
                    coa_payload = {"line_results": line_results}
                    if preview.get("formula_qc"):
                        coa_payload["qc_result_value"] = request.POST.get("qc_result_value")
                resolve_hold_case(
                    case,
                    user=request.user,
                    resolution=resolution,
                    quantity=qty,
                    notes=request.POST.get("resolution_notes") or "",
                    coa_payload=coa_payload,
                )
                case.refresh_from_db()
                if case.status == "resolved":
                    messages.success(
                        request,
                        f"Hold case resolved ({case.get_resolution_display()}).",
                    )
                else:
                    messages.success(
                        request,
                        f"Recorded {resolution} for {qty}; remaining hold stays open.",
                    )
            else:
                messages.error(request, "Unknown action.")
            return redirect("slurp_ui:inventory_hold_case", pk=case.pk)
        except LotFlowError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "slurp_ui/inventory/hold_case.html",
        _inventory_ctx(
            active_tab="holds",
            case=case,
            lot=lot,
            hold_qty=hold_qty,
            notes=list(case.notes.all()),
            preview=preview,
            next_url=_inventory_return_url(request),
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET"])
def inventory_lot_hold_log(request: HttpRequest, pk: int) -> HttpResponse:
    """Jump from inventory table lot → open hold case (create if missing)."""
    from erp_core.hold_services import ensure_open_hold_case, open_hold_qty

    lot = get_object_or_404(Lot.objects.select_related("item"), pk=pk)
    if open_hold_qty(lot) <= 0 and not LotHoldCase.objects.filter(lot=lot).exists():
        messages.info(request, f"Lot {lot.lot_number} has no hold quantity or hold log.")
        return redirect(_inventory_return_url(request))
    case = (
        LotHoldCase.objects.filter(lot=lot, status="open").order_by("-opened_at").first()
        or LotHoldCase.objects.filter(lot=lot).order_by("-opened_at").first()
    )
    if case is None:
        case = ensure_open_hold_case(
            lot,
            user=request.user,
            summary="On hold",
            initial_note="Hold log opened from inventory.",
        )
    return redirect("slurp_ui:inventory_hold_case", pk=case.pk)


@login_required
@require_http_methods(["GET", "POST"])
def inventory_lot_reconcile(request: HttpRequest, pk: int) -> HttpResponse:
    lot = get_object_or_404(Lot.objects.select_related("item"), pk=pk)
    next_url = _inventory_return_url(request)

    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "Admin reconcile requires staff.")
        return redirect(next_url)

    if request.method == "POST":
        try:
            reconcile_lot(
                request.user,
                lot,
                request.POST.get("quantity_remaining"),
                reason=(request.POST.get("reason") or "").strip(),
            )
            messages.success(request, f"Reconciled lot {lot.lot_number}.")
            return redirect(next_url)
        except LotFlowError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "slurp_ui/inventory/lot_reconcile.html",
        _inventory_ctx(
            active_tab="inventory",
            lot=lot,
            next_url=next_url,
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def inventory_reverse_check_in(request: HttpRequest) -> HttpResponse:
    # Eligible: unused received lots still at full quantity
    eligible = (
        Lot.objects.select_related("item")
        .filter(quantity_remaining__gt=0, po_number__isnull=False)
        .exclude(po_number="")
        .order_by("-received_date")[:200]
    )
    eligible = [lot for lot in eligible if abs(float(lot.quantity_remaining) - float(lot.quantity)) < 1e-6]

    if request.method == "POST":
        lot_id = request.POST.get("lot_id")
        try:
            lot = get_object_or_404(Lot, pk=lot_id)
            info = reverse_check_in(lot)
            messages.success(
                request,
                f"Reversed check-in for lot {info.get('lot_number')} "
                f"({info.get('quantity')} {info.get('item_sku')}).",
            )
            return redirect("slurp_ui:inventory_reverse_check_in")
        except BuyFlowError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "slurp_ui/inventory/reverse_check_in.html",
        _inventory_ctx(
            active_tab="inventory",
            eligible_lots=eligible,
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def inventory_counts(request: HttpRequest) -> HttpResponse:
    """List count sessions; POST creates a new session."""
    if request.method == "POST":
        try:
            session = create_count_session(
                request.user,
                count_type=(request.POST.get("count_type") or "annual_physical").strip(),
                count_date=(request.POST.get("count_date") or "").strip() or None,
                name=(request.POST.get("name") or "").strip(),
                notes=(request.POST.get("notes") or "").strip(),
            )
            messages.success(request, f"Started count {session.session_number}.")
            return redirect("slurp_ui:inventory_count_detail", pk=session.id)
        except InventoryCountError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))

    sessions = list(InventoryCountSession.objects.all()[:50])
    open_session = None
    for s in sessions:
        if s.status in ("draft", "review"):
            p = variance_summary(s)
            s.progress_status = p["progress_status"]
            s.progress_pct = p["progress_pct"]
            s.progress_counted = p["counted_count"]
            s.progress_lines = p["line_count"]
            if open_session is None:
                open_session = s
        elif s.status == "posted":
            s.progress_status = "complete"
            s.progress_pct = 100
            s.progress_counted = None
            s.progress_lines = None
        else:
            s.progress_status = "not_started"
            s.progress_pct = 0
            s.progress_counted = None
            s.progress_lines = None

    return render(
        request,
        "slurp_ui/inventory/counts.html",
        _inventory_ctx(
            active_tab="counts",
            sessions=sessions,
            open_session=open_session,
            today=timezone.localdate().isoformat(),
            count_type_choices=InventoryCountSession.COUNT_TYPE_CHOICES,
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def inventory_count_detail(request: HttpRequest, pk: int) -> HttpResponse:
    session = get_object_or_404(InventoryCountSession, pk=pk)
    if request.method == "POST":
        action = (request.POST.get("action") or "save_counts").strip()
        try:
            if action == "save_counts":
                if not session.is_editable:
                    raise InventoryCountError("This count is locked.")
                for line in session.lines.all():
                    raw = request.POST.get(f"counted_{line.id}")
                    include = request.POST.get(f"include_{line.id}") == "on"
                    notes = request.POST.get(f"notes_{line.id}")
                    # Only touch lines present in POST (paged future); here all lines
                    if f"counted_{line.id}" in request.POST or f"include_{line.id}" in request.POST:
                        update_count_line(
                            request.user,
                            line,
                            counted_qty=raw if raw is not None else line.counted_qty,
                            include_in_post=include,
                            line_notes=notes if notes is not None else line.line_notes,
                        )
                messages.success(
                    request,
                    "Draft saved. You can leave and resume this count anytime from Physical Counts.",
                )
            elif action == "add_lot":
                add_new_lot_line(
                    request.user,
                    session,
                    item_id=request.POST.get("item_id"),
                    counted_qty=request.POST.get("counted_qty"),
                    vendor_lot_number=request.POST.get("vendor_lot_number") or "",
                    manufacture_date=request.POST.get("manufacture_date") or None,
                    expiration_date=request.POST.get("expiration_date") or None,
                    line_notes=request.POST.get("line_notes") or "",
                )
                messages.success(request, "Added found / beginning-balance line.")
            elif action == "refresh_lots":
                n = refresh_snapshot_missing_lots(session)
                messages.success(request, f"Added {n} open lot(s) missing from this count.")
            elif action == "to_review":
                mark_session_review(request.user, session)
                messages.success(request, "Moved to variance review.")
                return redirect("slurp_ui:inventory_count_variances", pk=session.id)
            elif action == "reopen":
                reopen_session_draft(request.user, session)
                messages.success(request, "Reopened for counting.")
            elif action == "cancel":
                cancel_count_session(request.user, session)
                messages.success(request, f"Cancelled {session.session_number}.")
                return redirect("slurp_ui:inventory_counts")
            else:
                messages.error(request, f"Unknown action: {action}")
        except InventoryCountError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))
        return redirect("slurp_ui:inventory_count_detail", pk=session.id)

    lines = list(session.lines.select_related("item", "lot").all())
    summary = variance_summary(session)
    items = Item.objects.order_by("sku", "vendor")[:800]
    q = (request.GET.get("q") or "").strip().lower()
    if q:
        lines = [
            ln
            for ln in lines
            if q in (ln.sku_snapshot or "").lower()
            or q in (ln.lot_number_snapshot or "").lower()
            or q in (ln.vendor_snapshot or "").lower()
            or q in (ln.item_name_snapshot or "").lower()
        ]
    only_open = request.GET.get("filter") == "uncounted"
    if only_open:
        lines = [ln for ln in lines if ln.counted_qty is None]

    available_lines = [ln for ln in lines if not ln.is_on_hold_line]
    on_hold_lines = [ln for ln in lines if ln.is_on_hold_line]

    return render(
        request,
        "slurp_ui/inventory/count_detail.html",
        _inventory_ctx(
            active_tab="counts",
            session=session,
            lines=lines,
            available_lines=available_lines,
            on_hold_lines=on_hold_lines,
            summary=summary,
            items=items,
            q=request.GET.get("q") or "",
            filter_mode=request.GET.get("filter") or "",
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def inventory_count_variances(request: HttpRequest, pk: int) -> HttpResponse:
    session = get_object_or_404(InventoryCountSession, pk=pk)
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        try:
            if action == "post":
                post_count_session(request.user, session)
                messages.success(
                    request,
                    f"Posted {session.session_number}. Inventory quantities updated (audit only; no GL).",
                )
                return redirect("slurp_ui:inventory_count_variances", pk=session.id)
            if action == "reopen":
                reopen_session_draft(request.user, session)
                messages.success(request, "Reopened for counting.")
                return redirect("slurp_ui:inventory_count_detail", pk=session.id)
            if action == "to_review":
                mark_session_review(request.user, session)
                messages.success(request, "Marked for variance review.")
            else:
                messages.error(request, "Unknown action.")
        except InventoryCountError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))
        return redirect("slurp_ui:inventory_count_variances", pk=session.id)

    summary = variance_summary(session)
    show = (request.GET.get("show") or "variances").strip().lower()
    if show == "all":
        report_lines = summary["lines"]
    elif show == "uncounted":
        report_lines = summary["uncounted_lines"]
    else:
        report_lines = summary["variance_lines"]

    return render(
        request,
        "slurp_ui/inventory/count_variances.html",
        _inventory_ctx(
            active_tab="counts",
            session=session,
            summary=summary,
            report_lines=report_lines,
            show=show,
            port_status="full",
        ),
    )
