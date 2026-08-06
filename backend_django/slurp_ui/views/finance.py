from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_http_methods, require_POST

from erp_core.invoice_services import InvoiceFlowError, cancel_invoice, issue_invoice
from erp_core.models import (
    Account,
    AccountsPayable,
    AccountsReceivable,
    BankReconciliation,
    CostMaster,
    Customer,
    CustomerPricing,
    FiscalPeriod,
    GeneralLedgerEntry,
    Invoice,
    Item,
    JournalEntry,
    Payment,
    PricingWhatIfLine,
    RDFormula,
    VendorPricing,
)

from ..finance_helpers import (
    FinanceFormError,
    aging_totals_for_dashboard,
    close_fiscal_period,
    commercial_raw_cost_masters,
    create_account,
    create_bank_reconciliation,
    create_customer_pricing,
    create_fiscal_period,
    create_journal_entry,
    create_manual_invoice,
    create_payment,
    create_vendor_pricing,
    get_ap_aging,
    get_ar_aging,
    get_balance_sheet,
    get_cash_flow,
    get_cost_master_actuals,
    get_dashboard_metrics,
    get_income_statement,
    get_lot_cost_profile,
    get_trial_balance,
    gl_balance_for_account,
    margin_trend_rows,
    mark_ap_as_paid,
    mark_ar_as_paid,
    mark_invoice_paid,
    post_journal_entry,
)
from ..nav import FINANCE_NAV


def _finance_ctx(active_tab: str, **extra):
    ctx = {
        "module": "finance",
        "sidebar_nav": FINANCE_NAV,
        "active_tab": active_tab,
        "page_css": [
            "SalesWorkspace.css",
            "Finance.css",
            "Invoices.css",
            "ViewInvoice.css",
        ],
    }
    ctx.update(extra)
    return ctx


def _status_label(status: str) -> str:
    if status == "sent":
        return "Issued"
    return (status or "").replace("_", " ").title()


def _parse_int_list(raw: str) -> list[int]:
    out = []
    for part in (raw or "").split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


