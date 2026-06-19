"""Organizer referral program (d2) — happy path + idempotency."""
from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402
from routers.organizer_referrals import (  # noqa: E402
    _ref_code_for, maybe_grant_referral_on_first_approval,
)


def test_ref_code_is_deterministic():
    uid = "user_abc12345"
    assert _ref_code_for(uid) == _ref_code_for(uid)
    assert _ref_code_for(uid).startswith("ref_")
    assert _ref_code_for(uid) != _ref_code_for("user_xyz98765")


def test_referral_credit_grants_on_first_approval_and_is_idempotent():
    async def run():
        referrer_id = f"u_{uuid.uuid4().hex[:8]}"
        referred_id = f"u_{uuid.uuid4().hex[:8]}"
        ref_code = _ref_code_for(referrer_id)
        # Seed both users
        await db.users.insert_many([
            {"user_id": referrer_id, "name": "Ref", "email": f"{referrer_id}@t.local", "role": "organizer", "created_at": utc_now().isoformat()},
            {"user_id": referred_id, "name": "New", "email": f"{referred_id}@t.local", "role": "organizer", "referred_by_code": ref_code, "created_at": utc_now().isoformat()},
        ])
        event_id = f"evt_ref_{uuid.uuid4().hex[:8]}"
        await db.events.insert_one({
            "event_id": event_id,
            "organizer_id": referred_id,
            "organizer_name": "New",
            "title": "First Event",
            "status": "approved",
            "date": (utc_now() + timedelta(days=3)).isoformat(),
            "created_at": utc_now().isoformat(),
        })
        try:
            event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
            ok = await maybe_grant_referral_on_first_approval(event)
            assert ok is True
            # Referrer gets a single $50 credit; the referred organizer
            # does NOT receive a welcome bonus (program update — refer-only).
            referrer_credits = await db.organizer_credits.count_documents(
                {"user_id": referrer_id, "reason": "referral_payout"}
            )
            referred_credits = await db.organizer_credits.count_documents(
                {"user_id": referred_id}
            )
            assert referrer_credits == 1
            assert referred_credits == 0
            # Referred user is stamped so a second pass is a no-op.
            stamped = await db.users.find_one({"user_id": referred_id}, {"_id": 0})
            assert stamped.get("referral_credited_at")

            # Second call → no new credits (idempotent)
            ok2 = await maybe_grant_referral_on_first_approval(event)
            assert ok2 is False
            assert await db.organizer_credits.count_documents(
                {"user_id": referrer_id, "reason": "referral_payout"}
            ) == 1
        finally:
            await db.organizer_credits.delete_many({"user_id": {"$in": [referrer_id, referred_id]}})
            await db.events.delete_one({"event_id": event_id})
            await db.users.delete_many({"user_id": {"$in": [referrer_id, referred_id]}})

    asyncio.get_event_loop().run_until_complete(run())


def test_no_credit_when_user_was_not_referred():
    async def run():
        organizer_id = f"u_{uuid.uuid4().hex[:8]}"
        await db.users.insert_one({
            "user_id": organizer_id, "name": "Solo", "email": f"{organizer_id}@t.local",
            "role": "organizer", "created_at": utc_now().isoformat(),
        })
        event_id = f"evt_ref_{uuid.uuid4().hex[:8]}"
        await db.events.insert_one({
            "event_id": event_id, "organizer_id": organizer_id,
            "title": "Solo Event", "status": "approved",
            "date": (utc_now() + timedelta(days=3)).isoformat(),
            "created_at": utc_now().isoformat(),
        })
        try:
            event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
            ok = await maybe_grant_referral_on_first_approval(event)
            assert ok is False
            cnt = await db.organizer_credits.count_documents({"user_id": organizer_id})
            assert cnt == 0
        finally:
            await db.events.delete_one({"event_id": event_id})
            await db.users.delete_one({"user_id": organizer_id})

    asyncio.get_event_loop().run_until_complete(run())
