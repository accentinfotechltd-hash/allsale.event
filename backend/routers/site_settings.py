"""Site-wide editable content — admin can edit About/Contact copy + contact details.

Single Mongo document keyed by `_kind: "site"` in `site_settings`. The public
GET is open (no auth) so any visitor can render the About/Contact pages.
The PATCH is admin-only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import db, event_to_public, get_current_user, utc_now

router = APIRouter(tags=["site-settings"])


DEFAULTS = {
    "about": {
        "hero_eyebrow": "About us",
        "hero_title": "Live experiences,\nsold the human way.",
        "hero_subtitle": "Allsale Events is a tickets & events platform built in Auckland for the next generation of organizers — the local bhajan night, the touring comic, the cinema reopening with a curated lineup. We obsess over two things: seat-level accuracy and organizer payout speed.",
        "story_title": "Why we built it",
        "story_body": "The first time we tried to run a sold-out community event, the existing platforms were either too expensive, too clunky, or both. Worse — we had no way to actually see which seats were taken in real-time.\n\nSo we built Allsale Events: 10-minute atomic seat holds, custom layouts with aisle gaps and section colours, AI that reads your venue diagram and builds the seat map automatically, QR-scanner door-check-in on any phone, and Stripe payouts that hit organizers within 24 hours.\n\nWe're a small team and we read every contact-form message. If something can be better, tell us.",
    },
    "contact": {
        "hero_eyebrow": "Contact us",
        "hero_title": "Let's talk.",
        "hero_subtitle": "Question, feedback, partnership, or running an event you'd like us to host? Drop a note — a real human reads every message and replies within 24 hours.",
        "email": "support@allsale.events",
        "phone": "+64 9 555 0100",
        "address": "Auckland, New Zealand",
        "organizer_note": "Organizers: for payout, refund and Stripe support, please include your event ID so we can resolve faster.",
    },
    "editor_pick": {
        # Empty = no pick set; falls back to the first featured event on the
        # landing page hero. When `event_id` is set, the landing page shows
        # this event with the curator blurb beneath the title and an
        # "Editor's Pick" badge instead of "Featured".
        "event_id": None,
        "blurb": "",
        "badge_text": "Editor's Pick",
    },
}


async def _load() -> dict:
    """Return the stored document, falling back to DEFAULTS for any missing keys."""
    doc = await db.site_settings.find_one({"_kind": "site"}, {"_id": 0}) or {}
    return {
        "about": {**DEFAULTS["about"], **(doc.get("about") or {})},
        "contact": {**DEFAULTS["contact"], **(doc.get("contact") or {})},
        "editor_pick": {**DEFAULTS["editor_pick"], **(doc.get("editor_pick") or {})},
        "updated_at": doc.get("updated_at"),
    }


@router.get("/site-settings")
async def public_site_settings():
    """Public read for About + Contact pages."""
    return await _load()


@router.get("/site-settings/editor-pick")
async def public_editor_pick():
    """Public read used by the landing-page hero. Returns the curator-picked
    event (joined into a public event payload) + the blurb to render under
    the title. Returns `{event: null}` when no pick is set or the picked
    event was deleted / un-approved — frontend falls back to the first
    featured event in that case.
    """
    settings = await _load()
    pick = settings.get("editor_pick") or {}
    event_id = pick.get("event_id")
    if not event_id:
        return {"event": None, "blurb": "", "badge_text": pick.get("badge_text", "Editor's Pick")}

    event = await db.events.find_one(
        {"event_id": event_id, "status": {"$in": ["approved", "published"]}},
        {"_id": 0},
    )
    if not event:
        # Stale pick — fall through so the landing page uses its featured fallback.
        return {"event": None, "blurb": "", "badge_text": pick.get("badge_text", "Editor's Pick")}
    return {
        "event": event_to_public(event),
        "blurb": pick.get("blurb") or "",
        "badge_text": pick.get("badge_text") or "Editor's Pick",
    }


class AboutIn(BaseModel):
    hero_eyebrow: str | None = None
    hero_title: str | None = None
    hero_subtitle: str | None = None
    story_title: str | None = None
    story_body: str | None = None


class ContactIn(BaseModel):
    hero_eyebrow: str | None = None
    hero_title: str | None = None
    hero_subtitle: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    organizer_note: str | None = None


class EditorPickIn(BaseModel):
    event_id: str | None = None  # `null` to clear the pick
    blurb: str | None = None
    badge_text: str | None = None


class SettingsPatchIn(BaseModel):
    about: AboutIn | None = None
    contact: ContactIn | None = None
    editor_pick: EditorPickIn | None = None


@router.patch("/admin/site-settings")
async def update_site_settings(payload: SettingsPatchIn, user: dict = Depends(get_current_user)):
    """Admin-only edit of site content."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admins only")

    existing = await db.site_settings.find_one({"_kind": "site"}, {"_id": 0}) or {}
    new_about = {**(existing.get("about") or {}), **(payload.about.model_dump(exclude_none=True) if payload.about else {})}
    new_contact = {**(existing.get("contact") or {}), **(payload.contact.model_dump(exclude_none=True) if payload.contact else {})}
    # Editor pick: `exclude_none=False` so the admin can explicitly clear the
    # pick by sending `{"event_id": null}` without losing the blurb/badge.
    if payload.editor_pick is not None:
        ep_in = payload.editor_pick.model_dump(exclude_unset=True)
        new_editor_pick = {**(existing.get("editor_pick") or {}), **ep_in}
    else:
        new_editor_pick = existing.get("editor_pick") or {}

    await db.site_settings.update_one(
        {"_kind": "site"},
        {"$set": {
            "_kind": "site",
            "about": new_about,
            "contact": new_contact,
            "editor_pick": new_editor_pick,
            "updated_at": utc_now().isoformat(),
            "updated_by": user["user_id"],
        }},
        upsert=True,
    )
    return await _load()