def _money(n) -> float:
    try:
        return round(float(n or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _fetch_finance_calendar_events(start_date, end_date, event_types):
    """AR/AP due-date events for the Finance cash calendar."""
    events = []
    type_set = set(event_types or [])
    today = timezone.localdate()
    open_statuses = ["open", "partial", "overdue"]

    if "receivables" in type_set:
        ar_qs = (
            AccountsReceivable.objects.filter(status__in=open_statuses)
            .exclude(due_date__isnull=True)
            .select_related("invoice")
        )
        if start_date:
            ar_qs = ar_qs.filter(due_date__gte=start_date)
        if end_date:
            ar_qs = ar_qs.filter(due_date__lte=end_date)
        for ar in ar_qs.order_by("due_date", "customer_name")[:400]:
            bal = _money(ar.balance)
            inv_no = ""
            if ar.invoice_id and ar.invoice:
                inv_no = ar.invoice.invoice_number or ""
            overdue = ar.due_date < today or ar.status == "overdue"
            events.append(
                {
                    "id": f"receivable_{ar.id}",
                    "type": "receivable",
                    "title": f"AR due: {ar.customer_name} — ${bal:,.2f}",
                    "short_label": f"{ar.customer_name} · ${bal:,.0f}",
                    "subtitle": inv_no or "Open receivable",
                    "date": ar.due_date.isoformat(),
                    "ar_id": ar.id,
                    "invoice_id": ar.invoice_id,
                    "customer_name": ar.customer_name,
                    "balance": bal,
                    "status": ar.status,
                    "is_overdue": overdue,
                    "reschedulable": False,
                }
            )

    if "payables" in type_set:
        ap_qs = AccountsPayable.objects.filter(status__in=open_statuses).exclude(due_date__isnull=True)
        if start_date:
            ap_qs = ap_qs.filter(due_date__gte=start_date)
        if end_date:
            ap_qs = ap_qs.filter(due_date__lte=end_date)
        for ap in ap_qs.order_by("due_date", "vendor_name")[:400]:
            bal = _money(ap.balance)
            overdue = ap.due_date < today or ap.status == "overdue"
            events.append(
                {
                    "id": f"payable_{ap.id}",
                    "type": "payable",
                    "title": f"AP due: {ap.vendor_name} — ${bal:,.2f}",
                    "short_label": f"{ap.vendor_name} · ${bal:,.0f}",
                    "subtitle": ap.invoice_number or "Open payable",
                    "date": ap.due_date.isoformat(),
                    "ap_id": ap.id,
                    "vendor_name": ap.vendor_name,
                    "invoice_number": ap.invoice_number or "",
                    "balance": bal,
                    "status": ap.status,
                    "is_overdue": overdue,
                    "reschedulable": False,
                }
            )

    events.sort(key=lambda x: (x["date"], 0 if x["type"] == "receivable" else 1, x["title"]))
    return events


def _finance_calendar_month_grid(month_anchor: date, events: list) -> dict:
    """Sunday-start month grid (same shape as Ops Calendar)."""
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
                    "ar_total": sum(e["balance"] for e in day_events if e["type"] == "receivable"),
                    "ap_total": sum(e["balance"] for e in day_events if e["type"] == "payable"),
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


def _finance_calendar_context(request: HttpRequest, *, base_path: str) -> dict:
    """Shared month/day/filter state for dashboard + full calendar page."""
    today = timezone.localdate()
    month_raw = (request.GET.get("month") or "").strip()
    month_anchor = parse_date(month_raw + "-01") if month_raw and len(month_raw) >= 7 else today.replace(day=1)
    year, month = month_anchor.year, month_anchor.month
    start_date = date(year, month, 1)
    end_date = date(year, month, monthrange(year, month)[1])

    selected_day = parse_date((request.GET.get("day") or "").strip()) if request.GET.get("day") else today
    selected_types = request.GET.getlist("types") or ["receivables", "payables"]
    allowed = {"receivables", "payables"}
    selected_types = [t for t in selected_types if t in allowed] or ["receivables", "payables"]

    month_events = _fetch_finance_calendar_events(start_date, end_date, selected_types)
    day_events = [e for e in month_events if e["date"] == selected_day.isoformat()] if selected_day else []
    grid = _finance_calendar_month_grid(month_anchor, month_events)

    type_options = [
        ("receivables", "AR due"),
        ("payables", "AP due"),
    ]
    types_qs = "".join(f"&types={t}" for t in selected_types)

    return {
        "events": day_events,
        "month_events": month_events,
        "month_anchor": month_anchor,
        "month_param": month_anchor.strftime("%Y-%m"),
        "calendar_grid": grid,
        "selected_day": selected_day,
        "selected_types": selected_types,
        "type_options": type_options,
        "calendar_base": base_path,
        "types_qs": types_qs,
        "today": today,
    }


def _finance_today_board(today: date) -> dict:
    """Overdue + due-today + this-week cash tasks for the dashboard."""
    week_end = today + timedelta(days=7)
    open_statuses = ["open", "partial", "overdue"]

    ar_open_qs = AccountsReceivable.objects.filter(status__in=open_statuses).exclude(due_date__isnull=True)
    ap_open_qs = AccountsPayable.objects.filter(status__in=open_statuses).exclude(due_date__isnull=True)

    ar_overdue = list(
        ar_open_qs.filter(due_date__lt=today).select_related("invoice").order_by("due_date")[:12]
    )
    ap_overdue = list(ap_open_qs.filter(due_date__lt=today).order_by("due_date")[:12])
    ar_today = list(ar_open_qs.filter(due_date=today).select_related("invoice").order_by("customer_name")[:12])
    ap_today = list(ap_open_qs.filter(due_date=today).order_by("vendor_name")[:12])

    ar_week = ar_open_qs.filter(due_date__gte=today, due_date__lte=week_end)
    ap_week = ap_open_qs.filter(due_date__gte=today, due_date__lte=week_end)

    ar_open_total = _money(ar_open_qs.aggregate(s=Sum("balance"))["s"])
    ap_open_total = _money(ap_open_qs.aggregate(s=Sum("balance"))["s"])
    ar_due_week = _money(ar_week.aggregate(s=Sum("balance"))["s"])
    ap_due_week = _money(ap_week.aggregate(s=Sum("balance"))["s"])
    ar_overdue_total = _money(ar_open_qs.filter(due_date__lt=today).aggregate(s=Sum("balance"))["s"])
    ap_overdue_total = _money(ap_open_qs.filter(due_date__lt=today).aggregate(s=Sum("balance"))["s"])

    today_tasks = []
    for ar in ar_overdue:
        today_tasks.append(
            {
                "kind": "ar",
                "urgency": "overdue",
                "label": ar.customer_name,
                "detail": (ar.invoice.invoice_number if ar.invoice_id and ar.invoice else "AR"),
                "amount": _money(ar.balance),
                "due": ar.due_date,
                "pay_url": reverse("slurp_ui:finance_ar_mark_paid", kwargs={"pk": ar.id}),
                "invoice_id": ar.invoice_id,
            }
        )
    for ap in ap_overdue:
        today_tasks.append(
            {
                "kind": "ap",
                "urgency": "overdue",
                "label": ap.vendor_name,
                "detail": ap.invoice_number or "AP",
                "amount": _money(ap.balance),
                "due": ap.due_date,
                "pay_url": reverse("slurp_ui:finance_ap_mark_paid", kwargs={"pk": ap.id}),
                "invoice_id": None,
            }
        )
    for ar in ar_today:
        today_tasks.append(
            {
                "kind": "ar",
                "urgency": "today",
                "label": ar.customer_name,
                "detail": (ar.invoice.invoice_number if ar.invoice_id and ar.invoice else "AR"),
                "amount": _money(ar.balance),
                "due": ar.due_date,
                "pay_url": reverse("slurp_ui:finance_ar_mark_paid", kwargs={"pk": ar.id}),
                "invoice_id": ar.invoice_id,
            }
        )
    for ap in ap_today:
        today_tasks.append(
            {
                "kind": "ap",
                "urgency": "today",
                "label": ap.vendor_name,
                "detail": ap.invoice_number or "AP",
                "amount": _money(ap.balance),
                "due": ap.due_date,
                "pay_url": reverse("slurp_ui:finance_ap_mark_paid", kwargs={"pk": ap.id}),
                "invoice_id": None,
            }
        )

    # Overdue first, then today; AR before AP within urgency
    urgency_rank = {"overdue": 0, "today": 1}
    today_tasks.sort(key=lambda t: (urgency_rank.get(t["urgency"], 9), 0 if t["kind"] == "ar" else 1, t["label"]))

    return {
        "today_tasks": today_tasks[:20],
        "ar_open_total": ar_open_total,
        "ap_open_total": ap_open_total,
        "ar_due_week": ar_due_week,
        "ap_due_week": ap_due_week,
        "ar_overdue_total": ar_overdue_total,
        "ap_overdue_total": ap_overdue_total,
        "net_week": round(ar_due_week - ap_due_week, 2),
        "overdue_count": len(ar_overdue) + len(ap_overdue),
        "due_today_count": len(ar_today) + len(ap_today),
    }


# ---------------------------------------------------------------------------
# Dashboard & KPIs
# ---------------------------------------------------------------------------


def _month_keys(end: date, months_back: int = 12) -> list[str]:
    """Return YYYY-MM keys for the last N months ending at `end` (inclusive)."""
    keys: list[str] = []
    y, m = end.year, end.month
    for _ in range(months_back):
        keys.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    keys.reverse()
    return keys


def _month_label(key: str) -> str:
    y, m = key.split("-")
    months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    return f"{months[int(m) - 1]} {y[2:]}"


def _family_label(code: str) -> str:
    return (code or "other").replace("_", " ").strip().title() or "Other"


def _aging_bucket_totals(qs, today: date) -> dict[str, float]:
    buckets = {
        "Current": 0.0,
        "1–30": 0.0,
        "31–60": 0.0,
        "61–90": 0.0,
        "90+": 0.0,
    }
    for row in qs:
        bal = float(row.balance or 0)
        if bal <= 0:
            continue
        due = row.due_date
        if due is None or due >= today:
            buckets["Current"] += bal
            continue
        days = (today - due).days
        if days <= 30:
            buckets["1–30"] += bal
        elif days <= 60:
            buckets["31–60"] += bal
        elif days <= 90:
            buckets["61–90"] += bal
        else:
            buckets["90+"] += bal
    return {k: round(v, 2) for k, v in buckets.items()}


def _finance_chart_payload(today: date) -> dict[str, Any]:
    """Live chart series for the Finance dashboard toggles."""
    months = _month_keys(today, 12)
    month_set = set(months)
    start = date(int(months[0][:4]), int(months[0][5:7]), 1)

    revenue: dict[str, float] = {k: 0.0 for k in months}
    cogs: dict[str, float] = {k: 0.0 for k in months}
    opex: dict[str, float] = {k: 0.0 for k in months}

    entries = (
        GeneralLedgerEntry.objects.filter(entry_date__gte=start, entry_date__lte=today)
        .select_related("account")
        .only("amount", "debit_credit", "entry_date", "account__account_type", "account__account_number")
    )
    for entry in entries:
        key = f"{entry.entry_date.year:04d}-{entry.entry_date.month:02d}"
        if key not in month_set:
            continue
        amt = float(entry.amount or 0)
        atype = (entry.account.account_type or "").lower() if entry.account_id else ""
        anum = (entry.account.account_number or "") if entry.account_id else ""
        if atype == "revenue":
            if entry.debit_credit == "credit":
                revenue[key] += amt
            else:
                revenue[key] -= amt
        elif atype == "expense":
            signed = amt if entry.debit_credit == "debit" else -amt
            if anum.startswith("5"):
                cogs[key] += signed
            else:
                opex[key] += signed

    # Invoice totals backfill months with billed AR not yet in GL
    inv_by_month: dict[str, float] = defaultdict(float)
    for inv in Invoice.objects.exclude(status__in=["cancelled", "draft"]).filter(
        invoice_date__gte=start, invoice_date__lte=today
    ).only("invoice_date", "grand_total"):
        d = inv.invoice_date
        if not d:
            continue
        key = f"{d.year:04d}-{d.month:02d}"
        if key in month_set:
            inv_by_month[key] += float(inv.grand_total or 0)
    for key, total in inv_by_month.items():
        if revenue[key] == 0 and total:
            revenue[key] = total

    cash_in: dict[str, float] = {k: 0.0 for k in months}
    cash_out: dict[str, float] = {k: 0.0 for k in months}
    for row in (
        Payment.objects.filter(payment_date__gte=start, payment_date__lte=today)
        .values("payment_date", "payment_type")
        .annotate(s=Sum("amount"))
    ):
        d = row["payment_date"]
        key = f"{d.year:04d}-{d.month:02d}"
        if key not in month_set:
            continue
        if row["payment_type"] == "ar_payment":
            cash_in[key] += float(row["s"] or 0)
        elif row["payment_type"] == "ap_payment":
            cash_out[key] += float(row["s"] or 0)

    # Catalog margin by product family (sell vs landed cost)
    cm_by_sku: dict[str, CostMaster] = {}
    for cm in CostMaster.objects.exclude(wwi_product_code__isnull=True).exclude(wwi_product_code="").order_by(
        "-updated_at"
    ):
        sku = (cm.wwi_product_code or "").strip()
        if sku and sku not in cm_by_sku:
            cm_by_sku[sku] = cm

    price_by_item: dict[int, float] = {}
    for cp in CustomerPricing.objects.filter(is_active=True).order_by("-effective_date"):
        if cp.item_id and cp.item_id not in price_by_item and cp.unit_price:
            price_by_item[cp.item_id] = float(cp.unit_price)

    family_vals: dict[str, list[float]] = defaultdict(list)
    for item in Item.objects.exclude(product_category__isnull=True).exclude(product_category=""):
        sku = (item.sku or "").strip()
        cm = cm_by_sku.get(sku)
        if not cm:
            continue
        cost = cm.landed_cost_per_lb
        if cost is None and cm.landed_cost_per_kg:
            cost = float(cm.landed_cost_per_kg) / 2.20462
        if cost is None and cm.price_per_lb:
            cost = float(cm.price_per_lb)
        if not cost or float(cost) <= 0:
            continue
        sell = price_by_item.get(item.id)
        if sell is None and item.price:
            sell = float(item.price)
        if not sell or sell <= 0:
            continue
        family_vals[item.product_category or "other"].append((sell - float(cost)) / sell * 100)

    margin_families = []
    for code, vals in family_vals.items():
        margin_families.append(
            {
                "family": code,
                "label": _family_label(code),
                "avg_margin_pct": round(sum(vals) / len(vals), 1),
                "item_count": len(vals),
            }
        )
    margin_families.sort(key=lambda r: r["avg_margin_pct"], reverse=True)

    open_statuses = ["open", "partial", "overdue"]
    ar_aging = _aging_bucket_totals(
        AccountsReceivable.objects.filter(status__in=open_statuses).only("balance", "due_date"),
        today,
    )
    ap_aging = _aging_bucket_totals(
        AccountsPayable.objects.filter(status__in=open_statuses).only("balance", "due_date"),
        today,
    )
    aging_labels = list(ar_aging.keys())

    q_start_month = ((today.month - 1) // 3) * 3 + 1
    quarter_key = f"{today.year:04d}-{q_start_month:02d}"
    ytd_key = f"{today.year:04d}-01"
    six_key = months[-6] if len(months) >= 6 else months[0]

    return {
        "default_mode": "rev_exp_cogs",
        "default_range": "quarter",
        "ranges": [
            {"id": "quarter", "label": "Quarter"},
            {"id": "six_month", "label": "6 mo"},
            {"id": "ytd", "label": "YTD"},
            {"id": "twelve_month", "label": "12 mo"},
        ],
        "range_starts": {
            "quarter": quarter_key if quarter_key >= months[0] else months[0],
            "six_month": six_key,
            "ytd": ytd_key if ytd_key >= months[0] else months[0],
            "twelve_month": months[0],
        },
        "labels": [_month_label(k) for k in months],
        "month_keys": months,
        "rev_exp_cogs": {
            "revenue": [round(revenue[k], 2) for k in months],
            "cogs": [round(cogs[k], 2) for k in months],
            "expenses": [round(opex[k], 2) for k in months],
            "note": "GL revenue, COGS (5xxx), and OpEx (6xxx+). Invoice totals fill months with no revenue posts.",
        },
        "cashflow": {
            "cash_in": [round(cash_in[k], 2) for k in months],
            "cash_out": [round(cash_out[k], 2) for k in months],
            "note": "AR payments received vs AP payments made.",
        },
        "margin": {
            "families": margin_families,
            "note": "Catalog margin by family (sell vs landed). Period slicer does not apply.",
        },
        "aging": {
            "labels": aging_labels,
            "ar": [ar_aging[k] for k in aging_labels],
            "ap": [ap_aging[k] for k in aging_labels],
            "note": "Open AR/AP by days past due. Period slicer does not apply.",
        },
    }


@login_required
def finance_dashboard(request: HttpRequest) -> HttpResponse:
    """Cash calendar + today's AR/AP tasks + invoicing glance."""
    today = timezone.localdate()
    cal = _finance_calendar_context(request, base_path=reverse("slurp_ui:finance"))
    board = _finance_today_board(today)
    chart_payload = _finance_chart_payload(today)

    draft = Invoice.objects.filter(status="draft").count()
    issued = Invoice.objects.filter(status__in=["sent", "overdue"]).count()
    paid = Invoice.objects.filter(status="paid").count()
    ar_open = AccountsReceivable.objects.exclude(status__in=["paid", "cancelled"]).count()
    ap_open = AccountsPayable.objects.exclude(status__in=["paid", "cancelled"]).count()
    draft_rows = list(
        Invoice.objects.filter(status="draft")
        .select_related("sales_order")
        .order_by("-invoice_date", "-id")[:4]
    )
    for inv in draft_rows:
        inv.status_label = _status_label(inv.status)

    return render(
        request,
        "slurp_ui/finance/dashboard.html",
        _finance_ctx(
            "dashboard",
            draft_count=draft,
            issued_count=issued,
            paid_count=paid,
            ar_open=ar_open,
            ap_open=ap_open,
            draft_invoices=draft_rows,
            chart_payload=chart_payload,
            **board,
            **cal,
            port_status="full",
        ),
    )


@login_required
def finance_calendar(request: HttpRequest) -> HttpResponse:
    """Full-page Finance cash calendar (AR/AP due dates)."""
    cal = _finance_calendar_context(request, base_path=reverse("slurp_ui:finance_calendar"))
    board = _finance_today_board(timezone.localdate())
    return render(
        request,
        "slurp_ui/finance/calendar.html",
        _finance_ctx(
            "calendar",
            due_today_count=board["due_today_count"],
            overdue_count=board["overdue_count"],
            ar_due_week=board["ar_due_week"],
            ap_due_week=board["ap_due_week"],
            **cal,
            port_status="full",
        ),
    )


@login_required
def finance_kpis(request: HttpRequest) -> HttpResponse:
    """Legacy URL — shipping KPIs live under Sales now."""
    qs = request.GET.urlencode()
    target = reverse("slurp_ui:sales_kpis")
    if qs:
        target = f"{target}?{qs}"
    return redirect(target)


# ---------------------------------------------------------------------------
# General Ledger & accounts
# ---------------------------------------------------------------------------


@login_required
def finance_ledger(request: HttpRequest) -> HttpResponse:
    accounts = Account.objects.filter(is_active=True).order_by("account_number")[:500]
    return render(
        request,
        "slurp_ui/finance/ledger.html",
        _finance_ctx("ledger", accounts=accounts, port_status="full"),
    )


@login_required
@require_http_methods(["GET", "POST"])
def finance_account_create(request: HttpRequest) -> HttpResponse:
    parent_accounts = Account.objects.filter(is_active=True).order_by("account_number")
    if request.method == "POST":
        try:
            parent = request.POST.get("parent_account") or None
            create_account(
                account_number=request.POST.get("account_number", ""),
                name=request.POST.get("name", ""),
                account_type=request.POST.get("account_type", "asset"),
                parent_account_id=int(parent) if parent else None,
                description=request.POST.get("description"),
            )
            messages.success(request, "Account created.")
            return redirect("slurp_ui:finance_ledger")
        except FinanceFormError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))
    return render(
        request,
        "slurp_ui/finance/account_create.html",
        _finance_ctx("ledger", parent_accounts=parent_accounts, port_status="full"),
    )


# ---------------------------------------------------------------------------
# Journal entries
# ---------------------------------------------------------------------------


@login_required
def finance_journal(request: HttpRequest) -> HttpResponse:
    status_filter = (request.GET.get("status") or "").strip()
    entries = JournalEntry.objects.prefetch_related("lines", "lines__account").all()
    if status_filter:
        entries = entries.filter(status=status_filter)
    entries = list(entries.order_by("-entry_date", "-created_at")[:200])
    for je in entries:
        je.total_debits = sum(l.amount for l in je.lines.all() if l.debit_credit == "debit")
        je.total_credits = sum(l.amount for l in je.lines.all() if l.debit_credit == "credit")
    return render(
        request,
        "slurp_ui/finance/journal.html",
        _finance_ctx(
            "journal",
            entries=entries,
            status_filter=status_filter,
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def finance_journal_create(request: HttpRequest) -> HttpResponse:
    accounts = Account.objects.filter(is_active=True).order_by("account_number")
    if request.method == "POST":
        lines = []
        idx = 0
        while True:
            acct = request.POST.get(f"line_{idx}_account")
            if acct is None:
                break
            amt = request.POST.get(f"line_{idx}_amount")
            dc = request.POST.get(f"line_{idx}_debit_credit")
            if acct and amt:
                lines.append(
                    {
                        "account": acct,
                        "amount": amt,
                        "debit_credit": dc or "debit",
                        "description": request.POST.get(f"line_{idx}_description", ""),
                    }
                )
            idx += 1
        try:
            create_journal_entry(
                request.user,
                entry_date=request.POST.get("entry_date"),
                description=request.POST.get("description", ""),
                reference_number=request.POST.get("reference_number"),
                lines=lines,
            )
            messages.success(request, "Journal entry created.")
            return redirect("slurp_ui:finance_journal")
        except FinanceFormError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))
    return render(
        request,
        "slurp_ui/finance/journal_create.html",
        _finance_ctx("journal", accounts=accounts, port_status="full"),
    )


@login_required
@require_POST
def finance_journal_post(request: HttpRequest, pk: int) -> HttpResponse:
    try:
        post_journal_entry(request.user, pk)
        messages.success(request, "Journal entry posted.")
    except FinanceFormError as e:
        messages.error(request, e.message)
    except Exception as e:
        messages.error(request, str(e))
    return redirect("slurp_ui:finance_journal")


# ---------------------------------------------------------------------------
# Fiscal periods
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def finance_periods(request: HttpRequest) -> HttpResponse:
    if request.method == "POST" and request.POST.get("action") == "create":
        try:
            create_fiscal_period(
                period_name=request.POST.get("period_name", ""),
                start_date=request.POST.get("start_date"),
                end_date=request.POST.get("end_date"),
                notes=request.POST.get("notes"),
            )
            messages.success(request, "Fiscal period created.")
            return redirect("slurp_ui:finance_periods")
        except FinanceFormError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))

    periods = FiscalPeriod.objects.all().order_by("-start_date")[:100]
    return render(
        request,
        "slurp_ui/finance/periods.html",
        _finance_ctx("periods", periods=periods, port_status="full"),
    )


