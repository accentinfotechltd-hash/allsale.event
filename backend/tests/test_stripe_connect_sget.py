"""Stripe Connect onboarding — regression suite for the July 2026 fix.

**Backstory**: Stripe's newer Python SDK returns `StripeObject` instances
whose `.get(...)` method raises `AttributeError: get` (it treats `.get`
as an attribute lookup instead of a dict method). Our onboarding path
called `link.get("expires_at")` and every request 502'd even though the
underlying Stripe API returned HTTP 200 with a valid URL.

**Fix**: introduced `_sget(obj, key, default)` which uses `getattr` first
and falls back to `__getitem__`. All Stripe SDK reads now go through
`_sget` so a future SDK version bump can't re-break this the same way.

These tests do NOT hit the real Stripe API — they build fake objects
that mimic the two SDK behaviours (dict-like and attribute-only) and
verify `_sget` reads both correctly, plus the placeholder-key guard
returns a friendly 503.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from routers import stripe_connect as sc  # noqa: E402


# ---------------------------------------------------------------------------
# _sget — the safe accessor
# ---------------------------------------------------------------------------
class _AttrOnlyLike:
    """Newer StripeObject: attribute access works, `.get()` raises."""
    def __init__(self, **fields):
        for k, v in fields.items():
            setattr(self, k, v)

    def get(self, *a, **kw):  # simulate the broken behaviour
        raise AttributeError("get")


class _DictLike:
    """Older StripeObject: behaves like a dict."""
    def __init__(self, **fields):
        self._d = fields

    def __getitem__(self, k):
        return self._d[k]

    def get(self, k, default=None):
        return self._d.get(k, default)


def test_sget_reads_attribute_only_object():
    obj = _AttrOnlyLike(url="https://x/foo", expires_at=1700000000)
    # Attribute access works transparently — `.get` would raise so this is the
    # WHOLE point of the helper.
    assert sc._sget(obj, "url") == "https://x/foo"
    assert sc._sget(obj, "expires_at") == 1700000000
    assert sc._sget(obj, "missing") is None
    assert sc._sget(obj, "missing", "fallback") == "fallback"


def test_sget_reads_dict_like_object():
    obj = _DictLike(url="https://y/bar", expires_at=1700000001)
    assert sc._sget(obj, "url") == "https://y/bar"
    assert sc._sget(obj, "missing") is None
    assert sc._sget(obj, "missing", 42) == 42


def test_sget_reads_plain_dict():
    d = {"a": 1, "b": None}
    assert sc._sget(d, "a") == 1
    # None values should fall back to the default (that's the historical
    # behaviour of `.get() or default`).
    assert sc._sget(d, "b", "fallback") == "fallback"
    assert sc._sget(d, "missing", "fallback") == "fallback"


def test_sget_returns_default_for_none_obj():
    assert sc._sget(None, "any") is None
    assert sc._sget(None, "any", "x") == "x"


# ---------------------------------------------------------------------------
# _ensure_stripe placeholder-key guard
# ---------------------------------------------------------------------------
def test_ensure_stripe_rejects_placeholder_key(monkeypatch):
    monkeypatch.setattr(sc, "STRIPE_API_KEY", "sk_test_emergent")
    monkeypatch.setattr(sc, "_STRIPE_AVAILABLE", True)
    with pytest.raises(HTTPException) as ei:
        sc._ensure_stripe()
    assert ei.value.status_code == 503
    assert "emergent test key" in ei.value.detail.lower()
    assert "dashboard.stripe.com" in ei.value.detail


def test_ensure_stripe_rejects_missing_key(monkeypatch):
    monkeypatch.setattr(sc, "STRIPE_API_KEY", "")
    monkeypatch.setattr(sc, "_STRIPE_AVAILABLE", True)
    with pytest.raises(HTTPException) as ei:
        sc._ensure_stripe()
    assert ei.value.status_code == 503


def test_ensure_stripe_accepts_real_key(monkeypatch):
    # A real-looking test secret — sk_test_51 prefix, ~107 chars.
    monkeypatch.setattr(sc, "STRIPE_API_KEY", "sk_test_51" + "a" * 97)
    monkeypatch.setattr(sc, "_STRIPE_AVAILABLE", True)
    # Should NOT raise.
    sc._ensure_stripe()
