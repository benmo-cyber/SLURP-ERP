"""
Build a single display string for vendor location from Vendor columns + SupplierSurvey.company_info.
Used by VendorSerializer and management commands.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from django.core.exceptions import ObjectDoesNotExist


def _pick(d: dict, keys: list[str]) -> str:
    """String values from questionnaire JSON; also accepts int/float (e.g. zip as number)."""
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            s = str(v).strip()
            if s:
                return s
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ''


def extract_structured_from_company_info(info: dict | None) -> dict[str, str | None]:
    """Structured keys + one nested level (same as sync_vendor_address_from_survey)."""
    if not info or not isinstance(info, dict):
        return {}

    street = _pick(
        info,
        [
            'street_address',
            'street',
            'street1',
            'street2',
            'address_line_1',
            'address_line1',
            'AddressLine1',
            'addressLine1',
            'line1',
            'line_1',
            'Address1',
            'Addr1',
            'addr1',
            'Street',
            'streetAddress',
            'StreetAddress',
            'facility_street',
            'plant_street',
        ],
    )
    block = _pick(
        info,
        [
            'address',
            'physical_address',
            'company_address',
            'mailing_address',
            'full_address',
            'Address',
            'business_address',
            'vendor_address',
            'facility_address',
            'plant_address',
            'location_address',
            'hq_address',
        ],
    )
    city = _pick(
        info,
        ['city', 'town', 'municipality', 'City', 'locality', 'CityTown']
    )
    state = _pick(
        info,
        ['state', 'province', 'region', 'State', 'StateProvince', 'state_province', 'st']
    )
    zip_code = _pick(
        info,
        ['zip_code', 'zip', 'postal_code', 'postal', 'Zip', 'ZipCode', 'postalCode', 'zipcode'],
    )
    country = _pick(info, ['country', 'Country', 'CountryCode', 'country_code'])

    if street or block or city or state or zip_code or country:
        return {
            'street_address': street or None,
            'address': block or None,
            'city': city or None,
            'state': state or None,
            'zip_code': zip_code or None,
            'country': country or None,
        }

    nested_keys = [
        'headquarters',
        'facility',
        'facility_address',
        'location',
        'company_address',
        'mailing_address',
        'physical_address',
        'billing_address',
        'shipping_address',
        'company_info',
        'plant',
        'manufacturing',
        'manufacturing_site',
        'vendor_facility',
        'address_block',
    ]
    for nk in nested_keys:
        sub = info.get(nk)
        if isinstance(sub, dict):
            inner = extract_structured_from_company_info(sub)
            if any(inner.values()):
                return inner
    return {}


def _collect_strings(obj: Any, depth: int = 0, max_depth: int = 8) -> list[str]:
    if depth > max_depth:
        return []
    if isinstance(obj, str):
        s = obj.strip()
        return [s] if s else []
    if isinstance(obj, dict):
        out: list[str] = []
        for k, v in obj.items():
            lk = str(k).lower() if k is not None else ''
            # Skip contact fields unless the key clearly denotes an address (e.g. billing_address).
            if any(x in lk for x in ('email', 'phone', 'fax', 'url', 'website', '@')) and 'address' not in lk:
                continue
            out.extend(_collect_strings(v, depth + 1, max_depth))
        return out
    if isinstance(obj, list):
        out = []
        for item in obj:
            out.extend(_collect_strings(item, depth + 1, max_depth))
        return out
    return []


_RE_LOOKS_ADDRESS = re.compile(
    r'(\d+\s+.+\s+(?:st|street|ave|avenue|rd|road|dr|drive|blvd|way|ln|lane|ct|court|hwy|pkwy|suite|ste|unit|box)\b)|'
    r'(\d{4,})|'
    r'(.{15,})',
    re.IGNORECASE,
)


def _string_looks_like_address_line(s: str) -> bool:
    if len(s) < 6:
        return False
    if '@' in s:
        return False
    if _RE_LOOKS_ADDRESS.search(s):
        return True
    if ',' in s and any(c.isdigit() for c in s):
        return True
    if sum(1 for c in s if c.isdigit()) >= 2 and len(s) >= 10:
        return True
    return False


def _format_from_parts(
    street_address: str | None,
    address: str | None,
    city: str | None,
    state: str | None,
    zip_code: str | None,
    country: str | None,
) -> str:
    st = (street_address or '').strip()
    legacy = (address or '').strip()
    city = (city or '').strip()
    state = (state or '').strip()
    zip_s = (zip_code or '').strip() if zip_code is not None else ''
    country = (country or '').strip()

    parts: list[str] = []
    if st:
        parts.append(st)
    if legacy and legacy != st:
        parts.append(legacy)
    if not parts and legacy:
        parts.append(legacy)
    city_state = ', '.join([x for x in (city, state) if x])
    if city_state:
        parts.append(city_state)
    if zip_s:
        parts.append(zip_s)
    if country and country.upper() != 'USA':
        parts.append(country)
    return ' · '.join(parts)


def format_company_info_fallback(company_info: dict | None) -> str:
    """When structured extraction fails, join address-like strings from JSON."""
    if not company_info or not isinstance(company_info, dict):
        return ''

    structured = extract_structured_from_company_info(company_info)
    s = _format_from_parts(
        structured.get('street_address'),
        structured.get('address'),
        structured.get('city'),
        structured.get('state'),
        structured.get('zip_code'),
        structured.get('country'),
    )
    if s:
        return s

    raw_strings = _collect_strings(company_info)
    candidates = []
    seen: set[str] = set()
    for t in raw_strings:
        if not _string_looks_like_address_line(t):
            continue
        if t in seen:
            continue
        seen.add(t)
        candidates.append(t)
        if len(candidates) >= 6:
            break
    if candidates:
        return ' · '.join(candidates)
    return ''


_SURVEY_JSON_ATTRS = (
    'company_info',
    'compliance_responses',
    'quality_program_responses',
    'food_security_responses',
    'see_program_responses',
)


def iter_survey_address_dicts(vendor) -> list[dict]:
    """All non-empty JSON blobs on the supplier questionnaire that may contain facility address fields."""
    out: list[dict] = []
    try:
        survey = vendor.survey
    except ObjectDoesNotExist:
        return out
    if survey is None:
        return out
    for attr in _SURVEY_JSON_ATTRS:
        val = getattr(survey, attr, None)
        if isinstance(val, dict) and val:
            out.append(val)
    return out


def get_survey_company_info(vendor) -> dict | None:
    """Avoid RelatedObjectDoesNotExist on optional reverse OneToOne."""
    try:
        survey = vendor.survey
    except ObjectDoesNotExist:
        return None
    if survey is None:
        return None
    ci = getattr(survey, 'company_info', None)
    if isinstance(ci, dict) and ci:
        return ci
    return None


def _display_from_survey_blobs(vendor) -> str:
    for blob in iter_survey_address_dicts(vendor):
        structured = extract_structured_from_company_info(blob)
        s = _format_from_parts(
            structured.get('street_address'),
            structured.get('address'),
            structured.get('city'),
            structured.get('state'),
            structured.get('zip_code'),
            structured.get('country'),
        )
        if s:
            return s
        fb = format_company_info_fallback(blob)
        if fb:
            return fb
    return ''


def vendor_address_columns_blank(vendor) -> bool:
    """True when structured address fields on Vendor are empty (legacy `address` alone may still be set)."""
    return not (
        (getattr(vendor, 'street_address', None) or '').strip()
        or (getattr(vendor, 'address', None) or '').strip()
        or (getattr(vendor, 'city', None) or '').strip()
    )


def sync_survey_address_to_vendor(vendor, dry_run: bool = False) -> bool:
    """
    Copy facility address from SupplierSurvey JSON onto Vendor columns when those columns are empty.
    Used by management command and post_save signal.
    """
    if not vendor_address_columns_blank(vendor):
        return False
    blobs = iter_survey_address_dicts(vendor)
    if not blobs:
        return False

    combined: dict[str, str | None] = {}
    fallback_text = ''

    for blob in blobs:
        ext = extract_structured_from_company_info(blob)
        for k in ('street_address', 'address', 'city', 'state', 'zip_code', 'country'):
            v = ext.get(k)
            if v and not combined.get(k):
                combined[k] = v
        if not any(combined.values()) and not fallback_text:
            fallback_text = format_company_info_fallback(blob)

    if not any(combined.values()) and not fallback_text:
        return False

    if dry_run:
        return True

    if combined.get('street_address') and not (vendor.street_address or '').strip():
        vendor.street_address = (combined['street_address'] or '')[:255]
    if combined.get('address') and not (vendor.address or '').strip():
        vendor.address = combined['address']
    if combined.get('city') and not (vendor.city or '').strip():
        vendor.city = (combined['city'] or '')[:100]
    if combined.get('state') and not (vendor.state or '').strip():
        vendor.state = (combined['state'] or '')[:50]
    if combined.get('zip_code') and not (vendor.zip_code or '').strip():
        vendor.zip_code = str(combined['zip_code'])[:20]
    if combined.get('country') and not (vendor.country or '').strip():
        vendor.country = (combined['country'] or '')[:100]
    if (
        fallback_text
        and not (vendor.street_address or '').strip()
        and not (vendor.address or '').strip()
    ):
        vendor.address = fallback_text[:10000]

    vendor.save()
    return True


def _fallback_address_from_notes(notes: Optional[str]) -> str:
    """Last resort: lines in vendor notes that look like an address or an 'Address:' block."""
    if not notes or not str(notes).strip():
        return ''
    text = str(notes).strip()
    m = re.search(r'Address\s*:\s*([^\n]+(?:\n[^\n]+){0,4})', text, re.IGNORECASE)
    if m:
        block = ' '.join(line.strip() for line in m.group(1).splitlines() if line.strip())
        if len(block) > 5:
            return block[:500]
    zip_line = re.compile(r'\b\d{5}(?:-\d{4})?\b')
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for i, line in enumerate(lines):
        if zip_line.search(line):
            chunk = lines[max(0, i - 2) : i + 3]
            return ' · '.join(chunk)[:500]
    for line in lines:
        if len(line) < 8:
            continue
        if re.search(r'\d', line) and (
            ',' in line
            or re.search(r'\b(st|street|ave|avenue|rd|road|dr|drive|blvd|suite|ste|unit|box)\b', line, re.I)
        ):
            return line[:500]
    return ''


def build_display_address(vendor) -> str:
    """Single line for API display_address and UI."""
    street = (getattr(vendor, 'street_address', None) or '').strip()
    legacy = (getattr(vendor, 'address', None) or '').strip()
    city = (getattr(vendor, 'city', None) or '').strip()
    state = (getattr(vendor, 'state', None) or '').strip()
    z = getattr(vendor, 'zip_code', None)
    zip_code = (str(z).strip() if z is not None else '')
    country = (getattr(vendor, 'country', None) or '').strip()

    direct = _format_from_parts(
        street or None,
        legacy or None,
        city or None,
        state or None,
        zip_code or None,
        country or None,
    )
    if direct:
        return direct

    notes_fb = _fallback_address_from_notes(getattr(vendor, 'notes', None))
    if notes_fb:
        return notes_fb

    return _display_from_survey_blobs(vendor)