@login_required
@require_POST
def finance_period_close(request: HttpRequest, pk: int) -> HttpResponse:
    try:
        close_fiscal_period(request.user, pk)
        messages.success(request, "Fiscal period closed.")
    except FinanceFormError as e:
        messages.error(request, e.message)
    except Exception as e:
        messages.error(request, str(e))
    return redirect("slurp_ui:finance_periods")


# ---------------------------------------------------------------------------
# Bank reconciliation
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def finance_bank_recon(request: HttpRequest) -> HttpResponse:
    bank_accounts = Account.objects.filter(
        is_active=True, account_type="asset"
    ).filter(
        Q(account_number__startswith="10")
        | Q(name__icontains="cash")
        | Q(name__icontains="bank")
        | Q(name__icontains="checking")
    ).order_by("account_number")

    if request.method == "POST":
        try:
            create_bank_reconciliation(
                account_id=request.POST.get("account"),
                statement_date=request.POST.get("statement_date"),
                statement_balance=request.POST.get("statement_balance"),
                notes=request.POST.get("notes"),
            )
            messages.success(request, "Bank reconciliation saved.")
            return redirect("slurp_ui:finance_bank_recon")
        except FinanceFormError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))

    recons = BankReconciliation.objects.select_related("account").order_by("-statement_date")[:100]
    rows = []
    for r in recons:
        try:
            gl_bal = gl_balance_for_account(r.account_id, r.statement_date)
        except Exception:
            gl_bal = None
        rows.append({"recon": r, "gl_balance": gl_bal, "variance": (gl_bal - r.statement_balance) if gl_bal is not None else None})

    return render(
        request,
        "slurp_ui/finance/bank_recon.html",
        _finance_ctx(
            "bank-recon",
            recons=rows,
            bank_accounts=bank_accounts,
            port_status="partial",
        ),
    )


