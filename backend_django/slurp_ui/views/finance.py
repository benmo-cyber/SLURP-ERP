from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
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
    Invoice,
    Item,
    JournalEntry,
    Payment,
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
    get_kpis,
    get_lot_cost_profile,
    get_trial_balance,
    gl_balance_for_account,
    margin_trend_rows,
    mark_invoice_paid,
    post_journal_entry,
)
from ..nav import FINANCE_NAV


def _finance_ctx(active_tab: str, **extra):
    ctx = {
        "module": "finance",
        "sidebar_nav": FINANCE_NAV,
        "active_tab": active_tab,
        "page_css": ["Finance.css", "Invoices.css", "ViewInvoice.css"],
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


# ---------------------------------------------------------------------------
# Dashboard & KPIs
# ---------------------------------------------------------------------------


@login_required
def finance_dashboard(request: HttpRequest) -> HttpResponse:
    """Quiet invoice-first home — not a metric dashboard."""
    from erp_core.models import AccountsPayable, AccountsReceivable

    draft = Invoice.objects.filter(status="draft").count()
    issued = Invoice.objects.filter(status__in=["sent", "overdue"]).count()
    paid = Invoice.objects.filter(status="paid").count()
    ar_open = AccountsReceivable.objects.exclude(status__in=["paid", "cancelled"]).count()
    ap_open = AccountsPayable.objects.exclude(status__in=["paid", "cancelled"]).count()
    draft_rows = list(
        Invoice.objects.filter(status="draft")
        .select_related("sales_order")
        .order_by("-invoice_date", "-id")[:8]
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
            port_status="full",
        ),
    )


@login_required
def finance_kpis(request: HttpRequest) -> HttpResponse:
    try:
        months_back = int(request.GET.get("months_back") or 12)
    except ValueError:
        months_back = 12
    kpis = get_kpis(request.user, months_back)
    return render(
        request,
        "slurp_ui/finance/kpis.html",
        _finance_ctx("kpis", kpis=kpis, months_back=months_back, port_status="full"),
    )


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
    status_filter = (request.GET.get("status") or "").strip()
    invoices = Invoice.objects.select_related("sales_order").order_by("-created_at")
    if status_filter:
        invoices = invoices.filter(status=status_filter)
    invoices = list(invoices[:200])
    for inv in invoices:
        inv.status_label = _status_label(inv.status)
    return render(
        request,
        "slurp_ui/finance/invoices.html",
        _finance_ctx(
            "invoices",
            invoices=invoices,
            status_filter=status_filter,
            port_status="full",
        ),
    )


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
        _finance_ctx("invoices", items=items, port_status="full"),
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
            "invoices",
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
            "invoices",
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
def finance_ar(request: HttpRequest) -> HttpResponse:
    status_filter = (request.GET.get("status") or "").strip()
    qs = AccountsReceivable.objects.select_related("invoice", "sales_order").order_by("due_date")
    if status_filter:
        qs = qs.filter(status=status_filter)
    entries = list(qs[:200])
    aging = None
    try:
        aging = aging_totals_for_dashboard(get_ar_aging(request.user))
    except Exception:
        pass
    return render(
        request,
        "slurp_ui/finance/ar.html",
        _finance_ctx(
            "ar",
            entries=entries,
            status_filter=status_filter,
            aging=aging,
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
            return redirect("slurp_ui:finance_ar")
        except FinanceFormError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))

    return render(
        request,
        "slurp_ui/finance/payment_entry.html",
        _finance_ctx(
            "ar" if payment_type == "ar_payment" else "ap",
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


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------


@login_required
def finance_pricing(request: HttpRequest) -> HttpResponse:
    tab = request.GET.get("tab") or "customer"
    customer_rows = CustomerPricing.objects.select_related("customer", "item").order_by(
        "-effective_date"
    )[:200]
    vendor_rows = VendorPricing.objects.select_related("item").order_by("-effective_date")[:200]
    return render(
        request,
        "slurp_ui/finance/pricing.html",
        _finance_ctx(
            "pricing",
            tab=tab,
            customer_rows=customer_rows,
            vendor_rows=vendor_rows,
            port_status="full",
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
def finance_pricing_customer_create(request: HttpRequest) -> HttpResponse:
    customers = Customer.objects.order_by("name")[:500]
    items = Item.objects.filter(
        item_type__in=["finished_good", "distributed_item"]
    ).order_by("sku")[:500]
    if request.method == "POST":
        try:
            create_customer_pricing(
                customer_id=request.POST.get("customer"),
                item_id=request.POST.get("item"),
                unit_price=request.POST.get("unit_price"),
                unit_of_measure=request.POST.get("unit_of_measure", "lbs"),
                effective_date=request.POST.get("effective_date"),
                expiry_date=request.POST.get("expiry_date") or None,
                incoterms=request.POST.get("incoterms"),
                incoterms_place=request.POST.get("incoterms_place"),
                notes=request.POST.get("notes"),
            )
            messages.success(request, "Customer pricing created.")
            return redirect("slurp_ui:finance_pricing")
        except FinanceFormError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))
    return render(
        request,
        "slurp_ui/finance/pricing_customer_create.html",
        _finance_ctx("pricing", customers=customers, items=items, port_status="full"),
    )


@login_required
@require_http_methods(["GET", "POST"])
def finance_pricing_vendor_create(request: HttpRequest) -> HttpResponse:
    items = Item.objects.filter(item_type="raw_material").order_by("sku")[:500]
    if request.method == "POST":
        try:
            create_vendor_pricing(
                vendor_name=request.POST.get("vendor_name", ""),
                item_id=request.POST.get("item"),
                unit_price=request.POST.get("unit_price"),
                unit_of_measure=request.POST.get("unit_of_measure", "lbs"),
                effective_date=request.POST.get("effective_date"),
                vendor_item_number=request.POST.get("vendor_item_number"),
                expiry_date=request.POST.get("expiry_date") or None,
                notes=request.POST.get("notes"),
            )
            messages.success(request, "Vendor pricing created.")
            return redirect("slurp_ui:finance_pricing?tab=vendor")
        except FinanceFormError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, str(e))
    return render(
        request,
        "slurp_ui/finance/pricing_vendor_create.html",
        _finance_ctx("pricing", items=items, port_status="full"),
    )


# ---------------------------------------------------------------------------
# Cost master / margin / RM lot costs
# ---------------------------------------------------------------------------


@login_required
def finance_cost_master(request: HttpRequest) -> HttpResponse:
    search = (request.GET.get("q") or "").strip()
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
    return render(
        request,
        "slurp_ui/finance/cost_master.html",
        _finance_ctx(
            "cost-master",
            rows=rows,
            search=search,
            port_status="partial",
        ),
    )


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
            "margin-trends",
            items=items,
            selected_ids=selected_ids,
            trend_rows=trend_rows,
            port_status="partial",
        ),
    )


@login_required
def finance_rm_lot_costs(request: HttpRequest) -> HttpResponse:
    search = (request.GET.get("q") or "").strip()
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
    return render(
        request,
        "slurp_ui/finance/rm_lot_costs.html",
        _finance_ctx(
            "rm-lot-costs",
            rows=rows,
            search=search,
            expand_id=int(expand_id) if expand_id and str(expand_id).isdigit() else None,
            profile=profile,
            actuals=actuals,
            port_status="partial",
        ),
    )


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
