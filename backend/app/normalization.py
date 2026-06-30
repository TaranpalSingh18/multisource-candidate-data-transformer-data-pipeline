from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import phonenumbers
from dateutil import parser as date_parser
from datetime import datetime
import pycountry


@dataclass(slots=True)
class PhoneNormalizationResult:
    e164: Optional[str]
    region_used: Optional[str]
    valid: bool


def normalize_phone(raw: str, region_hint: Optional[str] = None) -> PhoneNormalizationResult:
    """
    Normalize a phone number to E.164.
    If parsing fails, returns valid=False and e164=None.
    """
    raw = (raw or "").strip()
    if not raw:
        return PhoneNormalizationResult(e164=None, region_used=region_hint, valid=False)

    try:
        if raw.startswith("+"):
            parsed = phonenumbers.parse(raw, None)
        else:
            parsed = phonenumbers.parse(raw, region_hint or None)
        if not phonenumbers.is_valid_number(parsed):
            return PhoneNormalizationResult(e164=None, region_used=region_hint, valid=False)
        e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        region = phonenumbers.region_code_for_number(parsed)
        return PhoneNormalizationResult(e164=e164, region_used=region or region_hint, valid=True)
    except phonenumbers.NumberParseException:
        return PhoneNormalizationResult(e164=None, region_used=region_hint, valid=False)


def normalize_year_month(raw: str) -> Optional[str]:
    """
    Parse a free-form date string into YYYY-MM.
    Returns None if unparseable or if it signifies 'present/current'.
    """
    text = (raw or "").strip().lower()
    if not text:
        return None

    if "present" in text or "current" in text:
        return None

    try:
        # dateutil will pick a sensible default month/day; we only care about year+month.
        dt = date_parser.parse(text, default=datetime(2000, 1, 1))
        return f"{dt.year:04d}-{dt.month:02d}"
    except (ValueError, OverflowError):
        return None


def normalize_country(raw: str) -> Optional[str]:
    """
    Fuzzy-normalize a free-text country/location string to ISO 3166-1 alpha-2.
    Returns None if we cannot confidently resolve it.
    """
    text = (raw or "").strip()
    if not text:
        return None

    # Try exact name first
    try:
        country = pycountry.countries.lookup(text)
        return country.alpha_2
    except LookupError:
        pass

    # Very small heuristic: if text contains a comma, look at last token.
    if "," in text:
        tail = text.split(",")[-1].strip()
        try:
            country = pycountry.countries.lookup(tail)
            return country.alpha_2
        except LookupError:
            return None

    return None