# ---------------------------------------------------------------------------
# Invoices (existing + create / mark paid)
# ---------------------------------------------------------------------------


@login_required
def finance_invoices(request: HttpRequest) -> HttpResponse:
    """Unified Invoicing workspace: invoice register + receivables."""
    tab = (request.GET.get("tab") or "register").strip().lower()
    if tab not in ("register", "ar"):
        tab = "register"

    status_filter = (request.GET.get("status") or "").strip()
    ar_status_filter = (request.GET.get("ar_status") or "").strip()

    invoices = []
    ar_entries = []
    if tab == "ar":
        qs = AccountsReceivable.objects.select_related("invoice", "sales_order").order_by("due_date")
        if ar_status_filter:
            qs = qs.filter(status=ar_status_filter)
        ar_entries = list(qs[:200])
    else:
        inv_qs = Invoice.objects.select_related("sales_order").order_by("-created_at")
        if status_filter:
            inv_qs = inv_qs.filter(status=status_filter)
        invoices = list(inv_qs[:200])
        for inv in invoices:
            inv.status_label = _status_label(inv.status)

    return render(
        request,
        "slurp_ui/finance/invoicing.html",
        _finance_ctx(
            "invoicing",
            tab=tab,
            invoices=invoices,
            ar_entries=ar_entries,
            status_filter=status_filter,
            ar_status_filter=ar_status_filter,
            port_status="full",
        ),
    )


@login_required
def finance_ar(request: HttpRequest) -> HttpResponse:
    """Legacy AR URL → unified Invoicing workspace (Receivables tab)."""
    params = request.GET.copy()
    params["tab"] = "ar"
    if params.get("status") and not params.get("ar_status"):
        params["ar_status"] = params.get("status")
    qs = params.urlencode()
    target = reverse("slurp_ui:finance_invoices")
    return redirect(f"{target}?{qs}" if qs else f"{target}?tab=ar")


@login_required
@require_http_methods(["GET", "POST"])
def finance_invoice_create(request: HttpRequest) -> HttpResponse:
    items = Item.objects.filter(
        item_type__in=["finished_good", "distributed_item"]
    ).order_by("sku")[:500]
    if request.method == "POST":
        line_items = []
        idx = 0
        while True:
            item_id = request.POST.get(f"line_{idx}_item")
            if item_id is None:
                break
            qty = request.POST.get(f"line_{idx}_quantity")
            if item_id and qty:
                up = float(request.POST.get(f"line_{idx}_unit_price") or 0)
                q = float(qty)
                line_items.append(
                    {
                        "item_id": item_id,
                        "description": request.POST.get(f"line_{idx}_description", ""),
                        "quantity": q,
                        "unit_price": up,
                        "line_total": q * up,
                    }
                )
            idx += 1
        try:
            inv = create_manual_invoice(
                customer_vendor_name=request.POST.get("customer_vendor_name", ""),
                customer_vendor_id=request.POST.get("customer_vendor_id"),
                invoice_date=request.POST.get("invoice_date"),
                due_date=request.POST.get("due_date") or None,
                tax=request.POST.get("tax") or 0,
                freight=request.POST.get("freight") or 0,
                discount=request.POST.get("discount") or 0,
                notes=request.POST.get("notes"),
                invoice_number=request.POST.get("invoice_number") or None,
                items=line_items,
            )
            messages.success(request, f"Created draft invoice {inv.invoice_number}.")
            return redirect("slurp_ui:finance_invoice_detail", pk=inv.pk)
        except FinanceFormError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))
    return render(
        request,
        "slurp_ui/finance/invoice_create.html",
        _finance_ctx("invoicing", items=items, port_status="full"),
    )


