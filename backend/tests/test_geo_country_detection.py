"""GET /api/geo/country resolution order.

Frontend's CountryPicker calls this on first visit (no localStorage) to
auto-default to the visitor's country. Resolution order:
   1. CDN edge header (cf-ipcountry, x-vercel-ip-country, …)
   2. ipapi.co lookup using x-forwarded-for / client IP
   3. NZ fallback
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import requests

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

API_URL = os.environ.get("EXTERNAL_API_URL") or "http://localhost:8001"


def test_geo_header_takes_priority():
    """A `cf-ipcountry` edge header trumps any IP-based lookup."""
    r = requests.get(
        f"{API_URL}/api/geo/country",
        headers={"cf-ipcountry": "IN"},
        timeout=5,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["country"] == "IN"
    assert body["source"] == "header"


def test_geo_vercel_header_also_recognised():
    r = requests.get(
        f"{API_URL}/api/geo/country",
        headers={"x-vercel-ip-country": "GB"},
        timeout=5,
    )
    assert r.json()["country"] == "GB"
    assert r.json()["source"] == "header"


def test_geo_invalid_header_falls_through():
    """`XX` / 1-letter / numeric values must be ignored, not echoed back."""
    r = requests.get(
        f"{API_URL}/api/geo/country",
        headers={"cf-ipcountry": "XX"},
        timeout=5,
    )
    body = r.json()
    # Source must NOT be 'header' since XX is invalid; we end up at ip or default.
    assert body["source"] in ("ip", "default")
    assert len(body["country"]) == 2


def test_geo_lowercase_header_normalised_to_upper():
    r = requests.get(
        f"{API_URL}/api/geo/country",
        headers={"cf-ipcountry": "au"},
        timeout=5,
    )
    assert r.json()["country"] == "AU"


def test_geo_response_shape_is_stable():
    """The frontend relies on the {country, source} shape — pin it."""
    r = requests.get(f"{API_URL}/api/geo/country", timeout=5)
    body = r.json()
    assert set(body.keys()) == {"country", "source"}
    assert isinstance(body["country"], str)
    assert len(body["country"]) == 2
    assert body["source"] in ("header", "ip", "default")


def test_geo_cache_helpers():
    """Unit-test the TTL cache in isolation — important so a single visitor
    can't accidentally hammer the upstream API on every refresh."""
    from routers.events import _geo_cache_get, _geo_cache_put, _GEO_CACHE

    _GEO_CACHE.clear()
    assert _geo_cache_get("1.2.3.4") is None

    _geo_cache_put("1.2.3.4", "NZ")
    assert _geo_cache_get("1.2.3.4") == "NZ"

    # Force expiry by mutating the stored timestamp directly.
    _GEO_CACHE["1.2.3.4"] = ("NZ", 0.0)
    assert _geo_cache_get("1.2.3.4") is None
    assert "1.2.3.4" not in _GEO_CACHE  # auto-evicted on stale read
