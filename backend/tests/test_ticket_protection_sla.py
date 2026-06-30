"""Ticket Protection — P2a: SLA digest + canned denial templates.

Covers:
  • GET /admin/ticket-protection/denial-templates returns the canned list.
  • Non-admin gets 403 on the templates endpoint.
  • Denying a claim fires the buyer denial email + stamps admin_note.
  • Scheduler digest finds claims >24h old, sends ONE digest, stamps platform_meta
    so re-runs in the same day are a no-op.
  • Digest skips when there are no overdue claims.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from dotenv import load_dotenv
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402
from routers import ticket_protection as tp  # noqa: E402
from emails import TEMPLATES  # noqa: E402


def test_denial_templates_returns_list():
    """Admin can fetch the canned denial templates; non-admin gets 403."""
    async def run():
        # Admin
        resp = await tp.list_denial_templates(user={"role": "admin", "user_id": "admin_x"})
        assert "templates" in resp
        assert len(resp["templates"]) >= 5  # we ship at least 5 canned ones
        # Each entry has the required shape
        for t in resp["templates"]:
            assert "id" in t and "label" in t and "text" in t
            assert len(t["text"]) > 20  # not stubs
        # Non-admin
        from fastapi import HTTPException as E
        try:
            await tp._require_admin(user={"role": "attendee", "user_id": "u_x"})
            assert False, "should have raised"
        except E as e:
            assert e.status_code == 403

    asyncio.get_event_loop().run_until_complete(run())


def test_deny_claim_sends_buyer_email_and_stamps_note():
    """Denying a claim fires the protection_claim_denied email with the
    admin's note baked in, and stamps the claim doc."""
    async def run():
        claim_id = f"clm_{uuid.uuid4().hex[:12]}"
        try:
            await db.protection_claims.insert_one({
                "claim_id": claim_id,
                "booking_id": "bk_test",
                "user_id": "u_test",
                "user_email": "buyer@example.com",
                "user_name": "Test Buyer",
                "event_id": "evt_test",
                "event_title": "Concert Night",
                "amount": 32.15,
                "currency": "NZD",
                "reason": "Sick.",
                "status": "pending",
                "created_at": utc_now().isoformat(),
            })

            captured = {"calls": []}

            def fake_send(template, to, ctx, _db):
                captured["calls"].append({"template": template, "to": to, "ctx": ctx})

            with patch("emails.send_template_fireforget", fake_send):
                resp = await tp.deny_claim(
                    claim_id,
                    tp.DecisionIn(admin_note="No medical evidence provided."),
                    user={"role": "admin", "user_id": "admin_x"},
                )
            assert resp == {"ok": True}

            # Email captured
            assert len(captured["calls"]) == 1
            call = captured["calls"][0]
            assert call["template"] == "protection_claim_denied"
            assert call["to"] == "buyer@example.com"
            assert "No medical evidence provided." in call["ctx"]["reason_text"]
            assert call["ctx"]["event_title"] == "Concert Night"

            # Stamped
            row = await db.protection_claims.find_one({"claim_id": claim_id}, {"_id": 0})
            assert row["status"] == "denied"
            assert row["admin_note"] == "No medical evidence provided."
            assert row["decided_by"] == "admin_x"
        finally:
            await db.protection_claims.delete_one({"claim_id": claim_id})

    asyncio.get_event_loop().run_until_complete(run())


def test_denied_template_renders():
    """The protection_claim_denied template compiles and includes the
    admin's reason text."""
    fn = TEMPLATES["protection_claim_denied"]
    subject, html, text = fn({
        "user_name": "Alice",
        "event_title": "Big Show",
        "reason_text": "No evidence of illness was attached.",
        "booking_id": "bk_x",
    })
    assert "Ticket Protection" in subject
    assert "Big Show" in html
    assert "Alice" in html
    assert "No evidence of illness was attached." in html
    assert "No evidence of illness was attached." in text


def test_sla_digest_template_renders():
    """The protection_claims_sla_digest template compiles and lists every
    overdue claim in the table."""
    fn = TEMPLATES["protection_claims_sla_digest"]
    rows = [
        {
            "claim_id": "clm_a",
            "user_name": "Alice",
            "user_email": "alice@example.com",
            "event_title": "Show A",
            "reason": "Flu",
            "amount": 32.15,
            "currency": "NZD",
            "age_hours": 30,
        },
        {
            "claim_id": "clm_b",
            "user_name": "Bob",
            "user_email": "bob@example.com",
            "event_title": "Show B",
            "reason": "Family emergency",
            "amount": 107.45,
            "currency": "NZD",
            "age_hours": 50,
        },
    ]
    subject, html, text = fn({"claims": rows, "count": len(rows)})
    assert "2" in subject and "claim" in subject.lower()
    assert "Alice" in html and "Bob" in html
    assert "Show A" in html and "Show B" in html
    assert "30h" in html and "50h" in html
    assert "/admin?tab=ticket-protection" in html
    # Text fallback has both
    assert "Alice" in text and "Bob" in text


