from calendar import monthrange
from datetime import date, datetime, timedelta
import json
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import Count, Prefetch, Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.views.decorators.http import require_http_methods, require_POST

from erp_core.lot_display_quantities import compute_lot_quantity_breakdown
from erp_core.pack_display import pack_quantity_breakdown, resolve_pack_size
from erp_core.models import (
    AccountsPayable,
    AccountsReceivable,
    CampaignLot,
    Customer,
    CustomerContact,
    CustomerCoaRequirement,
    CustomerForecast,
    CustomerPricing,
    CustomerQuote,
    CustomerQuoteItem,
    Item,
    Lot,
    ProductionBatch,
    ProductionBatchOutput,
    PurchaseOrder,
    QuoteNumberSequence,
    SalesCall,
    SalesOrder,
    SalesOrderItem,
    ShipToLocation,
    Shipment,
    CustomerRma,
    Invoice,
)
from erp_core.rma_services import open_customer_rma, shipped_lot_quantities_for_so
from erp_core.sell_services import (
    SellFlowError,
    allocate_sales_order,
    cancel_sales_order,
    combined_ship_sales_orders,
    create_sales_order,
    issue_sales_order,
    mark_shipment_picked_up,
    revert_sales_order_to_draft,
    reverse_sales_shipment,
    ship_sales_order,
)

from erp_core.views import generate_customer_id

from ..nav import SALES_NAV


def _sales_ctx(**extra):
    ctx = {
        "module": "sales",
        "sidebar_nav": SALES_NAV,
        "page_css": [
            "Sales.css",
            "SalesWorkspace.css",
            "CRMDashboard.css",
            "SalesOrdersList.css",
            "CreateSalesOrder.css",
            "CustomerProfile.css",
            "CustomerManagement.css",
            "Calendar.css",
            "CreateShipToLocation.css",
            "CreateContact.css",
            "CreateSalesCall.css",
            "CreateForecast.css",
            "CreateCustomerPricing.css",
        ],
    }
    ctx.update(extra)
    return ctx


IN_HOUSE_SO_STATUSES = ("draft", "issued", "allocated", "ready_for_shipment")
SHIPPED_SO_STATUSES = ("shipped", "completed", "received")


def _so_allocated_lots_prefetch():
    from erp_core.models import SalesOrderLot

    return Prefetch(
        "items__allocated_lots",
        queryset=SalesOrderLot.objects.select_related(
            "lot", "lot__coa_certificate"
        ).prefetch_related("coa_customer_copies"),
    )


def _annotate_so_coa_docs(orders) -> None:
    """Attach coa_copies / coa_master_certs for document links (view-only)."""
    from erp_core.coa_allocation import (
        consolidate_customer_coas_for_sales_order,
        current_customer_coa,
    )

    for o in orders:
        o.coa_copies = []
        o.coa_master_certs = []
        try:
            o.coa_copies = consolidate_customer_coas_for_sales_order(o)
        except Exception:
            seen_copy = set()
            for line in o.items.all():
                for al in line.allocated_lots.all():
                    copy = current_customer_coa(al)
                    if copy and copy.id not in seen_copy:
                        seen_copy.add(copy.id)
                        o.coa_copies.append(copy)
        from erp_core.coa_allocation import customer_coa_button_label

        for copy in o.coa_copies:
            copy.button_label = customer_coa_button_label(copy)
        if o.coa_copies:
            continue
        seen_cert = set()
        for line in o.items.all():
            for al in line.allocated_lots.all():
                cert = getattr(al.lot, "coa_certificate", None) if al.lot_id else None
                if cert and cert.id not in seen_cert:
                    seen_cert.add(cert.id)
                    o.coa_master_certs.append(cert)


def fulfilled_sales_orders_qs(base=None):
    """
    Fulfilled SOs for Order Archive + customer history.

    Status shipped/completed/received, or actual_ship_date set (pickup done even
    if status lagged, e.g. partial / drop-ship).
    """
    qs = base if base is not None else SalesOrder.objects.all()
    return qs.filter(
        models.Q(status__in=SHIPPED_SO_STATUSES)
        | models.Q(actual_ship_date__isnull=False)
    ).distinct()


def _customer_queryset(active_filter=None):
    qs = Customer.objects.annotate(
        ship_to_locations_count=Count("ship_to_locations", filter=models.Q(ship_to_locations__is_active=True)),
        contacts_count=Count("contacts", filter=models.Q(contacts__is_active=True)),
        open_orders_count=Count(
            "sales_orders",
            filter=models.Q(sales_orders__status__in=IN_HOUSE_SO_STATUSES),
            distinct=True,
        ),
    ).order_by("name")
    if active_filter == "true":
        qs = qs.filter(is_active=True)
    elif active_filter == "false":
        qs = qs.filter(is_active=False)
    return qs


def _customer_usage_rows(customer, *, year=None):
    """YTD shipped qty + open/in-house remaining qty by SKU."""
    today = timezone.localdate()
    year = year or today.year
    ytd_start = date(year, 1, 1)
    ytd_end = date(year, 12, 31)

    # Shipped qty attributed to calendar year via ship date when present, else order date.
    shipped_items = (
        SalesOrderItem.objects.filter(sales_order__customer=customer)
        .filter(quantity_shipped__gt=0)
        .filter(
            models.Q(sales_order__actual_ship_date__date__gte=ytd_start, sales_order__actual_ship_date__date__lte=ytd_end)
            | models.Q(
                sales_order__actual_ship_date__isnull=True,
                sales_order__order_date__date__gte=ytd_start,
                sales_order__order_date__date__lte=ytd_end,
            )
        )
        .values("item_id", "item__sku", "item__name")
        .annotate(ytd_shipped=Sum("quantity_shipped"))
    )
    in_house = (
        SalesOrderItem.objects.filter(
            sales_order__customer=customer,
            sales_order__status__in=IN_HOUSE_SO_STATUSES,
        )
        .values("item_id", "item__sku", "item__name")
        .annotate(
            in_house_ordered=Sum("quantity_ordered"),
            in_house_shipped=Sum("quantity_shipped"),
            in_house_allocated=Sum("quantity_allocated"),
        )
    )
    by_item = {}
    for row in shipped_items:
        by_item[row["item_id"]] = {
            "sku": row["item__sku"],
            "name": row["item__name"],
            "ytd_shipped": float(row["ytd_shipped"] or 0),
            "in_house_open": 0.0,
            "in_house_allocated": 0.0,
        }
    for row in in_house:
        open_qty = float(row["in_house_ordered"] or 0) - float(row["in_house_shipped"] or 0)
        if open_qty < 0:
            open_qty = 0.0
        entry = by_item.setdefault(
            row["item_id"],
            {
                "sku": row["item__sku"],
                "name": row["item__name"],
                "ytd_shipped": 0.0,
                "in_house_open": 0.0,
                "in_house_allocated": 0.0,
            },
        )
        entry["in_house_open"] = open_qty
        entry["in_house_allocated"] = float(row["in_house_allocated"] or 0)
    return sorted(
        by_item.values(),
        key=lambda r: (-(r["ytd_shipped"] + r["in_house_open"]), r["sku"] or ""),
    )[:100]


def _generate_quote_number():
    yy = timezone.localdate().strftime("%y")
    seq, _ = QuoteNumberSequence.objects.get_or_create(year_prefix=yy, defaults={"sequence_number": 0})
    QuoteNumberSequence.objects.filter(pk=seq.pk).update(sequence_number=models.F("sequence_number") + 1)
    seq.refresh_from_db()
    return f"Q-{yy}{seq.sequence_number:04d}"


def _customer_initials(customer):
    name = (customer.name or "?").strip()
    parts = [p for p in name.split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _customer_from_post(post, *, customer=None):
    errors = []
    name = (post.get("name") or "").strip()
    if not name:
        errors.append("Customer name is required.")
    bill_same = bool(post.get("bill_to_same_as_hq"))
    data = {
        "name": name,
        "contact_name": (post.get("contact_name") or "").strip() or None,
        "email": (post.get("email") or "").strip() or None,
        "phone": (post.get("phone") or "").strip() or None,
        "address": (post.get("address") or "").strip() or None,
        "city": (post.get("city") or "").strip() or None,
        "state": (post.get("state") or "").strip() or None,
        "zip_code": (post.get("zip_code") or "").strip() or None,
        "country": (post.get("country") or "USA").strip() or "USA",
        "payment_terms": (post.get("payment_terms") or "").strip() or None,
        "notes": (post.get("notes") or "").strip() or None,
        "is_active": post.get("is_active") != "off" if "is_active" in post else True,
    }
    if bill_same:
        data["bill_to_address"] = data["address"]
        data["bill_to_city"] = data["city"]
        data["bill_to_state"] = data["state"]
        data["bill_to_zip_code"] = data["zip_code"]
        data["bill_to_country"] = data["country"]
    else:
        data["bill_to_address"] = (post.get("bill_to_address") or "").strip() or None
        data["bill_to_city"] = (post.get("bill_to_city") or "").strip() or None
        data["bill_to_state"] = (post.get("bill_to_state") or "").strip() or None
        data["bill_to_zip_code"] = (post.get("bill_to_zip_code") or "").strip() or None
        data["bill_to_country"] = (post.get("bill_to_country") or "").strip() or None
    return data, errors


def _fetch_calendar_events(start_date, end_date, event_types):
    """Mirror CalendarEventsViewSet.events for server-rendered calendar."""
    from datetime import datetime

    events = []
    type_set = set(event_types or [])

    if "shipments" in type_set:
        start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time())) if start_date else None
        end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time())) if end_date else None
        shipments = SalesOrder.objects.filter(
            status__in=["draft", "allocated", "ready_for_shipment", "issued", "shipped", "received", "completed"]
        ).exclude(status="cancelled").exclude(expected_ship_date__isnull=True)
        if start_dt:
            shipments = shipments.filter(
                models.Q(actual_ship_date__gte=start_dt) | models.Q(expected_ship_date__gte=start_dt)
            )
        if end_dt:
            shipments = shipments.filter(
                models.Q(actual_ship_date__lte=end_dt) | models.Q(expected_ship_date__lte=end_dt)
            )
        for so in shipments.select_related("customer"):
            ship_date = (
                so.expected_ship_date.date()
                if so.expected_ship_date
                else (so.actual_ship_date.date() if so.actual_ship_date else None)
            )
            if not ship_date:
                continue
            awaiting_pickup = so.status == "ready_for_shipment"
            needs_ready = so.status in ("issued", "allocated")
            needs_allocation = so.status == "draft"
            is_actual = so.status in ("shipped", "completed") and so.actual_ship_date is not None
            if awaiting_pickup:
                title = f"Awaiting pickup: {so.so_number}"
            elif needs_ready:
                title = f"Mark Ready: {so.so_number}"
            elif needs_allocation:
                title = f"Allocate & Ship: {so.so_number}"
            elif is_actual:
                title = f"Ship: {so.so_number}"
            else:
                title = f"Ship (Expected): {so.so_number}"
            cust = so.customer_name or (so.customer.name if so.customer_id else "")
            events.append(
                {
                    "id": f"shipment_{so.id}",
                    "type": "shipment",
                    "type_label": "Ship",
                    "title": title,
                    "short_label": f"Ship · {so.so_number}",
                    "subtitle": cust,
                    "date": ship_date.isoformat(),
                    "sales_order_id": so.id,
                    "sales_order_number": so.so_number,
                    "customer_name": cust,
                    "status": so.status,
                    "reschedulable": so.status not in ("shipped", "completed", "cancelled"),
                }
            )

    if "raw_materials" in type_set:
        lots = Lot.objects.filter(status="accepted").select_related("item")
        if start_date:
            lots = lots.filter(received_date__gte=timezone.make_aware(datetime.combine(start_date, datetime.min.time())))
        if end_date:
            lots = lots.filter(received_date__lte=timezone.make_aware(datetime.combine(end_date, datetime.max.time())))
        for lot in lots[:300]:
            if not lot.received_date:
                continue
            item = lot.item
            sku = item.sku if item else ""
            qty = float(lot.quantity or 0)
            uom = (item.unit_of_measure if item else None) or "lbs"
            short = f"In · {sku or lot.lot_number} · {qty:g} {uom}" if sku else f"In · {lot.lot_number}"
            events.append(
                {
                    "id": f"raw_material_{lot.id}",
                    "type": "raw_material",
                    "type_label": "Inbound",
                    "title": f"Inbound: {sku or lot.lot_number}",
                    "short_label": short,
                    "subtitle": lot.lot_number,
                    "date": lot.received_date.date().isoformat(),
                    "lot_id": lot.id,
                    "product_sku": sku,
                    "product_name": item.name if item else "",
                    "quantity": qty,
                    "unit": uom,
                    "quantity_label": f"{qty:g} {uom}",
                    "reschedulable": False,
                }
            )

    if "production" in type_set:
        # Open production tickets only (ops planning). Closed/archived stay off the calendar.
        batches = (
            ProductionBatch.objects.filter(
                batch_type="production",
                is_archived=False,
                status__in=["draft", "scheduled", "in_progress"],
            )
            .select_related("finished_good_item")
        )
        if start_date:
            batches = batches.filter(
                production_date__gte=timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
            )
        if end_date:
            batches = batches.filter(
                production_date__lte=timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
            )
        for batch in batches:
            fg = batch.finished_good_item
            sku = fg.sku if fg else ""
            name = fg.name if fg else ""
            uom = "lbs"
            qty = float(batch.quantity_produced or 0)
            qty_label = f"{qty:g} {uom}"
            product_label = sku or name or "FG"
            short_label = f"Make · {product_label} · {qty_label}"
            title = f"Production: {product_label}: {qty_label} ({batch.batch_number})"
            events.append(
                {
                    "id": f"production_{batch.id}",
                    "type": "production",
                    "type_label": "Production",
                    "title": title,
                    "short_label": short_label,
                    "subtitle": name if sku and name and name != sku else batch.batch_number,
                    "date": batch.production_date.date().isoformat(),
                    "batch_id": batch.id,
                    "batch_number": batch.batch_number,
                    "product_sku": sku,
                    "product_name": name,
                    "quantity": qty,
                    "unit": uom,
                    "quantity_label": qty_label,
                    "status": batch.status,
                    "reschedulable": batch.status in ("draft", "scheduled", "in_progress"),
                }
            )

    if "repacks" in type_set:
        repacks = (
            ProductionBatch.objects.filter(
                batch_type="repack",
                is_archived=False,
                status__in=["draft", "scheduled", "in_progress"],
            )
            .select_related("finished_good_item")
        )
        if start_date:
            repacks = repacks.filter(
                production_date__gte=timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
            )
        if end_date:
            repacks = repacks.filter(
                production_date__lte=timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
            )
        for batch in repacks:
            fg = batch.finished_good_item
            sku = fg.sku if fg else ""
            name = fg.name if fg else ""
            uom = (fg.unit_of_measure if fg else None) or "lbs"
            qty = float(batch.quantity_produced or 0)
            qty_label = f"{qty:g} {uom}"
            product_label = sku or name or "FG"
            short_label = f"Repack · {product_label} · {qty_label}"
            title = f"Repack: {product_label}: {qty_label} ({batch.batch_number})"
            events.append(
                {
                    "id": f"repack_{batch.id}",
                    "type": "repack",
                    "type_label": "Repack",
                    "title": title,
                    "short_label": short_label,
                    "subtitle": name if sku and name and name != sku else batch.batch_number,
                    "date": batch.production_date.date().isoformat(),
                    "batch_id": batch.id,
                    "batch_number": batch.batch_number,
                    "product_sku": sku,
                    "product_name": name,
                    "quantity": qty,
                    "unit": uom,
                    "quantity_label": qty_label,
                    "status": batch.status,
                    "reschedulable": batch.status in ("draft", "scheduled", "in_progress"),
                }
            )

    if "receivables" in type_set:
        ar_qs = AccountsReceivable.objects.filter(status__in=["open", "partial"]).exclude(due_date__isnull=True)
        if start_date:
            ar_qs = ar_qs.filter(due_date__gte=start_date)
        if end_date:
            ar_qs = ar_qs.filter(due_date__lte=end_date)
        for ar in ar_qs[:200]:
            events.append(
                {
                    "id": f"receivable_{ar.id}",
                    "type": "receivable",
                    "title": f"AR due: {ar.customer_name} - ${ar.balance:,.2f}",
                    "date": ar.due_date.isoformat(),
                    "reschedulable": False,
                }
            )

    if "payables" in type_set:
        ap_qs = AccountsPayable.objects.filter(status__in=["open", "partial"]).exclude(due_date__isnull=True)
        if start_date:
            ap_qs = ap_qs.filter(due_date__gte=start_date)
        if end_date:
            ap_qs = ap_qs.filter(due_date__lte=end_date)
        for ap in ap_qs[:200]:
            events.append(
                {
                    "id": f"payable_{ap.id}",
                    "type": "payable",
                    "title": f"AP due: {ap.vendor_name} - ${ap.balance:,.2f}",
                    "date": ap.due_date.isoformat(),
                    "reschedulable": False,
                }
            )

    events.sort(key=lambda x: x["date"])
    return events


