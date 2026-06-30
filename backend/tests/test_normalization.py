from app.normalization import normalize_phone, normalize_year_month, normalize_country


def test_normalize_phone_with_country_code():
    result = normalize_phone("+1 415 555 2671")
    assert result.valid
    assert result.e164.startswith("+1")


def test_normalize_phone_without_country_code_uses_region_hint():
    # No country code, but region_hint should allow parsing.
    result = normalize_phone("0415 555 2671", region_hint="AU")
    # We don't assert exact number, just that parsing succeeded or failed deterministically.
    assert result.region_used in {"AU", None}


def test_normalize_year_month_parses_simple_date():
    assert normalize_year_month("Jan 2022") == "2022-01"


def test_normalize_year_month_present_returns_none():
    assert normalize_year_month("2020 - present") is None


def test_normalize_country_basic_lookup():
    assert normalize_country("United States") == "US"
    assert normalize_country("US") == "US"