def test_scheduler_sla_digest_finds_overdue_claims_in_window():
    """The scheduler picks up claims >24h old and fires the digest to admin."""
    from scheduler import _send_protection_claim_sla_digest

    async def run():
        # Force the scheduler's time window check to pass
        fake_now = datetime(2026, 3, 1, 9, 30, tzinfo=timezone.utc)

        admin_id = f"admin_{uuid.uuid4().hex[:8]}"
        old_claim_id = f"clm_{uuid.uuid4().hex[:12]}"
        new_claim_id = f"clm_{uuid.uuid4().hex[:12]}"

        try:
            # Seed an admin user so the digest has a recipient
            await db.users.insert_one({
                "user_id": admin_id,
                "email": f"{admin_id}@example.com",
                "role": "admin",
            })
            # Overdue claim (created 30h ago)
            old_iso = (fake_now - timedelta(hours=30)).isoformat()
            await db.protection_claims.insert_one({
                "claim_id": old_claim_id,
                "booking_id": "bk_x",
                "user_id": "u_x",
                "user_email": "buyer@example.com",
                "user_name": "Old Claim",
                "event_id": "evt_x",
                "event_title": "Old Event",
                "amount": 50.0,
                "currency": "NZD",
                "reason": "Flu",
                "status": "pending",
                "created_at": old_iso,
            })
            # Fresh claim (created 2h ago) — must NOT be in the digest
            new_iso = (fake_now - timedelta(hours=2)).isoformat()
            await db.protection_claims.insert_one({
                "claim_id": new_claim_id,
                "booking_id": "bk_y",
                "user_id": "u_y",
                "user_email": "buyer2@example.com",
                "user_name": "Fresh Claim",
                "event_id": "evt_y",
                "event_title": "Fresh Event",
                "amount": 25.0,
                "currency": "NZD",
                "reason": "Sick",
                "status": "pending",
                "created_at": new_iso,
            })
            # Clear any prior dedupe meta so this run actually fires
            await db.platform_meta.delete_one({"key": "protection_sla_digest"})

            captured = {"calls": []}

            def fake_send(template, to, ctx, _db):
                captured["calls"].append({"template": template, "to": to, "ctx": ctx})

            with patch("scheduler.datetime") as mock_dt, \
                 patch("scheduler.send_template_fireforget", fake_send):
                mock_dt.now.return_value = fake_now
                mock_dt.fromisoformat = datetime.fromisoformat
                sent = await _send_protection_claim_sla_digest(db)

            assert sent >= 1, f"expected ≥1 admin emailed, got {sent}"
            # At least one call to our template was made
            sla_calls = [c for c in captured["calls"] if c["template"] == "protection_claims_sla_digest"]
            assert len(sla_calls) >= 1
            # The overdue claim is in the ctx
            ctx = sla_calls[0]["ctx"]
            ids_in_ctx = [c["claim_id"] for c in ctx["claims"]]
            assert old_claim_id in ids_in_ctx
            # The fresh claim is NOT in the ctx
            assert new_claim_id not in ids_in_ctx

            # Dedupe stamp landed
            meta = await db.platform_meta.find_one({"key": "protection_sla_digest"}, {"_id": 0})
            assert meta is not None
            assert meta["day"] == fake_now.strftime("%Y-%m-%d")
            assert meta["overdue_count"] >= 1

            # Re-running the same day must be a no-op
            captured["calls"].clear()
            with patch("scheduler.datetime") as mock_dt2, \
                 patch("scheduler.send_template_fireforget", fake_send):
                mock_dt2.now.return_value = fake_now
                mock_dt2.fromisoformat = datetime.fromisoformat
                sent_again = await _send_protection_claim_sla_digest(db)
            assert sent_again == 0
            assert all(c["template"] != "protection_claims_sla_digest" for c in captured["calls"])
        finally:
            await db.protection_claims.delete_many(
                {"claim_id": {"$in": [old_claim_id, new_claim_id]}}
            )
            await db.users.delete_one({"user_id": admin_id})
            await db.platform_meta.delete_one({"key": "protection_sla_digest"})

    asyncio.get_event_loop().run_until_complete(run())


def test_scheduler_sla_digest_skips_outside_window():
    """If the hour is outside the 09:00-10:00 UTC window, return 0 without
    doing anything (even if there are overdue claims)."""
    from scheduler import _send_protection_claim_sla_digest

    async def run():
        fake_now = datetime(2026, 3, 1, 15, 30, tzinfo=timezone.utc)  # outside window
        with patch("scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.fromisoformat = datetime.fromisoformat
            sent = await _send_protection_claim_sla_digest(db)
        assert sent == 0

    asyncio.get_event_loop().run_until_complete(run())
