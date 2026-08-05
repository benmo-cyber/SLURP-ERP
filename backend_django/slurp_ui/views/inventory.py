from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from django.urls import reverse
from urllib.parse import urlencode

from erp_core.buy_services import (
    BuyFlowError,
    cancel_purchase_order,
    check_in_lot,
    create_purchase_order,
    issue_purchase_order,
    reverse_check_in,
    revise_purchase_order,
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
    Item,
    ItemPackSize,
    Lot,
    LotAttributeChangeLog,
    LotDepletionLog,
    LotTransactionLog,
    ProductionLog,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderLog,
    Vendor,
)
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
    data = {
        "sku": sku,
        "name": name,
        "description": (post.get("description") or name).strip() or None,
        "vendor_item_name": (post.get("vendor_item_name") or "").strip() or None,
        "vendor_item_number": (post.get("vendor_item_number") or "").strip() or None,
        "item_type": post.get("item_type") or getattr(item, "item_type", "raw_material"),
        "unit_of_measure": post.get("unit_of_measure") or getattr(item, "unit_of_measure", "lbs"),
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
    price_raw = (post.get("price") or "").strip()
    if price_raw:
        try:
            data["price"] = float(price_raw)
        except ValueError:
            errors.append("Price must be a number.")
    pack_raw = (post.get("pack_size") or "").strip()
    if pack_raw:
        try:
            data["pack_size"] = float(pack_raw)
        except ValueError:
            errors.append("Pack size must be a number.")
    return data, errors


def _maybe_create_default_pack_size(item, post):
    """Create ItemPackSize from create form when pack_size + unit provided."""
    pack_val = (post.get("pack_size") or "").strip()
    pack_unit = (post.get("pack_size_unit") or post.get("unit_of_measure") or "lbs").strip()
    price_raw = (post.get("price") or "").strip()
    if not pack_val:
        return
    try:
        pack_f = float(pack_val)
    except ValueError:
        return
    price = None
    if price_raw:
        try:
            price = float(price_raw)
        except ValueError:
            pass
    if item.pack_sizes.filter(is_active=True).exists():
        return
    ItemPackSize.objects.create(
        item=item,
        pack_size=pack_f,
        pack_size_unit=pack_unit if pack_unit in dict(ItemPackSize.PACK_SIZE_UNIT_CHOICES) else "lbs",
        price=price,
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
        if is_expanded:
            for v in master.get("vendors") or []:
                vname = v.get("vendor")
                # React uses vendor string; Unknown when empty
                key = vname if vname not in (None, "") else "Unknown"
                v_expanded = expand_vendor is not None and (
                    (expand_vendor == "Unknown" and key == "Unknown")
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
                "vendor_count": master.get("vendor_count") or len(master.get("vendors") or []),
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
    items = Item.objects.all().prefetch_related("pack_sizes")
    if q:
        items = items.filter(Q(sku__icontains=q) | Q(name__icontains=q) | Q(vendor__icontains=q))
    if item_type:
        items = items.filter(item_type=item_type)
    items = items.order_by("sku", "vendor")[:500]
    return render(
        request,
        "slurp_ui/inventory/items.html",
        _inventory_ctx(
            active_tab="items",
            items=items,
            q=q,
            item_type=item_type,
            item_type_choices=Item.ITEM_TYPE_CHOICES,
            port_status="full",
        ),
    )


@login_required
def inventory_purchase_orders(request: HttpRequest) -> HttpResponse:
    pos = (
        PurchaseOrder.objects.prefetch_related(
            Prefetch("items", queryset=PurchaseOrderItem.objects.select_related("item"))
        )
        .order_by("-created_at")[:200]
    )
    return render(
        request,
        "slurp_ui/inventory/purchase_orders.html",
        _inventory_ctx(
            active_tab="purchase-orders",
            purchase_orders=pos,
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
    except BuyFlowError as e:
        messages.error(request, e.message)
    return redirect("slurp_ui:inventory_purchase_orders")


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
def inventory_revise_po(request: HttpRequest, pk: int) -> HttpResponse:
    po = get_object_or_404(PurchaseOrder, pk=pk)
    try:
        new_po = revise_purchase_order(po)
        messages.success(
            request,
            f"Created revision draft {new_po.po_number} (r{new_po.revision_number}).",
        )
    except BuyFlowError as e:
        messages.error(request, e.message)
    except Exception as e:
        messages.error(request, str(e))
    return redirect("slurp_ui:inventory_purchase_orders")


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
            item_id = request.POST.get("item_id")
            payload = {
                "item_id": item_id,
                "quantity": request.POST.get("quantity"),
                "entry_uom": request.POST.get("entry_uom") or "",
                "po_number": po.po_number,
                "vendor_lot_number": request.POST.get("vendor_lot_number") or "",
                "status": request.POST.get("lot_status") or "accepted",
                "received_date": request.POST.get("received_date") or "",
                "expiration_date": request.POST.get("expiration_date") or None,
                "manufacture_date": request.POST.get("manufacture_date") or None,
                "short_reason": request.POST.get("short_reason") or "",
                "carrier": request.POST.get("carrier") or (po.carrier or ""),
                "coa": request.POST.get("coa") == "on",
                "prod_free_pests": request.POST.get("prod_free_pests") == "on",
                "carrier_free_pests": request.POST.get("carrier_free_pests") == "on",
                "shipment_accepted": request.POST.get("shipment_accepted") == "on",
                "initials": request.POST.get("initials") or "",
                "notes": request.POST.get("notes") or "",
                "lot_number": request.POST.get("lot_number") or "",
                "freight_actual": request.POST.get("freight_actual") or None,
            }
            lot = check_in_lot(request.user, payload)
            messages.success(
                request,
                f"Checked in lot {lot.lot_number} — {lot.quantity} {lot.item.unit_of_measure}.",
            )
            return redirect(f"{request.path}?po={po.id}")
        except BuyFlowError as e:
            messages.error(request, e.message)
            selected_po = PurchaseOrder.objects.filter(pk=request.POST.get("po_id")).first()
        except Exception as e:
            messages.error(request, str(e))

    today = timezone.localdate().isoformat()
    return render(
        request,
        "slurp_ui/inventory/check_in.html",
        _inventory_ctx(
            active_tab="inventory",
            issued_pos=issued_pos,
            selected_po=selected_po,
            today=today,
            god_mode=bool(request.session.get("god_mode")) and request.user.is_staff,
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def inventory_create_item(request: HttpRequest) -> HttpResponse:
    vendors = _approved_vendors()
    master_items = (
        Item.objects.exclude(item_type="indirect_material")
        .exclude(sku_parent_code__isnull=True)
        .exclude(sku_parent_code="")
        .order_by("sku_parent_code", "sku")[:300]
    )
    mode = request.POST.get("mode") or request.GET.get("mode") or "new"
    selected_parent = None
    parent_id = request.POST.get("sku_parent_item") or request.GET.get("parent")
    if parent_id:
        selected_parent = Item.objects.filter(pk=parent_id).first()

    if request.method == "POST":
        action = request.POST.get("action") or "create"
        if action == "create":
            data, errors = _item_from_post(request.POST)
            if mode == "add-vendor":
                existing_sku = (request.POST.get("existing_sku") or "").strip().upper()
                if existing_sku:
                    data["sku"] = existing_sku
                    ref = Item.objects.filter(sku=existing_sku).first()
                    if ref and not data.get("name"):
                        data["name"] = ref.name
            if errors:
                for e in errors:
                    messages.error(request, e)
            else:
                serializer = ItemSerializer(data=data)
                if serializer.is_valid():
                    item = serializer.save()
                    _maybe_create_default_pack_size(item, request.POST)
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
            mode=mode,
            selected_parent=selected_parent,
            item_type_choices=Item.ITEM_TYPE_CHOICES,
            product_category_choices=Item.PRODUCT_CATEGORY_CHOICES,
            pack_unit_choices=ItemPackSize.PACK_SIZE_UNIT_CHOICES,
            uom_choices=Item.UNIT_CHOICES,
            port_status="full",
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
            item_type_choices=Item.ITEM_TYPE_CHOICES,
            product_category_choices=Item.PRODUCT_CATEGORY_CHOICES,
            pack_unit_choices=ItemPackSize.PACK_SIZE_UNIT_CHOICES,
            uom_choices=Item.UNIT_CHOICES,
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def inventory_create_po(request: HttpRequest) -> HttpResponse:
    vendors = Vendor.objects.order_by("name")
    items = Item.objects.exclude(item_type="finished_good").order_by("sku")[:500]

    if request.method == "POST":
        try:
            line_count = int(request.POST.get("line_count") or 0)
        except ValueError:
            line_count = 0
        lines = []
        for i in range(line_count):
            item_id = request.POST.get(f"item_id_{i}")
            qty = request.POST.get(f"quantity_{i}")
            if not item_id or not qty:
                continue
            try:
                q = float(qty)
            except ValueError:
                continue
            if q <= 0:
                continue
            lines.append(
                {
                    "item_id": int(item_id),
                    "quantity": q,
                    "unit_cost": float(request.POST.get(f"unit_cost_{i}") or 0),
                    "order_uom": (request.POST.get(f"order_uom_{i}") or "").strip() or None,
                    "notes": request.POST.get(f"notes_{i}") or "",
                }
            )
        payload = {
            "vendor_id": request.POST.get("vendor_id"),
            "required_date": request.POST.get("required_date") or None,
            "expected_delivery_date": request.POST.get("required_date") or None,
            "shipping_terms": request.POST.get("shipping_terms") or "",
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

        # Snapshot vendor address fields if available
        try:
            v = Vendor.objects.get(pk=payload["vendor_id"])
            payload["vendor_address"] = v.street_address or v.address or ""
            payload["vendor_city"] = v.city or ""
            payload["vendor_state"] = v.state or ""
            payload["vendor_zip"] = v.zip_code or ""
            payload["vendor_country"] = v.country or ""
        except (Vendor.DoesNotExist, ValueError, TypeError):
            pass

        try:
            po = create_purchase_order(request.user, payload)
            messages.success(request, f"Created draft PO {po.po_number}.")
            return redirect("slurp_ui:inventory_purchase_orders")
        except BuyFlowError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "slurp_ui/inventory/create_po.html",
        _inventory_ctx(
            active_tab="purchase-orders",
            vendors=vendors,
            items=items,
            god_mode=bool(request.session.get("god_mode")) and request.user.is_staff,
            today=timezone.localdate().isoformat(),
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
            put_on_hold(lot, qty)
            messages.success(request, f"Put {qty} on hold for lot {lot.lot_number}.")
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
