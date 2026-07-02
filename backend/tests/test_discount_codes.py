"""Discount-code create + validate — including the Feb 2026 admin-attribution
fix.

The bug: admins can create discount codes on organizer events via
`POST /organizer/discount-codes`. Pre-Feb-2026, `created_by` was stamped
with the ADMIN's user_id — but `POST /discount-codes/validate` looks up
codes via `_find_active_code`, which filters by
`created_by = event.organizer_id`. Result: admin-created codes existed
in the DB but were silently invisible at checkout.

Fix: when an admin creates a code for a specific event, attribute
`created_by` to the event's organizer_id, and stash the admin's user_id
under `created_by_actor` for audit. Admin-created codes with no event_id
are now rejected with 400 (they would be unfindable).
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402
from routers import discount_codes as dc  # noqa: E402


async def _mk_user(role="organizer", **extra):
    uid = f"user_test_{uuid.uuid4().hex[:8]}"
    doc = {
        "user_id": uid,
        "email": f"{uid}@example.com",
        "name": "Test",
        "role": role,
        **extra,
    }
    await db.users.update_one({"user_id": uid}, {"$set": doc}, upsert=True)
    return doc


async def _mk_event(organizer):
    eid = f"evt_test_{uuid.uuid4().hex[:10]}"
    doc = {
        "event_id": eid,
        "organizer_id": organizer["user_id"],
        "organizer_name": organizer["name"],
        "title": "Discount Test",
        "status": "approved",
        "date": "2027-05-15T20:00:00Z",
        "currency": "NZD",
        "tiers": [{"name": "General", "price": 50, "capacity": 100}],
        "created_at": utc_now().isoformat(),
    }
    await db.events.insert_one(doc)
    return doc


async def _cleanup(event_id=None, code_ids=None, user_ids=None):
    if event_id:
        await db.events.delete_one({"event_id": event_id})
    if code_ids:
        await db.discount_codes.delete_many({"code_id": {"$in": code_ids}})
    if user_ids:
        await db.users.delete_many({"user_id": {"$in": user_ids}})


# ---------------------------------------------------------------------------
# 1. Organizer creates their own code — the happy path (unchanged).
# ---------------------------------------------------------------------------
async def test_organizer_creates_own_code():
    org = await _mk_user(role="organizer")
    event = await _mk_event(org)
    payload = dc.DiscountCodeIn(code="SAVE10", kind="percent", value=10, event_id=event["event_id"])
    created = await dc.create_code(payload, org)
    try:
        assert created["created_by"] == org["user_id"]
        assert created["created_by_actor"] == org["user_id"]
        assert created["created_by_actor_role"] == "organizer"

        # Validation works.
        v = await dc.validate_code(dc.ValidateIn(
            code="SAVE10", event_id=event["event_id"],
            tier_name="General", quantity=1, subtotal=100,
        ))
        assert v["discount_amount"] == 10.0
        assert v["final_amount"] == 90.0
    finally:
        await _cleanup(event["event_id"], [created["code_id"]], [org["user_id"]])


# ---------------------------------------------------------------------------
# 2. THE BUG FIX — admin creates a code, buyer validates, discount applies.
# ---------------------------------------------------------------------------
async def test_admin_creates_code_gets_attributed_to_organizer():
    org = await _mk_user(role="organizer")
    admin = await _mk_user(role="admin")
    event = await _mk_event(org)
    payload = dc.DiscountCodeIn(code="ADMINSAVE20", kind="percent", value=20, event_id=event["event_id"])
    created = await dc.create_code(payload, admin)
    try:
        # Code is attributed to the organizer — this is the whole fix.
        assert created["created_by"] == org["user_id"]
        # But audit trail preserves who actually clicked "create".
        assert created["created_by_actor"] == admin["user_id"]
        assert created["created_by_actor_role"] == "admin"

        # The bug: validation used to 404 because _find_active_code searched
        # {"created_by": event.organizer_id} which never matched the admin's
        # user_id. With the fix, validation finds the code cleanly.
        v = await dc.validate_code(dc.ValidateIn(
            code="ADMINSAVE20", event_id=event["event_id"],
            tier_name="General", quantity=1, subtotal=100,
        ))
        assert v["discount_amount"] == 20.0
        assert v["final_amount"] == 80.0
    finally:
        await _cleanup(event["event_id"], [created["code_id"]], [org["user_id"], admin["user_id"]])


# ---------------------------------------------------------------------------
# 3. Admin CANNOT create an all-events code (would be unfindable).
# ---------------------------------------------------------------------------
async def test_admin_cannot_create_all_events_code():
    admin = await _mk_user(role="admin")
    payload = dc.DiscountCodeIn(code="ADMINALL", kind="percent", value=5, event_id=None)
    with pytest.raises(HTTPException) as ei:
        await dc.create_code(payload, admin)
    assert ei.value.status_code == 400
    assert "event_id" in ei.value.detail.lower()
    await _cleanup(user_ids=[admin["user_id"]])


# ---------------------------------------------------------------------------
# 4. Organizer CAN create all-events codes (attributed to themselves).
# ---------------------------------------------------------------------------
async def test_organizer_can_create_all_events_code():
    org = await _mk_user(role="organizer")
    event = await _mk_event(org)
    payload = dc.DiscountCodeIn(code="ANYEVENT", kind="flat", value=5, event_id=None)
    created = await dc.create_code(payload, org)
    try:
        assert created["created_by"] == org["user_id"]
        # Validate against ANY of the organizer's events.
        v = await dc.validate_code(dc.ValidateIn(
            code="ANYEVENT", event_id=event["event_id"],
            tier_name="General", quantity=1, subtotal=100,
        ))
        assert v["discount_amount"] == 5.0
    finally:
        await _cleanup(event["event_id"], [created["code_id"]], [org["user_id"]])


# ---------------------------------------------------------------------------
# 5. Duplicate-code detection uses the ATTRIBUTED owner, not the actor.
# ---------------------------------------------------------------------------
async def test_admin_cant_create_duplicate_code_for_same_organizer():
    org = await _mk_user(role="organizer")
    admin = await _mk_user(role="admin")
    event = await _mk_event(org)
    first = await dc.create_code(
        dc.DiscountCodeIn(code="DUPE", kind="percent", value=10, event_id=event["event_id"]),
        admin,
    )
    try:
        # A SECOND admin-create for the same organizer should conflict.
        with pytest.raises(HTTPException) as ei:
            await dc.create_code(
                dc.DiscountCodeIn(code="DUPE", kind="flat", value=5, event_id=event["event_id"]),
                admin,
            )
        assert ei.value.status_code == 409
    finally:
        await _cleanup(event["event_id"], [first["code_id"]], [org["user_id"], admin["user_id"]])


# ---------------------------------------------------------------------------
# 6. Two DIFFERENT organizers can each own a code with the same name.
# ---------------------------------------------------------------------------
async def test_same_code_different_organizers_coexist():
    org_a = await _mk_user(role="organizer")
    org_b = await _mk_user(role="organizer")
    event_a = await _mk_event(org_a)
    event_b = await _mk_event(org_b)
    code_a = await dc.create_code(
        dc.DiscountCodeIn(code="EARLY", kind="percent", value=15, event_id=event_a["event_id"]),
        org_a,
    )
    code_b = await dc.create_code(
        dc.DiscountCodeIn(code="EARLY", kind="percent", value=25, event_id=event_b["event_id"]),
        org_b,
    )
    try:
        # Each event resolves to the OWN organizer's code, not the other one.
        va = await dc.validate_code(dc.ValidateIn(
            code="EARLY", event_id=event_a["event_id"],
            tier_name="General", quantity=1, subtotal=100,
        ))
        vb = await dc.validate_code(dc.ValidateIn(
            code="EARLY", event_id=event_b["event_id"],
            tier_name="General", quantity=1, subtotal=100,
        ))
        assert va["discount_amount"] == 15.0
        assert vb["discount_amount"] == 25.0
    finally:
        await _cleanup(event_a["event_id"], [code_a["code_id"]], [org_a["user_id"]])
        await _cleanup(event_b["event_id"], [code_b["code_id"]], [org_b["user_id"]])


# ---------------------------------------------------------------------------
# 7. Foreign organizer cannot create a code on someone else's event.
# ---------------------------------------------------------------------------
async def test_foreign_organizer_gets_403():
    owner = await _mk_user(role="organizer")
    intruder = await _mk_user(role="organizer")
    event = await _mk_event(owner)
    try:
        payload = dc.DiscountCodeIn(code="STEAL", kind="percent", value=50, event_id=event["event_id"])
        with pytest.raises(HTTPException) as ei:
            await dc.create_code(payload, intruder)
        assert ei.value.status_code == 403
    finally:
        await _cleanup(event["event_id"], [], [owner["user_id"], intruder["user_id"]])


# ---------------------------------------------------------------------------
# 8. Missing / inactive / expired codes still 404 or 400 correctly.
# ---------------------------------------------------------------------------
async def test_invalid_code_returns_404():
    org = await _mk_user(role="organizer")
    event = await _mk_event(org)
    try:
        with pytest.raises(HTTPException) as ei:
            await dc.validate_code(dc.ValidateIn(
                code="DOESNTEXIST", event_id=event["event_id"],
                tier_name="General", quantity=1, subtotal=100,
            ))
        assert ei.value.status_code == 404
    finally:
        await _cleanup(event["event_id"], [], [org["user_id"]])
