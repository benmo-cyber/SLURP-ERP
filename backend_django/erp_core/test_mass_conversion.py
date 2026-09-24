"""Regression tests for plant-standard mass conversion (LBS_PER_KG = 2.2)."""
from django.test import SimpleTestCase

from erp_core.mass_quantity import LBS_PER_KG, convert_mass_uom, normalize_mass_quantity
from erp_core.pack_display import format_packs_partial_note, pack_quantity_breakdown


class PlantMassConversionTests(SimpleTestCase):
    def test_lbs_per_kg_is_plant_standard(self):
        self.assertEqual(LBS_PER_KG, 2.2)

    def test_convert_round_trip(self):
        lbs = convert_mass_uom(100, "kg", "lbs")
        self.assertEqual(lbs, 220.0)
        back = convert_mass_uom(lbs, "lbs", "kg")
        self.assertEqual(back, 100.0)

    def test_batch_ticket_d1300_packs_note_matches_displayed_lbs(self):
        """
        BT-20260922-002 style: 195.45 kg @ 10 kg pack, ticket mass unit lbs.

        Display qty snaps to 430 lbs via plant 2.2; packs note must use the same
        factor so 19*22 + 12 == 430 (not NIST 2.2046… → 11.12 lb remainder).
        """
        stored_kg = 195.45
        pack_kg = 10.0
        display_lbs = convert_mass_uom(stored_kg, "kg", "lbs")
        self.assertEqual(display_lbs, 430.0)

        note = format_packs_partial_note(display_lbs, "lbs", pack_kg, "kg")
        self.assertEqual(note, "19 pk + 12 lb")

        pack_lbs = convert_mass_uom(pack_kg, "kg", "lbs")
        self.assertEqual(pack_lbs, 22.0)
        full = int(display_lbs // pack_lbs)
        rem = normalize_mass_quantity(display_lbs - full * pack_lbs)
        self.assertEqual(full * pack_lbs + rem, display_lbs)

    def test_reject_nist_factor_in_packs_note(self):
        """Guard: NIST-ish pack conversion must not be used for pick-list notes."""
        note = format_packs_partial_note(430.0, "lbs", 10.0, "kg")
        self.assertNotIn("11.12", note)
        self.assertEqual(note, "19 pk + 12 lb")

    def test_pack_quantity_breakdown_995_of_20(self):
        brk = pack_quantity_breakdown(995.0, "lbs", 20.0, "lbs")
        self.assertIsNotNone(brk)
        self.assertEqual(brk["full_packs"], 49)
        self.assertEqual(brk["full_mass"], 980.0)
        self.assertEqual(brk["remainder"], 15.0)
        self.assertTrue(brk["has_remainder"])
        self.assertEqual(brk["display"], "49 × 20 lbs + 15 lbs partial")
        self.assertEqual(brk["note"], "49 pk + 15 lb")