def _calendar_month_grid(month_anchor: date, events: list) -> dict:
    """Build month grid weeks for server-rendered calendar (Sunday-start, no drag)."""
    year, month = month_anchor.year, month_anchor.month
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    grid_start = first - timedelta(days=(first.weekday() + 1) % 7)
    grid_end = last + timedelta(days=(6 - ((last.weekday() + 1) % 7)) % 7)

    by_date: dict[str, list] = {}
    for ev in events:
        by_date.setdefault(ev["date"], []).append(ev)

    today = timezone.localdate()
    weeks = []
    day = grid_start
    while day <= grid_end:
        week = []
        for _ in range(7):
            day_events = by_date.get(day.isoformat(), [])
            week.append(
                {
                    "date": day,
                    "in_month": day.month == month,
                    "is_today": day == today,
                    "events": day_events[:4],
                    "more_count": max(0, len(day_events) - 4),
                    "total_count": len(day_events),
                }
            )
            day += timedelta(days=1)
        weeks.append(week)

    prev_month = (first - timedelta(days=1)).replace(day=1)
    next_month = (last + timedelta(days=1)).replace(day=1)
    return {
        "weeks": weeks,
        "month_label": first.strftime("%B %Y"),
        "prev_month": prev_month,
        "next_month": next_month,
    }


@login_required
def sales_crm(request: HttpRequest) -> HttpResponse:
    q = (request.GET.get("q") or "").strip()
    active_filter = request.GET.get("active") or "true"
    filter_arg = None if active_filter == "all" else active_filter
    customers = _customer_queryset(filter_arg)
    if q:
        customers = customers.filter(
            models.Q(name__icontains=q)
            | models.Q(customer_id__icontains=q)
            | models.Q(email__icontains=q)
            | models.Q(city__icontains=q)
            | models.Q(phone__icontains=q)
        )
    customers = list(customers[:200])
    for c in customers:
        c.initials = _customer_initials(c)

    open_order_total = SalesOrder.objects.filter(status__in=IN_HOUSE_SO_STATUSES).count()
    ready_count = SalesOrder.objects.filter(status="ready_for_shipment").count()
    active_customers = Customer.objects.filter(is_active=True).count()
    needs_attention = (
        SalesOrder.objects.filter(status__in=("issued", "allocated", "ready_for_shipment"))
        .select_related("customer")
        .order_by("-updated_at")[:8]
    )
    return render(
        request,
        "slurp_ui/sales/crm.html",
        _sales_ctx(
            active_tab="customers",
            customers=customers,
            q=q,
            active_filter=active_filter,
            open_order_total=open_order_total,
            ready_count=ready_count,
            active_customers=active_customers,
            needs_attention=needs_attention,
            port_status="full",
        ),
    )


def _order_fulfillment_flow(order) -> dict:
    """
    Compact process strip for the workqueue Process column.

    Mirrors page hint: Allocate → Pick / Mark Ready → Mark picked up → Issue invoice.
    Current step = next handoff (shipping users stop before Issue invoice).
    """
    steps_meta = (
        ("allocate", "Allocate"),
        ("ready", "Mark Ready"),
        ("pickup", "Mark picked up"),
        ("invoice", "Issue invoice"),
    )
    status = (order.status or "").strip()
    if status == "cancelled":
        return {
            "mode": "cancelled",
            "label": "Cancelled",
            "current": None,
            "steps": [
                {"key": k, "label": lab, "state": "todo"} for k, lab in steps_meta
            ],
        }
    if status == "draft":
        return {
            "mode": "draft",
            "label": "Draft — issue order first",
            "current": None,
            "steps": [
                {"key": k, "label": lab, "state": "todo"} for k, lab in steps_meta
            ],
        }

    ready_sh = getattr(order, "ready_shipment", None)
    picked_up = bool(getattr(order, "has_picked_up_shipment", False))
    draft_inv = getattr(order, "draft_invoice", None)
    total_alloc = float(getattr(order, "total_allocated", 0) or 0)
    drop_ship = bool(getattr(order, "drop_ship", False))
    terminal = status in ("shipped", "completed", "received")

    # Shipping complete once picked up (or terminal / draft invoice exists from pickup).
    shipping_done = bool(picked_up or terminal or draft_inv)

    if shipping_done and terminal and not draft_inv:
        current = "invoice"
        all_done = True
    elif shipping_done:
        current = "invoice"
        all_done = False
    elif ready_sh:
        current = "pickup"
        all_done = False
    elif drop_ship or total_alloc > 0 or status in ("allocated", "ready_for_shipment"):
        current = "ready"
        all_done = False
    else:
        current = "allocate"
        all_done = False

    order_keys = [k for k, _ in steps_meta]
    cur_i = order_keys.index(current)
    steps = []
    for i, (key, lab) in enumerate(steps_meta):
        if all_done or i < cur_i:
            state = "done"
        elif i == cur_i:
            state = "current"
        else:
            state = "todo"
        # After allocate: bold the pick + stage handoff (not for drop-ship).
        display = lab
        if key == "ready" and state == "current" and not drop_ship:
            display = "Pick, then Mark Ready"
        steps.append({"key": key, "label": display, "state": state})

    if all_done:
        label = "Complete"
    elif current == "invoice":
        label = "Shipping done — invoice in Finance"
    elif current == "pickup":
        label = "Awaiting pickup"
    elif current == "ready":
        label = (
            "Next: Mark Ready"
            if drop_ship
            else "Next: Pick, then Mark Ready"
        )
    else:
        label = "Next: Allocate"

    return {
        "mode": "flow",
        "label": label,
        "current": current,
        "steps": steps,
    }


@login_required
def sales_orders(request: HttpRequest) -> HttpResponse:
    from erp_core.models import Invoice, SalesOrderLot, Shipment

    # Legacy: allocate used to set ready_for_shipment without a Ready shipment.
    # Those are still allocated — Mark Ready (pieces/dims) is the next step.
    ready_exists = Shipment.objects.filter(
        sales_order_id=models.OuterRef("pk"),
        fulfillment_status="ready",
    )
    SalesOrder.objects.filter(status="ready_for_shipment").annotate(
        _has_ready=models.Exists(ready_exists)
    ).filter(_has_ready=False).update(status="allocated")

    queue = (request.GET.get("queue") or "open").strip()
    q = (request.GET.get("q") or "").strip()
    focus = (request.GET.get("focus") or "").strip()
    sort = (request.GET.get("sort") or "exp_ship").strip()
    qs = (
        SalesOrder.objects.select_related("customer")
        .prefetch_related(
            "items__item",
            "shipments",
            Prefetch(
                "items__allocated_lots",
                queryset=SalesOrderLot.objects.select_related(
                    "lot", "lot__coa_certificate"
                ).prefetch_related("coa_customer_copies"),
            ),
        )
        .annotate(total_allocated=Sum("items__quantity_allocated"))
    )
    queue_map = {
        "open": list(IN_HOUSE_SO_STATUSES),
        "draft": ["draft"],
        "issue": ["draft"],
        "allocate": ["issued", "allocated"],
        "ship": ["issued", "ready_for_shipment", "allocated"],
        "done": ["shipped", "completed", "received"],
        "all": None,
    }
    statuses = queue_map.get(queue, queue_map["open"])
    if statuses is not None:
        qs = qs.filter(status__in=statuses)
    if queue == "ship":
        qs = qs.filter(status__in=("issued", "ready_for_shipment", "allocated"))
    if q:
        qs = qs.filter(
            models.Q(so_number__icontains=q)
            | models.Q(customer_name__icontains=q)
            | models.Q(customer_reference_number__icontains=q)
            | models.Q(customer__name__icontains=q)
        )

    today = timezone.localdate()
    week_end = today + timedelta(days=7)
    open_base = SalesOrder.objects.filter(status__in=IN_HOUSE_SO_STATUSES)
    awaiting_qs = SalesOrder.objects.filter(status="ready_for_shipment").filter(
        shipments__fulfillment_status="ready"
    ).distinct()
    need_inv_ids = set(
        Invoice.objects.filter(
            invoice_type="customer",
            status="draft",
            sales_order_id__isnull=False,
        ).values_list("sales_order_id", flat=True)
    )

    kpi = {
        "today": open_base.filter(expected_ship_date__date=today).count(),
        "week": open_base.filter(
            expected_ship_date__date__gte=today,
            expected_ship_date__date__lte=week_end,
        ).count(),
        "awaiting_pickup": awaiting_qs.count(),
        "need_invoice": SalesOrder.objects.filter(id__in=need_inv_ids).count() if need_inv_ids else 0,
        "open": open_base.count(),
    }

    if focus == "today":
        qs = qs.filter(status__in=IN_HOUSE_SO_STATUSES, expected_ship_date__date=today)
        queue = "open"
    elif focus == "week":
        qs = qs.filter(
            status__in=IN_HOUSE_SO_STATUSES,
            expected_ship_date__date__gte=today,
            expected_ship_date__date__lte=week_end,
        )
        queue = "open"
    elif focus == "awaiting_pickup":
        qs = qs.filter(status="ready_for_shipment", shipments__fulfillment_status="ready").distinct()
        queue = "open"
    elif focus == "need_invoice":
        qs = qs.filter(id__in=need_inv_ids) if need_inv_ids else qs.none()
        queue = "all"
    elif focus == "missing_ship":
        qs = qs.filter(status__in=IN_HOUSE_SO_STATUSES, expected_ship_date__isnull=True)
        queue = "open"
    elif focus == "overdue_crd":
        qs = qs.filter(
            status__in=IN_HOUSE_SO_STATUSES,
            customer_required_date__isnull=False,
            customer_required_date__lt=today,
        )
        queue = "open"

    if sort == "customer":
        qs = qs.order_by("customer_name", models.F("expected_ship_date").asc(nulls_last=True))
    elif sort == "crd":
        qs = qs.order_by(
            models.F("customer_required_date").asc(nulls_last=True),
            models.F("expected_ship_date").asc(nulls_last=True),
        )
    elif sort == "status":
        qs = qs.order_by("status", models.F("expected_ship_date").asc(nulls_last=True))
    elif sort == "newest":
        qs = qs.order_by("-created_at", "-id")
    elif sort == "oldest":
        qs = qs.order_by("created_at", "id")
    else:
        # Default / exp_ship
        qs = qs.order_by(
            models.F("expected_ship_date").asc(nulls_last=True),
            models.F("customer_required_date").asc(nulls_last=True),
            "-created_at",
        )

    orders = list(qs[:200])
    # Annotate ready / picked-up shipments + draft invoice + COA docs for actions
    for o in orders:
        ready_sh = next(
            (s for s in o.shipments.all() if s.fulfillment_status == "ready"),
            None,
        )
        o.ready_shipment = ready_sh
        o.has_picked_up_shipment = any(
            (s.fulfillment_status or "") == "picked_up" for s in o.shipments.all()
        )
        o.draft_invoice = None
        o.coa_copies = []
        o.coa_master_certs = []
        o.coa_missing_lots = []
        from erp_core.coa_allocation import (
            consolidate_customer_coas_for_sales_order,
            current_customer_coa,
            customer_coa_button_label,
        )

        try:
            o.coa_copies = consolidate_customer_coas_for_sales_order(o)
        except Exception:
            o.coa_copies = []
            for line in o.items.all():
                for al in line.allocated_lots.all():
                    copy = current_customer_coa(al)
                    if copy:
                        o.coa_copies.append(copy)
        for copy in o.coa_copies:
            copy.button_label = customer_coa_button_label(copy)
        if not o.coa_copies:
            seen_cert = set()
            seen_missing = set()
            for line in o.items.all():
                for al in line.allocated_lots.all():
                    cert = getattr(al.lot, "coa_certificate", None) if al.lot_id else None
                    if cert and cert.id not in seen_cert:
                        seen_cert.add(cert.id)
                        o.coa_master_certs.append(cert)
                    elif al.lot_id and al.lot_id not in seen_missing and not cert:
                        seen_missing.add(al.lot_id)
                        o.coa_missing_lots.append(al.lot)

    draft_by_so = {
        inv.sales_order_id: inv
        for inv in Invoice.objects.filter(
            sales_order_id__in=[o.id for o in orders],
            invoice_type="customer",
            status="draft",
        )
    }
    for o in orders:
        o.draft_invoice = draft_by_so.get(o.id)
        o.fulfill_flow = _order_fulfillment_flow(o)
        # Allocate / Re-allocate until Mark picked up; Mark Ready only before Ready lock
        o.show_allocate = (
            not o.has_picked_up_shipment
            and not o.draft_invoice
            and o.status in ("issued", "allocated", "ready_for_shipment")
        )
        o.is_reallocate = bool(
            o.show_allocate
            and (
                float(o.total_allocated or 0) > 0
                or o.status in ("allocated", "ready_for_shipment")
                or o.ready_shipment
            )
        )
        o.show_mark_ready = bool(
            not o.ready_shipment
            and not o.has_picked_up_shipment
            and not o.draft_invoice
            and o.status in ("issued", "allocated", "ready_for_shipment")
            and (o.drop_ship or float(o.total_allocated or 0) > 0)
        )
        o.show_mark_picked_up = bool(o.ready_shipment and not o.has_picked_up_shipment)
        o.show_cancel = bool(
            o.status in ("draft", "issued", "allocated", "ready_for_shipment")
            and not o.has_picked_up_shipment
            and not o.draft_invoice
        )

    counts = {
        "open": SalesOrder.objects.filter(status__in=IN_HOUSE_SO_STATUSES).count(),
        "draft": SalesOrder.objects.filter(status="draft").count(),
        "allocate": SalesOrder.objects.filter(status__in=("issued", "allocated")).count(),
        "ship": SalesOrder.objects.filter(status__in=("issued", "ready_for_shipment", "allocated")).count(),
        "done": SalesOrder.objects.filter(status__in=SHIPPED_SO_STATUSES).count(),
        "all": SalesOrder.objects.count(),
    }
    return render(
        request,
        "slurp_ui/sales/orders.html",
        _sales_ctx(
            active_tab="orders",
            orders=orders,
            queue=queue,
            q=q,
            focus=focus,
            sort=sort,
            counts=counts,
            kpi=kpi,
            today=today,
            port_status="full",
            god_mode=bool(request.session.get("god_mode")) and request.user.is_staff,
        ),
    )