@login_required
def finance_invoice_detail(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = get_object_or_404(
        Invoice.objects.select_related("sales_order", "sales_order__customer").prefetch_related(
            "items__item", "items__sales_order_item"
        ),
        pk=pk,
    )
    return render(
        request,
        "slurp_ui/finance/invoice_detail.html",
        _finance_ctx(
            "invoicing",
            invoice=invoice,
            status_label=_status_label(invoice.status),
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def finance_invoice_issue(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = get_object_or_404(
        Invoice.objects.select_related("sales_order"),
        pk=pk,
    )
    if invoice.status != "draft":
        messages.warning(
            request,
            f"Invoice {invoice.invoice_number} is {_status_label(invoice.status)}, not draft.",
        )
        return redirect("slurp_ui:finance_invoice_detail", pk=pk)

    so = invoice.sales_order
    if request.method == "POST":
        carrier = (request.POST.get("carrier") or "").strip() or None
        tracking = (request.POST.get("tracking_number") or "").strip() or None
        try:
            issue_invoice(invoice, carrier=carrier, tracking_number=tracking)
            messages.success(request, f"Issued invoice {invoice.invoice_number}.")
            return redirect("slurp_ui:finance_invoice_detail", pk=pk)
        except InvoiceFlowError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "slurp_ui/finance/invoice_issue.html",
        _finance_ctx(
            "invoicing",
            invoice=invoice,
            so=so,
            port_status="full",
        ),
    )


@login_required
def finance_invoice_pdf(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = get_object_or_404(
        Invoice.objects.select_related("sales_order").prefetch_related("items__item"),
        pk=pk,
    )
    try:
        from erp_core.invoice_pdf_html import generate_invoice_pdf_from_html

        pdf_bytes = generate_invoice_pdf_from_html(invoice)
    except Exception as e:
        messages.error(request, f"PDF generation failed: {e}")
        return redirect("slurp_ui:finance_invoice_detail", pk=pk)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    filename = f"{invoice.invoice_number or f'invoice-{pk}'}.pdf"
    disposition = "attachment" if request.GET.get("download") else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    return response


@login_required
@require_POST
def finance_invoice_cancel(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = get_object_or_404(Invoice, pk=pk)
    try:
        cancel_invoice(invoice)
        messages.success(request, f"Voided invoice {invoice.invoice_number}.")
    except InvoiceFlowError as e:
        messages.error(request, e.message)
    except Exception as e:
        messages.error(request, str(e))
    return redirect("slurp_ui:finance_invoice_detail", pk=pk)


@login_required
@require_POST
def finance_invoice_mark_paid(request: HttpRequest, pk: int) -> HttpResponse:
    invoice = get_object_or_404(Invoice, pk=pk)
    try:
        mark_invoice_paid(invoice)
        messages.success(request, f"Invoice {invoice.invoice_number} marked paid.")
    except FinanceFormError as e:
        messages.error(request, e.message)
    except Exception as e:
        messages.error(request, str(e))
    return redirect("slurp_ui:finance_invoice_detail", pk=pk)


# ---------------------------------------------------------------------------
# AR / AP / payments
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def finance_ar_mark_paid(request: HttpRequest, pk: int) -> HttpResponse:
    ar = get_object_or_404(
        AccountsReceivable.objects.select_related("invoice"),
        pk=pk,
    )
    ar_list_url = reverse("slurp_ui:finance_invoices") + "?tab=ar"
    if ar.status in ("paid", "cancelled"):
        messages.info(request, "This AR entry is already closed.")
        return redirect(ar_list_url)

    if request.method == "POST":
        try:
            _payment, days = mark_ar_as_paid(
                ar,
                payment_date=request.POST.get("payment_date"),
                reference_number=request.POST.get("reference_number"),
                notes=request.POST.get("notes"),
            )
            inv_label = ar.invoice.invoice_number if ar.invoice_id and ar.invoice else "AR"
            timing = ""
            if days is not None:
                if days < 0:
                    timing = f" ({abs(days)} day{'s' if abs(days) != 1 else ''} early)"
                elif days > 0:
                    timing = f" ({days} day{'s' if days != 1 else ''} late)"
                else:
                    timing = " (on time)"
            messages.success(request, f"Marked {inv_label} paid{timing}.")
            return redirect(ar_list_url)
        except FinanceFormError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "slurp_ui/finance/ar_mark_paid.html",
        _finance_ctx(
            "invoicing",
            ar=ar,
            today=timezone.localdate(),
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def finance_payment_entry(request: HttpRequest) -> HttpResponse:
    payment_type = request.GET.get("type") or request.POST.get("payment_type") or "ar_payment"
    ar_entry_id = request.GET.get("ar_entry") or request.POST.get("ar_entry")
    ap_entry_id = request.GET.get("ap_entry") or request.POST.get("ap_entry")

    cash_accounts = Account.objects.filter(is_active=True, account_type="asset").order_by("account_number")
    open_ar = AccountsReceivable.objects.filter(
        status__in=["open", "partial", "overdue"]
    ).select_related("invoice").order_by("customer_name")[:200]
    open_ap = AccountsPayable.objects.filter(
        status__in=["open", "partial", "overdue"]
    ).order_by("vendor_name")[:200]

    if request.method == "POST":
        try:
            create_payment(
                payment_type=request.POST.get("payment_type"),
                payment_date=request.POST.get("payment_date"),
                payment_method=request.POST.get("payment_method", "check"),
                amount=request.POST.get("amount"),
                account_id=request.POST.get("account") or None,
                ap_entry_id=request.POST.get("ap_entry") or None,
                ar_entry_id=request.POST.get("ar_entry") or None,
                reference_number=request.POST.get("reference_number"),
                notes=request.POST.get("notes"),
            )
            messages.success(request, "Payment recorded.")
            if request.POST.get("payment_type") == "ap_payment":
                return redirect("slurp_ui:finance_ap")
            return redirect(reverse("slurp_ui:finance_invoices") + "?tab=ar")
        except FinanceFormError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "slurp_ui/finance/payment_entry.html",
        _finance_ctx(
            "invoicing" if payment_type == "ar_payment" else "ap",
            payment_type=payment_type,
            cash_accounts=cash_accounts,
            open_ar=open_ar,
            open_ap=open_ap,
            ar_entry_id=ar_entry_id,
            ap_entry_id=ap_entry_id,
            port_status="full",
        ),
    )


@login_required
def finance_ap(request: HttpRequest) -> HttpResponse:
    status_filter = (request.GET.get("status") or "").strip()
    vendor_filter = (request.GET.get("vendor") or "").strip()
    qs = AccountsPayable.objects.select_related("purchase_order").order_by("due_date")
    if status_filter:
        qs = qs.filter(status=status_filter)
    if vendor_filter:
        qs = qs.filter(vendor_name__icontains=vendor_filter)
    entries = list(qs[:200])
    aging = None
    try:
        aging = aging_totals_for_dashboard(get_ap_aging(request.user))
    except Exception:
        pass
    return render(
        request,
        "slurp_ui/finance/ap.html",
        _finance_ctx(
            "ap",
            entries=entries,
            status_filter=status_filter,
            vendor_filter=vendor_filter,
            aging=aging,
            port_status="partial",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def finance_ap_mark_paid(request: HttpRequest, pk: int) -> HttpResponse:
    ap = get_object_or_404(AccountsPayable, pk=pk)
    if ap.status in ("paid", "cancelled"):
        messages.info(request, "This AP entry is already closed.")
        return redirect("slurp_ui:finance_ap")

    if request.method == "POST":
        try:
            _payment, days = mark_ap_as_paid(
                ap,
                payment_date=request.POST.get("payment_date"),
                payment_method=request.POST.get("payment_method") or "check",
                reference_number=request.POST.get("reference_number"),
                notes=request.POST.get("notes"),
            )
            label = ap.invoice_number or ap.vendor_name
            timing = ""
            if days is not None:
                if days < 0:
                    timing = f" ({abs(days)} day{'s' if abs(days) != 1 else ''} early)"
                elif days > 0:
                    timing = f" ({days} day{'s' if days != 1 else ''} late)"
                else:
                    timing = " (on time)"
            messages.success(request, f"Marked {label} paid{timing}.")
            return redirect("slurp_ui:finance_ap")
        except FinanceFormError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "slurp_ui/finance/ap_mark_paid.html",
        _finance_ctx(
            "ap",
            ap=ap,
            today=timezone.localdate(),
            port_status="full",
        ),
    )


# ---------------------------------------------------------------------------
# Pricing (Sales owns customer prices; Finance URLs redirect)
# ---------------------------------------------------------------------------


@login_required
def finance_pricing(request: HttpRequest) -> HttpResponse:
    """Legacy Finance Pricing — customer prices live on Sales customer profiles."""
    messages.info(
        request,
        "Customer pricing is managed on each Sales customer profile (Pricing tab).",
    )
    return redirect("slurp_ui:sales")


@login_required
@require_http_methods(["GET", "POST"])
def finance_pricing_customer_create(request: HttpRequest) -> HttpResponse:
    messages.info(
        request,
        "Add customer prices from the Sales customer profile → Pricing.",
    )
    return redirect("slurp_ui:sales")


@login_required
@require_http_methods(["GET", "POST"])
def finance_pricing_vendor_create(request: HttpRequest) -> HttpResponse:
    messages.info(
        request,
        "Vendor list prices will hang off Quality vendors; Costing covers landed cost for now.",
    )
    return redirect(reverse("slurp_ui:finance_costing") + "?tab=master")


# ---------------------------------------------------------------------------
# Costing workspace (Cost Master / R&D / RM lot costs / What-if)
# ---------------------------------------------------------------------------


def _parse_optional_float(raw):
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    if s == "":
        return None
    return float(s)


def _whatif_line_payload(line: PricingWhatIfLine) -> dict:
    return {
        "id": line.pk,
        "sort_order": line.sort_order,
        "customer_name": line.customer_name or "",
        "close_probability": float(line.close_probability or 0),
        "win_pct": round(float(line.close_probability or 0) * 100, 2),
        "source_type": line.source_type,
        "product_name": line.product_name or "",
        "catalog_key": line.catalog_key or "",
        "rd_formula_id": line.rd_formula_id,
        "cost_master_id": line.cost_master_id,
        "cost_scenario_id": line.cost_scenario_id,
        "ingredient_overrides": line.ingredient_overrides or {},
        "base_cost_per_lb": line.base_cost_per_lb,
        "cost_is_manual": bool(line.cost_is_manual),
        "tariff_rate": float(line.tariff_rate or 0),
        "tariff_pct": round(float(line.tariff_rate or 0) * 100, 4),
        "freight_per_lb": float(line.freight_per_lb or 0),
        "freight_per_kg": float(line.freight_per_kg or 0),
        "landed_whatif_per_lb": line.landed_whatif_per_lb,
        "additional_cost_per_lb": float(line.additional_cost_per_lb or 0),
        "margin": line.margin,
        "margin_pct": round(float(line.margin) * 100, 4) if line.margin is not None else None,
        "volume_lb": line.volume_lb,
        "volume_pct_target": line.volume_pct_target,
        "agreement": line.agreement or "",
        "incoterms": line.incoterms or "",
        "first_order_ship": line.first_order_ship or "",
        "order_pattern": line.order_pattern or "",
        "notes": line.notes or "",
        "price_per_lb": line.price_per_lb,
        "annual_revenue": line.annual_revenue,
        "gross_profit": line.gross_profit,
        "weighted_revenue": line.weighted_revenue,
    }


def _whatif_json_body(request: HttpRequest) -> dict:
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e
    return {k: request.POST.get(k) for k in request.POST.keys()}


@login_required
@require_POST
def finance_whatif_lookup_cost(request: HttpRequest) -> HttpResponse:
    """Resolve catalog selection / product → cost (Cost Master or R&D formula)."""
    from ..pricing_whatif import formula_ingredient_payload, resolve_catalog_selection

    try:
        data = _whatif_json_body(request)
    except ValueError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)

    overrides = data.get("ingredient_overrides") if isinstance(data.get("ingredient_overrides"), dict) else {}
    kind, cost, cm, rd, label = resolve_catalog_selection(
        catalog_key=data.get("catalog_key"),
        product_name=data.get("product_name"),
        source_type=data.get("source_type"),
    )
    if rd and overrides:
        from ..pricing_whatif import compute_formula_cost

        cost = compute_formula_cost(rd, overrides)

    from ..pricing_whatif import cm_freight_per_lb

    tariff_rate = 0.0
    freight_lb = 0.0
    if cm is not None:
        tariff_rate = float(cm.tariff or 0)
        freight_lb = cm_freight_per_lb(cm)
    landed = None
    if cost is not None:
        landed = float(cost) * (1.0 + tariff_rate) + freight_lb

    payload = {
        "ok": True,
        "cost": float(cost) if cost is not None else None,
        "base_cost_per_lb": float(cost) if cost is not None else None,
        "tariff_rate": tariff_rate,
        "tariff_pct": round(tariff_rate * 100, 4),
        "freight_per_lb": freight_lb,
        "freight_per_kg": freight_lb * 2.2,
        "landed_whatif_per_lb": landed,
        "matched": label,
        "source_type": kind,
        "product_name": label or (data.get("product_name") or ""),
        "catalog_key": (
            f"cm:{cm.pk}" if cm else (f"rd:{rd.pk}" if rd else (data.get("catalog_key") or ""))
        ),
        "rd_formula_id": rd.pk if rd else None,
        "cost_master_id": cm.pk if cm else None,
        "formula": formula_ingredient_payload(rd, overrides) if rd else None,
    }
    return JsonResponse(payload)


@login_required
@require_http_methods(["GET"])
def finance_whatif_formula(request: HttpRequest, pk: int) -> HttpResponse:
    """Ingredient breakdown + vendor options for an R&D formula."""
    from ..pricing_whatif import formula_ingredient_payload

    rd = get_object_or_404(RDFormula.objects.prefetch_related("lines__item"), pk=pk)
    overrides = {}
    raw = (request.GET.get("overrides") or "").strip()
    if raw:
        try:
            overrides = json.loads(raw)
        except json.JSONDecodeError:
            overrides = {}
    return JsonResponse({"ok": True, "formula": formula_ingredient_payload(rd, overrides)})


@login_required
@require_POST
def finance_whatif_scenario_save(request: HttpRequest) -> HttpResponse:
    """Save named ingredient override pack for a formula."""
    from erp_core.models import PricingWhatIfScenario

    try:
        data = _whatif_json_body(request)
    except ValueError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)

    name = (data.get("name") or "").strip()
    try:
        rd_id = int(data.get("rd_formula_id"))
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "rd_formula_id required."}, status=400)
    if not name:
        return JsonResponse({"ok": False, "error": "Scenario name required."}, status=400)
    rd = get_object_or_404(RDFormula, pk=rd_id)
    overrides = data.get("overrides") if isinstance(data.get("overrides"), dict) else {}
    scenario_id = data.get("id")
    if scenario_id:
        scenario = get_object_or_404(PricingWhatIfScenario, pk=scenario_id, rd_formula=rd)
        scenario.name = name
        scenario.overrides = overrides
        scenario.notes = (data.get("notes") or "").strip()
        scenario.save()
    else:
        scenario = PricingWhatIfScenario.objects.create(
            name=name,
            rd_formula=rd,
            overrides=overrides,
            notes=(data.get("notes") or "").strip(),
        )
    return JsonResponse(
        {
            "ok": True,
            "scenario": {"id": scenario.pk, "name": scenario.name, "rd_formula_id": rd.pk},
        }
    )


@login_required
@require_POST
def finance_whatif_line_save(request: HttpRequest) -> HttpResponse:
    """Create or update one what-if line (autosave). Accepts margin_pct / win_pct / overrides."""
    from erp_core.models import PricingWhatIfScenario
    from ..pricing_whatif import refresh_line_cost, resolve_catalog_selection

    try:
        data = _whatif_json_body(request)
    except ValueError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)

    pk = data.get("id")
    if pk in ("", None, "new"):
        pk = None
    else:
        try:
            pk = int(pk)
        except (TypeError, ValueError):
            return JsonResponse({"ok": False, "error": "Invalid line id."}, status=400)

    if pk:
        line = get_object_or_404(PricingWhatIfLine, pk=pk)
    else:
        max_order = (
            PricingWhatIfLine.objects.order_by("-sort_order").values_list("sort_order", flat=True).first()
            or 0
        )
        line = PricingWhatIfLine(sort_order=max_order + 1, margin=0.30, close_probability=0.5)

    line.customer_name = (data.get("customer_name") or "").strip()

    new_key = (data.get("catalog_key") or "").strip()
    key_changed = new_key != (line.catalog_key or "")
    if "catalog_key" in data:
        line.catalog_key = new_key

    new_product = (data.get("product_name") or "").strip()
    product_changed = new_product != (line.product_name or "")
    if "product_name" in data:
        line.product_name = new_product

    if "ingredient_overrides" in data and isinstance(data.get("ingredient_overrides"), dict):
        line.ingredient_overrides = data["ingredient_overrides"]

    if data.get("cost_scenario_id") in (None, "", 0, "0"):
        if "cost_scenario_id" in data:
            line.cost_scenario = None
    else:
        try:
            sid = int(data.get("cost_scenario_id"))
            scenario = PricingWhatIfScenario.objects.filter(pk=sid).first()
            if scenario:
                line.cost_scenario = scenario
                if data.get("apply_scenario"):
                    line.ingredient_overrides = scenario.overrides or {}
                    line.catalog_key = line.catalog_key or f"rd:{scenario.rd_formula_id}"
                    line.rd_formula_id = scenario.rd_formula_id
        except (TypeError, ValueError):
            pass

    src = (data.get("source_type") or line.source_type or "distributed").strip()
    if src not in ("distributed", "manufactured", "rd"):
        src = "distributed"
    line.source_type = src

    if "margin_pct" in data and data.get("margin_pct") not in (None, ""):
        try:
            line.margin = max(0.0, min(0.99, float(data["margin_pct"]) / 100.0))
        except (TypeError, ValueError):
            pass
    elif "margin" in data:
        line.margin = _parse_optional_float(data.get("margin"))

    if "win_pct" in data and data.get("win_pct") not in (None, ""):
        try:
            line.close_probability = max(0.0, min(1.0, float(data["win_pct"]) / 100.0))
        except (TypeError, ValueError):
            pass
    elif "close_probability" in data:
        try:
            line.close_probability = max(0.0, min(1.0, float(data.get("close_probability") or 0)))
        except (TypeError, ValueError):
            line.close_probability = 0.0

    line.volume_lb = _parse_optional_float(data.get("volume_lb"))
    line.volume_pct_target = _parse_optional_float(data.get("volume_pct_target"))
    if "additional_cost_per_lb" in data:
        try:
            line.additional_cost_per_lb = float(data.get("additional_cost_per_lb") or 0)
        except (TypeError, ValueError):
            line.additional_cost_per_lb = 0.0

    line.agreement = (data.get("agreement") or "").strip()
    line.incoterms = (data.get("incoterms") or "").strip()
    line.first_order_ship = (data.get("first_order_ship") or "").strip()
    line.order_pattern = (data.get("order_pattern") or "").strip()
    line.notes = (data.get("notes") or "").strip()

    # What-if trade stack (applied to ex-works / formula base — never on top of CM landed)
    if "tariff_pct" in data and data.get("tariff_pct") not in (None, ""):
        try:
            line.tariff_rate = max(0.0, float(data["tariff_pct"]) / 100.0)
        except (TypeError, ValueError):
            pass
    elif "tariff_rate" in data and data.get("tariff_rate") not in (None, ""):
        try:
            line.tariff_rate = max(0.0, float(data["tariff_rate"]))
        except (TypeError, ValueError):
            pass

    if "freight_per_kg" in data and data.get("freight_per_kg") not in (None, "") and "freight_per_lb" not in data:
        try:
            line.freight_per_lb = max(0.0, float(data["freight_per_kg"]) / 2.2)
        except (TypeError, ValueError):
            pass
    elif "freight_per_lb" in data and data.get("freight_per_lb") not in (None, ""):
        try:
            line.freight_per_lb = max(0.0, float(data["freight_per_lb"]))
        except (TypeError, ValueError):
            pass

    force_lookup = bool(data.get("refresh_cost") or data.get("apply_scenario"))
    reset_trade = bool(data.get("reset_trade") or key_changed or product_changed)
    overrides_changed = "ingredient_overrides" in data
    manual_flag = data.get("cost_is_manual")
    is_manual = manual_flag is True or manual_flag == "1" or manual_flag == 1

    if line.catalog_key or force_lookup or key_changed or product_changed:
        kind, _cost, cm, rd, label = resolve_catalog_selection(
            catalog_key=line.catalog_key,
            product_name=line.product_name,
            source_type=line.source_type,
        )
        if kind:
            line.source_type = kind
        if cm:
            line.cost_master = cm
        if rd:
            line.rd_formula = rd
        if label and (key_changed or not line.product_name):
            line.product_name = label

    if is_manual and not force_lookup and not overrides_changed:
        line.cost_is_manual = True
        cost_val = _parse_optional_float(data.get("base_cost_per_lb"))
        if cost_val is not None:
            line.base_cost_per_lb = cost_val
    elif force_lookup or key_changed or product_changed or overrides_changed or data.get("apply_scenario"):
        line.cost_is_manual = False
        # Don't let refresh overwrite user tariff/freight just scrubbed unless product changed.
        trade_from_client = ("tariff_pct" in data or "tariff_rate" in data or "freight_per_lb" in data or "freight_per_kg" in data)
        refresh_line_cost(
            line,
            force=True,
            reset_trade=reset_trade and not (trade_from_client and not key_changed and not product_changed),
        )
        if trade_from_client and not key_changed and not product_changed:
            if "tariff_pct" in data and data.get("tariff_pct") not in (None, ""):
                try:
                    line.tariff_rate = max(0.0, float(data["tariff_pct"]) / 100.0)
                except (TypeError, ValueError):
                    pass
            elif "tariff_rate" in data and data.get("tariff_rate") not in (None, ""):
                try:
                    line.tariff_rate = max(0.0, float(data["tariff_rate"]))
                except (TypeError, ValueError):
                    pass
            if "freight_per_kg" in data and data.get("freight_per_kg") not in (None, "") and "freight_per_lb" not in data:
                try:
                    line.freight_per_lb = max(0.0, float(data["freight_per_kg"]) / 2.2)
                except (TypeError, ValueError):
                    pass
            elif "freight_per_lb" in data and data.get("freight_per_lb") not in (None, ""):
                try:
                    line.freight_per_lb = max(0.0, float(data["freight_per_lb"]))
                except (TypeError, ValueError):
                    pass
    else:
        line.cost_is_manual = False
        if data.get("base_cost_per_lb") not in (None, ""):
            cost_val = _parse_optional_float(data.get("base_cost_per_lb"))
            if cost_val is not None:
                line.base_cost_per_lb = cost_val
        elif line.base_cost_per_lb is None and (line.product_name or line.catalog_key):
            refresh_line_cost(line, force=True, reset_trade=False)

    line.save()
    from ..pricing_whatif import formula_ingredient_payload

    formula = None
    if line.rd_formula_id:
        rd = RDFormula.objects.prefetch_related("lines__item").filter(pk=line.rd_formula_id).first()
        if rd:
            formula = formula_ingredient_payload(rd, line.ingredient_overrides)
    return JsonResponse({"ok": True, "line": _whatif_line_payload(line), "formula": formula})


@login_required
@require_POST
def finance_whatif_line_delete(request: HttpRequest, pk: int) -> HttpResponse:
    deleted, _ = PricingWhatIfLine.objects.filter(pk=pk).delete()
    return JsonResponse({"ok": True, "deleted": bool(deleted), "id": pk})


@login_required
@require_http_methods(["GET"])
def finance_costing(request: HttpRequest) -> HttpResponse:
    tab = (request.GET.get("tab") or "whatif").strip().lower()
    if tab not in ("master", "rd", "lots", "whatif"):
        tab = "whatif"

    search = (request.GET.get("q") or "").strip()
    ctx = {
        "tab": tab,
        "search": search,
        "rows": [],
        "formulas": [],
        "counts": {},
        "rd_q": "",
        "rd_status": "active",
        "profile": None,
        "expand_id": None,
        "port_status": "partial",
        "whatif_lines": [],
        "whatif_totals": {},
        "whatif_catalog": {"distributed": [], "manufactured": []},
        "agreement_choices": PricingWhatIfLine.AGREEMENT_CHOICES,
    }

    if tab == "whatif":
        from ..pricing_whatif import pipeline_totals, product_catalog

        lines = list(PricingWhatIfLine.objects.select_related("cost_master", "rd_formula").all())
        import json as _json

        for _line in lines:
            _line.overrides_json = _json.dumps(_line.ingredient_overrides or {})
        ctx.update(
            {
                "whatif_lines": lines,
                "whatif_totals": pipeline_totals(lines),
                "whatif_catalog": product_catalog(),
                "port_status": "full",
            }
        )
    elif tab == "rd":
        from ..rd_formula_workspace import rd_formula_counts, rd_formula_list_queryset

        rd_status = (request.GET.get("status") or "active").strip().lower()
        rd_q = search
        ctx.update(
            {
                "rd_status": rd_status,
                "rd_q": rd_q,
                "formulas": rd_formula_list_queryset(status=rd_status, q=rd_q),
                "counts": rd_formula_counts(),
                "port_status": "full",
            }
        )
    elif tab == "lots":
        rows = list(commercial_raw_cost_masters())
        if search:
            s = search.lower()
            rows = [
                r
                for r in rows
                if s in (r.vendor_material or "").lower()
                or s in (r.wwi_product_code or "").lower()
                or s in (r.vendor or "").lower()
            ]
        expand_id = request.GET.get("expand")
        profile = None
        if expand_id and str(expand_id).isdigit():
            try:
                profile = get_lot_cost_profile(int(expand_id))
            except Exception as e:
                messages.warning(request, f"Could not load lot profile: {e}")
        actuals = {}
        try:
            actuals = get_cost_master_actuals(request.user, [r.id for r in rows[:100]]) or {}
        except Exception:
            pass
        for r in rows:
            a = actuals.get(r.id) or actuals.get(str(r.id)) or {}
            r.actual_comparison = a.get("comparison", "—")
        ctx.update(
            {
                "rows": rows,
                "expand_id": int(expand_id) if expand_id and str(expand_id).isdigit() else None,
                "profile": profile,
                "actuals": actuals,
            }
        )
    else:
        qs = CostMaster.objects.all().order_by("vendor_material", "wwi_product_code")
        if search:
            qs = qs.filter(
                Q(vendor_material__icontains=search)
                | Q(wwi_product_code__icontains=search)
                | Q(vendor__icontains=search)
            )
        rows = list(qs[:300])
        actuals = {}
        try:
            actuals = get_cost_master_actuals(request.user, [r.id for r in rows]) or {}
        except Exception:
            pass
        for r in rows:
            a = actuals.get(r.id) or actuals.get(str(r.id)) or {}
            r.actual_comparison = a.get("comparison", "—")
            r.shipments_count = a.get("shipments_count", 0)
        ctx["rows"] = rows

    return render(
        request,
        "slurp_ui/finance/costing.html",
        _finance_ctx("costing", **ctx),
    )


@login_required
def finance_cost_master(request: HttpRequest) -> HttpResponse:
    params = request.GET.copy()
    params["tab"] = "master"
    return redirect(f"{reverse('slurp_ui:finance_costing')}?{params.urlencode()}")


@login_required
def finance_margin_trends(request: HttpRequest) -> HttpResponse:
    items = Item.objects.filter(
        item_type__in=["finished_good", "distributed_item"]
    ).order_by("sku")[:500]
    selected_ids = _parse_int_list(request.GET.get("items", ""))
    trend_rows = margin_trend_rows(selected_ids) if selected_ids else []
    return render(
        request,
        "slurp_ui/finance/margin_trends.html",
        _finance_ctx(
            "costing",
            items=items,
            selected_ids=selected_ids,
            trend_rows=trend_rows,
            port_status="partial",
        ),
    )


@login_required
def finance_rm_lot_costs(request: HttpRequest) -> HttpResponse:
    params = request.GET.copy()
    params["tab"] = "lots"
    return redirect(f"{reverse('slurp_ui:finance_costing')}?{params.urlencode()}")


# ---------------------------------------------------------------------------
# Reports / P&L
# ---------------------------------------------------------------------------


def _report_date_defaults():
    end = date.today()
    start = end - timedelta(days=30)
    return start.isoformat(), end.isoformat()


@login_required
def finance_reports(request: HttpRequest) -> HttpResponse:
    report_type = request.GET.get("report") or "trial-balance"
    fiscal_periods = FiscalPeriod.objects.order_by("-start_date")[:50]
    fp_id = request.GET.get("fiscal_period_id")
    as_of = request.GET.get("as_of_date") or date.today().isoformat()
    start, end = _report_date_defaults()
    start = request.GET.get("start_date") or start
    end = request.GET.get("end_date") or end

    report_data = None
    try:
        if report_type == "trial-balance":
            report_data = get_trial_balance(
                request.user,
                fiscal_period_id=int(fp_id) if fp_id else None,
                as_of_date=as_of if not fp_id else None,
            )
        elif report_type == "balance-sheet":
            report_data = get_balance_sheet(
                request.user,
                fiscal_period_id=int(fp_id) if fp_id else None,
                as_of_date=as_of if not fp_id else None,
            )
        elif report_type == "income-statement":
            report_data = get_income_statement(
                request.user,
                fiscal_period_id=int(fp_id) if fp_id else None,
                start_date=start if not fp_id else None,
                end_date=end if not fp_id else None,
            )
        elif report_type == "cash-flow":
            report_data = get_cash_flow(
                request.user,
                fiscal_period_id=int(fp_id) if fp_id else None,
                start_date=start if not fp_id else None,
                end_date=end if not fp_id else None,
            )
    except Exception as e:
        messages.error(request, str(e))

    return render(
        request,
        "slurp_ui/finance/reports.html",
        _finance_ctx(
            "reports",
            report_type=report_type,
            report_data=report_data,
            fiscal_periods=fiscal_periods,
            fiscal_period_id=fp_id,
            as_of_date=as_of,
            start_date=start,
            end_date=end,
            port_status="full",
        ),
    )


@login_required
def finance_pl_actual(request: HttpRequest) -> HttpResponse:
    fiscal_periods = FiscalPeriod.objects.order_by("-start_date")[:50]
    fp_id = request.GET.get("fiscal_period_id")
    start, end = _report_date_defaults()
    start = request.GET.get("start_date") or start
    end = request.GET.get("end_date") or end
    data = None
    try:
        data = get_income_statement(
            request.user,
            fiscal_period_id=int(fp_id) if fp_id else None,
            start_date=start if not fp_id else None,
            end_date=end if not fp_id else None,
        )
    except Exception as e:
        messages.error(request, str(e))
    return render(
        request,
        "slurp_ui/finance/pl_actual.html",
        _finance_ctx(
            "pl-actual",
            data=data,
            fiscal_periods=fiscal_periods,
            fiscal_period_id=fp_id,
            start_date=start,
            end_date=end,
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def finance_pl_proforma(request: HttpRequest) -> HttpResponse:
    fiscal_periods = FiscalPeriod.objects.order_by("-start_date")[:50]
    fp_id = request.GET.get("fiscal_period_id")
    start, end = _report_date_defaults()
    start = request.GET.get("start_date") or start
    end = request.GET.get("end_date") or end

    data = None
    forecast = {}
    try:
        data = get_income_statement(
            request.user,
            fiscal_period_id=int(fp_id) if fp_id else None,
            start_date=start if not fp_id else None,
            end_date=end if not fp_id else None,
        )
    except Exception as e:
        messages.error(request, str(e))

    total_rev = 0.0
    total_exp = 0.0
    if data:
        for rev in data.get("revenues") or []:
            key = f"rev_{rev['account_id']}"
            if request.method == "POST":
                raw = request.POST.get(key)
                rev["forecast_amount"] = float(raw) if raw not in (None, "") else rev.get("amount", 0)
            else:
                rev["forecast_amount"] = rev.get("amount", 0)
            total_rev += rev["forecast_amount"]
        for exp in data.get("expenses") or []:
            key = f"exp_{exp['account_id']}"
            if request.method == "POST":
                raw = request.POST.get(key)
                exp["forecast_amount"] = float(raw) if raw not in (None, "") else exp.get("amount", 0)
            else:
                exp["forecast_amount"] = exp.get("amount", 0)
            total_exp += exp["forecast_amount"]

    return render(
        request,
        "slurp_ui/finance/pl_proforma.html",
        _finance_ctx(
            "pl-proforma",
            data=data,
            forecast=forecast,
            forecast_total_revenue=total_rev,
            forecast_total_expenses=total_exp,
            forecast_net_income=total_rev - total_exp,
            fiscal_periods=fiscal_periods,
            fiscal_period_id=fp_id,
            start_date=start,
            end_date=end,
            port_status="full",
        ),
    )


# ---------------------------------------------------------------------------
# R&D formula costing (shared records with Quality)
# ---------------------------------------------------------------------------


@login_required
def finance_rd_formulas(request: HttpRequest) -> HttpResponse:
    params = request.GET.copy()
    params["tab"] = "rd"
    return redirect(f"{reverse('slurp_ui:finance_costing')}?{params.urlencode()}")


@login_required
@require_http_methods(["GET", "POST"])
def finance_rd_formula_detail(request: HttpRequest, pk: int | None = None) -> HttpResponse:
    from ..rd_formula_workspace import (
        rd_catalog_items,
        rd_lines_from_formula,
        rd_lines_payload_from_post,
        save_rd_formula,
    )

    rd = None
    if pk is not None:
        rd = get_object_or_404(RDFormula.objects.prefetch_related("lines__item"), pk=pk)

    catalog_items = rd_catalog_items()

    if request.method == "POST":
        action = (request.POST.get("action") or "save").strip()

        if action == "scrap" and rd:
            rd.status = "scrapped"
            rd.save(update_fields=["status", "updated_at"])
            messages.success(request, f"Archived {rd.rd_code} as scrapped. Code will never be reused.")
            return redirect(reverse("slurp_ui:finance_costing") + "?tab=rd")

        if action == "unscrap" and rd and rd.status == "scrapped":
            rd.status = "draft"
            rd.save(update_fields=["status", "updated_at"])
            messages.success(request, f"Restored {rd.rd_code} to draft.")
            return redirect("slurp_ui:finance_rd_formula_detail", pk=rd.pk)

        if action == "commercialize" and rd:
            sku = (request.POST.get("commercial_sku") or "").strip().upper()
            if not sku:
                messages.error(request, "Enter the commercial SKU (e.g. L1303).")
                return redirect(request.path)
            rd.commercial_sku = sku
            rd.status = "commercialized"
            rd.save(update_fields=["commercial_sku", "status", "updated_at"])
            messages.success(
                request,
                f"{rd.rd_code} marked commercialized as {sku}. R&D code kept for history.",
            )
            return redirect("slurp_ui:finance_rd_formula_detail", pk=rd.pk)

        if action == "delete" and rd:
            messages.error(
                request,
                "Hard delete is disabled so R&D codes stay unique. Use Archive (scrap) instead.",
            )
            return redirect("slurp_ui:finance_rd_formula_detail", pk=rd.pk)

        name = (request.POST.get("name") or "").strip()
        if not name:
            messages.error(request, "Product name is required.")
        else:
            try:
                rd = save_rd_formula(
                    rd=rd,
                    name=name,
                    status=request.POST.get("status") or (rd.status if rd else "draft"),
                    notes=(request.POST.get("notes") or "").strip() or None,
                    family_letter=request.POST.get("family_letter"),
                    lines_payload=rd_lines_payload_from_post(request.POST),
                )
                messages.success(request, f"Saved {rd.rd_code} — {rd.name}.")
                return redirect("slurp_ui:finance_rd_formula_detail", pk=rd.pk)
            except Exception as e:
                messages.error(request, str(e))

    line_rows = rd_lines_from_formula(rd)
    total_cost = sum((r["line"].formula_cost or 0) for r in line_rows if r.get("line"))

    return render(
        request,
        "slurp_ui/finance/rd_formula_detail.html",
        _finance_ctx(
            "costing",
            rd=rd,
            line_rows=line_rows,
            catalog_items=catalog_items,
            status_choices=[c for c in RDFormula.STATUS_CHOICES if c[0] != "commercialized"],
            total_cost=total_cost,
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def finance_rd_formula_create(request: HttpRequest) -> HttpResponse:
    return finance_rd_formula_detail(request, pk=None)

