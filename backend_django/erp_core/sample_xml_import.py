"""
Import legacy/sample master data from XML files in data/private_sample_data/.
See repo data/sample_import_template.xml for schema.
"""
from __future__ import annotations

import glob
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from django.conf import settings
from django.db import transaction
from rest_framework import status as http_status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Customer, Item, Vendor


def get_private_sample_data_dir() -> Path:
    """Repo root data/private_sample_data (next to backend_django)."""
    base = Path(settings.BASE_DIR)  # backend_django
    return (base.parent / "data" / "private_sample_data").resolve()


def _item_type(value: str) -> str:
    v = (value or "").strip()
    allowed = {"raw_material", "distributed_item", "finished_good", "indirect_material"}
    if v not in allowed:
        raise ValueError(f"Invalid item_type {v!r}; use one of {sorted(allowed)}")
    return v


def _uom(value: str) -> str:
    v = (value or "").strip().lower()
    allowed = {"lbs", "kg", "ea"}
    if v not in allowed:
        raise ValueError(f"Invalid unit_of_measure {v!r}; use one of {sorted(allowed)}")
    return v


def _product_category(value: str | None) -> str | None:
    if not value or not str(value).strip():
        return None
    v = str(value).strip()
    allowed = {"natural_colors", "synthetic_colors", "antioxidants", "other"}
    if v not in allowed:
        raise ValueError(f"Invalid product_category {v!r}; use one of {sorted(allowed)}")
    return v


def _vendor_approval(value: str | None) -> str:
    v = (value or "approved").strip() or "approved"
    allowed = {"pending", "approved", "rejected", "suspended"}
    if v not in allowed:
        return "approved"
    return v


@transaction.atomic
def import_sample_xml_file(path: Path) -> dict[str, Any]:
    """Parse one XML file and upsert vendors, customers, items. Returns counts."""
    tree = ET.parse(path)
    root = tree.getroot()
    if root.tag != "wwi_sample_data":
        raise ValueError(f"Root must be <wwi_sample_data>, got <{root.tag}>")
    ver = root.get("version", "1")
    if ver != "1":
        raise ValueError(f"Unsupported wwi_sample_data version {ver!r} (expected 1)")

    stats = {
        "file": str(path.name),
        "vendors_created": 0,
        "vendors_updated": 0,
        "customers_created": 0,
        "customers_updated": 0,
        "items_created": 0,
        "items_updated": 0,
    }

    for vel in root.findall("./vendors/vendor"):
        name = (vel.get("name") or "").strip()
        if not name:
            continue
        approval = _vendor_approval(vel.get("approval_status"))
        obj, created = Vendor.objects.update_or_create(
            name=name,
            defaults={
                "approval_status": approval,
            },
        )
        if created:
            stats["vendors_created"] += 1
        else:
            stats["vendors_updated"] += 1

    for cel in root.findall("./customers/customer"):
        cid = (cel.get("customer_id") or "").strip()
        cname = (cel.get("name") or "").strip()
        if not cid or not cname:
            raise ValueError("Each <customer> needs customer_id and name")
        defaults = {
            "name": cname,
            "contact_name": (cel.get("contact_name") or "").strip() or None,
            "email": (cel.get("email") or "").strip() or None,
            "phone": (cel.get("phone") or "").strip() or None,
            "address": (cel.get("address") or "").strip() or None,
            "city": (cel.get("city") or "").strip() or None,
            "state": (cel.get("state") or "").strip() or None,
            "zip_code": (cel.get("zip_code") or "").strip() or None,
            "country": (cel.get("country") or "").strip() or "USA",
            "payment_terms": (cel.get("payment_terms") or "").strip() or None,
            "notes": (cel.get("notes") or "").strip() or None,
        }
        obj, created = Customer.objects.update_or_create(customer_id=cid, defaults=defaults)
        if created:
            stats["customers_created"] += 1
        else:
            stats["customers_updated"] += 1

    for iel in root.findall("./items/item"):
        sku = (iel.get("sku") or "").strip()
        iname = (iel.get("name") or "").strip()
        if not sku or not iname:
            raise ValueError("Each <item> needs sku and name")
        vendor_str = (iel.get("vendor") or "").strip()
        itype = _item_type(iel.get("item_type", "finished_good"))
        uom = _uom(iel.get("unit_of_measure", "kg"))
        pc = _product_category(iel.get("product_category"))

        defaults = {
            "name": iname,
            "item_type": itype,
            "unit_of_measure": uom,
            "vendor": vendor_str or None,
            "description": (iel.get("description") or "").strip() or None,
            "vendor_item_name": (iel.get("vendor_item_name") or "").strip() or None,
            "vendor_item_number": (iel.get("vendor_item_number") or "").strip() or None,
            "product_category": pc,
        }
        obj, created = Item.objects.update_or_create(
            sku=sku,
            vendor=vendor_str or None,
            defaults=defaults,
        )
        if created:
            stats["items_created"] += 1
        else:
            stats["items_updated"] += 1

    return stats


def find_xml_files() -> list[Path]:
    d = get_private_sample_data_dir()
    if not d.is_dir():
        return []
    paths = sorted(Path(p) for p in glob.glob(str(d / "*.xml")))
    return [p for p in paths if p.is_file()]


def import_all_private_xml() -> dict[str, Any]:
    """
    Import every *.xml file in data/private_sample_data/.
    Returns summary with per-file stats.
    """
    d = get_private_sample_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    files = find_xml_files()
    if not files:
        return {
            "ok": True,
            "message": f"No .xml files found in {d}. Add files or use data/sample_import_template.xml as a guide.",
            "directory": str(d),
            "files": [],
            "totals": {},
        }

    per_file = []
    totals: dict[str, int] = {
        "vendors_created": 0,
        "vendors_updated": 0,
        "customers_created": 0,
        "customers_updated": 0,
        "items_created": 0,
        "items_updated": 0,
    }
    for path in files:
        stats = import_sample_xml_file(path)
        per_file.append(stats)
        for k in totals:
            totals[k] += stats.get(k, 0)

    return {
        "ok": True,
        "directory": str(d),
        "files": per_file,
        "totals": totals,
    }


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def import_private_sample_xml_api(request):
    if not request.user.is_staff:
        return Response({"error": "Staff only."}, status=http_status.HTTP_403_FORBIDDEN)
    try:
        result = import_all_private_xml()
        return Response(result)
    except Exception as e:
        return Response({"ok": False, "error": str(e)}, status=http_status.HTTP_400_BAD_REQUEST)