@login_required
def sales_order_archive(request: HttpRequest) -> HttpResponse:
    """Fulfilled sales orders: search + year/month folders (by ship date)."""
    from calendar import month_name
    from django.db.models import Count
    from django.db.models.functions import Coalesce, TruncMonth, TruncYear

    q = (request.GET.get("q") or "").strip()
    year_raw = (request.GET.get("year") or "").strip()
    month_raw = (request.GET.get("month") or "").strip()
    year = int(year_raw) if year_raw.isdigit() else None
    month = int(month_raw) if month_raw.isdigit() and 1 <= int(month_raw) <= 12 else None

    base = fulfilled_sales_orders_qs().select_related("customer")
    if q:
        base = base.filter(
            models.Q(so_number__icontains=q)
            | models.Q(customer_name__icontains=q)
            | models.Q(customer__name__icontains=q)
            | models.Q(customer_reference_number__icontains=q)
            | models.Q(notes__icontains=q)
        )

    dated = base.annotate(folder_date=Coalesce("actual_ship_date", "order_date"))

    folders = []
    orders = []
    folder_level = "years"
    crumbs = [{"label": "Order archive", "url_params": {}}]

    def _qp(**extra):
        params = {}
        if q:
            params["q"] = q
        params.update({k: v for k, v in extra.items() if v not in (None, "")})
        return params

    if q and not year and not month:
        orders = list(
            dated.annotate(
                total_shipped=Sum("items__quantity_shipped"),
                total_ordered=Sum("items__quantity_ordered"),
            ).order_by("-folder_date", "-id")[:300]
        )
        folder_level = "list"
        crumbs.append({"label": f'Search “{q}”', "url_params": None})
    elif year and month:
        crumbs.append({"label": str(year), "url_params": _qp(year=year)})
        crumbs.append({"label": month_name[month], "url_params": None})
        orders = list(
            dated.filter(folder_date__year=year, folder_date__month=month)
            .annotate(
                total_shipped=Sum("items__quantity_shipped"),
                total_ordered=Sum("items__quantity_ordered"),
            )
            .order_by("-folder_date", "-id")[:300]
        )
        folder_level = "list"
    elif year:
        crumbs.append({"label": str(year), "url_params": None})
        folder_level = "months"
        rows = (
            dated.filter(folder_date__year=year)
            .annotate(m=TruncMonth("folder_date"))
            .values("m")
            .annotate(count=Count("id", distinct=True))
            .order_by("-m")
        )
        for row in rows:
            m = row["m"]
            if not m:
                continue
            folders.append(
                {
                    "kind": "month",
                    "label": month_name[m.month],
                    "sublabel": str(m.year),
                    "count": row["count"],
                    "url_params": _qp(year=m.year, month=m.month),
                }
            )
    else:
        folder_level = "years"
        rows = (
            dated.annotate(y=TruncYear("folder_date"))
            .values("y")
            .annotate(count=Count("id", distinct=True))
            .order_by("-y")
        )
        for row in rows:
            y = row["y"]
            if not y:
                continue
            folders.append(
                {
                    "kind": "year",
                    "label": str(y.year),
                    "sublabel": None,
                    "count": row["count"],
                    "url_params": _qp(year=y.year),
                }
            )

    return render(
        request,
        "slurp_ui/sales/order_archive.html",
        _sales_ctx(
            active_tab="order-archive",
            q=q,
            year=year,
            month=month,
            folders=folders,
            orders=orders,
            folder_level=folder_level,
            crumbs=crumbs,
            result_count=len(orders),
            port_status="full",
        ),
    )


def _reschedule_ops_event(event_id: str, new_date: date) -> tuple[bool, str]:
    """Move a shipment/production planned date. Returns (ok, message)."""
    if event_id.startswith("shipment_"):
        so_id = event_id.split("_", 1)[1]
        so = get_object_or_404(SalesOrder, pk=so_id)
        if so.status in ("shipped", "completed", "cancelled"):
            return False, f"{so.so_number} cannot be rescheduled ({so.status})."
        old = so.expected_ship_date.date().isoformat() if so.expected_ship_date else "—"
        so.expected_ship_date = timezone.make_aware(datetime.combine(new_date, datetime.min.time()))
        so.save(update_fields=["expected_ship_date"])
        return True, f"Moved {so.so_number} ship date {old} -> {new_date.isoformat()}."
    if event_id.startswith("production_") or event_id.startswith("repack_"):
        batch_id = event_id.split("_", 1)[1]
        batch = get_object_or_404(ProductionBatch, pk=batch_id)
        if batch.status not in ("draft", "scheduled", "in_progress"):
            return False, f"Batch {batch.batch_number} cannot be rescheduled ({batch.status})."
        old = batch.production_date.date().isoformat() if batch.production_date else "—"
        batch.production_date = timezone.make_aware(datetime.combine(new_date, datetime.min.time()))
        batch.save(update_fields=["production_date", "updated_at"])
        return True, f"Moved batch {batch.batch_number} {old} -> {new_date.isoformat()}."
    return False, "This event type cannot be rescheduled from the ops calendar."


@login_required
@require_http_methods(["GET", "POST"])
def sales_calendar(request: HttpRequest) -> HttpResponse:
    today = timezone.localdate()
    month_raw = (request.GET.get("month") or request.POST.get("month") or "").strip()
    month_anchor = parse_date(month_raw + "-01") if month_raw and len(month_raw) >= 7 else today.replace(day=1)

    start_raw = (request.GET.get("start") or request.POST.get("start") or "").strip()
    end_raw = (request.GET.get("end") or request.POST.get("end") or "").strip()
    if start_raw and end_raw:
        start_date = parse_date(start_raw)
        end_date = parse_date(end_raw)
    else:
        year, month = month_anchor.year, month_anchor.month
        start_date = date(year, month, 1)
        end_date = date(year, month, monthrange(year, month)[1])
    if end_date and start_date and end_date < start_date:
        end_date = start_date

    selected_day = parse_date((request.GET.get("day") or "").strip()) if request.GET.get("day") else None

    selected_types = request.GET.getlist("types") or request.POST.getlist("types") or [
        "shipments",
        "raw_materials",
        "production",
    ]
    # Ops calendar only — finance due dates belong on Finance calendar.
    allowed_types = {"shipments", "raw_materials", "production", "repacks"}
    selected_types = [t for t in selected_types if t in allowed_types] or [
        "shipments",
        "raw_materials",
        "production",
    ]
    if request.method == "POST" and request.POST.get("action") == "reschedule":
        event_id = (request.POST.get("event_id") or "").strip()
        new_date_raw = (request.POST.get("new_date") or "").strip()
        new_date = parse_date(new_date_raw)
        wants_json = (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or "application/json" in (request.headers.get("Accept") or "")
        )
        if not event_id or not new_date:
            if wants_json:
                return JsonResponse({"ok": False, "message": "Event and new date are required."}, status=400)
            messages.error(request, "Event and new date are required.")
        else:
            ok, msg = _reschedule_ops_event(event_id, new_date)
            if wants_json:
                return JsonResponse(
                    {"ok": ok, "message": msg, "date": new_date.isoformat() if ok else None},
                    status=200 if ok else 400,
                )
            if ok:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
        qs = urlencode({"month": month_anchor.strftime("%Y-%m")})
        for t in selected_types:
            qs += "&" + urlencode({"types": t})
        return redirect(f"{reverse('slurp_ui:sales_calendar')}?{qs}")

    month_events = _fetch_calendar_events(start_date, end_date, selected_types)
    events = month_events
    if selected_day:
        day_str = selected_day.isoformat()
        events = [e for e in month_events if e["date"] == day_str]

    grid = _calendar_month_grid(month_anchor, month_events)
    selected_event = None
    sel_id = request.GET.get("event")
    if sel_id:
        selected_event = next((e for e in month_events if e["id"] == sel_id), None)

    type_options = [
        ("shipments", "Ships"),
        ("raw_materials", "Inbound"),
        ("production", "Production"),
        ("repacks", "Repacks"),
    ]
    return render(
        request,
        "slurp_ui/sales/calendar.html",
        _sales_ctx(
            active_tab="calendar",
            events=events,
            month_events=month_events,
            start_date=start_date,
            end_date=end_date,
            month_anchor=month_anchor,
            month_param=month_anchor.strftime("%Y-%m"),
            calendar_grid=grid,
            selected_day=selected_day,
            selected_types=selected_types,
            type_options=type_options,
            selected_event=selected_event,
            port_status="full",
        ),
    )


@login_required
def sales_kpis(request: HttpRequest) -> HttpResponse:
    from ..finance_helpers import get_kpis

    try:
        months_back = int(request.GET.get("months_back") or 12)
    except ValueError:
        months_back = 12
    kpis = get_kpis(request.user, months_back)
    return render(
        request,
        "slurp_ui/sales/kpis.html",
        _sales_ctx(active_tab="kpis", kpis=kpis, months_back=months_back, port_status="full"),
    )


