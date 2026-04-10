"""
Resolve free-text country input to ISO 3166-1 alpha-2 for APIs (e.g. Nominatim `countrycodes`).
"""
from __future__ import annotations

import re
from typing import Optional

# Common English and local names / abbreviations → ISO alpha-2 (lowercase)
_COUNTRY_ALIASES: dict[str, str] = {
    "afghanistan": "af",
    "albania": "al",
    "algeria": "dz",
    "argentina": "ar",
    "australia": "au",
    "austria": "at",
    "bangladesh": "bd",
    "belgium": "be",
    "brazil": "br",
    "bulgaria": "bg",
    "cambodia": "kh",
    "canada": "ca",
    "chile": "cl",
    "china": "cn",
    "colombia": "co",
    "costa rica": "cr",
    "croatia": "hr",
    "czech republic": "cz",
    "czechia": "cz",
    "denmark": "dk",
    "ecuador": "ec",
    "egypt": "eg",
    "estonia": "ee",
    "ethiopia": "et",
    "finland": "fi",
    "france": "fr",
    "germany": "de",
    "deutschland": "de",
    "ghana": "gh",
    "greece": "gr",
    "guatemala": "gt",
    "hong kong": "hk",
    "hungary": "hu",
    "iceland": "is",
    "india": "in",
    "indonesia": "id",
    "ireland": "ie",
    "israel": "il",
    "italy": "it",
    "italia": "it",
    "jamaica": "jm",
    "japan": "jp",
    "kenya": "ke",
    "latvia": "lv",
    "lithuania": "lt",
    "luxembourg": "lu",
    "malaysia": "my",
    "mexico": "mx",
    "morocco": "ma",
    "netherlands": "nl",
    "the netherlands": "nl",
    "holland": "nl",
    "new zealand": "nz",
    "nigeria": "ng",
    "norway": "no",
    "pakistan": "pk",
    "panama": "pa",
    "peru": "pe",
    "philippines": "ph",
    "poland": "pl",
    "portugal": "pt",
    "romania": "ro",
    "russia": "ru",
    "russian federation": "ru",
    "saudi arabia": "sa",
    "serbia": "rs",
    "singapore": "sg",
    "slovakia": "sk",
    "slovenia": "si",
    "south africa": "za",
    "south korea": "kr",
    "korea": "kr",
    "spain": "es",
    "sri lanka": "lk",
    "sweden": "se",
    "switzerland": "ch",
    "taiwan": "tw",
    "thailand": "th",
    "turkey": "tr",
    "türkiye": "tr",
    "turkiye": "tr",
    "ukraine": "ua",
    "united arab emirates": "ae",
    "uae": "ae",
    "united kingdom": "gb",
    "uk": "gb",
    "great britain": "gb",
    "britain": "gb",
    "england": "gb",
    "scotland": "gb",
    "wales": "gb",
    "northern ireland": "gb",
    "united states": "us",
    "united states of america": "us",
    "usa": "us",
    "u s": "us",
    "vietnam": "vn",
    "viet nam": "vn",
}

# ISO 3166-1 alpha-3 → alpha-2 (common in forms)
_ALPHA3_TO_ALPHA2: dict[str, str] = {
    "usa": "us",
    "gbr": "gb",
    "deu": "de",
    "fra": "fr",
    "ind": "in",
    "chn": "cn",
    "jpn": "jp",
    "aus": "au",
    "can": "ca",
    "mex": "mx",
    "bra": "br",
    "nld": "nl",
    "ita": "it",
    "esp": "es",
    "che": "ch",
    "swe": "se",
    "nor": "no",
    "irl": "ie",
    "pol": "pl",
    "tur": "tr",
    "kor": "kr",
    "sgp": "sg",
    "mys": "my",
    "tha": "th",
    "phl": "ph",
    "vnm": "vn",
    "idn": "id",
    "pak": "pk",
    "bgd": "bd",
    "zaf": "za",
    "egy": "eg",
    "nga": "ng",
    "arg": "ar",
    "chl": "cl",
    "col": "co",
    "per": "pe",
    "aut": "at",
    "bel": "be",
    "cze": "cz",
    "hun": "hu",
    "rou": "ro",
    "bgr": "bg",
    "hrv": "hr",
    "svn": "si",
    "svk": "sk",
    "ltu": "lt",
    "lva": "lv",
    "est": "ee",
    "fin": "fi",
    "dnk": "dk",
    "isl": "is",
    "prt": "pt",
    "grc": "gr",
    "cyp": "cy",
    "mlt": "mt",
    "lux": "lu",
    "nzl": "nz",
    "isr": "il",
    "sau": "sa",
    "are": "ae",
}


def _normalize(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[\s.]+", " ", s)
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def country_text_to_iso3166_alpha2(raw: str) -> Optional[str]:
    """
    Return lowercase ISO 3166-1 alpha-2 if recognized, else None.
    Accepts common English names, 2- and 3-letter codes.
    """
    if not raw or not raw.strip():
        return None
    t = _normalize(raw)
    if not t:
        return None
    if len(t) == 2 and t.isalpha():
        return t.lower()
    if len(t) == 3 and t.isalpha():
        a2 = _ALPHA3_TO_ALPHA2.get(t)
        if a2:
            return a2
    return _COUNTRY_ALIASES.get(t)
