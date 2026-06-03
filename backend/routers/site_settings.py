"""Site-wide editable content — admin can edit About/Contact copy + contact details.

Single Mongo document keyed by `_kind: "site"` in `site_settings`. The public
GET is open (no auth) so any visitor can render the About/Contact pages.
The PATCH is admin-only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import db, get_current_user, utc_now

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
}


async def _load() -> dict:
    """Return the stored document, falling back to DEFAULTS for any missing keys."""
    doc = await db.site_settings.find_one({"_kind": "site"}, {"_id": 0}) or {}
    return {
        "about": {**DEFAULTS["about"], **(doc.get("about") or {})},
        "contact": {**DEFAULTS["contact"], **(doc.get("contact") or {})},
        "updated_at": doc.get("updated_at"),
    }


@router.get("/site-settings")
async def public_site_settings():
    """Public read for About + Contact pages."""
    return await _load()


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


class SettingsPatchIn(BaseModel):
    about: AboutIn | None = None
    contact: ContactIn | None = None


@router.patch("/admin/site-settings")
async def update_site_settings(payload: SettingsPatchIn, user: dict = Depends(get_current_user)):
    """Admin-only edit of site content."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admins only")

    existing = await db.site_settings.find_one({"_kind": "site"}, {"_id": 0}) or {}
    new_about = {**(existing.get("about") or {}), **(payload.about.model_dump(exclude_none=True) if payload.about else {})}
    new_contact = {**(existing.get("contact") or {}), **(payload.contact.model_dump(exclude_none=True) if payload.contact else {})}

    await db.site_settings.update_one(
        {"_kind": "site"},
        {"$set": {
            "_kind": "site",
            "about": new_about,
            "contact": new_contact,
            "updated_at": utc_now().isoformat(),
            "updated_by": user["user_id"],
        }},
        upsert=True,
    )
    return await _load()
