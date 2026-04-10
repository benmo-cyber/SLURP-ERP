"""
Per-lot actual landed cost vs Cost Master estimate (commercial raw materials).

Actual $/unit is built from Accounts Payable linked to the lot's PO:
  - Material (COGS): AP rows with cost_category=material (or legacy unspecified), using
    original_amount; optionally scaled to match PO received-line extended value.
  - Freight: category=freight (original_amount + freight_total on that row) plus
    freight_total on material rows (legacy pattern).
  - Duty / broker / CBP: category=duty_tax (original_amount + tariff_duties_paid) plus
    tariff_duties_paid on material rows.

Allocations:
  - Material: per PO line, split across lots on that PO for the same item by lot.quantity.
  - Freight + duty: prorated across all lots on the PO by mass (kg); ea treated 1:1 kg.

Payments on AP do not change these amounts — invoice fields (original_amount, etc.) are the cost basis.
"""

from collections import defaultdict

LBS_PER_KG = 2.20462
TOLERANCE_PCT = 0.05


def _uom_base(po_item):
    if not po_item.item:
        return 'lbs'
    return (po_item.order_uom or po_item.item.unit_of_measure or 'lbs').strip().lower()


def _line_unit_price_to_per_kg(po_item):
    if not po_item.item:
        return None
    up = float(po_item.unit_price or 0)
    uom = _uom_base(po_item)
    if uom == 'kg':
        return up
    if uom == 'lbs':
        return up * LBS_PER_KG
    return up


def lot_quantity_to_kg(quantity, uom):
    q = float(quantity or 0)
    u = (uom or 'lbs').strip().lower()
    if u == 'kg':
        return q
    if u == 'lbs':
        return q / LBS_PER_KG
    return q


def lot_row_kg(lot):
    return lot_quantity_to_kg(lot.quantity, lot.item.unit_of_measure if lot.item else 'lbs')


def aggregate_ap_landed_costs_for_po(po):
    """
    Sum material / freight / duty dollars from all AP rows on this PO.
    Legacy rows: cost_category blank — original_amount counts as material; freight_total /
    tariff_duties_paid on any row add to freight / duty pools.
    """
    from .models import AccountsPayable

    aps = list(AccountsPayable.objects.filter(purchase_order=po).order_by('invoice_date', 'id'))
    material_total = 0.0
    freight_total = 0.0
    duty_total = 0.0

    for ap in aps:
        cat = (getattr(ap, 'cost_category', None) or '').strip()
        oa = float(ap.original_amount or 0)
        ft = float(ap.freight_total or 0)
        td = float(ap.tariff_duties_paid or 0)

        if cat == 'freight':
            freight_total += oa + ft
            duty_total += td
        elif cat == 'duty_tax':
            duty_total += oa + td
            freight_total += ft
        elif cat == 'material':
            material_total += oa
            freight_total += ft
            duty_total += td
        else:
            # Legacy / unspecified: invoice total is material; side fields are freight/duty splits
            material_total += oa
            freight_total += ft
            duty_total += td

    return {
        'material_total': material_total,
        'freight_total': freight_total,
        'duty_total': duty_total,
        'ap_count': len(aps),
    }


def _po_line_extended_by_item(po):
    """item_id -> sum(quantity_received * unit_price) for lines with received qty."""
    by_item = defaultdict(float)
    for pi in po.items.select_related('item').all():
        if not pi.item_id:
            continue
        q = float(pi.quantity_received or 0)
        if q <= 0:
            continue
        by_item[pi.item_id] += q * float(pi.unit_price or 0)
    return dict(by_item)


def _scaled_material_by_item(po, material_total_from_ap):
    """
    If AP material total is set, scale PO-line extended values to match (invoice vs PO parity).
    Otherwise use PO extended at scale 1.0.
    """
    by_item = _po_line_extended_by_item(po)
    sum_v = sum(by_item.values())
    if sum_v <= 0:
        return dict(by_item), 0.0
    if material_total_from_ap and material_total_from_ap > 0:
        scale = material_total_from_ap / sum_v
    else:
        scale = 1.0
    return {iid: v * scale for iid, v in by_item.items()}, scale


def _all_lots_for_po_number(po_number_str):
    from .models import Lot

    if not po_number_str or not str(po_number_str).strip():
        return []
    pn = str(po_number_str).strip()
    return list(
        Lot.objects.filter(po_number=pn)
        .select_related('item')
        .order_by('-received_date')
    )


