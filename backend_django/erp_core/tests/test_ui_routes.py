"""
Integration tests: hit every GET route and exercise POST workflows.
Run: python manage.py test erp_core.tests.test_ui_routes --settings=wwi_erp.settings -v 2
"""

from datetime import date

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from erp_core.models import (
    Customer,
    Item,
    Lot,
    ProductionBatch,
    PurchaseOrder,
    SalesOrder,
    Vendor,
)


class AllRoutesSmokeTest(TestCase):
    """Every linked page must return 200 for authenticated user."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('tester', 't@test.com', 'testpass123')
        cls.vendor = Vendor.objects.create(name='Test Vendor Co')
        cls.item = Item.objects.create(
            sku='SKU-001', name='Test Material', item_type='raw_material',
            unit_of_measure='lbs', vendor='Test Vendor Co', price=10.0,
        )
        cls.fg = Item.objects.create(
            sku='FG-001', name='Finished Good', item_type='finished_good',
            unit_of_measure='lbs',
        )
        cls.customer = Customer.objects.create(customer_id='001', name='Test Customer')
        cls.po = PurchaseOrder.objects.create(
            po_number='2099001', vendor_customer_name='Test Vendor Co', status='draft',
        )
        cls.lot = Lot.objects.create(
            lot_number='VLOT-001', item=cls.item, quantity=100, quantity_remaining=100,
            received_date='2026-06-18T12:00:00Z', status='accepted',
        )
        cls.so = SalesOrder.objects.create(
            so_number='3099001', customer=cls.customer, customer_name='Test Customer',
        )
        cls.batch = ProductionBatch.objects.create(
            batch_number='BATCH-TEST-001', finished_good_item=cls.fg,
            quantity_produced=50, status='in_progress',
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def _get(self, name, *args, **kwargs):
        url = reverse(name, args=args, kwargs=kwargs)
        r = self.client.get(url)
        self.assertIn(r.status_code, (200, 302), f'GET {name} -> {r.status_code}')
        return r

    def test_auth_and_dashboards(self):
        self._get('inventory_dashboard')
        self._get('finance_dashboard')
        self._get('production_dashboard')
        self._get('quality_dashboard')
        self._get('sales_dashboard')

    def test_inventory_get_routes(self):
        self._get('check_in')
        self._get('reverse_check_in')
        self._get('item_create')
        self._get('item_edit', pk=self.item.pk)
        self._get('lot_edit', pk=self.lot.pk)
        self._get('po_create')
        self._get('po_detail', pk=self.po.pk)

    def test_production_get_routes(self):
        self._get('production_batch_create')
        self._get('production_batch_detail', pk=self.batch.pk)

    def test_quality_get_routes(self):
        self._get('vendor_create')
        self._get('vendor_detail', pk=self.vendor.pk)
        self._get('finished_good_create')
        self._get('lot_tracking')

    def test_sales_get_routes(self):
        self._get('customer_create')
        self._get('customer_detail', pk=self.customer.pk)
        self._get('sales_order_create')
        self._get('sales_order_checkout', pk=self.so.pk)
        self._get('calendar')

    def test_finance_get_routes(self):
        self._get('account_create')
        self._get('cost_master_create')
        self._get('vendor_pricing_create')
        self._get('customer_pricing_create')
        self._get('aging_report')


class WorkflowPostTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('tester2', 't2@test.com', 'testpass123')

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def test_create_item(self):
        r = self.client.post(reverse('item_create'), {
            'sku': 'NEW-SKU', 'name': 'New Item', 'item_type': 'raw_material',
            'unit_of_measure': 'lbs', 'vendor': 'Acme', 'price': '5.00',
            'description': '', 'pack_size': '', 'approved_for_formulas': False,
        })
        self.assertIn(r.status_code, (200, 302))
        self.assertTrue(Item.objects.filter(sku='NEW-SKU').exists())

    def test_check_in(self):
        item = Item.objects.create(
            sku='CI-001', name='Check In Item', item_type='finished_good', unit_of_measure='lbs',
        )
        r = self.client.post(reverse('check_in'), {
            'item': item.pk, 'quantity': '25', 'status': 'accepted',
            'vendor_lot_number': '', 'po_number': '', 'freight_actual': '', 'short_reason': '',
        })
        self.assertIn(r.status_code, (200, 302))
        self.assertTrue(Lot.objects.filter(item=item).exists())

    def test_create_vendor(self):
        r = self.client.post(reverse('vendor_create'), {
            'name': 'Vendor ABC', 'vendor_id': '', 'contact_name': 'Bob',
            'email': 'bob@v.com', 'phone': '', 'address': '', 'risk_profile': '2',
            'risk_tier': '', 'notes': '', 'gfsi_certified': False,
            'fsma_compliant': False, 'ctpat_certified': False,
        })
        self.assertIn(r.status_code, (200, 302))
        self.assertTrue(Vendor.objects.filter(name='Vendor ABC').exists())

    def test_create_customer(self):
        r = self.client.post(reverse('customer_create'), {
            'name': 'Cust Co', 'contact_name': '', 'email': '', 'phone': '',
            'address': '', 'city': '', 'state': '', 'zip_code': '', 'country': 'USA',
            'payment_terms': 'Net 30', 'notes': '', 'is_active': True,
        })
        self.assertIn(r.status_code, (200, 302))
        self.assertTrue(Customer.objects.filter(name='Cust Co').exists())

    def test_create_po(self):
        item = Item.objects.create(
            sku='PO-ITEM', name='PO Item', item_type='raw_material', unit_of_measure='lbs',
        )
        r = self.client.post(reverse('po_create'), {
            'vendor_customer_name': 'Supplier X',
            'expected_delivery_date': '2026-07-01',
            'required_date': '', 'shipping_terms': '', 'shipping_method': '',
            'shipping_cost': '0', 'discount': '0', 'coa_sds_email': '',
            'tracking_number': '', 'carrier': '', 'notes': '',
            'form-TOTAL_FORMS': '1', 'form-INITIAL_FORMS': '0', 'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-item': item.pk, 'form-0-quantity_ordered': '10',
            'form-0-unit_price': '5', 'form-0-notes': '',
        })
        self.assertIn(r.status_code, (200, 302), f'PO create failed: {r.content[:500]}')
        self.assertTrue(PurchaseOrder.objects.filter(vendor_customer_name='Supplier X').exists())

    def test_create_account(self):
        r = self.client.post(reverse('account_create'), {
            'account_number': '1000', 'name': 'Cash', 'account_type': 'asset',
            'parent_account': '', 'description': '', 'is_active': True,
        })
        self.assertIn(r.status_code, (200, 302))
