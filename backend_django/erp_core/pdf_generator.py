"""Logo resolution and invoice address blocks for HTML→PDF documents."""
import base64
import os
from pathlib import Path

_LOGO_B64_BY_PATH: dict[str, str] = {}
_LOGO_NAMES = (
    'Wildwood Ingredients Logo - Transparent Background.png',
    'logo.png',
    'Logo.png',
)


def get_logo_path() -> str | None:
    base = Path(__file__).resolve().parent.parent.parent
    backend = Path(__file__).resolve().parent.parent
    frontend_path = base / 'frontend' / 'public' / 'logo.png'
    if frontend_path.exists():
        return str(frontend_path)
    for folder in (backend / 'batch_ticket_template', base / 'Sensitive', base / 'frontend' / 'public'):
        if not folder.is_dir():
            continue
        for name in _LOGO_NAMES:
            path = folder / name
            if path.is_file():
                return str(path.resolve())
    return None


def get_batch_ticket_logo_path() -> str | None:
    base = Path(__file__).resolve().parent.parent.parent
    backend = Path(__file__).resolve().parent.parent
    for folder, check_names in (
        (backend / 'batch_ticket_template', _LOGO_NAMES),
        (base / 'Sensitive', _LOGO_NAMES),
        (base / 'frontend' / 'public', _LOGO_NAMES),
    ):
        if folder.is_dir():
            for name in check_names:
                path = folder / name
                if path.is_file():
                    return str(path.resolve())
    return get_logo_path()


def logo_file_base64_cached(absolute_path: str | None) -> str:
    if not absolute_path:
        return ''
    try:
        key = str(Path(absolute_path).resolve())
    except OSError:
        key = absolute_path
    if key in _LOGO_B64_BY_PATH:
        return _LOGO_B64_BY_PATH[key]
    try:
        with open(key, 'rb') as fh:
            _LOGO_B64_BY_PATH[key] = base64.b64encode(fh.read()).decode('ascii')
    except OSError:
        return ''
    return _LOGO_B64_BY_PATH[key]


def get_batch_ticket_logo_base64_cached() -> str:
    return logo_file_base64_cached(get_batch_ticket_logo_path())


def get_logo_base64_cached() -> str:
    return logo_file_base64_cached(get_logo_path())


def _customer_has_any_bill_to_field(customer) -> bool:
    return bool(
        (getattr(customer, 'bill_to_address', None) or '').strip()
        or (getattr(customer, 'bill_to_city', None) or '').strip()
        or (getattr(customer, 'bill_to_state', None) or '').strip()
        or (getattr(customer, 'bill_to_zip_code', None) or '').strip()
        or (getattr(customer, 'bill_to_country', None) or '').strip()
    )


def _strict_bill_to_lines_from_customer(customer):
    name = (getattr(customer, 'name', None) or '').strip()
    lines = []
    if name:
        lines.append(name)
    if _customer_has_any_bill_to_field(customer):
        bt_a = (getattr(customer, 'bill_to_address', None) or '').strip()
        bt_ci = (getattr(customer, 'bill_to_city', None) or '').strip()
        bt_st = (getattr(customer, 'bill_to_state', None) or '').strip()
        bt_z = (getattr(customer, 'bill_to_zip_code', None) or '').strip()
        bt_co = (getattr(customer, 'bill_to_country', None) or '').strip()
        if bt_a:
            lines.append(bt_a)
        csz = ', '.join(filter(None, [bt_ci, bt_st, bt_z])).strip()
        if csz:
            lines.append(csz)
        if bt_co:
            lines.append(bt_co)
    else:
        hq_a = (getattr(customer, 'address', None) or '').strip()
        hq_ci = (getattr(customer, 'city', None) or '').strip()
        hq_st = (getattr(customer, 'state', None) or '').strip()
        hq_z = (getattr(customer, 'zip_code', None) or '').strip()
        if hq_a:
            lines.append(hq_a)
        csz = ', '.join(filter(None, [hq_ci, hq_st, hq_z])).strip()
        if csz:
            lines.append(csz)
    phone = (getattr(customer, 'phone', None) or '').strip()
    if phone:
        lines.append('Phone: ' + phone)
    return [line for line in lines if line]


def _invoice_bill_to_from_sales_order_legacy(sales_order):
    lines = []
    name = (getattr(sales_order, 'customer_name', None) or '').strip()
    if name:
        lines.append(name)
    addr = (getattr(sales_order, 'customer_address', None) or '').strip()
    if addr:
        lines.append(addr)
    csz = ', '.join(filter(None, [
        (getattr(sales_order, 'customer_city', None) or '').strip(),
        (getattr(sales_order, 'customer_state', None) or '').strip(),
        (getattr(sales_order, 'customer_zip', None) or '').strip(),
    ])).strip()
    if csz:
        lines.append(csz)
    phone = (getattr(sales_order, 'customer_phone', None) or '').strip()
    if phone:
        lines.append('Phone: ' + phone)
    return [line for line in lines if line]


def _invoice_bill_to(invoice):
    from .invoice_helpers import resolve_customer_for_invoice, resolve_payment_terms_for_invoice

    terms = resolve_payment_terms_for_invoice(invoice)
    customer = resolve_customer_for_invoice(invoice)
    if customer:
        return _strict_bill_to_lines_from_customer(customer), terms
    sales_order = getattr(invoice, 'sales_order', None)
    if sales_order:
        return _invoice_bill_to_from_sales_order_legacy(sales_order), terms
    return [], terms


def _invoice_ship_to(invoice):
    sales_order = getattr(invoice, 'sales_order', None)
    if not sales_order:
        return []
    location = getattr(sales_order, 'ship_to_location', None)
    if location:
        lines = [
            (getattr(location, 'location_name', None) or getattr(location, 'contact_name', None) or '').strip(),
            (getattr(location, 'address', None) or '').strip(),
            ', '.join(filter(None, [
                (getattr(location, 'city', None) or '').strip(),
                (getattr(location, 'state', None) or '').strip(),
                (getattr(location, 'zip_code', None) or '').strip(),
            ])).strip(),
            ('Phone: ' + (getattr(location, 'phone', None) or '').strip()) if getattr(location, 'phone', None) else '',
        ]
    else:
        lines = [
            (getattr(sales_order, 'customer_name', None) or '').strip(),
            (getattr(sales_order, 'customer_address', None) or '').strip(),
            ', '.join(filter(None, [
                (getattr(sales_order, 'customer_city', None) or '').strip(),
                (getattr(sales_order, 'customer_state', None) or '').strip(),
                (getattr(sales_order, 'customer_zip', None) or '').strip(),
            ])).strip(),
            ('Phone: ' + (getattr(sales_order, 'customer_phone', None) or '').strip())
            if getattr(sales_order, 'customer_phone', None) else '',
        ]
    return [line for line in lines if line]
