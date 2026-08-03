"""Finance helpers for slurp_ui — ORM creates and ViewSet report dispatch."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.db.models import Exists, OuterRef, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date


class FinanceFormError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _viewset_action(viewset_cls, action_name, user, *, query_params=None, data=None, method="get", pk=None):
    from rest_framework.request import Request
    from rest_framework.test import APIRequestFactory

    factory = APIRequestFactory()
    if method == "get":
        wsgi = factory.get("/", query_params or {})
    elif method == "post":
        wsgi = factory.post("/", data or {}, format="json")
    else:
        wsgi = factory.patch("/", data or {}, format="json")
    wsgi.user = user
    drf_req = Request(wsgi)
    viewset = viewset_cls()
    viewset.request = drf_req
    viewset.format_kwarg = None
    if pk is not None:
        viewset.kwargs = {"pk": str(pk)}
    handler = getattr(viewset, action_name)
    response = handler(drf_req, pk=pk) if pk is not None else handler(drf_req)
    if hasattr(response, "data"):
        if response.status_code >= 400:
            detail = response.data.get("error") or response.data.get("detail") or str(response.data)
            raise FinanceFormError(str(detail))
        return response.data
    return response


def aging_totals_for_dashboard(report: dict) -> dict:
    totals = report.get("totals") or {}
    return {
        "current": totals.get("not_due", 0),
        "days_1_30": totals.get("0-30", 0),
        "days_31_60": totals.get("31-60", 0),
        "days_61_90": totals.get("61-90", 0),
        "over_90": totals.get("over_90", 0),
        "total": totals.get("total", 0),
    }


def get_dashboard_metrics(user, period_type="monthly", months_back=12):
    from erp_core.views import FinancialReportsViewSet

    return _viewset_action(
        FinancialReportsViewSet,
        "dashboard_metrics",
        user,
        query_params={"period_type": period_type, "months_back": months_back},
    )


def get_kpis(user, months_back=12):
    from erp_core.views import FinancialReportsViewSet

    return _viewset_action(
        FinancialReportsViewSet,
        "kpis",
        user,
        query_params={"months_back": months_back},
    )


def get_trial_balance(user, *, as_of_date=None, fiscal_period_id=None):
    from erp_core.views import FinancialReportsViewSet

    params = {}
    if fiscal_period_id:
        params["fiscal_period_id"] = fiscal_period_id
    elif as_of_date:
        params["as_of_date"] = as_of_date
    return _viewset_action(FinancialReportsViewSet, "trial_balance", user, query_params=params)


def get_balance_sheet(user, *, as_of_date=None, fiscal_period_id=None):
    from erp_core.views import FinancialReportsViewSet

    params = {}
    if fiscal_period_id:
        params["fiscal_period_id"] = fiscal_period_id
    elif as_of_date:
        params["as_of_date"] = as_of_date
    return _viewset_action(FinancialReportsViewSet, "balance_sheet", user, query_params=params)


def get_income_statement(user, *, start_date=None, end_date=None, fiscal_period_id=None):
    from erp_core.views import FinancialReportsViewSet

    params = {}
    if fiscal_period_id:
        params["fiscal_period_id"] = fiscal_period_id
    else:
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
    return _viewset_action(FinancialReportsViewSet, "income_statement", user, query_params=params)


def get_cash_flow(user, *, start_date=None, end_date=None, fiscal_period_id=None):
    from erp_core.views import FinancialReportsViewSet

    params = {}
    if fiscal_period_id:
        params["fiscal_period_id"] = fiscal_period_id
    else:
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
    return _viewset_action(FinancialReportsViewSet, "cash_flow", user, query_params=params)


def get_ar_aging(user):
    from erp_core.views import AccountsReceivableViewSet

    return _viewset_action(AccountsReceivableViewSet, "aging_report", user)


def get_ap_aging(user):
    from erp_core.views import AccountsPayableViewSet

    return _viewset_action(AccountsPayableViewSet, "aging_report", user)


def get_cost_master_actuals(user, cost_master_ids=None):
    from erp_core.views import CostMasterViewSet

    params = {}
    if cost_master_ids:
        params = [("id", str(i)) for i in cost_master_ids]
        # APIRequestFactory get with list params
        qp = {}
        for i in cost_master_ids:
            qp.setdefault("id", [])
            if isinstance(qp["id"], list):
                qp["id"].append(str(i))
        # use repeated keys via manual query string
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        q = "&".join(f"id={i}" for i in cost_master_ids)
        wsgi = factory.get(f"/?{q}")
        wsgi.user = user
        drf_req = Request(wsgi)
        vs = CostMasterViewSet()
        vs.request = drf_req
        vs.format_kwarg = None
        resp = vs.actuals(drf_req)
        return resp.data
    return _viewset_action(CostMasterViewSet, "actuals", user)


def get_lot_cost_profile(cost_master_id: int) -> dict:
    from erp_core.cost_lot_profile import build_lot_cost_profile
    from erp_core.models import CostMaster

    cm = CostMaster.objects.get(pk=cost_master_id)
    return build_lot_cost_profile(cm)


def create_account(*, account_number, name, account_type, parent_account_id=None, description=None):
    from erp_core.models import Account
    from erp_core.serializers import AccountSerializer

    data = {
        "account_number": account_number.strip(),
        "name": name.strip(),
        "account_type": account_type,
        "parent_account": parent_account_id or None,
        "description": (description or "").strip() or None,
        "is_active": True,
    }
    ser = AccountSerializer(data=data)
    if not ser.is_valid():
        raise FinanceFormError("; ".join(f"{k}: {v}" for k, v in ser.errors.items()))
    return ser.save()


def create_journal_entry(user, *, entry_date, description, reference_number, lines):
    from erp_core.models import FiscalPeriod, JournalEntry, JournalEntryLine
    from erp_core.views import generate_journal_entry_number

    if isinstance(entry_date, str):
        entry_date = parse_date(entry_date)
    if not entry_date:
        raise FinanceFormError("Invalid entry date.")

    total_debits = sum(float(l["amount"]) for l in lines if l["debit_credit"] == "debit")
    total_credits = sum(float(l["amount"]) for l in lines if l["debit_credit"] == "credit")
    if abs(total_debits - total_credits) > 0.01:
        raise FinanceFormError(
            f"Journal entry must be balanced. Debits: ${total_debits:.2f}, Credits: ${total_credits:.2f}"
        )

    fiscal_period = FiscalPeriod.objects.filter(
        start_date__lte=entry_date, end_date__gte=entry_date
    ).first()
    if fiscal_period and fiscal_period.is_closed:
        raise FinanceFormError("Cannot create journal entry in a closed fiscal period.")

    je = JournalEntry.objects.create(
        entry_number=generate_journal_entry_number(entry_date),
        entry_date=entry_date,
        description=description.strip(),
        reference_number=(reference_number or "").strip() or None,
        fiscal_period=fiscal_period,
        created_by=getattr(user, "username", None) or "system",
    )
    for line in lines:
        JournalEntryLine.objects.create(
            journal_entry=je,
            account_id=int(line["account"]),
            debit_credit=line["debit_credit"],
            amount=float(line["amount"]),
            description=(line.get("description") or "").strip(),
        )
    return je


def post_journal_entry(user, journal_entry_id: int):
    from erp_core.views import JournalEntryViewSet

    return _viewset_action(
        JournalEntryViewSet, "post_entry", user, method="post", pk=journal_entry_id
    )


def create_fiscal_period(*, period_name, start_date, end_date, notes=None):
    from erp_core.models import FiscalPeriod
    from erp_core.serializers import FiscalPeriodSerializer

    if isinstance(start_date, str):
        start_date = parse_date(start_date)
    if isinstance(end_date, str):
        end_date = parse_date(end_date)
    data = {
        "period_name": period_name.strip(),
        "start_date": start_date,
        "end_date": end_date,
        "notes": (notes or "").strip() or None,
        "is_closed": False,
    }
    ser = FiscalPeriodSerializer(data=data)
    if not ser.is_valid():
        raise FinanceFormError("; ".join(f"{k}: {v}" for k, v in ser.errors.items()))
    return ser.save()


def close_fiscal_period(user, period_id: int):
    from erp_core.views import FiscalPeriodViewSet

    return _viewset_action(FiscalPeriodViewSet, "close_period", user, method="post", pk=period_id)


def create_bank_reconciliation(*, account_id, statement_date, statement_balance, notes=None):
    from erp_core.serializers import BankReconciliationSerializer

    if isinstance(statement_date, str):
        statement_date = parse_date(statement_date)
    data = {
        "account": int(account_id),
        "statement_date": statement_date,
        "statement_balance": float(statement_balance),
        "notes": (notes or "").strip() or None,
    }
    ser = BankReconciliationSerializer(data=data)
    if not ser.is_valid():
        raise FinanceFormError("; ".join(f"{k}: {v}" for k, v in ser.errors.items()))
    return ser.save()


def gl_balance_for_account(account_id: int, as_of: date) -> float:
    from erp_core.models import Account, GeneralLedgerEntry

    account = Account.objects.get(pk=account_id)
    entries = GeneralLedgerEntry.objects.filter(account=account, entry_date__lte=as_of)
    debits = sum(e.amount for e in entries if e.debit_credit == "debit")
    credits = sum(e.amount for e in entries if e.debit_credit == "credit")
    if account.account_type in ("asset", "expense"):
        return debits - credits
    return credits - debits


def create_payment(*, payment_type, payment_date, payment_method, amount, account_id=None,
                   ap_entry_id=None, ar_entry_id=None, reference_number=None, notes=None):
    from erp_core.models import AccountsPayable, AccountsReceivable, Payment
    from erp_core.serializers import PaymentSerializer

    if isinstance(payment_date, str):
        payment_date = parse_date(payment_date)
    data = {
        "payment_type": payment_type,
        "payment_date": payment_date,
        "payment_method": payment_method,
        "amount": float(amount),
        "reference_number": (reference_number or "").strip() or None,
        "notes": (notes or "").strip() or None,
    }
    if account_id:
        data["account"] = int(account_id)
    if ap_entry_id:
        data["ap_entry"] = int(ap_entry_id)
    if ar_entry_id:
        data["ar_entry"] = int(ar_entry_id)

    ser = PaymentSerializer(data=data)
    if not ser.is_valid():
        raise FinanceFormError("; ".join(f"{k}: {v}" for k, v in ser.errors.items()))
    payment = ser.save()

    if payment.ap_entry_id:
        ap = AccountsPayable.objects.get(pk=payment.ap_entry_id)
        ap.amount_paid += payment.amount
        ap.balance = ap.original_amount - ap.amount_paid
        if ap.balance <= 0.01:
            ap.status = "paid"
            ap.balance = 0.0
        elif ap.amount_paid > 0:
            ap.status = "partial"
        if ap.status in ("open", "partial") and ap.due_date < timezone.now().date():
            ap.status = "overdue"
        ap.save()

    elif payment.ar_entry_id:
        ar = AccountsReceivable.objects.get(pk=payment.ar_entry_id)
        ar.amount_paid += payment.amount
        ar.balance = ar.original_amount - ar.amount_paid
        if ar.balance <= 0.01:
            ar.status = "paid"
            ar.balance = 0.0
        elif ar.amount_paid > 0:
            ar.status = "partial"
        if ar.status in ("open", "partial") and ar.due_date < timezone.now().date():
            ar.status = "overdue"
        ar.save()

    return payment


def create_customer_pricing(*, customer_id, item_id, unit_price, unit_of_measure, effective_date,
                            expiry_date=None, incoterms=None, incoterms_place=None, notes=None):
    from erp_core.serializers import CustomerPricingSerializer

    if isinstance(effective_date, str):
        effective_date = parse_date(effective_date)
    if expiry_date and isinstance(expiry_date, str):
        expiry_date = parse_date(expiry_date)
    data = {
        "customer": int(customer_id),
        "item": int(item_id),
        "unit_price": float(unit_price),
        "unit_of_measure": unit_of_measure,
        "effective_date": effective_date,
        "expiry_date": expiry_date,
        "incoterms": (incoterms or "").strip() or None,
        "incoterms_place": (incoterms_place or "").strip() or None,
        "notes": (notes or "").strip() or None,
        "is_active": True,
    }
    ser = CustomerPricingSerializer(data=data)
    if not ser.is_valid():
        raise FinanceFormError("; ".join(f"{k}: {v}" for k, v in ser.errors.items()))
    return ser.save()


def create_vendor_pricing(*, vendor_name, item_id, unit_price, unit_of_measure, effective_date,
                          vendor_item_number=None, expiry_date=None, notes=None):
    from erp_core.serializers import VendorPricingSerializer

    if isinstance(effective_date, str):
        effective_date = parse_date(effective_date)
    if expiry_date and isinstance(expiry_date, str):
        expiry_date = parse_date(expiry_date)
    data = {
        "vendor_name": vendor_name.strip(),
        "item": int(item_id),
        "unit_price": float(unit_price),
        "unit_of_measure": unit_of_measure,
        "effective_date": effective_date,
        "vendor_item_number": (vendor_item_number or "").strip() or None,
        "expiry_date": expiry_date,
        "notes": (notes or "").strip() or None,
        "is_active": True,
    }
    ser = VendorPricingSerializer(data=data)
    if not ser.is_valid():
        raise FinanceFormError("; ".join(f"{k}: {v}" for k, v in ser.errors.items()))
    return ser.save()


def create_manual_invoice(*, customer_vendor_name, invoice_date, due_date=None, items, tax=0, freight=0,
                          discount=0, notes=None, invoice_number=None, customer_vendor_id=None):
    from erp_core.models import Invoice, InvoiceItem
    from erp_core.views import generate_invoice_number

    if isinstance(invoice_date, str):
        invoice_date = parse_date(invoice_date)
    if due_date and isinstance(due_date, str):
        due_date = parse_date(due_date)
    if not due_date and invoice_date:
        due_date = invoice_date + timedelta(days=30)

    inv_num = (invoice_number or "").strip() or generate_invoice_number()
    if Invoice.objects.filter(invoice_number=inv_num).exists():
        raise FinanceFormError(f'Invoice number "{inv_num}" already exists.')

    subtotal = sum(
        float(it.get("line_total") or 0)
        or float(it.get("quantity", 0)) * float(it.get("unit_price", 0))
        for it in items
    )
    tax_f = float(tax or 0)
    freight_f = float(freight or 0)
    discount_f = float(discount or 0)
    grand_total = subtotal + tax_f + freight_f - discount_f

    inv_kw = dict(
        invoice_number=inv_num,
        invoice_date=invoice_date,
        due_date=due_date,
        status="draft",
        subtotal=subtotal,
        freight=freight_f,
        tax=tax_f,
        tax_amount=tax_f,
        discount=discount_f,
        grand_total=grand_total,
        total_amount=grand_total,
        notes=(notes or "").strip() or "",
        sales_order=None,
    )
    if hasattr(Invoice, "customer_vendor_name"):
        inv_kw["customer_vendor_name"] = customer_vendor_name or ""
    if hasattr(Invoice, "customer_vendor_id"):
        inv_kw["customer_vendor_id"] = customer_vendor_id or ""

    invoice = Invoice.objects.create(**inv_kw)
    for it in items:
        qty = float(it.get("quantity", 0))
        price = float(it.get("unit_price", 0))
        line_total = float(it.get("line_total") or qty * price)
        item_id = it.get("item_id") or it.get("item")
        InvoiceItem.objects.create(
            invoice=invoice,
            item_id=int(item_id) if item_id else None,
            description=(it.get("description") or "").strip(),
            quantity=qty,
            unit_price=price,
            total=line_total,
        )
    return invoice


def mark_invoice_paid(invoice):
    if invoice.status not in ("sent", "overdue", "paid"):
        raise FinanceFormError("Only issued/overdue invoices can be marked paid.")
    invoice.status = "paid"
    invoice.save(update_fields=["status", "updated_at"] if hasattr(invoice, "updated_at") else ["status"])
    return invoice


def commercial_raw_cost_masters():
    from erp_core.models import CostMaster, Item

    return (
        CostMaster.objects.filter(
            Exists(
                Item.objects.filter(
                    sku=OuterRef("wwi_product_code"), item_type="raw_material"
                )
            )
        )
        .exclude(wwi_product_code__isnull=True)
        .exclude(wwi_product_code="")
        .order_by("vendor_material", "wwi_product_code")[:500]
    )


def margin_trend_rows(item_ids: list[int]) -> list[dict[str, Any]]:
    """Simple tabular margin trend data for selected finished goods / distributed items."""
    from erp_core.models import CostMaster, CustomerPricing, Item

    if not item_ids:
        return []
    items = {i.id: i for i in Item.objects.filter(id__in=item_ids)}
    rows = []
    for iid in item_ids:
        item = items.get(iid)
        if not item:
            continue
        sku = item.sku
        cm = (
            CostMaster.objects.filter(wwi_product_code=sku)
            .order_by("-updated_at")
            .first()
        )
        cp = (
            CustomerPricing.objects.filter(item_id=iid, is_active=True)
            .order_by("-effective_date")
            .first()
        )
        cost = None
        if cm:
            cost = cm.landed_cost_per_lb or (
                (cm.landed_cost_per_kg / 2.2) if cm.landed_cost_per_kg else None
            )
        price = cp.unit_price if cp else None
        margin_pct = None
        if cost and price and price > 0:
            margin_pct = round((price - cost) / price * 100, 1)
        rows.append(
            {
                "sku": sku,
                "name": item.name,
                "cost_per_lb": cost,
                "price": price,
                "margin_pct": margin_pct,
            }
        )
    return rows