@login_required
@require_http_methods(["GET", "POST"])
def sales_customers(request: HttpRequest) -> HttpResponse:
    edit_id = request.GET.get("edit") or request.POST.get("edit_id")
    editing = None
    if edit_id:
        editing = Customer.objects.filter(pk=edit_id).first()

    if request.method == "POST":
        action = request.POST.get("action") or "save"
        if action == "delete":
            cust = get_object_or_404(Customer, pk=request.POST.get("customer_id"))
            if SalesOrder.objects.filter(customer=cust).exists():
                messages.error(request, f"Cannot delete {cust.name}: sales orders exist.")
            else:
                cust.delete()
                messages.success(request, "Customer deleted.")
            return redirect("slurp_ui:sales_customers")
        data, errors = _customer_from_post(request.POST, customer=editing)
        if errors:
            for e in errors:
                messages.error(request, e)
        elif editing:
            for k, v in data.items():
                setattr(editing, k, v)
            editing.save()
            messages.success(request, f"Updated {editing.name}.")
            return redirect("slurp_ui:sales_customer_profile", pk=editing.pk)
        else:
            cid = generate_customer_id()
            customer = Customer.objects.create(customer_id=cid, **data)
            messages.success(request, f"Created customer {customer.name} ({cid}).")
            return redirect("slurp_ui:sales_customer_profile", pk=customer.pk)

    customers = _customer_queryset().order_by("name")[:300]
    return render(
        request,
        "slurp_ui/sales/customers.html",
        _sales_ctx(
            active_tab="customers-manage",
            customers=customers,
            editing=editing,
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def sales_customer_profile(request: HttpRequest, pk: int) -> HttpResponse:
    customer = get_object_or_404(Customer, pk=pk)
    tab = request.GET.get("tab") or request.POST.get("tab") or "glance"
    if request.method == "POST" and request.POST.get("action") == "save_profile":
        data, errors = _customer_from_post(request.POST, customer=customer)
        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            for k, v in data.items():
                setattr(customer, k, v)
            customer.save()
            messages.success(request, "Profile updated.")
            return redirect(f"{reverse('slurp_ui:sales_customer_profile', kwargs={'pk': pk})}?tab={tab}")

    if request.method == "POST" and tab == "coa":
        action = (request.POST.get("action") or "").strip()
        if action == "delete_coa_req":
            req_id = request.POST.get("req_id")
            CustomerCoaRequirement.objects.filter(pk=req_id, customer=customer).delete()
            messages.success(request, "COA requirement removed.")
            item_q = (request.POST.get("item_id") or "").strip()
            q = f"?tab=coa&item={item_q}" if item_q.isdigit() else "?tab=coa"
            return redirect(f"{reverse('slurp_ui:sales_customer_profile', kwargs={'pk': pk})}{q}")
        if action == "save_coa_req":
            item_id = (request.POST.get("item_id") or "").strip()
            test_name = (request.POST.get("test_name") or "").strip()
            raw_item = Item.objects.filter(
                pk=item_id, item_type__in=("finished_good", "distributed_item")
            ).first()
            from erp_core.coa_template import (
                coa_test_lines_for_item,
                resolve_coa_template_item,
            )

            item = resolve_coa_template_item(raw_item) if raw_item else None
            if not item or not test_name:
                messages.error(request, "Select an FPS SKU and test.")
            else:
                fps_line = (
                    coa_test_lines_for_item(item, select_related=("catalog_test",))
                    .filter(test_name__iexact=test_name)
                    .first()
                )
                spec_raw = (request.POST.get("specification_text") or "").strip()
                include_raw = (request.POST.get("include_on_customer_coa") or "").strip()
                # tri-state: "" = FPS default, "1" = yes, "0" = no
                if include_raw == "1":
                    include_val = True
                elif include_raw == "0":
                    include_val = False
                else:
                    include_val = None
                disp = (request.POST.get("customer_result_display") or "").strip()
                if disp not in ("actual", "pass_fail"):
                    disp = ""
                notes = (request.POST.get("notes") or "").strip()[:255]
                # Empty Spec + all defaults → delete existing override
                if not spec_raw and include_val is None and not disp:
                    CustomerCoaRequirement.objects.filter(
                        customer=customer, item=item, test_name__iexact=test_name
                    ).delete()
                    messages.success(request, f"Cleared override for {test_name} (FPS default).")
                else:
                    req, _created = CustomerCoaRequirement.objects.update_or_create(
                        customer=customer,
                        item=item,
                        test_name=fps_line.test_name if fps_line else test_name,
                        defaults={
                            "catalog_test_id": (
                                fps_line.catalog_test_id if fps_line else None
                            ),
                            "specification_text": spec_raw or None,
                            "include_on_customer_coa": include_val,
                            "customer_result_display": disp,
                            "notes": notes,
                            "is_active": True,
                        },
                    )
                    messages.success(
                        request,
                        f"Saved COA requirement for {item.sku} — {req.test_name}.",
                    )
            return redirect(
                f"{reverse('slurp_ui:sales_customer_profile', kwargs={'pk': pk})}"
                f"?tab=coa&item={item.id if item else item_id}"
            )

    pricing = (
        CustomerPricing.objects.filter(customer=customer)
        .select_related("item")
        .order_by("-is_active", "-effective_date")[:100]
    )
    ship_tos = ShipToLocation.objects.filter(customer=customer).order_by("-is_default", "location_name")
    contacts = list(
        CustomerContact.objects.filter(customer=customer).order_by(
            "-is_primary", "-is_ap_contact", "-is_purchasing_contact", "last_name"
        )
    )
    forecasts = (
        CustomerForecast.objects.filter(customer=customer).select_related("item").order_by("-forecast_period")[:100]
    )
    quotes = list(
        CustomerQuote.objects.filter(customer=customer)
        .prefetch_related("lines__item")
        .order_by("-quote_date", "-id")[:100]
    )
    usage_rows = _customer_usage_rows(customer)

    open_orders = list(
        SalesOrder.objects.filter(customer=customer, status__in=IN_HOUSE_SO_STATUSES)
        .prefetch_related("items__item", _so_allocated_lots_prefetch())
        .annotate(
            total_allocated=Sum("items__quantity_allocated"),
            total_ordered=Sum("items__quantity_ordered"),
            total_shipped=Sum("items__quantity_shipped"),
        )
        .order_by("-order_date")[:50]
    )
    recent_shipped = list(
        fulfilled_sales_orders_qs(SalesOrder.objects.filter(customer=customer))
        .prefetch_related("items__item", _so_allocated_lots_prefetch())
        .annotate(
            total_allocated=Sum("items__quantity_allocated"),
            total_ordered=Sum("items__quantity_ordered"),
            total_shipped=Sum("items__quantity_shipped"),
        )
        .order_by("-actual_ship_date", "-order_date")[:50]
    )
    _annotate_so_coa_docs(open_orders)
    _annotate_so_coa_docs(recent_shipped)
    all_customer_orders = list(
        SalesOrder.objects.filter(customer=customer)
        .annotate(
            total_allocated=Sum("items__quantity_allocated"),
            total_ordered=Sum("items__quantity_ordered"),
            total_shipped=Sum("items__quantity_shipped"),
        )
        .order_by("-order_date")[:100]
    )

    # Invoice history for this customer (SO link and/or name match for legacy rows).
    cust_name = (customer.name or "").strip()
    customer_invoices = list(
        Invoice.objects.filter(invoice_type__in=("customer", "credit"))
        .filter(
            models.Q(sales_order__customer_id=customer.id)
            | models.Q(customer_vendor_name__iexact=cust_name)
        )
        .select_related("sales_order")
        .distinct()
        .order_by("-invoice_date", "-id")[:100]
    )

    ops_contacts = [
        c
        for c in contacts
        if c.is_active
        and (
            c.contact_type in ("shipping", "billing", "sales")
            or c.is_ap_contact
            or c.is_purchasing_contact
            or c.is_primary
        )
    ]
    glance_contacts = ops_contacts or [c for c in contacts if c.is_active][:8]

    ytd_shipped_total = sum(r["ytd_shipped"] for r in usage_rows)
    in_house_total = sum(r["in_house_open"] for r in usage_rows)
    active_price_count = sum(1 for p in pricing if p.is_active)
    open_quote_count = sum(1 for q in quotes if q.status in ("draft", "sent", "accepted"))

    tabs = [
        ("glance", "At a glance"),
        ("orders", "Orders"),
        ("invoices", "Invoices"),
        ("payments", "Payments"),
        ("contacts", "Contacts"),
        ("pricing", "Pricing"),
        ("coa", "COA"),
        ("quotes", "Quotes"),
        ("forecast", "Forecast"),
        ("usage", "Usage"),
        ("ship-to", "Ship-to"),
        ("overview", "Account edit"),
    ]
    from ..finance_helpers import customer_payment_timeliness

    # COA requirements tab context — one row per family COA template
    from erp_core.coa_template import (
        coa_test_lines_for_item,
        fps_parent_code,
        resolve_coa_template_item,
    )

    coa_candidates = list(
        Item.objects.filter(item_type__in=("finished_good", "distributed_item"))
        .filter(coa_test_lines__isnull=False)
        .distinct()
        .order_by("sku")[:400]
    )
    # Deduplicate to template items (and include templates even if lines live only there)
    coa_by_parent: dict[str, Item] = {}
    for it in coa_candidates:
        tmpl = resolve_coa_template_item(it) or it
        key = fps_parent_code(tmpl) or (tmpl.sku or str(tmpl.id))
        prev = coa_by_parent.get(key)
        if prev is None or tmpl.id < prev.id:
            coa_by_parent[key] = tmpl
    coa_fps_items = sorted(coa_by_parent.values(), key=lambda x: (x.sku or "").upper())

    coa_item_id = (request.GET.get("item") or "").strip()
    coa_selected_item = None
    coa_fps_lines = []
    coa_req_by_name = {}
    if coa_item_id.isdigit():
        raw = Item.objects.filter(
            pk=int(coa_item_id), item_type__in=("finished_good", "distributed_item")
        ).first()
        if raw:
            coa_selected_item = resolve_coa_template_item(raw) or raw
    if coa_selected_item:
        coa_fps_lines = list(coa_test_lines_for_item(coa_selected_item))
        for req in CustomerCoaRequirement.objects.filter(
            customer=customer, item=coa_selected_item, is_active=True
        ):
            coa_req_by_name[(req.test_name or "").strip().casefold()] = req
    coa_fps_line_rows = []
    for line in coa_fps_lines:
        coa_fps_line_rows.append(
            {
                "line": line,
                "req": coa_req_by_name.get((line.test_name or "").strip().casefold()),
            }
        )
    coa_all_reqs = list(
        CustomerCoaRequirement.objects.filter(customer=customer, is_active=True)
        .select_related("item", "catalog_test")
        .order_by("item__sku", "test_name")[:200]
    )

    pay_hist = customer_payment_timeliness(customer)
    return render(
        request,
        "slurp_ui/sales/customer_profile.html",
        _sales_ctx(
            active_tab="customers",
            customer=customer,
            customer_initials=_customer_initials(customer),
            tab=tab,
            tabs=tabs,
            pricing=pricing,
            ship_tos=ship_tos,
            contacts=contacts,
            forecasts=forecasts,
            quotes=quotes,
            usage_rows=usage_rows,
            open_orders=open_orders,
            recent_shipped=recent_shipped,
            all_customer_orders=all_customer_orders,
            customer_invoices=customer_invoices,
            coa_fps_items=coa_fps_items,
            coa_selected_item=coa_selected_item,
            coa_fps_lines=coa_fps_lines,
            coa_fps_line_rows=coa_fps_line_rows,
            coa_req_by_name=coa_req_by_name,
            coa_all_reqs=coa_all_reqs,
            glance_contacts=glance_contacts,
            ytd_shipped_total=ytd_shipped_total,
            in_house_total=in_house_total,
            active_price_count=active_price_count,
            open_quote_count=open_quote_count,
            usage_year=timezone.localdate().year,
            contact_type_choices=CustomerContact.CONTACT_TYPE_CHOICES,
            quote_status_choices=CustomerQuote.STATUS_CHOICES,
            payment_history=pay_hist,
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def sales_customer_ship_to(request: HttpRequest, customer_pk: int, pk: int = None) -> HttpResponse:
    customer = get_object_or_404(Customer, pk=customer_pk)
    location = get_object_or_404(ShipToLocation, pk=pk, customer=customer) if pk else None
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete" and location:
            location.delete()
            messages.success(request, "Ship-to location deleted.")
            return redirect(f"{reverse('slurp_ui:sales_customer_profile', kwargs={'pk': customer_pk})}?tab=ship-to")
        fields = {
            "location_name": (request.POST.get("location_name") or "").strip(),
            "contact_name": (request.POST.get("contact_name") or "").strip() or None,
            "email": (request.POST.get("email") or "").strip() or None,
            "phone": (request.POST.get("phone") or "").strip() or None,
            "address": (request.POST.get("address") or "").strip(),
            "city": (request.POST.get("city") or "").strip(),
            "state": (request.POST.get("state") or "").strip() or None,
            "zip_code": (request.POST.get("zip_code") or "").strip(),
            "country": (request.POST.get("country") or "USA").strip(),
            "is_default": bool(request.POST.get("is_default")),
            "is_active": request.POST.get("is_active") != "off",
            "notes": (request.POST.get("notes") or "").strip() or None,
        }
        if not fields["location_name"] or not fields["address"] or not fields["city"] or not fields["zip_code"]:
            messages.error(request, "Location name, address, city, and ZIP are required.")
        else:
            if fields["is_default"]:
                ShipToLocation.objects.filter(customer=customer).update(is_default=False)
            if location:
                for k, v in fields.items():
                    setattr(location, k, v)
                location.save()
                messages.success(request, "Ship-to location updated.")
            else:
                ShipToLocation.objects.create(customer=customer, **fields)
                messages.success(request, "Ship-to location created.")
            return redirect(f"{reverse('slurp_ui:sales_customer_profile', kwargs={'pk': customer_pk})}?tab=ship-to")
    return render(
        request,
        "slurp_ui/sales/ship_to_form.html",
        _sales_ctx(active_tab="customers", customer=customer, location=location, port_status="full"),
    )


@login_required
@require_http_methods(["GET", "POST"])
def sales_customer_contact(request: HttpRequest, customer_pk: int, pk: int = None) -> HttpResponse:
    customer = get_object_or_404(Customer, pk=customer_pk)
    contact = get_object_or_404(CustomerContact, pk=pk, customer=customer) if pk else None
    if request.method == "POST":
        if request.POST.get("action") == "delete" and contact:
            contact.delete()
            messages.success(request, "Contact deleted.")
            return redirect(f"{reverse('slurp_ui:sales_customer_profile', kwargs={'pk': customer_pk})}?tab=contacts")
        emails = [e.strip() for e in (request.POST.get("emails") or "").replace(";", "\n").split("\n") if e.strip()]
        fields = {
            "first_name": (request.POST.get("first_name") or "").strip(),
            "last_name": (request.POST.get("last_name") or "").strip(),
            "title": (request.POST.get("title") or "").strip() or None,
            "contact_type": request.POST.get("contact_type") or "general",
            "emails": emails,
            "phone": (request.POST.get("phone") or "").strip() or None,
            "mobile": (request.POST.get("mobile") or "").strip() or None,
            "is_primary": bool(request.POST.get("is_primary")),
            "is_ap_contact": bool(request.POST.get("is_ap_contact")),
            "is_purchasing_contact": bool(request.POST.get("is_purchasing_contact")),
            "is_active": request.POST.get("is_active") != "off",
            "notes": (request.POST.get("notes") or "").strip() or None,
        }
        if not fields["first_name"] or not fields["last_name"]:
            messages.error(request, "First and last name are required.")
        else:
            if contact:
                for k, v in fields.items():
                    setattr(contact, k, v)
                contact.save()
                messages.success(request, "Contact updated.")
            else:
                CustomerContact.objects.create(customer=customer, **fields)
                messages.success(request, "Contact created.")
            return redirect(f"{reverse('slurp_ui:sales_customer_profile', kwargs={'pk': customer_pk})}?tab=contacts")
    emails_text = "\n".join(contact.emails or []) if contact else ""
    return render(
        request,
        "slurp_ui/sales/contact_form.html",
        _sales_ctx(
            active_tab="customers",
            customer=customer,
            contact=contact,
            emails_text=emails_text,
            contact_type_choices=CustomerContact.CONTACT_TYPE_CHOICES,
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def sales_customer_call(request: HttpRequest, customer_pk: int, pk: int = None) -> HttpResponse:
    customer = get_object_or_404(Customer, pk=customer_pk)
    call = get_object_or_404(SalesCall, pk=pk, customer=customer) if pk else None
    contacts = CustomerContact.objects.filter(customer=customer, is_active=True).order_by("last_name")
    if request.method == "POST":
        if request.POST.get("action") == "delete" and call:
            call.delete()
            messages.success(request, "Sales call deleted.")
            return redirect(f"{reverse('slurp_ui:sales_customer_profile', kwargs={'pk': customer_pk})}?tab=sales-calls")
        notes = (request.POST.get("notes") or "").strip()
        if not notes:
            messages.error(request, "Call notes are required.")
        else:
            call_date_raw = request.POST.get("call_date") or timezone.localtime().strftime("%Y-%m-%dT%H:%M")
            call_dt = parse_datetime(call_date_raw) or timezone.now()
            follow_up_dt = None
            if request.POST.get("follow_up_required") and request.POST.get("follow_up_date"):
                follow_up_dt = parse_datetime(request.POST.get("follow_up_date"))
            contact_id = request.POST.get("contact")
            fields = {
                "call_date": call_dt,
                "call_type": request.POST.get("call_type") or "phone",
                "subject": (request.POST.get("subject") or "").strip() or None,
                "notes": notes,
                "follow_up_required": bool(request.POST.get("follow_up_required")),
                "follow_up_date": follow_up_dt,
                "contact_id": int(contact_id) if contact_id else None,
                "created_by": request.user.get_username(),
            }
            if call:
                for k, v in fields.items():
                    setattr(call, k, v)
                call.save()
                messages.success(request, "Sales call updated.")
            else:
                SalesCall.objects.create(customer=customer, **fields)
                messages.success(request, "Sales call logged.")
            return redirect(f"{reverse('slurp_ui:sales_customer_profile', kwargs={'pk': customer_pk})}?tab=sales-calls")
    default_call_date = (
        timezone.localtime(call.call_date).strftime("%Y-%m-%dT%H:%M")
        if call
        else timezone.localtime().strftime("%Y-%m-%dT%H:%M")
    )
    return render(
        request,
        "slurp_ui/sales/sales_call_form.html",
        _sales_ctx(
            active_tab="customers",
            customer=customer,
            call=call,
            contacts=contacts,
            default_call_date=default_call_date,
            call_type_choices=SalesCall.CALL_TYPE_CHOICES,
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def sales_customer_forecast(request: HttpRequest, customer_pk: int, pk: int = None) -> HttpResponse:
    customer = get_object_or_404(Customer, pk=customer_pk)
    forecast = get_object_or_404(CustomerForecast, pk=pk, customer=customer) if pk else None
    items = Item.objects.filter(item_type__in=["finished_good", "distributed_item"]).order_by("sku")[:500]
    if request.method == "POST":
        if request.POST.get("action") == "delete" and forecast:
            forecast.delete()
            messages.success(request, "Forecast deleted.")
            return redirect(f"{reverse('slurp_ui:sales_customer_profile', kwargs={'pk': customer_pk})}?tab=forecast")
        item_id = request.POST.get("item")
        period = (request.POST.get("forecast_period") or "").strip()
        try:
            qty = float(request.POST.get("forecast_quantity") or 0)
        except ValueError:
            qty = 0
        if not item_id or not period or qty <= 0:
            messages.error(request, "Item, period, and quantity are required.")
        else:
            fields = {
                "item_id": int(item_id),
                "forecast_period": period,
                "forecast_quantity": qty,
                "unit_of_measure": request.POST.get("unit_of_measure") or "lbs",
                "notes": (request.POST.get("notes") or "").strip() or None,
                "created_by": request.user.get_username(),
            }
            if forecast:
                for k, v in fields.items():
                    setattr(forecast, k, v)
                forecast.save()
                messages.success(request, "Forecast updated.")
            else:
                CustomerForecast.objects.create(customer=customer, **fields)
                messages.success(request, "Forecast created.")
            return redirect(f"{reverse('slurp_ui:sales_customer_profile', kwargs={'pk': customer_pk})}?tab=forecast")
    return render(
        request,
        "slurp_ui/sales/forecast_form.html",
        _sales_ctx(
            active_tab="customers",
            customer=customer,
            forecast=forecast,
            items=items,
            uom_choices=Item.UNIT_CHOICES,
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def sales_customer_pricing(request: HttpRequest, customer_pk: int, pk: int = None) -> HttpResponse:
    customer = get_object_or_404(Customer, pk=customer_pk)
    pricing = get_object_or_404(CustomerPricing, pk=pk, customer=customer) if pk else None
    items = Item.objects.filter(item_type__in=["finished_good", "distributed_item"]).order_by("sku")[:500]
    incoterms = ["EXW", "FCA", "CPT", "CIP", "DAP", "DPU", "DDP", "FAS", "FOB", "CFR", "CIF"]
    if request.method == "POST":
        if request.POST.get("action") == "delete" and pricing:
            pricing.delete()
            messages.success(request, "Pricing record deleted.")
            return redirect(f"{reverse('slurp_ui:sales_customer_profile', kwargs={'pk': customer_pk})}?tab=pricing")
        item_id = request.POST.get("item")
        eff = (request.POST.get("effective_date") or "").strip()
        try:
            unit_price = float(request.POST.get("unit_price") or 0)
        except ValueError:
            unit_price = 0
        if not item_id or not eff or unit_price <= 0:
            messages.error(request, "Item, unit price, and effective date are required.")
        else:
            exp = (request.POST.get("expiry_date") or "").strip() or None
            fields = {
                "item_id": int(item_id),
                "unit_price": unit_price,
                "unit_of_measure": request.POST.get("unit_of_measure") or "lbs",
                "incoterms": (request.POST.get("incoterms") or "").strip() or None,
                "incoterms_place": (request.POST.get("incoterms_place") or "").strip() or None,
                "effective_date": eff,
                "expiry_date": exp,
                "is_active": request.POST.get("is_active") != "off",
                "notes": (request.POST.get("notes") or "").strip() or None,
            }
            if pricing:
                for k, v in fields.items():
                    setattr(pricing, k, v)
                pricing.save()
                messages.success(request, "Pricing updated.")
            else:
                CustomerPricing.objects.create(customer=customer, **fields)
                messages.success(request, "Pricing created.")
            return redirect(f"{reverse('slurp_ui:sales_customer_profile', kwargs={'pk': customer_pk})}?tab=pricing")
    return render(
        request,
        "slurp_ui/sales/pricing_form.html",
        _sales_ctx(
            active_tab="customers",
            customer=customer,
            pricing=pricing,
            items=items,
            incoterms=incoterms,
            uom_choices=Item.UNIT_CHOICES,
            today=timezone.localdate().isoformat(),
            port_status="full",
        ),
    )


def _parse_quote_lines(post):
    lines = []
    try:
        line_count = int(post.get("line_count") or 1)
    except ValueError:
        line_count = 1
    for i in range(max(1, min(line_count, 20))):
        item_id = post.get(f"item_id_{i}")
        if not item_id:
            continue
        try:
            qty = float(post.get(f"qty_{i}") or 0)
        except ValueError:
            qty = 0
        try:
            price = float(post.get(f"price_{i}") or 0)
        except ValueError:
            price = 0
        if qty <= 0:
            continue
        lines.append(
            {
                "item_id": int(item_id),
                "quantity": qty,
                "unit_price": price,
                "unit_of_measure": post.get(f"uom_{i}") or "lbs",
                "notes": (post.get(f"notes_{i}") or "").strip() or None,
                "sort_order": i,
            }
        )
    return lines


@login_required
@require_http_methods(["GET", "POST"])
def sales_customer_quote(request: HttpRequest, customer_pk: int, pk: int = None) -> HttpResponse:
    customer = get_object_or_404(Customer, pk=customer_pk)
    quote = (
        get_object_or_404(
            CustomerQuote.objects.prefetch_related("lines__item"),
            pk=pk,
            customer=customer,
        )
        if pk
        else None
    )
    items = Item.objects.filter(item_type__in=["finished_good", "distributed_item"]).order_by("sku")[:500]
    ship_tos = ShipToLocation.objects.filter(customer=customer, is_active=True).order_by("-is_default", "location_name")
    contacts = CustomerContact.objects.filter(customer=customer, is_active=True).order_by("-is_primary", "last_name")

    if request.method == "POST":
        action = request.POST.get("action") or "save"
        if action == "delete" and quote:
            if quote.status == "converted":
                messages.error(request, "Converted quotes cannot be deleted.")
            else:
                quote.delete()
                messages.success(request, "Quote deleted.")
            return redirect(f"{reverse('slurp_ui:sales_customer_profile', kwargs={'pk': customer_pk})}?tab=quotes")

        if action.startswith("status:") and quote:
            new_status = action.split(":", 1)[1]
            valid = {c[0] for c in CustomerQuote.STATUS_CHOICES}
            if new_status in valid and quote.status != "converted":
                quote.status = new_status
                quote.save(update_fields=["status", "updated_at"])
                messages.success(request, f"Quote marked {quote.get_status_display()}.")
            return redirect("slurp_ui:sales_customer_quote_edit", customer_pk=customer_pk, pk=quote.pk)

        if action == "convert" and quote:
            if quote.status == "converted" and quote.converted_sales_order_id:
                messages.info(request, f"Already converted to {quote.converted_sales_order.so_number}.")
                return redirect("slurp_ui:sales_order_detail", pk=quote.converted_sales_order_id)
            q_lines = list(quote.lines.select_related("item").all())
            if not q_lines:
                messages.error(request, "Quote has no lines to convert.")
                return redirect("slurp_ui:sales_customer_quote_edit", customer_pk=customer_pk, pk=quote.pk)
            from erp_core.customer_pricing_resolve import unit_price_in_item_uom

            so_items = []
            for ql in q_lines:
                if not ql.item_id:
                    continue
                # Quote lines may price in lbs while the pack SKU is kg (or reverse).
                up = None
                if ql.unit_price is not None:
                    up = unit_price_in_item_uom(
                        float(ql.unit_price),
                        getattr(ql, "unit_of_measure", None),
                        ql.item,
                    )
                so_items.append(
                    {
                        "item_id": ql.item_id,
                        "quantity_ordered": float(ql.quantity or 0),
                        "unit_price": up,
                    }
                )
            if not so_items:
                messages.error(request, "Quote lines have no items.")
                return redirect("slurp_ui:sales_customer_quote_edit", customer_pk=customer_pk, pk=quote.pk)
            payload = {
                "customer_id": customer.id,
                "customer_name": customer.name,
                "customer_reference_number": (quote.customer_reference or "").strip(),
                "status": "draft",
                "notes": (quote.notes or "").strip(),
                "items": so_items,
            }
            if quote.ship_to_location_id:
                payload["ship_to_location"] = quote.ship_to_location_id
            try:
                so = create_sales_order(request.user, payload)
                quote.status = "converted"
                quote.converted_sales_order = so
                quote.save(update_fields=["status", "converted_sales_order", "updated_at"])
                messages.success(request, f"Converted {quote.quote_number} → {so.so_number}.")
                return redirect("slurp_ui:sales_order_detail", pk=so.pk)
            except SellFlowError as e:
                messages.error(request, e.message)
                return redirect("slurp_ui:sales_customer_quote_edit", customer_pk=customer_pk, pk=quote.pk)
            except Exception as e:
                messages.error(request, str(e))
                return redirect("slurp_ui:sales_customer_quote_edit", customer_pk=customer_pk, pk=quote.pk)

        lines = _parse_quote_lines(request.POST)
        quote_date = parse_date((request.POST.get("quote_date") or "").strip()) or timezone.localdate()
        valid_until = parse_date((request.POST.get("valid_until") or "").strip() or "")
        status = request.POST.get("status") or (quote.status if quote else "draft")
        if status not in {c[0] for c in CustomerQuote.STATUS_CHOICES}:
            status = "draft"
        ship_to_id = request.POST.get("ship_to_location") or None
        contact_id = request.POST.get("contact") or None
        if not lines:
            messages.error(request, "Add at least one quote line with quantity.")
        else:
            fields = {
                "ship_to_location_id": int(ship_to_id) if ship_to_id else None,
                "contact_id": int(contact_id) if contact_id else None,
                "status": status if not quote or quote.status != "converted" else quote.status,
                "quote_date": quote_date,
                "valid_until": valid_until,
                "customer_reference": (request.POST.get("customer_reference") or "").strip() or None,
                "notes": (request.POST.get("notes") or "").strip() or None,
            }
            if quote:
                for k, v in fields.items():
                    setattr(quote, k, v)
                quote.save()
                quote.lines.all().delete()
                for line in lines:
                    CustomerQuoteItem.objects.create(quote=quote, **line)
                messages.success(request, f"Updated {quote.quote_number}.")
            else:
                quote = CustomerQuote.objects.create(
                    customer=customer,
                    quote_number=_generate_quote_number(),
                    created_by=request.user.get_username(),
                    **fields,
                )
                for line in lines:
                    CustomerQuoteItem.objects.create(quote=quote, **line)
                messages.success(request, f"Created {quote.quote_number}.")
            return redirect(f"{reverse('slurp_ui:sales_customer_profile', kwargs={'pk': customer_pk})}?tab=quotes")

    existing_lines = list(quote.lines.select_related("item").all()) if quote else []
    # Seed one empty row for create / always allow adding more in template
    return render(
        request,
        "slurp_ui/sales/quote_form.html",
        _sales_ctx(
            active_tab="customers",
            customer=customer,
            quote=quote,
            existing_lines=existing_lines,
            items=items,
            ship_tos=ship_tos,
            contacts=contacts,
            status_choices=CustomerQuote.STATUS_CHOICES,
            uom_choices=Item.UNIT_CHOICES,
            today=timezone.localdate().isoformat(),
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def sales_create_order(request: HttpRequest) -> HttpResponse:
    customers = Customer.objects.filter(is_active=True).order_by("name")[:300]
    items = Item.objects.none()
    selected_customer = None
    ship_tos = []
    customer_id = request.GET.get("customer") or request.POST.get("customer_id")
    if customer_id:
        selected_customer = Customer.objects.filter(pk=customer_id).first()
        if selected_customer:
            ship_tos = list(
                ShipToLocation.objects.filter(customer=selected_customer, is_active=True).order_by(
                    "-is_default", "location_name"
                )
            )

    if request.method == "POST" and selected_customer:
        # Only items with current CustomerPricing may be ordered; price in item UoM.
        from erp_core.customer_pricing_resolve import (
            active_customer_pricing_by_item,
            customer_pricing_unit_price_for_item,
        )

        pricing_rows = active_customer_pricing_by_item(selected_customer)
        pricing_by_item: dict[int, float] = {
            iid: customer_pricing_unit_price_for_item(cp)
            for iid, cp in pricing_rows.items()
        }

        try:
            line_count = int(request.POST.get("line_count") or 1)
        except ValueError:
            line_count = 1
        lines = []
        skipped_unpriced = False
        for i in range(max(1, min(line_count, 20))):
            item_id = request.POST.get(f"item_id_{i}")
            qty = request.POST.get(f"qty_{i}")
            price = request.POST.get(f"price_{i}")
            if not item_id:
                continue
            try:
                q = float(qty or 0)
            except ValueError:
                q = 0
            if q <= 0:
                continue
            try:
                iid = int(item_id)
            except ValueError:
                continue
            if iid not in pricing_by_item:
                skipped_unpriced = True
                continue
            try:
                p = float(price) if price not in (None, "") else None
            except ValueError:
                p = None
            if p is None:
                p = pricing_by_item[iid]
            lines.append(
                {
                    "item_id": iid,
                    "quantity_ordered": q,
                    "unit_price": p,
                }
            )
        if not lines:
            if skipped_unpriced:
                messages.error(
                    request,
                    "Only items with pricing on this customer’s profile can be ordered.",
                )
            else:
                messages.error(request, "Add at least one line with item and quantity.")
        else:
            if skipped_unpriced:
                messages.warning(
                    request,
                    "Skipped line(s) without customer profile pricing.",
                )
            payload = {
                "customer_id": selected_customer.id,
                "customer_name": selected_customer.name,
                "customer_reference_number": (request.POST.get("customer_po") or "").strip(),
                "status": "draft",
                "notes": request.POST.get("notes") or "",
                "drop_ship": bool(request.POST.get("drop_ship")),
                "items": lines,
            }
            ship_to_id = request.POST.get("ship_to_location")
            if ship_to_id:
                payload["ship_to_location"] = int(ship_to_id)
            exp_ship = (request.POST.get("expected_ship_date") or "").strip()
            if exp_ship:
                payload["expected_ship_date"] = exp_ship
            crd = (request.POST.get("customer_required_date") or "").strip()
            if crd:
                payload["customer_required_date"] = crd
            if request.session.get("god_mode") and request.user.is_staff:
                od = (request.POST.get("order_date") or "").strip()
                if od:
                    payload["order_date"] = od
            try:
                so = create_sales_order(request.user, payload)
                messages.success(request, f"Created sales order {so.so_number}.")
                return redirect("slurp_ui:sales_orders")
            except SellFlowError as e:
                messages.error(request, e.message or "Failed to create sales order.")
            except Exception as e:
                messages.error(request, str(e))

    pricing_json = {}
    if selected_customer:
        from erp_core.customer_pricing_resolve import (
            active_customer_pricing_by_item,
            customer_pricing_unit_price_for_item,
        )

        pricing_rows = active_customer_pricing_by_item(selected_customer)
        # Picker: only SKUs with current profile pricing (avoids FG + distributed
        # duplicates like D1307 when only one item_id is priced).
        items = (
            Item.objects.filter(id__in=list(pricing_rows.keys()))
            .order_by("sku", "name", "id")
        )
        for iid, cp in pricing_rows.items():
            # Prefill in item native UoM (matches qty column UoM on the form).
            pricing_json[str(iid)] = round(customer_pricing_unit_price_for_item(cp), 4)

    today = timezone.localdate().isoformat()
    return render(
        request,
        "slurp_ui/sales/create_order.html",
        _sales_ctx(
            active_tab="orders",
            customers=customers,
            items=items,
            selected_customer=selected_customer,
            ship_tos=ship_tos,
            today=today,
            customer_pricing_json=json.dumps(pricing_json),
            god_mode=bool(request.session.get("god_mode")) and request.user.is_staff,
            port_status="full",
        ),
    )


@login_required
@require_POST
def sales_issue_order(request: HttpRequest, pk: int) -> HttpResponse:
    so = get_object_or_404(SalesOrder, pk=pk)
    issue_date = None
    if request.session.get("god_mode") and request.user.is_staff:
        issue_date = (request.POST.get("issue_date") or "").strip() or None
    try:
        issue_sales_order(so, request.user, issue_date=issue_date)
        messages.success(request, f"Issued {so.so_number}.")
    except SellFlowError as e:
        messages.error(request, e.message)
    except Exception as e:
        messages.error(request, str(e))
    return redirect("slurp_ui:sales_orders")


@login_required
@require_POST
def sales_order_update_dates(request: HttpRequest, pk: int) -> HttpResponse:
    """Inline update expected ship / customer required dates from workqueue or detail."""
    so = get_object_or_404(SalesOrder, pk=pk)
    next_url = (request.POST.get("next") or "").strip()
    if next_url.startswith("?"):
        next_url = reverse("slurp_ui:sales_orders") + next_url
    elif not next_url.startswith("/"):
        next_url = reverse("slurp_ui:sales_orders")

    if so.status in ("shipped", "completed", "cancelled", "received"):
        messages.error(request, f"{so.so_number} dates are locked ({so.status}).")
        return redirect(next_url)

    update_fields: list[str] = []
    if "expected_ship_date" in request.POST:
        raw = (request.POST.get("expected_ship_date") or "").strip()
        if raw:
            d = parse_date(raw)
            if not d:
                messages.error(request, "Invalid expected ship date.")
                return redirect(next_url)
            so.expected_ship_date = timezone.make_aware(datetime.combine(d, datetime.min.time()))
        else:
            so.expected_ship_date = None
        update_fields.append("expected_ship_date")

    if "customer_required_date" in request.POST:
        raw = (request.POST.get("customer_required_date") or "").strip()
        if raw:
            d = parse_date(raw)
            if not d:
                messages.error(request, "Invalid customer required date.")
                return redirect(next_url)
            so.customer_required_date = d
        else:
            so.customer_required_date = None
        update_fields.append("customer_required_date")

    if update_fields:
        update_fields.append("updated_at")
        so.save(update_fields=update_fields)
        messages.success(request, f"Updated dates on {so.so_number}.")

    return redirect(next_url)


@login_required
@require_http_methods(["GET", "POST"])
def sales_allocate_order(request: HttpRequest, pk: int) -> HttpResponse:
    so = get_object_or_404(
        SalesOrder.objects.select_related("customer").prefetch_related(
            "items__item",
            "items__allocated_lots__lot",
            "shipments",
        ),
        pk=pk,
    )
    if so.status in ("completed", "cancelled", "shipped", "received"):
        messages.warning(request, f"{so.so_number} cannot be allocated ({so.status}).")
        return redirect("slurp_ui:sales_orders")
    if so.shipments.filter(fulfillment_status="picked_up").exists():
        messages.warning(
            request,
            f"{so.so_number} already picked up — reverse the shipment before changing lots.",
        )
        return redirect("slurp_ui:sales_order_detail", pk=so.id)
    if any(float(i.quantity_shipped or 0) > 1e-6 for i in so.items.all()):
        messages.warning(
            request,
            f"{so.so_number} has shipped qty — reverse the shipment before changing lots.",
        )
        return redirect("slurp_ui:sales_order_detail", pk=so.id)

    ready_shipment = so.shipments.filter(fulfillment_status="ready").order_by("-id").first()
    is_reallocate = (
        float(
            sum(float(i.quantity_allocated or 0) for i in so.items.all())
        )
        > 0
        or so.status in ("allocated", "ready_for_shipment")
        or bool(ready_shipment)
    )

    ALLOC_MAX_LOTS_PER_LINE = 20

    from erp_core.inventory_fg_visibility import GATED_PRODUCT_CATEGORIES

    closed_batch_output_lot_ids = set(
        ProductionBatchOutput.objects.filter(batch__status="closed").values_list(
            "lot_id", flat=True
        )
    )

    line_lot_choices = []
    for line in so.items.all():
        item_type = getattr(line.item, "item_type", "") or ""
        product_category = (getattr(line.item, "product_category", None) or "").strip()
        gated_fg = item_type == "finished_good" and product_category in GATED_PRODUCT_CATEGORIES
        own_by_lot = {
            al.lot_id: float(al.quantity_allocated or 0)
            for al in line.allocated_lots.all()
            if al.lot_id
        }
        picks = [
            {"lot_id": al.lot_id, "qty": float(al.quantity_allocated or 0)}
            for al in line.allocated_lots.all()[:ALLOC_MAX_LOTS_PER_LINE]
            if al.lot_id
        ]
        if not picks:
            picks = [None]

        qs = Lot.objects.filter(quantity_remaining__gt=0).exclude(status="rejected")
        # Same pack SKU (covers FG + twin distributed Item rows sharing a SKU).
        line_sku = (getattr(line.item, "sku", None) or "").strip()
        if line_sku:
            qs = qs.filter(item__sku=line_sku)
        else:
            qs = qs.filter(item_id=line.item_id)
        lot_ids = set(qs.values_list("pk", flat=True)) | set(own_by_lot.keys())
        lots = list(
            Lot.objects.filter(pk__in=lot_ids)
            .exclude(status="rejected")
            .select_related("item")
            .order_by("-received_date")[:120]
        )

        # Multi-batch campaign membership (same rule as lot_campaign)
        lot_campaign_code = {}
        if lots:
            outs = (
                ProductionBatchOutput.objects.filter(
                    lot_id__in=[lot.id for lot in lots],
                    batch__campaign_id__isnull=False,
                )
                .select_related("batch__campaign")
                .order_by("-id")
            )
            lot_to_camp_id = {}
            camp_by_id = {}
            for out in outs:
                if out.lot_id in lot_to_camp_id:
                    continue
                camp = out.batch.campaign
                if not camp:
                    continue
                lot_to_camp_id[out.lot_id] = camp.id
                camp_by_id[camp.id] = camp
            if camp_by_id:
                multi_ids = set(
                    CampaignLot.objects.filter(id__in=list(camp_by_id.keys()))
                    .annotate(n=Count("batches"))
                    .filter(n__gte=2)
                    .values_list("id", flat=True)
                )
                for lid, cid in lot_to_camp_id.items():
                    if cid in multi_ids:
                        lot_campaign_code[lid] = camp_by_id[cid].campaign_code or ""

        sellable_rows = []
        raw_rows = []
        if item_type == "distributed_item":
            sellable_lot_ids = set(
                ProductionBatchOutput.objects.filter(
                    lot_id__in=[lot.id for lot in lots],
                    batch__batch_type="repack",
                    batch__status="closed",
                ).values_list("lot_id", flat=True)
            )
        elif gated_fg:
            sellable_lot_ids = {
                lot.id for lot in lots if lot.id in closed_batch_output_lot_ids
            }
        else:
            sellable_lot_ids = None  # all lots are sellable

        for lot in lots:
            avail = float(compute_lot_quantity_breakdown(lot)["quantity_available_for_use"])
            avail += own_by_lot.get(lot.id, 0.0)
            if avail <= 0:
                continue
            item = lot.item
            uom = (getattr(item, "unit_of_measure", None) or "lbs") if item else "lbs"
            pack_qty, pack_uom = resolve_pack_size(item=item, lot=lot)
            brk = pack_quantity_breakdown(avail, uom, pack_qty, pack_uom) or {}
            is_partial = bool(brk.get("has_remainder"))
            pack_note = (brk.get("display") or brk.get("note") or "").strip()
            camp_code = lot_campaign_code.get(lot.id) or ""
            is_campaign = bool(camp_code)
            label_bits = [f"{lot.lot_number} — avail {avail:.2f} {uom}"]
            if camp_code:
                label_bits.append(f"camp {camp_code}")
            if pack_note:
                label_bits.append(pack_note)
            label_bits.append(f"({lot.status})")
            row = {
                "lot": lot,
                "available": avail,
                "is_partial": is_partial,
                "is_campaign": is_campaign,
                "campaign_code": camp_code,
                "pack_note": pack_note,
                "uom": uom,
                "label": " · ".join(label_bits),
            }
            if sellable_lot_ids is None or lot.id in sellable_lot_ids:
                sellable_rows.append(row)
            else:
                raw_rows.append(row)

        def _alloc_sort(r):
            return (0 if r["is_partial"] else 1, -float(r["available"] or 0))

        sellable_rows.sort(key=_alloc_sort)
        raw_rows.sort(key=_alloc_sort)

        def _split(rows):
            regular = [r for r in rows if not r["is_campaign"]]
            campaign = [r for r in rows if r["is_campaign"]]
            return {
                "regular": regular,
                "campaign": campaign,
                "partial_lots": [r for r in regular if r["is_partial"]],
                "full_lots": [r for r in regular if not r["is_partial"]],
                "campaign_partial_lots": [r for r in campaign if r["is_partial"]],
                "campaign_full_lots": [r for r in campaign if not r["is_partial"]],
            }

        sell = _split(sellable_rows)
        raw = _split(raw_rows)
        line_lot_choices.append(
            {
                "line": line,
                "lots": sell["regular"],
                "campaign_lots": sell["campaign"],
                "partial_lots": sell["partial_lots"],
                "full_lots": sell["full_lots"],
                "campaign_partial_lots": sell["campaign_partial_lots"],
                "campaign_full_lots": sell["campaign_full_lots"],
                "raw_lots": raw["regular"],
                "raw_campaign_lots": raw["campaign"],
                "raw_partial_lots": raw["partial_lots"],
                "raw_full_lots": raw["full_lots"],
                "has_campaign_lots": bool(sell["campaign"] or raw["campaign"]),
                "picks": picks,
            }
        )
    if request.method == "POST":
        if so.drop_ship:
            try:
                allocate_sales_order(so, {"items": []})
                msg = f"Drop-ship {so.so_number} marked allocated (virtual)."
                if ready_shipment:
                    msg += " Mark Ready was cleared — Mark Ready again when packing dims are set."
                messages.success(request, msg)
                return redirect("slurp_ui:sales_orders")
            except SellFlowError as e:
                messages.error(request, e.message)
            except Exception as e:
                messages.error(request, str(e))
        else:
            allow_prerepack = bool(request.POST.get("allow_prerepack_allocation"))
            items_payload = []
            for line in so.items.all():
                picks = []
                seen_lots = set()
                for slot in range(ALLOC_MAX_LOTS_PER_LINE):
                    lot_id = request.POST.get(f"lot_{line.id}_{slot}")
                    qty = request.POST.get(f"qty_{line.id}_{slot}")
                    if not lot_id or not qty:
                        continue
                    try:
                        q = float(qty)
                    except ValueError:
                        continue
                    if q <= 0:
                        continue
                    try:
                        lid = int(lot_id)
                    except ValueError:
                        continue
                    if lid in seen_lots:
                        messages.error(
                            request,
                            f"{line.item.sku}: same lot selected more than once. "
                            "Combine quantities into one pick.",
                        )
                        picks = None
                        break
                    seen_lots.add(lid)
                    picks.append({"lot_id": lid, "quantity": q})
                if picks is None:
                    break
                is_distributed = getattr(line.item, "item_type", "") == "distributed_item"
                create_from_rm = is_distributed and bool(
                    request.POST.get(f"create_from_rm_{line.id}")
                )
                items_payload.append(
                    {
                        "item_id": line.item_id,
                        "is_distributed": is_distributed,
                        "allocations": [] if create_from_rm else picks,
                        "raw_materials": picks if create_from_rm else [],
                    }
                )
            else:
                try:
                    allocate_sales_order(
                        so,
                        {
                            "items": items_payload,
                            "allow_prerepack_allocation": allow_prerepack,
                        },
                    )
                    msg = f"Allocations saved for {so.so_number}."
                    if ready_shipment:
                        msg += " Mark Ready was cleared — Mark Ready again when packing dims are set."
                    messages.success(request, msg)
                    return redirect("slurp_ui:sales_orders")
                except SellFlowError as e:
                    messages.error(request, e.message)
                except Exception as e:
                    messages.error(request, str(e))

    return render(
        request,
        "slurp_ui/sales/allocate.html",
        _sales_ctx(
            active_tab="orders",
            order=so,
            line_lot_choices=line_lot_choices,
            is_reallocate=is_reallocate,
            clears_ready=bool(ready_shipment),
            alloc_max_lots=ALLOC_MAX_LOTS_PER_LINE,
            port_status="full",
        ),
    )



@login_required
@require_http_methods(["GET", "POST"])
def sales_checkout(request: HttpRequest) -> HttpResponse:
    """Mark Ready form (pieces/dims) when ?so=<id>; else list eligible orders."""
    so_id = request.GET.get("so") or request.POST.get("so_id")
    selected = None
    if so_id:
        selected = get_object_or_404(
            SalesOrder.objects.select_related("customer").prefetch_related(
                "items__item", "items__allocated_lots__lot"
            ),
            pk=so_id,
        )

    if request.method == "POST" and selected:
        try:
            pieces = int(request.POST.get("pieces") or 1)
        except ValueError:
            pieces = 1
        pieces = max(1, min(pieces, 20))
        dims = []
        weights = []
        for i in range(pieces):
            dims.append((request.POST.get(f"dim_{i}") or "").strip())
            weights.append((request.POST.get(f"weight_{i}") or "").strip())

        try:
            ship_items = []
            for line in selected.items.select_related("item").all():
                rem = float(line.quantity_allocated or 0)
                if rem <= 0 and selected.drop_ship:
                    rem = max(
                        0.0,
                        float(line.quantity_ordered or 0) - float(line.quantity_shipped or 0),
                    )
                if rem <= 0:
                    continue
                raw = (request.POST.get(f"ship_qty_{line.id}") or "").strip()
                if raw == "":
                    qty = rem
                else:
                    try:
                        qty = float(raw)
                    except ValueError:
                        raise SellFlowError(f"Invalid ship qty for {line.item.sku}.")
                if qty < 0:
                    raise SellFlowError(f"Ship qty for {line.item.sku} cannot be negative.")
                if qty > rem + 0.01:
                    raise SellFlowError(
                        f"Ship qty {qty} exceeds allocated {rem} {line.item.unit_of_measure} for {line.item.sku}."
                    )
                if qty > 0:
                    ship_items.append({"item_id": line.id, "quantity": qty})
            if not ship_items:
                raise SellFlowError("Enter a ship qty greater than 0 on at least one line.")

            payload = {
                "ship_date": (request.POST.get("ship_date") or timezone.localdate().isoformat()),
                "carrier": (request.POST.get("carrier") or "").strip(),
                "tracking_number": (request.POST.get("tracking_number") or "").strip(),
                "pieces": pieces,
                "piece_dimensions": dims,
                "piece_weights": weights,
                "dim_uom": (request.POST.get("dim_uom") or "in").strip(),
                "weight_uom": (request.POST.get("weight_uom") or "lbs").strip(),
                "items": ship_items,
            }
            ship_sales_order(selected, request.user, payload)
            messages.success(
                request,
                f"{selected.so_number} marked Ready — packing list & COAs available. "
                "Mark picked up when the truck leaves to create the draft invoice.",
            )
            return redirect(f"{reverse('slurp_ui:sales_orders')}?focus=awaiting_pickup")
        except SellFlowError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))

    ready = (
        SalesOrder.objects.filter(status__in=["issued", "allocated"])
        .annotate(total_allocated=Sum("items__quantity_allocated"))
        .select_related("customer")
        .order_by("-created_at")[:100]
    )
    eligible = [
        o
        for o in ready
        if o.drop_ship or float(o.total_allocated or 0) > 0
    ]
    # Exclude orders that already have an awaiting-pickup shipment
    from erp_core.models import Shipment

    awaiting_ids = set(
        Shipment.objects.filter(fulfillment_status="ready").values_list("sales_order_id", flat=True)
    )
    eligible = [o for o in eligible if o.id not in awaiting_ids]

    today = timezone.localdate().isoformat()
    return render(
        request,
        "slurp_ui/sales/checkout.html",
        _sales_ctx(
            active_tab="orders",
            orders=eligible,
            selected=selected,
            today=today,
            port_status="full" if selected else "partial",
        ),
    )


@login_required
@require_POST
def sales_mark_picked_up(request: HttpRequest, pk: int) -> HttpResponse:
    """Mark ready shipment as picked up → deplete inventory + draft invoice."""
    from erp_core.models import Shipment

    so = get_object_or_404(SalesOrder, pk=pk)
    shipment = (
        Shipment.objects.filter(sales_order=so, fulfillment_status="ready")
        .order_by("-id")
        .first()
    )
    if not shipment:
        messages.error(request, f"{so.so_number} has no shipment awaiting pickup.")
        return redirect("slurp_ui:sales_orders")

    next_url = (request.POST.get("next") or "").strip()
    if next_url.startswith("?"):
        next_url = reverse("slurp_ui:sales_orders") + next_url
    elif not next_url.startswith("/"):
        next_url = reverse("slurp_ui:sales_orders") + "?focus=need_invoice"

    try:
        result = mark_shipment_picked_up(
            shipment,
            request.user,
            {
                "pickup_date": (request.POST.get("pickup_date") or timezone.localdate().isoformat()),
                "tracking_number": (request.POST.get("tracking_number") or "").strip(),
            },
        )
        inv = (result.get("invoice") or {}).get("invoice_number") or "—"
        messages.success(
            request,
            f"{so.so_number} picked up. Draft invoice {inv} — review tracking and issue in Finance.",
        )
        inv_id = (result.get("invoice") or {}).get("id")
        if inv_id:
            return redirect("slurp_ui:finance_invoice_detail", pk=inv_id)
    except SellFlowError as e:
        messages.error(request, e.message)
    except Exception as e:
        messages.error(request, str(e))
    return redirect(next_url)


@login_required
@require_http_methods(["GET", "POST"])
def sales_combined_checkout(request: HttpRequest) -> HttpResponse:
    """Select 2+ issued/allocated SOs (same customer + ship-to) and Mark Ready together."""
    ready = (
        SalesOrder.objects.filter(status__in=["issued", "allocated"])
        .annotate(total_allocated=Sum("items__quantity_allocated"))
        .select_related("customer", "ship_to_location")
        .prefetch_related("items__item")
        .order_by("customer_id", "ship_to_location_id", "-created_at")[:150]
    )
    eligible = [
        o
        for o in ready
        if o.drop_ship or float(o.total_allocated or 0) > 0
    ]

    if request.method == "POST":
        try:
            order_ids = [int(x) for x in request.POST.getlist("order_ids")]
        except ValueError:
            order_ids = []
        if len(order_ids) < 2:
            messages.error(request, "Select at least two orders to Mark Ready together.")
        else:
            try:
                pieces = int(request.POST.get("pieces") or 1)
            except ValueError:
                pieces = 1
            pieces = max(1, min(pieces, 20))
            dims = []
            weights = []
            for i in range(pieces):
                dims.append((request.POST.get(f"dim_{i}") or "").strip())
                weights.append((request.POST.get(f"weight_{i}") or "").strip())

            try:
                orders_payload = []
                for oid in order_ids:
                    so = get_object_or_404(
                        SalesOrder.objects.prefetch_related("items__item"),
                        pk=oid,
                    )
                    ship_items = []
                    for line in so.items.all():
                        rem = float(line.quantity_allocated or 0)
                        if rem <= 0:
                            continue
                        raw = (request.POST.get(f"ship_qty_{line.id}") or "").strip()
                        if raw == "":
                            qty = rem
                        else:
                            try:
                                qty = float(raw)
                            except ValueError:
                                raise SellFlowError(
                                    f"Invalid ship qty for {line.item.sku} on {so.so_number}."
                                )
                        if qty < 0:
                            raise SellFlowError(f"Ship qty for {line.item.sku} cannot be negative.")
                        if qty > rem + 0.01:
                            raise SellFlowError(
                                f"Ship qty {qty} exceeds allocated {rem} {line.item.unit_of_measure} "
                                f"for {line.item.sku} on {so.so_number}."
                            )
                        if qty > 0:
                            ship_items.append({"item_id": line.id, "quantity": qty})
                    if not ship_items and not so.drop_ship:
                        raise SellFlowError(
                            f"Enter a ship qty on at least one line of {so.so_number}."
                        )
                    orders_payload.append({"sales_order_id": oid, "items": ship_items})

                payload = {
                    "orders": orders_payload,
                    "ship_date": (request.POST.get("ship_date") or timezone.localdate().isoformat()),
                    "invoice_date": (
                        request.POST.get("invoice_date")
                        or request.POST.get("ship_date")
                        or timezone.localdate().isoformat()
                    ),
                    "carrier": (request.POST.get("carrier") or "").strip(),
                    "tracking_number": (request.POST.get("tracking_number") or "").strip(),
                    "pieces": pieces,
                    "piece_dimensions": dims,
                    "piece_weights": weights,
                    "dim_uom": (request.POST.get("dim_uom") or "in").strip(),
                    "weight_uom": (request.POST.get("weight_uom") or "lbs").strip(),
                }
                result = combined_ship_sales_orders(request.user, payload)
                ck = result.get("combined_shipment_key")
                messages.success(
                    request,
                    f"Combined Mark Ready ({len(order_ids)} orders). "
                    f"Packing list available. Mark each picked up when the truck leaves.",
                )
                if ck:
                    return redirect(f"{reverse('slurp_ui:sales_combined_packing_list_pdf')}?key={ck}")
                return redirect(f"{reverse('slurp_ui:sales_orders')}?focus=awaiting_pickup")
            except SellFlowError as e:
                messages.error(request, e.message)
            except Exception as e:
                messages.error(request, str(e))

    today = timezone.localdate().isoformat()
    return render(
        request,
        "slurp_ui/sales/combined_checkout.html",
        _sales_ctx(
            active_tab="orders",
            orders=eligible,
            today=today,
            port_status="full",
        ),
    )



@login_required
def sales_pick_list_pdf(request: HttpRequest, pk: int) -> HttpResponse:
    so = get_object_or_404(SalesOrder.objects.select_related("customer"), pk=pk)
    from erp_core.pick_list_pdf_html import generate_pick_list_pdf_from_html, pick_list_has_rows

    if not pick_list_has_rows(so):
        messages.warning(request, f"No pick list rows for {so.so_number}.")
        return redirect("slurp_ui:sales_order_detail", pk=pk)
    try:
        pdf_bytes = generate_pick_list_pdf_from_html(so)
    except Exception as e:
        messages.error(request, f"Pick list PDF failed: {e}")
        return redirect("slurp_ui:sales_order_detail", pk=pk)
    if not pdf_bytes:
        messages.error(request, "Pick list PDF generation failed.")
        return redirect("slurp_ui:sales_order_detail", pk=pk)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    fname = f"pick-list-{so.so_number or pk}.pdf"
    disposition = "attachment" if request.GET.get("download") else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{fname}"'
    return response


@login_required
def sales_packing_list_pdf(request: HttpRequest, pk: int) -> HttpResponse:
    so = get_object_or_404(SalesOrder.objects.select_related("customer"), pk=pk)
    try:
        from erp_core.packing_list_pdf_html import generate_packing_list_pdf_from_html

        pdf_bytes = generate_packing_list_pdf_from_html(so)
    except Exception as e:
        messages.error(request, f"Packing list PDF failed: {e}")
        return redirect("slurp_ui:sales_order_detail", pk=pk)
    if not pdf_bytes:
        messages.error(request, "Packing list PDF generation failed.")
        return redirect("slurp_ui:sales_order_detail", pk=pk)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    fname = f"packing-list-{so.so_number or pk}.pdf"
    disposition = "attachment" if request.GET.get("download") else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{fname}"'
    return response


@login_required
def sales_combined_packing_list_pdf(request: HttpRequest) -> HttpResponse:
    import uuid as uuid_mod

    raw_key = request.GET.get("key") or request.GET.get("combined_shipment_key")
    if not raw_key:
        messages.error(request, "combined_shipment_key (or key) query parameter is required.")
        return redirect("slurp_ui:sales_orders")
    try:
        ck = uuid_mod.UUID(str(raw_key))
    except (ValueError, TypeError):
        messages.error(request, "Invalid combined_shipment_key UUID.")
        return redirect("slurp_ui:sales_orders")

    shipments = list(
        Shipment.objects.filter(combined_shipment_key=ck)
        .select_related("sales_order", "sales_order__customer")
        .order_by("id")
    )
    if not shipments:
        messages.warning(request, "No shipments found for that combined key.")
        return redirect("slurp_ui:sales_orders")
    try:
        from erp_core.packing_list_pdf_html import generate_combined_packing_list_pdf

        pdf_bytes = generate_combined_packing_list_pdf(shipments)
    except Exception as e:
        messages.error(request, f"Combined packing list PDF failed: {e}")
        return redirect("slurp_ui:sales_orders")
    if not pdf_bytes:
        messages.error(request, "Combined packing list PDF generation failed.")
        return redirect("slurp_ui:sales_orders")
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    fname = f"combined-packing-list-{ck}.pdf"
    disposition = "attachment" if request.GET.get("download") else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{fname}"'
    return response


@login_required
def sales_order_detail(request: HttpRequest, pk: int) -> HttpResponse:
    from erp_core.models import Shipment

    so = get_object_or_404(
        SalesOrder.objects.select_related("customer").prefetch_related(
            "items__item",
            "items__allocated_lots__lot",
            "items__allocated_lots__lot__coa_certificate",
            "items__allocated_lots__coa_customer_copies",
            "shipments__items",
            "invoices",
        ),
        pk=pk,
    )
    # Heal legacy ready_for_shipment with no Ready shipment
    ready_sh = so.shipments.filter(fulfillment_status="ready").order_by("-id").first()
    if so.status == "ready_for_shipment" and not ready_sh:
        so.status = "allocated"
        so.save(update_fields=["status"])

    is_staff = bool(request.user.is_staff)
    has_picked_up = so.shipments.filter(fulfillment_status="picked_up").exists()
    has_shipped_qty = any(float(i.quantity_shipped or 0) > 1e-6 for i in so.items.all())
    can_revert = (
        is_staff
        and so.status in ("issued", "allocated", "ready_for_shipment")
        and not has_picked_up
        and not has_shipped_qty
    )
    can_cancel = (
        so.status in ("draft", "issued", "allocated", "ready_for_shipment")
        and not has_picked_up
        and not has_shipped_qty
    )
    total_allocated = sum(float(i.quantity_allocated or 0) for i in so.items.all())
    show_allocate = (
        so.status in ("issued", "allocated", "ready_for_shipment")
        and not has_picked_up
        and not has_shipped_qty
    )
    is_reallocate = bool(
        show_allocate
        and (total_allocated > 0 or so.status in ("allocated", "ready_for_shipment") or ready_sh)
    )
    show_mark_ready = bool(
        show_allocate
        and not ready_sh
        and (so.drop_ship or total_allocated > 0)
    )
    can_return = has_shipped_qty
    returnable_invoices = list(
        so.invoices.filter(invoice_type="customer")
        .exclude(status="cancelled")
        .order_by("-invoice_date", "-id")
    )
    credit_memos = list(
        so.invoices.filter(invoice_type="credit").order_by("-invoice_date", "-id")
    )
    rma_lot_rows = shipped_lot_quantities_for_so(so) if can_return else []
    order_rmas = list(
        CustomerRma.objects.filter(sales_order=so)
        .select_related("credit_invoice")
        .prefetch_related("lines__source_lot", "lines__staging_lot")
        .order_by("-opened_at")
    )
    coa_copies = []
    coa_master_certs = []
    from erp_core.coa_allocation import (
        consolidate_customer_coas_for_sales_order,
        customer_coa_button_label,
    )

    try:
        coa_copies = consolidate_customer_coas_for_sales_order(so)
    except Exception:
        coa_copies = []
    for copy in coa_copies:
        copy.button_label = customer_coa_button_label(copy)
    if not coa_copies:
        seen_cert = set()
        for line in so.items.all():
            for al in line.allocated_lots.all():
                cert = getattr(al.lot, "coa_certificate", None) if al.lot_id else None
                if cert and cert.id not in seen_cert:
                    seen_cert.add(cert.id)
                    coa_master_certs.append(cert)
    return render(
        request,
        "slurp_ui/sales/order_detail.html",
        _sales_ctx(
            active_tab="orders",
            order=so,
            ready_shipment=ready_sh,
            is_staff=is_staff,
            can_revert=can_revert,
            can_cancel=can_cancel,
            can_return=can_return,
            show_allocate=show_allocate,
            is_reallocate=is_reallocate,
            show_mark_ready=show_mark_ready,
            has_allocation=total_allocated > 0,
            returnable_invoices=returnable_invoices,
            credit_memos=credit_memos,
            rma_lot_rows=rma_lot_rows,
            order_rmas=order_rmas,
            coa_copies=coa_copies,
            coa_master_certs=coa_master_certs,
            port_status="full",
        ),
    )


@login_required
@require_POST
def sales_create_return(request: HttpRequest, pk: int) -> HttpResponse:
    """Open customer RMA + credit memo (no restock). Inventory returns via Check-In → Customer return (RMA)."""
    so = get_object_or_404(SalesOrder.objects.prefetch_related("items__item"), pk=pk)
    lines = []
    for key, val in request.POST.items():
        if not key.startswith("return_qty_"):
            continue
        raw = (val or "").strip()
        if not raw:
            continue
        # return_qty_{soi_id}_{lot_id}
        parts = key[len("return_qty_") :].split("_", 1)
        if len(parts) != 2:
            messages.error(request, f"Invalid return field {key}.")
            return redirect("slurp_ui:sales_order_detail", pk=so.id)
        try:
            soi_id = int(parts[0])
            lot_id = int(parts[1])
            qty = float(raw)
        except ValueError:
            messages.error(request, "Invalid return quantity.")
            return redirect("slurp_ui:sales_order_detail", pk=so.id)
        if qty <= 0:
            continue
        lines.append(
            {
                "sales_order_item_id": soi_id,
                "lot_id": lot_id,
                "quantity": qty,
            }
        )
    # Whole-SO shortcut: return_all=1 fills available on every lot
    if not lines and request.POST.get("return_all"):
        for row in shipped_lot_quantities_for_so(so):
            avail = float(row["available_qty"] or 0)
            if avail <= 1e-6:
                continue
            lines.append(
                {
                    "sales_order_item_id": row["sales_order_item"].id,
                    "lot_id": row["lot"].id,
                    "quantity": avail,
                }
            )
    source_invoice = None
    inv_id = (request.POST.get("source_invoice_id") or "").strip()
    if inv_id:
        source_invoice = get_object_or_404(
            so.invoices.filter(invoice_type="customer").exclude(status="cancelled"),
            pk=int(inv_id),
        )
    try:
        result = open_customer_rma(
            so,
            lines,
            source_invoice=source_invoice,
            reason=(request.POST.get("reason") or "").strip(),
            notes=(request.POST.get("notes") or "").strip(),
            user=request.user,
        )
        rma = result["rma"]
        credit = result["credit_invoice"]
        msg = (
            f"RMA {rma.rma_number} opened. Credit memo {credit.invoice_number} "
            f"for ${credit.grand_total:,.2f}. Applied ${result['applied_amount']:,.2f} to AR"
        )
        if result["unapplied_amount"] > 0.01:
            msg += f"; ${result['unapplied_amount']:,.2f} unapplied credit on file"
        msg += ". Check in returned material under Inventory → Check-in (RMA)."
        messages.success(request, msg)
        return redirect("slurp_ui:sales_rma_detail", pk=rma.id)
    except SellFlowError as e:
        messages.error(request, e.message)
    except Exception as e:
        messages.error(request, str(e))
    return redirect("slurp_ui:sales_order_detail", pk=so.id)


@login_required
def sales_rma_detail(request: HttpRequest, pk: int) -> HttpResponse:
    rma = get_object_or_404(
        CustomerRma.objects.select_related(
            "sales_order", "customer", "credit_invoice"
        ).prefetch_related(
            "lines__source_lot__item",
            "lines__staging_lot",
            "lines__sales_order_item__item",
        ),
        pk=pk,
    )
    from erp_core.models import LotHoldCase

    staging_ids = [
        ln.staging_lot_id for ln in rma.lines.all() if ln.staging_lot_id
    ]
    hold_cases = list(
        LotHoldCase.objects.filter(lot_id__in=staging_ids)
        .select_related("lot")
        .order_by("-opened_at")
    ) if staging_ids else []
    return render(
        request,
        "slurp_ui/sales/rma_detail.html",
        _sales_ctx(
            active_tab="orders",
            rma=rma,
            hold_cases=hold_cases,
            port_status="full",
        ),
    )


@login_required
def sales_rma_list(request: HttpRequest) -> HttpResponse:
    status = (request.GET.get("status") or "").strip()
    qs = CustomerRma.objects.select_related(
        "sales_order", "customer", "credit_invoice"
    ).order_by("-opened_at")
    if status:
        qs = qs.filter(status=status)
    return render(
        request,
        "slurp_ui/sales/rma_list.html",
        _sales_ctx(
            active_tab="orders",
            rmas=list(qs[:200]),
            status_filter=status,
            port_status="full",
        ),
    )


@login_required
@require_POST
def sales_cancel_order(request: HttpRequest, pk: int) -> HttpResponse:
    so = get_object_or_404(SalesOrder, pk=pk)
    try:
        cancel_sales_order(so, request.user)
        messages.success(
            request,
            f"Cancelled {so.so_number}. Lot holds released back to inventory.",
        )
    except SellFlowError as e:
        messages.error(request, e.message)
    except Exception as e:
        messages.error(request, str(e))
    return redirect("slurp_ui:sales_orders")


@login_required
@require_POST
def sales_revert_order(request: HttpRequest, pk: int) -> HttpResponse:
    so = get_object_or_404(SalesOrder, pk=pk)
    try:
        revert_sales_order_to_draft(so, request.user)
        messages.success(request, f"Reverted {so.so_number} to draft.")
    except SellFlowError as e:
        messages.error(request, e.message)
    except Exception as e:
        messages.error(request, str(e))
    return redirect("slurp_ui:sales_order_detail", pk=pk)


@login_required
@require_POST
def sales_reverse_shipment(request: HttpRequest, pk: int) -> HttpResponse:
    """pk is shipment id."""
    shipment = get_object_or_404(Shipment.objects.select_related("sales_order"), pk=pk)
    so_id = shipment.sales_order_id
    try:
        info = reverse_sales_shipment(shipment.id, request.user)
        messages.success(
            request,
            f"Reversed shipment #{info.get('removed_shipment_id')}; "
            f"order now {info.get('new_status')}.",
        )
    except SellFlowError as e:
        messages.error(request, e.message)
    except Exception as e:
        messages.error(request, str(e))
    return redirect("slurp_ui:sales_order_detail", pk=so_id)
