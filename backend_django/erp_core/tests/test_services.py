from django.test import TestCase

from erp_core.models import Item, Lot
from erp_core.services.inventory import WorkflowError, check_in_lot, reverse_check_in
from erp_core.services.numbers import generate_lot_number, generate_po_number


class NumberGeneratorTests(TestCase):
    def test_generate_lot_number_format(self):
        lot_number = generate_lot_number()
        self.assertTrue(lot_number.startswith('1'))
        self.assertEqual(len(lot_number), 8)

    def test_generate_po_number_format(self):
        po_number = generate_po_number()
        self.assertTrue(po_number.startswith('2'))


class CheckInTests(TestCase):
    def setUp(self):
        self.item = Item.objects.create(
            sku='TEST-SKU',
            name='Test Item',
            item_type='finished_good',
            unit_of_measure='lbs',
        )

    def test_check_in_creates_lot(self):
        lot = check_in_lot(item=self.item, quantity=100.0)
        self.assertEqual(lot.quantity_remaining, 100.0)
        self.assertEqual(lot.status, 'accepted')

    def test_reverse_check_in_unused_lot(self):
        lot = check_in_lot(item=self.item, quantity=50.0)
        lot_number = lot.lot_number
        reverse_check_in(lot)
        self.assertFalse(Lot.objects.filter(lot_number=lot_number).exists())

    def test_raw_material_requires_vendor_lot(self):
        raw = Item.objects.create(
            sku='RAW-1', name='Raw', item_type='raw_material', unit_of_measure='lbs',
        )
        with self.assertRaises(WorkflowError):
            check_in_lot(item=raw, quantity=10.0, vendor_lot_number='')
