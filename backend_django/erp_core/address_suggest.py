"""
Address autocomplete for vendor facility addresses.

- Prefer Mapbox Geocoding API when MAPBOX_ACCESS_TOKEN is set (better US/international match quality).
- Fallback: OpenStreetMap Nominatim (free; usage policy: moderate requests, identify via User-Agent).
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from erp_core.country_iso import country_text_to_iso3166_alpha2

logger = logging.getLogger(__name__)

NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"
# Identifiable User-Agent per Nominatim usage policy
USER_AGENT = "WWI-ERP/1.0 (internal ERP; address autocomplete)"
# Force English result text (no wildcard — avoids servers falling back to other languages).
ACCEPT_LANGUAGE = "en-US,en;q=0.9"
# CJK / Japanese / Korean / Arabic script — if still present, try namedetails name:en / name:latin
_NON_LATIN_RE = re.compile(
    r"[\u0600-\u06ff"  # Arabic
    r"\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff"  # CJK
    r"\u3040-\u30ff"  # Hiragana/Katakana
    r"\uac00-\ud7af]"  # Hangul
)


def _english_name_from_namedetails(nd: dict) -> str:
    for k in ("name:en", "official_name:en", "name:latin", "alt_name:en"):
        v = nd.get(k)
        if v and str(v).strip():
            return str(v).strip()
    return ""


def _prefer_english_label(hit: dict) -> str:
    """Use Latin/English display when Nominatim still returns local script in display_name."""
    dn = (hit.get("display_name") or "").strip()
    nd = hit.get("namedetails")
    nd = nd if isinstance(nd, dict) else {}
    en = _english_name_from_namedetails(nd)
    if not dn:
        return en
    if not en:
        return dn
    if "," in dn:
        first, rest = dn.split(",", 1)
        if _NON_LATIN_RE.search(first):
            return f"{en},{rest}".strip()
    elif _NON_LATIN_RE.search(dn):
        return en
    return dn


def _line1_from_hit(hit: dict) -> str:
    addr = hit.get("address") or {}
    nd = hit.get("namedetails")
    nd = nd if isinstance(nd, dict) else {}
    hn = (addr.get("house_number") or "").strip()
    road = (
        addr.get("road")
        or addr.get("pedestrian")
        or addr.get("residential")
        or addr.get("path")
        or addr.get("footway")
    )
    road = (road or "").strip()
    if road and _NON_LATIN_RE.search(road):
        en_road = _english_name_from_namedetails(nd)
        if en_road and not _NON_LATIN_RE.search(en_road):
            road = en_road
    if hn and road:
        return f"{hn} {road}".strip()[:255]
    if road:
        return road[:255]
    if hn:
        return hn[:255]
    dn = (hit.get("display_name") or "").strip()
    if dn:
        first = dn.split(",")[0].strip()
        if _NON_LATIN_RE.search(first):
            en_fallback = _english_name_from_namedetails(nd)
            if en_fallback and not _NON_LATIN_RE.search(en_fallback):
                return en_fallback[:255]
        return first[:255]
    return ""


def _city_from_address(addr: dict) -> str:
    for k in (
        "city",
        "town",
        "village",
        "hamlet",
        "municipality",
        "city_district",
        "suburb",
    ):
        v = addr.get(k)
        if v:
            return str(v).strip()[:100]
    return ""


def _state_from_address(addr: dict) -> str:
    for k in ("state", "region", "province", "county"):
        v = addr.get(k)
        if v:
            return str(v).strip()[:50]
    return ""


def _hit_to_suggestion(hit: dict) -> dict:
    addr = hit.get("address") or {}
    line1 = _line1_from_hit(hit)
    city = _city_from_address(addr)
    state = _state_from_address(addr)
    pc = addr.get("postcode") or ""
    if pc:
        pc = str(pc).strip()[:20]
    country = (addr.get("country") or "").strip()[:100]
    label = (_prefer_english_label(hit) or line1 or "").strip()
    return {
        "label": label,
        "street_address": line1,
        "address": "",
        "city": city,
        "state": state,
        "zip_code": pc,
        "country": country,
    }


# --- Mapbox Geocoding API (optional) ---

MAPBOX_GEOCODE = "https://api.mapbox.com/geocoding/v5/mapbox.places/{query}.json"
MAPBOX_UA = "WWI-ERP/1.0 (address autocomplete; Mapbox)"


def _mapbox_context_parse(feature: dict) -> dict[str, str]:
    """Extract postcode, locality, region, country from Mapbox feature.context."""
    out = {"postcode": "", "place": "", "region": "", "country": ""}
    ctx = feature.get("context")
    if not isinstance(ctx, list):
        return out
    for c in ctx:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or "")
        text = str(c.get("text") or "").strip()
        if cid.startswith("postcode."):
            out["postcode"] = text[:20]
        elif cid.startswith("place.") or cid.startswith("district."):
            if not out["place"]:
                out["place"] = text[:100]
        elif cid.startswith("region."):
            sc = str(c.get("short_code") or "")
            if sc.upper().startswith("US-") and len(sc) > 3:
                out["region"] = sc.split("-")[-1].upper()[:50]
            else:
                out["region"] = text[:50]
        elif cid.startswith("country."):
            out["country"] = text[:100]
    return out


def _mapbox_feature_to_suggestion(feature: dict) -> dict:
    props = feature.get("properties") or {}
    if not isinstance(props, dict):
        props = {}
    house = str(feature.get("address") or props.get("address") or "").strip()
    street_name = str(feature.get("text") or "").strip()
    if house and street_name:
        line1 = f"{house} {street_name}".strip()[:255]
    elif street_name:
        line1 = street_name[:255]
    else:
        line1 = ""

    ctxp = _mapbox_context_parse(feature)
    place_name = str(feature.get("place_name") or "").strip()
    if not line1 and place_name:
        line1 = place_name.split(",")[0].strip()[:255]

    label = place_name or line1
    return {
        "label": label,
        "street_address": line1,
        "address": "",
        "city": ctxp["place"],
        "state": ctxp["region"],
        "zip_code": ctxp["postcode"],
        "country": ctxp["country"],
    }


def _fetch_mapbox_suggestions(q: str, country_raw: str) -> list[dict]:
    token = getattr(settings, "MAPBOX_ACCESS_TOKEN", "") or ""
    if not token:
        return []

    path_q = urllib.parse.quote(q, safe="")
    # language: IETF tag — English labels for place_name, context[].text, etc.
    params: dict[str, str] = {
        "access_token": token,
        "limit": "8",
        "types": "address",
        "autocomplete": "true",
        "language": "en",
    }
    cc = country_text_to_iso3166_alpha2(country_raw)
    if cc:
        params["country"] = cc.lower()

    url = f"{MAPBOX_GEOCODE.format(query=path_q)}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": MAPBOX_UA,
            "Accept": "application/json",
            "Accept-Language": ACCEPT_LANGUAGE,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        logger.warning("Mapbox geocoding failed: %s", e)
        return []

    feats = data.get("features") if isinstance(data, dict) else None
    if not isinstance(feats, list):
        return []

    out: list[dict] = []
    for f in feats:
        if not isinstance(f, dict):
            continue
        try:
            out.append(_mapbox_feature_to_suggestion(f))
        except Exception:
            continue
    return out


def _fetch_nominatim_suggestions(q: str, country_raw: str) -> list[dict]:
    nominatim_params: dict[str, str] = {
        "q": q,
        "format": "json",
        "addressdetails": "1",
        "namedetails": "1",
        "limit": "8",
        # Nominatim API: prefer English names for structured fields and display_name
        "accept-language": "en",
    }
    cc = country_text_to_iso3166_alpha2(country_raw)
    if cc:
        nominatim_params["countrycodes"] = cc

    params = urllib.parse.urlencode(nominatim_params)
    url = f"{NOMINATIM_SEARCH}?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": ACCEPT_LANGUAGE,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        logger.warning("Nominatim search failed: %s", e)
        return []

    if not isinstance(data, list):
        return []

    out: list[dict] = []
    for hit in data:
        if not isinstance(hit, dict):
            continue
        try:
            out.append(_hit_to_suggestion(hit))
        except Exception:
            continue
    return out


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def address_suggest(request):
    """
    Query params:
      q — search string (min 3 chars).
      country — optional; free-text country name or ISO code; limits results to that country when recognized.
    Returns a list of { label, street_address, address, city, state, zip_code, country }.
    """
    q = (request.GET.get("q") or "").strip()
    if len(q) < 3:
        return Response([])
    if len(q) > 200:
        q = q[:200]

    country_raw = (request.GET.get("country") or "").strip()

    if getattr(settings, "MAPBOX_ACCESS_TOKEN", ""):
        mb = _fetch_mapbox_suggestions(q, country_raw)
        if mb:
            return Response(mb)

    return Response(_fetch_nominatim_suggestions(q, country_raw))
