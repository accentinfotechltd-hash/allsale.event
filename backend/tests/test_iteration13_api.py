"""Iteration 13 — HTTP API-level tests for the 5 new features:

  c3 — Group bookings auto-discount
  b3 — FAQ chatbot endpoints
  c1 — Gift cards
  c2 — Season passes / bundles
  d2 — Organizer referral program

These complement the existing function-level unit tests in
test_group_discount.py / test_faq_chatbot.py / test_gift_cards.py /
test_bundles.py / test_organizer_referrals.py.

Stripe Checkout create-session calls (POST /api/gift-cards/purchase and
POST /api/bundles/{id}/purchase) may return 502 if the live Stripe keys
on the preview env aren't valid — we therefore test the preconditions
(auth, ownership, currency mismatch, missing events) rather than relying
on Stripe accepting the call.
"""
from __future__ import annotations

import os
import uuid
from datetime import timedelta, datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

BASE = os.environ.get("REACT_APP_BACKEND_URL") or os.environ.get("FRONTEND_PUBLIC_URL")
if not BASE:
    # Last resort — read from frontend env file directly so the test still
    # works inside the container even if shell env isn't propagated.
    fe_env = Path("/app/frontend/.env")
    if fe_env.exists():
        for line in fe_env.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE = line.split("=", 1)[1].strip()
                break
BASE = (BASE or "").rstrip("/")

ADMIN_EMAIL = "admin@allsale.events"
ADMIN_PASSWORD = "admin123"


# ---------- helpers ----------