def build_lot_cost_profile(cost_master):
    from .models import Item, Lot, PurchaseOrder

    cm = cost_master
    sku = (cm.wwi_product_code or '').strip()
    vendor = (cm.vendor or '').strip()
    if not sku:
        return {
            'cost_master_id': cm.id,
            'wwi_product_code': None,
            'vendor': vendor or None,
            'estimate_landed_per_kg': cm.landed_cost_per_kg,
            'estimate_landed_per_lb': cm.landed_cost_per_lb,
            'lots': [],
            'message': 'Cost Master has no WWI product code.',
        }

    qs = Item.objects.filter(sku=sku, item_type='raw_material')
    if vendor:
        qs = qs.filter(vendor__iexact=vendor)
    items = list(qs)

    if not items:
        return {
            'cost_master_id': cm.id,
            'wwi_product_code': sku,
            'vendor': vendor or None,
            'estimate_landed_per_kg': cm.landed_cost_per_kg,
            'estimate_landed_per_lb': cm.landed_cost_per_lb,
            'lots': [],
            'message': 'No commercial raw material Item matches this SKU and vendor.',
        }

    item_ids = [i.id for i in items]
    lots = (
        Lot.objects.filter(item_id__in=item_ids)
        .select_related('item')
        .order_by('-received_date')[:200]
    )

    est_kg = cm.landed_cost_per_kg
    if est_kg is None and cm.landed_cost_per_lb is not None:
        est_kg = cm.landed_cost_per_lb * LBS_PER_KG

    cert_per_kg = float(cm.cert_cost_per_kg or 0)

    rows = []
    for lot in lots:
        po = None
        if lot.po_number:
            po = PurchaseOrder.objects.filter(po_number=lot.po_number.strip()).first()

        comparison = 'ok'
        variance_kg = None
        actual_landed_kg = None
        ap_invoice = None

        allocated_material = None
        allocated_freight = None
        allocated_duty = None
        lot_freight_actual_usd = float(lot.freight_actual or 0) if lot.freight_actual else 0.0
        cert_cost_usd = None
        total_actual_cost_usd = None
        shipment_freight_per_kg = None
        shipment_tariff_rate = None
        price_kg = None
        po_item = None
        kg_lot = lot_row_kg(lot)
        has_ap = False

        if po:
            aps = aggregate_ap_landed_costs_for_po(po)
            has_ap = aps['ap_count'] > 0
            from .models import AccountsPayable

            first_ap = (
                AccountsPayable.objects.filter(purchase_order=po).order_by('-invoice_date').first()
            )
            ap_invoice = first_ap.invoice_number if first_ap else None

            scaled_by_item, _scale = _scaled_material_by_item(po, aps['material_total'])

            all_po_lots = _all_lots_for_po_number(po.po_number)
            if not all_po_lots:
                all_po_lots = [lot]

            total_kg_po = sum(lot_row_kg(L) for L in all_po_lots)

            # Material: share among lots on same PO + item
            siblings = [L for L in all_po_lots if L.item_id == lot.item_id]
            sum_qty = sum(float(L.quantity or 0) for L in siblings)
            line_material = scaled_by_item.get(lot.item_id, 0.0)
            if sum_qty > 0 and line_material:
                allocated_material = (float(lot.quantity or 0) / sum_qty) * line_material
            elif line_material and not siblings:
                allocated_material = line_material
            else:
                allocated_material = 0.0

            if total_kg_po > 0:
                allocated_freight = aps['freight_total'] * (kg_lot / total_kg_po)
                allocated_duty = aps['duty_total'] * (kg_lot / total_kg_po)
            else:
                allocated_freight = 0.0
                allocated_duty = 0.0

            cert_cost_usd = cert_per_kg * kg_lot
            total_actual_cost_usd = (
                (allocated_material or 0)
                + (allocated_freight or 0)
                + (allocated_duty or 0)
                + lot_freight_actual_usd
                + (cert_cost_usd or 0)
            )

            if kg_lot > 0 and total_actual_cost_usd is not None:
                actual_landed_kg = total_actual_cost_usd / kg_lot

            # Display helpers (PO-level rates — same as before for UI)
            if aps['freight_total'] and total_kg_po > 0:
                shipment_freight_per_kg = aps['freight_total'] / total_kg_po
            po_value = sum(_po_line_extended_by_item(po).values())
            if aps['duty_total'] and po_value > 0:
                shipment_tariff_rate = aps['duty_total'] / po_value

            for pi in po.items.select_related('item').all():
                if pi.item_id == lot.item_id:
                    po_item = pi
                    break
            if po_item:
                price_kg = _line_unit_price_to_per_kg(po_item)
        else:
            # No PO: still show cert + lot-level freight vs Cost Master if present
            cert_cost_usd = cert_per_kg * kg_lot
            total_actual_cost_usd = cert_cost_usd + lot_freight_actual_usd
            if kg_lot > 0 and total_actual_cost_usd > 0:
                actual_landed_kg = total_actual_cost_usd / kg_lot
            allocated_material = None
            allocated_freight = None
            allocated_duty = None

        if actual_landed_kg is not None and est_kg is not None:
            variance_kg = actual_landed_kg - est_kg
            tol = abs(est_kg * TOLERANCE_PCT) if est_kg else 0
            if variance_kg > tol:
                comparison = 'over'
            elif variance_kg < -tol:
                comparison = 'under'
            else:
                comparison = 'ok'

        has_allocation_dollars = bool(
            (po and (
                (allocated_material or 0) > 0
                or (allocated_freight or 0) > 0
                or (allocated_duty or 0) > 0
            ))
            or lot_freight_actual_usd > 0
            or (cert_cost_usd or 0) > 0
        )

        rows.append(
            {
                'lot_id': lot.id,
                'lot_number': lot.lot_number,
                'po_number': lot.po_number,
                'received_date': lot.received_date.isoformat() if lot.received_date else None,
                'quantity_received': lot.quantity,
                'quantity_remaining': lot.quantity_remaining,
                'item_sku': lot.item.sku,
                'item_uom': lot.item.unit_of_measure,
                'po_unit_price': float(po_item.unit_price) if po_item and po_item.unit_price is not None else None,
                'po_price_uom': _uom_base(po_item) if po_item else None,
                'price_per_kg_from_po': round(price_kg, 6) if price_kg is not None else None,
                'shipment_freight_per_kg': round(shipment_freight_per_kg, 6)
                if shipment_freight_per_kg is not None
                else None,
                'shipment_tariff_rate': round(shipment_tariff_rate, 6)
                if shipment_tariff_rate is not None
                else None,
                'allocated_material_usd': round(allocated_material, 2)
                if allocated_material is not None
                else None,
                'allocated_freight_usd': round(allocated_freight, 2)
                if allocated_freight is not None
                else None,
                'allocated_duty_usd': round(allocated_duty, 2)
                if allocated_duty is not None
                else None,
                'lot_freight_actual_usd': round(lot_freight_actual_usd, 2) if lot_freight_actual_usd else None,
                'cert_cost_usd': round(cert_cost_usd, 2) if cert_cost_usd is not None else None,
                'total_actual_cost_usd': round(total_actual_cost_usd, 2)
                if total_actual_cost_usd is not None
                else None,
                'actual_landed_per_kg': round(actual_landed_kg, 6) if actual_landed_kg is not None else None,
                'actual_landed_per_lb': round(actual_landed_kg / LBS_PER_KG, 6)
                if actual_landed_kg is not None
                else None,
                'actual_landed_per_uom': round(total_actual_cost_usd / float(lot.quantity or 0), 6)
                if total_actual_cost_usd is not None and float(lot.quantity or 0) > 0
                else None,
                'estimate_landed_per_kg': round(est_kg, 6) if est_kg is not None else None,
                'variance_per_kg': round(variance_kg, 6) if variance_kg is not None else None,
                'comparison': comparison,
                'ap_invoice_number': ap_invoice,
                'has_po_match': po is not None,
                'has_ap_allocation': has_ap,
                'has_cost_components': has_allocation_dollars,
            }
        )

    return {
        'cost_master_id': cm.id,
        'vendor_material': cm.vendor_material,
        'wwi_product_code': sku,
        'vendor': vendor or None,
        'estimate_landed_per_kg': cm.landed_cost_per_kg,
        'estimate_landed_per_lb': cm.landed_cost_per_lb,
        'lots': rows,
        'raw_material_item_ids': item_ids,
        'methodology': (
            'Actual = allocated material (AP by category + PO lines) + freight + duty '
            '(prorated by kg on PO) + lot freight_actual + cert_cost_per_kg from Cost Master. '
            'Enter separate AP lines per PO for vendor, freight, and duty; use cost category on each.'
        ),
    }
