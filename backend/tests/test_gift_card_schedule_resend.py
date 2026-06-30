"""Gift cards — scheduled delivery + purchaser resend.

Covers:
  • deliver_at validation: bad format → 400, past → 400, >365 days → 400.
  • finalize_gift_card_purchase honors deliver_at — holds email when future,
    fires immediately when null/past.
  • deliver_scheduled_gift_cards picks up due cards and stamps delivered_at.
  • POST /me/gift-cards/{card_id}/resend — fires email, increments
    resend_count, blocks after 3, blocks non-purchaser.
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402
from routers import gift_cards as gc  # noqa: E402


def test_parse_deliver_at_accepts_valid_future_date():
    tomorrow = (utc_now() + timedelta(days=1)).strftime("%Y-%m-%d")
    result = gc._parse_deliver_at(tomorrow)
    assert result is not None
    assert result.tzinfo is not None


def test_parse_deliver_at_rejects_past_date():
    yesterday = (utc_now() - timedelta(days=2)).strftime("%Y-%m-%d")
    try:
        gc._parse_deliver_at(yesterday)
        assert False, "should have raised"
    except HTTPException as e:
        assert e.status_code == 400
        assert "future" in e.detail.lower()


def test_parse_deliver_at_rejects_too_far_future():
    far = (utc_now() + timedelta(days=400)).strftime("%Y-%m-%d")
    try:
        gc._parse_deliver_at(far)
        assert False, "should have raised"
    except HTTPException as e:
        assert e.status_code == 400
        assert "365" in e.detail


def test_parse_deliver_at_returns_none_for_empty():
    assert gc._parse_deliver_at(None) is None
    assert gc._parse_deliver_at("") is None


async def test_finalize_holds_email_when_deliver_at_is_future():
    card_id = f"gc_{uuid.uuid4().hex[:12]}"
    future = (utc_now() + timedelta(days=7)).isoformat()
    try:
        await db.gift_cards.insert_one({
            "card_id": card_id,
            "code": "GIFT-TEST-FUTU-RE01",
            "amount": 50.0,
            "balance": 50.0,
            "currency": "NZD",
            "purchased_by": "u_p",
            "purchaser_email": "p@x.com",
            "purchaser_name": "Purchaser",
            "recipient_email": "r@x.com",
            "recipient_name": "Recipient",
            "personal_note": "Happy birthday",
            "deliver_at": future,
            "delivered_at": None,
            "resend_count": 0,
            "status": "pending",
            "redemptions": [],
            "created_at": utc_now().isoformat(),
        })

        calls = []

        def fake_send(template, to, ctx, _db):
            calls.append({"template": template, "to": to})

        with patch("emails.send_template_fireforget", fake_send):
            ok = await gc.finalize_gift_card_purchase(card_id)
        assert ok is True

        row = await db.gift_cards.find_one({"card_id": card_id}, {"_id": 0})
        assert row["status"] == "active"
        assert row["activated_at"] is not None
        assert row["delivered_at"] is None  # held — NOT delivered
        # No recipient email was fired
        assert all(c["to"] != "r@x.com" for c in calls)
    finally:
        await db.gift_cards.delete_one({"card_id": card_id})



async def test_finalize_sends_immediately_when_no_deliver_at():
    card_id = f"gc_{uuid.uuid4().hex[:12]}"
    try:
        await db.gift_cards.insert_one({
            "card_id": card_id,
            "code": "GIFT-TEST-NOWW-NOW1",
            "amount": 75.0,
            "balance": 75.0,
            "currency": "NZD",
            "purchased_by": "u_p",
            "purchaser_email": "p@x.com",
            "purchaser_name": "Purchaser",
            "recipient_email": "now@x.com",
            "recipient_name": "Now Recipient",
            "deliver_at": None,
            "delivered_at": None,
            "resend_count": 0,
            "status": "pending",
            "redemptions": [],
            "created_at": utc_now().isoformat(),
        })

        calls = []

        def fake_send(template, to, ctx, _db):
            calls.append({"template": template, "to": to})

        with patch("emails.send_template_fireforget", fake_send):
            ok = await gc.finalize_gift_card_purchase(card_id)
        assert ok is True

        row = await db.gift_cards.find_one({"card_id": card_id}, {"_id": 0})
        assert row["status"] == "active"
        assert row["delivered_at"] is not None
        assert any(c["template"] == "gift_card_delivered" and c["to"] == "now@x.com" for c in calls)
    finally:
        await db.gift_cards.delete_one({"card_id": card_id})



async def test_scheduler_delivers_due_cards():
    # Insert one DUE card and one NOT-DUE card
    due_id = f"gc_{uuid.uuid4().hex[:12]}"
    future_id = f"gc_{uuid.uuid4().hex[:12]}"
    past = (utc_now() - timedelta(hours=1)).isoformat()
    future = (utc_now() + timedelta(days=10)).isoformat()
    try:
        await db.gift_cards.insert_many([
            {
                "card_id": due_id, "code": "GIFT-DUE-AA-AA",
                "amount": 50.0, "balance": 50.0, "currency": "NZD",
                "purchased_by": "u_p", "purchaser_name": "P", "purchaser_email": "p@x.com",
                "recipient_email": "due@x.com", "recipient_name": "Due R",
                "deliver_at": past, "delivered_at": None,
                "resend_count": 0, "status": "active", "redemptions": [],
                "created_at": utc_now().isoformat(),
            },
            {
                "card_id": future_id, "code": "GIFT-FUT-AA-AA",
                "amount": 50.0, "balance": 50.0, "currency": "NZD",
                "purchased_by": "u_p", "purchaser_name": "P", "purchaser_email": "p@x.com",
                "recipient_email": "future@x.com", "recipient_name": "Fut R",
                "deliver_at": future, "delivered_at": None,
                "resend_count": 0, "status": "active", "redemptions": [],
                "created_at": utc_now().isoformat(),
            },
        ])

        calls = []

        def fake_send(template, to, ctx, _db):
            calls.append({"template": template, "to": to})

        with patch("emails.send_template_fireforget", fake_send):
            n = await gc.deliver_scheduled_gift_cards()

        assert n == 1
        assert any(c["to"] == "due@x.com" for c in calls)
        assert all(c["to"] != "future@x.com" for c in calls)

        # Due card has delivered_at stamped; future card does not
        due_row = await db.gift_cards.find_one({"card_id": due_id}, {"_id": 0})
        assert due_row["delivered_at"] is not None
        future_row = await db.gift_cards.find_one({"card_id": future_id}, {"_id": 0})
        assert future_row["delivered_at"] is None

        # Re-running the scheduler must NOT re-deliver the same card.
        calls.clear()
        with patch("emails.send_template_fireforget", fake_send):
            n2 = await gc.deliver_scheduled_gift_cards()
        assert n2 == 0
        assert calls == []
    finally:
        await db.gift_cards.delete_many({"card_id": {"$in": [due_id, future_id]}})



async def test_resend_increments_count_and_blocks_after_3():
    card_id = f"gc_{uuid.uuid4().hex[:12]}"
    purchaser_id = f"u_{uuid.uuid4().hex[:8]}"
    try:
        await db.gift_cards.insert_one({
            "card_id": card_id,
            "code": "GIFT-RSND-AA-AA",
            "amount": 50.0,
            "balance": 50.0,
            "currency": "NZD",
            "purchased_by": purchaser_id,
            "purchaser_email": "p@x.com",
            "purchaser_name": "P",
            "recipient_email": "r@x.com",
            "recipient_name": "R",
            "deliver_at": None,
            "delivered_at": utc_now().isoformat(),
            "resend_count": 0,
            "status": "active",
            "redemptions": [],
            "created_at": utc_now().isoformat(),
        })

        calls = []

        def fake_send(template, to, ctx, _db):
            calls.append(to)

        with patch("emails.send_template_fireforget", fake_send):
            # 1st, 2nd, 3rd resends should succeed
            for expected in (1, 2, 3):
                resp = await gc.resend_gift_card_email(
                    card_id, user={"user_id": purchaser_id, "role": "attendee"}
                )
                assert resp == {"ok": True, "resend_count": expected}
            # 4th must be blocked
            try:
                await gc.resend_gift_card_email(
                    card_id, user={"user_id": purchaser_id, "role": "attendee"}
                )
                assert False, "should have raised"
            except HTTPException as e:
                assert e.status_code == 429
        assert len(calls) == 3
    finally:
        await db.gift_cards.delete_one({"card_id": card_id})



async def test_resend_blocks_non_purchaser():
    card_id = f"gc_{uuid.uuid4().hex[:12]}"
    try:
        await db.gift_cards.insert_one({
            "card_id": card_id,
            "code": "GIFT-PRIV-AA-AA",
            "amount": 25.0,
            "balance": 25.0,
            "currency": "NZD",
            "purchased_by": "u_owner",
            "purchaser_email": "owner@x.com",
            "purchaser_name": "Owner",
            "recipient_email": "r@x.com",
            "recipient_name": "R",
            "deliver_at": None,
            "delivered_at": utc_now().isoformat(),
            "resend_count": 0,
            "status": "active",
            "redemptions": [],
            "created_at": utc_now().isoformat(),
        })
        try:
            await gc.resend_gift_card_email(
                card_id, user={"user_id": "u_stranger", "role": "attendee"}
            )
            assert False, "should have raised"
        except HTTPException as e:
            assert e.status_code == 403
    finally:
        await db.gift_cards.delete_one({"card_id": card_id})



async def test_admin_can_resend_any_card():
    card_id = f"gc_{uuid.uuid4().hex[:12]}"
    try:
        await db.gift_cards.insert_one({
            "card_id": card_id,
            "code": "GIFT-ADMN-AA-AA",
            "amount": 25.0,
            "balance": 25.0,
            "currency": "NZD",
            "purchased_by": "u_owner",
            "purchaser_email": "owner@x.com",
            "purchaser_name": "Owner",
            "recipient_email": "r@x.com",
            "recipient_name": "R",
            "deliver_at": None,
            "delivered_at": utc_now().isoformat(),
            "resend_count": 0,
            "status": "active",
            "redemptions": [],
            "created_at": utc_now().isoformat(),
        })

        calls = []

        def fake_send(template, to, ctx, _db):
            calls.append(to)

        with patch("emails.send_template_fireforget", fake_send):
            resp = await gc.resend_gift_card_email(
                card_id, user={"user_id": "admin_x", "role": "admin"}
            )
        assert resp["ok"] is True
        assert "r@x.com" in calls
    finally:
        await db.gift_cards.delete_one({"card_id": card_id})

