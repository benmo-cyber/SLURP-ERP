from calendar import monthrange
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models
from django.db.models import Count, Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from urllib.parse import urlencode
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.views.decorators.http import require_http_methods, require_POST

from erp_core.lot_display_quantities import compute_lot_quantity_breakdown
from erp_core.models import (
    AccountsPayable,
    AccountsReceivable,
    Customer,
    CustomerContact,
    CustomerForecast,
    CustomerPricing,
    CustomerQuote,
    CustomerQuoteItem,
    Item,
    Lot,
    ProductionBatch,
    PurchaseOrder,
    QuoteNumberSequence,
    SalesCall,
    SalesOrder,
    SalesOrderItem,
    ShipToLocation,
    Shipment,
)
from erp_core.sell_services import (
    SellFlowError,
    allocate_sales_order,
    combined_ship_sales_orders,
    create_sales_order,
    issue_sales_order,
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
            needs_checkout = so.status in ["ready_for_shipment"]
            needs_allocation = so.status in ["draft", "allocated"]
            is_actual = so.status in ["shipped", "completed"] and so.actual_ship_date is not None
            if needs_checkout:
                title = f"Check Out & Ship: {so.so_number}"
            elif needs_allocation:
                title = f"Allocate & Ship: {so.so_number}"
            elif is_actual:
                title = f"Ship: {so.so_number}"
            else:
                title = f"Ship (Expected): {so.so_number}"
            events.append(
                {
                    "id": f"shipment_{so.id}",
                    "type": "shipment",
                    "title": title,
                    "short_label": so.so_number,
                    "subtitle": so.customer_name or (so.customer.name if so.customer_id else ""),
                    "date": ship_date.isoformat(),
                    "sales_order_id": so.id,
                    "sales_order_number": so.so_number,
                    "customer_name": so.customer_name or (so.customer.name if so.customer_id else ""),
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
            short = f"{sku or lot.lot_number} · {qty:g} {uom}" if sku else f"Inbound · {lot.lot_number}"
            events.append(
                {
                    "id": f"raw_material_{lot.id}",
                    "type": "raw_material",
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
        batches = ProductionBatch.objects.filter(status__in=["draft", "scheduled", "in_progress", "closed"]).select_related(
            "finished_good_item"
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
            uom = "lbs" if batch.batch_type == "production" else ((fg.unit_of_measure if fg else None) or "lbs")
            qty = float(batch.quantity_produced or 0)
            qty_label = f"{qty:g} {uom}"
            product_label = sku or name or "FG"
            # Compact chip: product + qty (batch # in tooltip / detail)
            short_label = f"{product_label} · {qty_label}"
            title = f"{product_label}: {qty_label} ({batch.batch_number})"
            events.append(
                {
                    "id": f"production_{batch.id}",
                    "type": "production",
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


@login_required
def sales_orders(request: HttpRequest) -> HttpResponse:
    queue = (request.GET.get("queue") or "open").strip()
    q = (request.GET.get("q") or "").strip()
    qs = (
        SalesOrder.objects.select_related("customer")
        .prefetch_related("items")
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
        # Prefer shippable: issued/ready (and allocated) with some allocation or drop-ship
        qs = qs.filter(status__in=("issued", "ready_for_shipment", "allocated"))
    if q:
        qs = qs.filter(
            models.Q(so_number__icontains=q)
            | models.Q(customer_name__icontains=q)
            | models.Q(customer_reference_number__icontains=q)
            | models.Q(customer__name__icontains=q)
        )
    orders = list(qs.order_by("-created_at")[:200])

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
            counts=counts,
            port_status="full",
            god_mode=bool(request.session.get("god_mode")) and request.user.is_staff,
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
    if event_id.startswith("production_"):
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
    # Ops calendar only — finance due dates belong on a future Finance calendar.
    allowed_types = {"shipments", "raw_materials", "production"}
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
        ("shipments", "Expected ships"),
        ("raw_materials", "Incoming materials"),
        ("production", "Production"),
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
    tab = request.GET.get("tab") or "glance"
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
        .annotate(
            total_allocated=Sum("items__quantity_allocated"),
            total_ordered=Sum("items__quantity_ordered"),
            total_shipped=Sum("items__quantity_shipped"),
        )
        .order_by("-order_date")[:50]
    )
    recent_shipped = list(
        SalesOrder.objects.filter(customer=customer, status__in=SHIPPED_SO_STATUSES)
        .annotate(
            total_allocated=Sum("items__quantity_allocated"),
            total_ordered=Sum("items__quantity_ordered"),
            total_shipped=Sum("items__quantity_shipped"),
        )
        .order_by("-actual_ship_date", "-order_date")[:50]
    )
    all_customer_orders = list(
        SalesOrder.objects.filter(customer=customer)
        .annotate(
            total_allocated=Sum("items__quantity_allocated"),
            total_ordered=Sum("items__quantity_ordered"),
            total_shipped=Sum("items__quantity_shipped"),
        )
        .order_by("-order_date")[:100]
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
        ("payments", "Payments"),
        ("contacts", "Contacts"),
        ("pricing", "Pricing"),
        ("quotes", "Quotes"),
        ("forecast", "Forecast"),
        ("usage", "Usage"),
        ("ship-to", "Ship-to"),
        ("overview", "Account edit"),
    ]
    from ..finance_helpers import customer_payment_timeliness

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
    items = (
        Item.objects.filter(item_type__in=["finished_good", "distributed_item", "raw_material"])
        .order_by("sku")[:500]
    )
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
        try:
            line_count = int(request.POST.get("line_count") or 1)
        except ValueError:
            line_count = 1
        lines = []
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
                p = float(price) if price not in (None, "") else None
            except ValueError:
                p = None
            lines.append(
                {
                    "item_id": int(item_id),
                    "quantity_ordered": q,
                    "unit_price": p,
                }
            )
        if not lines:
            messages.error(request, "Add at least one line with item and quantity.")
        else:
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
@require_http_methods(["GET", "POST"])
def sales_allocate_order(request: HttpRequest, pk: int) -> HttpResponse:
    so = get_object_or_404(
        SalesOrder.objects.select_related("customer").prefetch_related("items__item"),
        pk=pk,
    )
    if so.status in ("completed", "cancelled", "shipped"):
        messages.warning(request, f"{so.so_number} cannot be allocated ({so.status}).")
        return redirect("slurp_ui:sales_orders")

    line_lot_choices = []
    for line in so.items.all():
        lots = (
            Lot.objects.filter(item_id=line.item_id, quantity_remaining__gt=0)
            .exclude(status="rejected")
            .select_related("item")
            .order_by("-received_date")[:40]
        )
        rows = []
        for lot in lots:
            avail = float(compute_lot_quantity_breakdown(lot)["quantity_available_for_use"])
            if avail <= 0:
                continue
            rows.append({"lot": lot, "available": avail})
        line_lot_choices.append({"line": line, "lots": rows})

    if request.method == "POST":
        if so.drop_ship:
            try:
                allocate_sales_order(so, {"items": []})
                messages.success(request, f"Drop-ship {so.so_number} marked ready (virtual allocation).")
                return redirect("slurp_ui:sales_orders")
            except SellFlowError as e:
                messages.error(request, e.message)
            except Exception as e:
                messages.error(request, str(e))
        else:
            allow_prerepack = bool(request.POST.get("allow_prerepack_allocation"))
            items_payload = []
            for line in so.items.all():
                allocations = []
                # Support up to 3 lots per line in simple UI
                for slot in range(3):
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
                    allocations.append({"lot_id": int(lot_id), "quantity": q})
                items_payload.append(
                    {
                        "item_id": line.item_id,
                        "is_distributed": False,
                        "allocations": allocations,
                        "raw_materials": [],
                    }
                )
            try:
                allocate_sales_order(
                    so,
                    {
                        "items": items_payload,
                        "allow_prerepack_allocation": allow_prerepack,
                    },
                )
                messages.success(request, f"Allocations saved for {so.so_number}.")
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
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def sales_checkout(request: HttpRequest) -> HttpResponse:
    """List checkout-eligible orders, or ship one SO when ?so=<id>."""
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

        ship_items = []
        for line in selected.items.all():
            rem = float(line.quantity_allocated or 0)
            if rem > 0:
                ship_items.append({"item_id": line.id, "quantity": rem})

        payload = {
            "ship_date": (request.POST.get("ship_date") or timezone.localdate().isoformat()),
            "invoice_date": (request.POST.get("invoice_date") or request.POST.get("ship_date") or timezone.localdate().isoformat()),
            "carrier": (request.POST.get("carrier") or "").strip(),
            "tracking_number": (request.POST.get("tracking_number") or "").strip(),
            "pieces": pieces,
            "piece_dimensions": dims,
            "piece_weights": weights,
            "items": ship_items,
        }
        try:
            result = ship_sales_order(selected, request.user, payload)
            inv = (result.get("invoice") or {}).get("invoice_number") or "—"
            messages.success(
                request,
                f"Shipped {selected.so_number}. Invoice {inv}.",
            )
            return redirect("slurp_ui:sales_orders")
        except SellFlowError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))

    ready = (
        SalesOrder.objects.filter(status__in=["issued", "ready_for_shipment"])
        .annotate(total_allocated=Sum("items__quantity_allocated"))
        .select_related("customer")
        .order_by("-created_at")[:100]
    )
    # Keep drop-ship (virtual alloc) and any with allocated qty
    eligible = [
        o
        for o in ready
        if o.drop_ship or float(o.total_allocated or 0) > 0
    ]

    today = timezone.localdate().isoformat()
    return render(
        request,
        "slurp_ui/sales/checkout.html",
        _sales_ctx(
            active_tab="checkout",
            orders=eligible,
            selected=selected,
            today=today,
            port_status="full" if selected else "partial",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def sales_combined_checkout(request: HttpRequest) -> HttpResponse:
    """Select 2+ issued/allocated SOs (same customer + ship-to) and ship together."""
    ready = (
        SalesOrder.objects.filter(status__in=["issued", "ready_for_shipment"])
        .annotate(total_allocated=Sum("items__quantity_allocated"))
        .select_related("customer", "ship_to_location")
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
            messages.error(request, "Select at least two orders for combined checkout.")
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

            orders_payload = []
            for oid in order_ids:
                so = get_object_or_404(
                    SalesOrder.objects.prefetch_related("items"),
                    pk=oid,
                )
                ship_items = []
                for line in so.items.all():
                    rem = float(line.quantity_allocated or 0)
                    if rem > 0:
                        ship_items.append({"item_id": line.id, "quantity": rem})
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
            }
            try:
                result = combined_ship_sales_orders(request.user, payload)
                ck = result.get("combined_shipment_key")
                messages.success(
                    request,
                    f"Combined checkout complete ({len(order_ids)} orders). "
                    f"Combined packing list key: {ck}.",
                )
                if ck:
                    return redirect(f"{reverse('slurp_ui:sales_combined_packing_list_pdf')}?key={ck}")
                return redirect("slurp_ui:sales_orders")
            except SellFlowError as e:
                messages.error(request, e.message)
            except Exception as e:
                messages.error(request, str(e))

    today = timezone.localdate().isoformat()
    return render(
        request,
        "slurp_ui/sales/combined_checkout.html",
        _sales_ctx(
            active_tab="combined-checkout",
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
    so = get_object_or_404(
        SalesOrder.objects.select_related("customer").prefetch_related(
            "items__item",
            "items__allocated_lots__lot",
            "shipments__items",
            "invoices",
        ),
        pk=pk,
    )
    is_staff = bool(request.user.is_staff)
    can_revert = is_staff and so.status in ("issued", "allocated", "ready_for_shipment")
    return render(
        request,
        "slurp_ui/sales/order_detail.html",
        _sales_ctx(
            active_tab="orders",
            order=so,
            is_staff=is_staff,
            can_revert=can_revert,
            port_status="full",
        ),
    )


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
