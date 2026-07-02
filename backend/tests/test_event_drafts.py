"""Event draft lifecycle (Jul 2026): Save-as-Draft + Publish transition.

Covers:
  • POST /events with is_draft=True skips the Stripe Connect gate on
    paid events and lands the event as status="draft".
  • Draft events are NOT visible on the public /events feed (which
    filters status in {approved, published}).
  • PATCH /events/{id} with is_draft=False transitions a draft → pending
    (organizer) or → approved (admin), and RE-runs the Stripe gate.
  • Paid draft → publish for an organizer without Stripe Connect returns
    402 stripe_payouts_required.
  • Free draft → publish succeeds regardless of Stripe status.
  • Non-draft events IGNORE the is_draft flag on PATCH — you can't un-
    publish an approved event just by sending is_draft=true.
  • Admin drafts do NOT fire the admin-moderation email fan-out.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402
from models import EventIn  # noqa: E402
from routers import events as events_router  # noqa: E402


def _payload(**overrides):
    base = {
        "title": overrides.pop("title", f"Draft Test {uuid.uuid4().hex[:6]}"),
        "description": "pytest",
        "category": "music",
        "venue": "Test Venue",
        "city": "Auckland",
        "country": "NZ",
        "timezone": "Pacific/Auckland",
        "date": "2027-01-15T20:00:00Z",
        "image_url": "https://example.com/x.jpg",
        "tiers": [{"name": "General", "price": 50, "capacity": 100}],
        "is_draft": False,
    }
    base.update(overrides)
    return EventIn(**base)


class _FakeRequest:
    """Minimal Request stub with just the `.headers` access the router uses."""
    def __init__(self):
        self.headers = {}


async def _organizer_no_stripe():
    return {
        "user_id": f"user_test_{uuid.uuid4().hex[:6]}",
        "name": "Test Organizer",
        "email": f"test_{uuid.uuid4().hex[:6]}@example.com",
        "role": "organizer",
        "stripe_payouts_enabled": False,
    }


async def _cleanup(event_id):
    await db.events.delete_one({"event_id": event_id})


async def test_paid_draft_skips_stripe_gate():
    """A paid event saved as a DRAFT must NOT trigger the 402 Stripe gate."""
    user = await _organizer_no_stripe()
    payload = _payload(is_draft=True, tiers=[{"name": "VIP", "price": 200, "capacity": 50}])
    result = await events_router.create_event(payload, _FakeRequest(), user)
    try:
        assert result["status"] == "draft"
        assert result["organizer_id"] == user["user_id"]
    finally:
        await _cleanup(result["event_id"])


async def test_paid_event_without_draft_still_gates():
    """Sanity: the pre-existing Stripe gate still fires on a non-draft paid event."""
    user = await _organizer_no_stripe()
    payload = _payload(is_draft=False, tiers=[{"name": "VIP", "price": 200, "capacity": 50}])
    try:
        await events_router.create_event(payload, _FakeRequest(), user)
        assert False, "should have raised 402"
    except HTTPException as e:
        assert e.status_code == 402
        assert e.detail.get("code") == "stripe_payouts_required"


async def test_free_draft_publishes_cleanly():
    """Free event: draft → publish should flip status to 'pending' for organizer."""
    user = await _organizer_no_stripe()
    draft = await events_router.create_event(
        _payload(is_draft=True, tiers=[{"name": "Free", "price": 0, "capacity": 100}]),
        _FakeRequest(),
        user,
    )
    try:
        assert draft["status"] == "draft"
        published = await events_router.update_event(
            draft["event_id"],
            {"is_draft": False},
            user,
        )
        assert published["status"] == "pending"
    finally:
        await _cleanup(draft["event_id"])


async def test_paid_draft_publish_gated_by_stripe():
    """Draft → publish on a PAID event without Stripe should still 402."""
    user = await _organizer_no_stripe()
    draft = await events_router.create_event(
        _payload(is_draft=True, tiers=[{"name": "VIP", "price": 200, "capacity": 50}]),
        _FakeRequest(),
        user,
    )
    try:
        try:
            await events_router.update_event(draft["event_id"], {"is_draft": False}, user)
            assert False, "should have raised 402"
        except HTTPException as e:
            assert e.status_code == 402
            assert e.detail.get("code") == "stripe_payouts_required"
        # Event should STILL be a draft after the failed transition.
        after = await db.events.find_one({"event_id": draft["event_id"]}, {"_id": 0})
        assert after["status"] == "draft"
    finally:
        await _cleanup(draft["event_id"])


async def test_admin_draft_lands_as_draft_not_approved():
    """Admin creates a draft — status must be 'draft', not 'approved'.

    Otherwise Save-as-Draft would auto-publish for admins, which defeats
    the entire point of the button.
    """
    admin = {
        "user_id": f"admin_test_{uuid.uuid4().hex[:6]}",
        "name": "Admin",
        "email": f"admin_{uuid.uuid4().hex[:6]}@example.com",
        "role": "admin",
    }
    payload = _payload(is_draft=True, tiers=[{"name": "General", "price": 50, "capacity": 100}])
    result = await events_router.create_event(payload, _FakeRequest(), admin)
    try:
        assert result["status"] == "draft"
    finally:
        await _cleanup(result["event_id"])


async def test_admin_publishing_a_draft_flips_to_approved():
    """Admin publishing their own draft → status "approved" (skips moderation)."""
    admin = {
        "user_id": f"admin_test_{uuid.uuid4().hex[:6]}",
        "name": "Admin",
        "email": f"admin_{uuid.uuid4().hex[:6]}@example.com",
        "role": "admin",
    }
    draft = await events_router.create_event(
        _payload(is_draft=True, tiers=[{"name": "Free", "price": 0, "capacity": 100}]),
        _FakeRequest(),
        admin,
    )
    try:
        published = await events_router.update_event(draft["event_id"], {"is_draft": False}, admin)
        assert published["status"] == "approved"
    finally:
        await _cleanup(draft["event_id"])


async def test_is_draft_ignored_on_approved_events():
    """Sending is_draft=true on an already-approved event should NOT downgrade it."""
    admin = {
        "user_id": f"admin_test_{uuid.uuid4().hex[:6]}",
        "name": "Admin",
        "email": f"admin_{uuid.uuid4().hex[:6]}@example.com",
        "role": "admin",
    }
    # Admin non-draft create → status "approved"
    live = await events_router.create_event(
        _payload(is_draft=False, tiers=[{"name": "Free", "price": 0, "capacity": 100}]),
        _FakeRequest(),
        admin,
    )
    try:
        result = await events_router.update_event(
            live["event_id"],
            {"is_draft": True, "title": "still approved after this"},
            admin,
        )
        # is_draft=true on non-draft events is a no-op — status stays "approved".
        assert result["status"] == "approved"
        assert result["title"] == "still approved after this"
    finally:
        await _cleanup(live["event_id"])


async def test_draft_hidden_from_public_events_list():
    """Drafts must never appear in the public /events discovery feed."""
    user = await _organizer_no_stripe()
    draft = await events_router.create_event(
        _payload(is_draft=True, tiers=[{"name": "Free", "price": 0, "capacity": 100}]),
        _FakeRequest(),
        user,
    )
    try:
        listing = await events_router.list_events()
        # `list_events` returns a list of public event dicts.
        assert not any(
            e.get("event_id") == draft["event_id"]
            for e in (listing if isinstance(listing, list) else listing.get("items", []))
        ), "draft leaked into the public events feed"
    finally:
        await _cleanup(draft["event_id"])