def _post(path, json=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return requests.post(f"{BASE}{path}", json=json, headers=h, timeout=30)


def _get(path, token=None):
    h = {}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return requests.get(f"{BASE}{path}", headers=h, timeout=30)


def _patch(path, json=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return requests.patch(f"{BASE}{path}", json=json, headers=h, timeout=30)


def _register_organizer():
    """Fresh organizer per test invocation."""
    email = f"test-org-{uuid.uuid4().hex[:8]}@iter13.example.com"
    r = requests.post(
        f"{BASE}/api/auth/register",
        json={"name": "Iter13 Org", "email": email, "password": "Pass1234!", "role": "organizer"},
        timeout=30,
    )
    assert r.status_code in (200, 201), f"register organizer failed: {r.status_code} {r.text}"
    return r.json()["token"], email


def _register_attendee():
    email = f"test-att-{uuid.uuid4().hex[:8]}@iter13.example.com"
    r = requests.post(
        f"{BASE}/api/auth/register",
        json={"name": "Iter13 Att", "email": email, "password": "Pass1234!", "role": "attendee"},
        timeout=30,
    )
    assert r.status_code in (200, 201), f"register attendee failed: {r.status_code} {r.text}"
    return r.json()["token"], email


def _admin_login():
    r = requests.post(
        f"{BASE}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    if r.status_code != 200:
        pytest.skip(f"admin login failed ({r.status_code}) — skipping admin-gated tests")
    return r.json()["token"]


def _make_event_payload(group_discount=None, currency="NZD", title=None):
    return {
        "title": title or f"TEST_evt_{uuid.uuid4().hex[:6]}",
        "description": "auto test",
        "category": "music",
        "venue": "Test Venue",
        "city": "Auckland",
        "country": "NZ",
        "date": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),
        "image_url": "https://example.com/img.jpg",
        "currency": currency,
        "tiers": [{"name": "GA", "price": 100.0, "capacity": 100}],
        "has_seatmap": False,
        "group_discount": group_discount,
    }


# ---------- c3 — group discount (via event create + read) ----------

class TestGroupDiscountAPI:
    def test_create_event_with_group_discount_persists_payload(self):
        token, _ = _register_organizer()
        payload = _make_event_payload(group_discount={"min_qty": 5, "pct_off": 20})
        r = _post("/api/events", payload, token=token)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        ev = r.json()
        assert ev["event_id"].startswith("evt_")
        assert ev.get("group_discount") == {"min_qty": 5, "pct_off": 20}

        # Verify GET returns it
        r2 = _get(f"/api/events/{ev['event_id']}")
        assert r2.status_code == 200
        assert r2.json().get("group_discount") == {"min_qty": 5, "pct_off": 20}

    def test_event_group_discount_editable_via_patch(self):
        token, _ = _register_organizer()
        r = _post("/api/events", _make_event_payload(group_discount={"min_qty": 3, "pct_off": 10}), token=token)
        assert r.status_code == 200
        eid = r.json()["event_id"]

        r2 = _patch(f"/api/events/{eid}", {"group_discount": {"min_qty": 6, "pct_off": 25}}, token=token)
        assert r2.status_code == 200, f"{r2.status_code} {r2.text}"
        assert r2.json().get("group_discount") == {"min_qty": 6, "pct_off": 25}


# ---------- b3 — FAQ chatbot ----------

class TestFaqChatbotAPI:
    def test_faq_ask_returns_answer_or_502_when_llm_unconfigured(self):
        sid = f"sup_{uuid.uuid4().hex[:14]}"
        r = _post("/api/support/faq/ask", {"session_id": sid, "question": "How do I find my ticket?"})
        # 200 happy path with EMERGENT_LLM_KEY set; 502 if the LLM call itself
        # fails (rate limit etc); 503 only if the key isn't configured at all.
        assert r.status_code in (200, 502, 503), f"{r.status_code} {r.text}"
        if r.status_code == 200:
            body = r.json()
            assert "answer" in body
            assert "can_help" in body
            assert isinstance(body["answer"], str) and len(body["answer"]) > 0

    def test_faq_escalate_404_on_missing_session(self):
        sid = f"sup_nope_{uuid.uuid4().hex[:8]}"
        r = _post("/api/support/faq/escalate", {"session_id": sid, "question": "help"})
        assert r.status_code == 404, f"{r.status_code} {r.text}"

    def test_faq_ask_payload_validation(self):
        # question too short
        r = _post("/api/support/faq/ask", {"session_id": "supshortid", "question": "x"})
        assert r.status_code == 422
        # session_id too short
        r2 = _post("/api/support/faq/ask", {"session_id": "abc", "question": "hello"})
        assert r2.status_code == 422


# ---------- c1 — gift cards ----------

class TestGiftCardsAPI:
    def test_balance_404_for_unknown_code(self):
        r = _get("/api/gift-cards/GIFT-XXXX-YYYY-ZZZZ/balance")
        assert r.status_code == 404

    def test_me_gift_cards_requires_auth(self):
        r = _get("/api/me/gift-cards")
        assert r.status_code in (401, 403)

    def test_me_gift_cards_returns_list_when_authed(self):
        token, _ = _register_attendee()
        r = _get("/api/me/gift-cards", token=token)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_gift_card_purchase_requires_auth(self):
        r = _post(
            "/api/gift-cards/purchase",
            {
                "amount": 25, "recipient_email": "x@y.com",
                "currency": "NZD", "origin_url": "https://example.com",
            },
        )
        assert r.status_code in (401, 403)

    def test_gift_card_purchase_validation_min_amount(self):
        token, _ = _register_attendee()
        r = _post(
            "/api/gift-cards/purchase",
            {"amount": 0, "recipient_email": "x@y.com", "currency": "NZD", "origin_url": "https://example.com"},
            token=token,
        )
        # Pydantic gt=0 -> 422, OR may surface as 400 if validator is custom
        assert r.status_code in (400, 422), f"{r.status_code} {r.text}"

    def test_gift_card_purchase_reaches_stripe_or_502(self):
        """Auth + payload pass — Stripe layer may fail with 502 (acceptable)."""
        token, _ = _register_attendee()
        r = _post(
            "/api/gift-cards/purchase",
            {
                "amount": 25, "recipient_email": "test-recip@iter13.example.com",
                "recipient_name": "Recip", "currency": "NZD",
                "origin_url": "https://example.com",
            },
            token=token,
        )
        assert r.status_code in (200, 502, 503), f"{r.status_code} {r.text}"
        if r.status_code == 200:
            body = r.json()
            assert "url" in body and "session_id" in body and "card_id" in body


# ---------- c2 — bundles ----------

class TestBundlesAPI:
    def test_create_bundle_requires_organizer(self):
        token, _ = _register_attendee()
        r = _post(
            "/api/organizer/bundles",
            {"title": "Attendee Try", "event_ids": ["evt_a", "evt_b"], "price": 50},
            token=token,
        )
        assert r.status_code == 403

    def test_create_bundle_min_two_events(self):
        token, _ = _register_organizer()
        r = _post(
            "/api/organizer/bundles",
            {"title": "Solo", "event_ids": ["evt_only"], "price": 50},
            token=token,
        )
        assert r.status_code == 422  # pydantic min_length=2

    def test_create_bundle_rejects_unknown_events(self):
        token, _ = _register_organizer()
        r = _post(
            "/api/organizer/bundles",
            {"title": "Phantom Bundle", "event_ids": ["evt_nope1", "evt_nope2"], "price": 50},
            token=token,
        )
        assert r.status_code == 400
        assert "not found" in r.text.lower()

    def test_full_bundle_lifecycle_create_get_patch(self):
        token, _ = _register_organizer()
        # Create 2 events under same organizer
        e1 = _post("/api/events", _make_event_payload(), token=token).json()
        e2 = _post("/api/events", _make_event_payload(), token=token).json()
        assert "event_id" in e1 and "event_id" in e2

        # Create bundle
        rb = _post(
            "/api/organizer/bundles",
            {
                "title": "TEST_Twin Pass",
                "description": "Two-show pass",
                "event_ids": [e1["event_id"], e2["event_id"]],
                "price": 150.0,
                "currency": "NZD",
            },
            token=token,
        )
        assert rb.status_code == 200, f"{rb.status_code} {rb.text}"
        bundle = rb.json()
        bid = bundle["bundle_id"]
        assert bundle["status"] == "active"
        assert bundle["currency"] == "NZD"
        assert bundle["price"] == 150.0

        # Public GET — events embedded, savings computed
        rg = _get(f"/api/bundles/{bid}")
        assert rg.status_code == 200, f"{rg.status_code} {rg.text}"
        body = rg.json()
        assert len(body["events"]) == 2
        assert body["total_separate"] == 200.0  # 2 x $100 GA
        assert body["savings"] == 50.0

        # PATCH toggles status
        rp = _patch(f"/api/organizer/bundles/{bid}", {"status": "inactive"}, token=token)
        assert rp.status_code == 200
        assert rp.json()["status"] == "inactive"

        # Public GET now returns 404 (inactive)
        rg2 = _get(f"/api/bundles/{bid}")
        assert rg2.status_code == 404

    def test_bundle_purchase_requires_auth(self):
        r = _post("/api/bundles/bnd_doesnotexist/purchase", {"origin_url": "https://x"})
        assert r.status_code in (401, 403)

    def test_bundle_purchase_404_unknown_bundle(self):
        token, _ = _register_attendee()
        r = _post(
            "/api/bundles/bnd_doesnotexist/purchase",
            {"origin_url": "https://example.com"},
            token=token,
        )
        # 404 (not found) or 400 (validation) acceptable; must NOT be 500
        assert r.status_code in (400, 404), f"{r.status_code} {r.text}"


# ---------- d2 — organizer referrals ----------

class TestReferralsAPI:
    def test_referral_stats_requires_organizer(self):
        token, _ = _register_attendee()
        r = _get("/api/organizer/referral", token=token)
        assert r.status_code == 403

    def test_referral_stats_shape(self):
        token, _ = _register_organizer()
        r = _get("/api/organizer/referral", token=token)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        body = r.json()
        for key in ("code", "share_url", "signups", "qualified", "available_credit_nzd", "credit_per_referral_nzd"):
            assert key in body, f"missing key {key} in {body}"
        assert body["code"].startswith("ref_")
        assert "ref=" in body["share_url"]
        # Fresh user — no credit yet
        assert body["signups"] == 0
        assert body["qualified"] == 0
        assert body["available_credit_nzd"] == 0
        # Credit per referral should be a positive number (configured constant)
        assert isinstance(body["credit_per_referral_nzd"], (int, float))
        assert body["credit_per_referral_nzd"] > 0

    def test_stamp_referral_rejects_invalid_code(self):
        token, _ = _register_attendee()
        r = _post("/api/auth/register/stamp-referral", {"ref_code": "bogus"}, token=token)
        assert r.status_code == 400

    def test_stamp_referral_rejects_self_referral(self):
        token, _ = _register_organizer()
        my_ref = _get("/api/organizer/referral", token=token).json()["code"]
        r = _post("/api/auth/register/stamp-referral", {"ref_code": my_ref}, token=token)
        assert r.status_code == 400
        assert "yourself" in r.text.lower() or "self" in r.text.lower()

    def test_stamp_referral_happy_path_and_idempotency(self):
        # User A is the referrer
        token_a, _ = _register_organizer()
        ref_code = _get("/api/organizer/referral", token=token_a).json()["code"]

        # User B stamps the referral
        token_b, _ = _register_attendee()
        r = _post("/api/auth/register/stamp-referral", {"ref_code": ref_code}, token=token_b)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        assert r.json().get("ok") is True

        # Second call → already_stamped
        r2 = _post("/api/auth/register/stamp-referral", {"ref_code": ref_code}, token=token_b)
        assert r2.status_code == 200
        body = r2.json()
        assert body.get("ok") is False
        assert body.get("reason") == "already_stamped"

        # Referrer should now see signups bumped to 1
        stats = _get("/api/organizer/referral", token=token_a).json()
        assert stats["signups"] >= 1
