"""Full workflow integration test against live DB patterns (in-memory)."""
from datetime import date, datetime

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from erp_core.models import (
    Customer,
    Invoice,
    Item,
    Lot,
    ProductionBatch,
    PurchaseOrder,
    SalesOrder,
    Vendor,
)


class FullWorkflowTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('wf', 'wf@test.com', 'pass')
        self.client = Client()
        self.client.force_login(self.user)

    def test_end_to_end_inventory_po_checkin(self):
        item = Item.objects.create(
            sku='WF-1', name='Workflow Item', item_type='raw_material',
            unit_of_measure='lbs', price=10,
        )
        r = self.client.post(reverse('po_create'), {
            'vendor_customer_name': 'Supplier',
            'expected_delivery_date': '2026-07-01',
            'required_date': '', 'shipping_terms': '', 'shipping_method': '',
            'shipping_cost': '0', 'discount': '0', 'coa_sds_email': '',
            'tracking_number': '', 'carrier': '', 'notes': '',
            'form-TOTAL_FORMS': '1', 'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0', 'form-MAX_NUM_FORMS': '1000',
            'form-0-item': item.pk, 'form-0-quantity_ordered': '100',
            'form-0-unit_price': '10', 'form-0-notes': '',
        })
        self.assertEqual(r.status_code, 302)
        po = PurchaseOrder.objects.get(vendor_customer_name='Supplier')
        r = self.client.post(reverse('po_action', kwargs={'pk': po.pk, 'action': 'issue'}))
        self.assertEqual(r.status_code, 302)
        r = self.client.post(reverse('check_in'), {
            'item': item.pk, 'quantity': '50', 'status': 'accepted',
            'vendor_lot_number': 'VL-001', 'po_number': po.po_number,
            'freight_actual': '', 'short_reason': '',
        })
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Lot.objects.filter(vendor_lot_number='VL-001').exists())

    def test_sales_checkout_ship(self):
        customer = Customer.objects.create(customer_id='010', name='Ship Co', payment_terms='Net 30')
        item = Item.objects.create(
            sku='SO-1', name='Sell Item', item_type='finished_good', unit_of_measure='lbs', price=20,
        )
        lot = Lot.objects.create(
            lot_number='1TEST001', item=item, quantity=100, quantity_remaining=100,
            received_date=timezone.now(), status='accepted',
        )
        r = self.client.post(reverse('sales_order_create'), {
            'customer': customer.pk, 'customer_reference_number': 'CPO-1',
            'expected_ship_date': '', 'notes': '',
            'form-TOTAL_FORMS': '1', 'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0', 'form-MAX_NUM_FORMS': '1000',
            'form-0-item': item.pk, 'form-0-quantity_ordered': '10', 'form-0-unit_price': '20',
        })
        self.assertEqual(r.status_code, 302, r.content[:300])
        so = SalesOrder.objects.latest('id')
        r = self.client.post(reverse('sales_order_allocate', kwargs={'pk': so.pk}), {
            f'lot_{so.items.first().id}': lot.pk,
            f'qty_{so.items.first().id}': '10',
        })
        self.assertEqual(r.status_code, 302)
        r = self.client.post(reverse('sales_order_ship', kwargs={'pk': so.pk}), {
            'ship_date': date.today().isoformat(),
            'invoice_date': date.today().isoformat(),
        })
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Invoice.objects.filter(sales_order=so).exists())

    def test_production_batch(self):
        fg = Item.objects.create(
            sku='FG-WF', name='FG', item_type='finished_good', unit_of_measure='lbs',
        )
        raw = Item.objects.create(
            sku='RAW-WF', name='Raw', item_type='raw_material', unit_of_measure='lbs',
        )
        lot = Lot.objects.create(
            lot_number='RAWLOT1', item=raw, quantity=100, quantity_remaining=100,
            received_date=timezone.now(), status='accepted',
        )
        r = self.client.post(reverse('production_batch_create'), {
            'batch_type': 'production', 'finished_good_item': fg.pk,
            'quantity_produced': '100', 'notes': '',
            'form-TOTAL_FORMS': '1', 'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0', 'form-MAX_NUM_FORMS': '1000',
            'form-0-lot': lot.pk, 'form-0-quantity_used': '100',
        })
        self.assertEqual(r.status_code, 302, r.content[:300])
        batch = ProductionBatch.objects.latest('id')
        r = self.client.post(reverse('production_batch_close', kwargs={'pk': batch.pk}), {
            'quantity_actual': '100', 'variance': '0', 'wastes': '0', 'spills': '0',
        })
        self.assertEqual(r.status_code, 302)
        batch.refresh_from_db()
        self.assertEqual(batch.status, 'closed')

    def test_all_get_pages(self):
        routes = [
            'inventory_dashboard', 'check_in', 'reverse_check_in', 'item_create', 'po_create',
            'production_dashboard', 'production_batch_create', 'quality_dashboard', 'vendor_create',
            'finished_good_create', 'lot_tracking', 'sales_dashboard', 'customer_create',
            'sales_order_create', 'calendar', 'finance_dashboard', 'account_create',
            'cost_master_create', 'vendor_pricing_create', 'customer_pricing_create', 'aging_report',
        ]
        for name in routes:
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 200, f'{name} returned {r.status_code}')
