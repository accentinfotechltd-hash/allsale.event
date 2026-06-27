"""Country → currency mapping invariants.

Every country in `frontend/src/lib/countries.js` MUST map to a currency
whose symbol is registered in `emails._money()` symbol map. Otherwise
buyers from that country would receive invoices showing a bare currency
code (e.g. "VND 50.00") instead of the local symbol ("₫50.00").

Also pins a sample of country → currency mappings so an accidental
regression (back to "USD" for India/Pakistan/Qatar/etc.) fails loud.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from emails import _money  # noqa: E402

FRONTEND_COUNTRIES_JS = Path(__file__).resolve().parent.parent.parent / "frontend/src/lib/countries.js"


def _parse_country_currencies() -> dict[str, str]:
    """Pull `code → currency` pairs out of the JS catalog with a regex.

    Cheaper + more robust than spinning up a Node runtime just for tests.
    """
    text = FRONTEND_COUNTRIES_JS.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for m in re.finditer(
        r'code:\s*"(?P<code>[A-Z]{2})".*?currency:\s*"(?P<cur>[A-Z]{3})"',
        text,
    ):
        out[m.group("code")] = m.group("cur")
    return out


def test_every_country_currency_has_a_symbol_in_emails():
    """If a buyer's event currency isn't in `_money`'s symbol map, the
    invoice falls back to a bare `<CODE> X.XX` string. Verify the map is
    complete for every currency used by any country.
    """
    mapping = _parse_country_currencies()
    assert mapping, "Failed to parse frontend countries.js — regex broke?"

    # Pull the actual symbols dict from emails._money() by introspecting
    # the source — simpler than calling _money() and pattern-matching the
    # output (which is ambiguous when a currency's "symbol" is the code
    # with a trailing space, e.g. "AED ").
    import inspect
    from emails import _money as _m
    src = inspect.getsource(_m)
    declared = set(re.findall(r'"([A-Z]{3})"\s*:\s*"', src))

    missing = [
        (country, cur) for country, cur in mapping.items() if cur not in declared
    ]
    assert not missing, (
        "These countries map to a currency that has no symbol entry in "
        f"emails._money(): {missing}. Add them so invoices render the "
        "right symbol instead of a bare code."
    )


@pytest.mark.parametrize("country,expected_currency", [
    ("NZ", "NZD"),  ("AU", "AUD"),  ("US", "USD"),
    ("IN", "INR"),  ("PK", "PKR"),  ("BD", "BDT"),  ("LK", "LKR"),
    ("NP", "NPR"),  ("VN", "VND"),  ("TW", "TWD"),
    ("AE", "AED"),  ("SA", "SAR"),  ("QA", "QAR"),  ("KW", "KWD"),
    ("BH", "BHD"),  ("OM", "OMR"),  ("IL", "ILS"),
    ("NG", "NGN"),  ("KE", "KES"),  ("EG", "EGP"),  ("MA", "MAD"),
    ("GH", "GHS"),  ("ZA", "ZAR"),
    ("AR", "ARS"),  ("CL", "CLP"),  ("CO", "COP"),  ("BR", "BRL"),
    ("TR", "TRY"),  ("PL", "PLN"),  ("CZ", "CZK"),
    ("FJ", "FJD"),
])
def test_country_maps_to_its_local_currency(country: str, expected_currency: str):
    """Pin the country → currency map so accidental reverts to USD fail loud."""
    mapping = _parse_country_currencies()
    assert mapping.get(country) == expected_currency, (
        f"{country} maps to {mapping.get(country)!r} but should be {expected_currency!r}"
    )
