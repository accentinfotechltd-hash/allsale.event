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
        # `picks` is the new multi-event list. Each item has its own event_id
        # and curator blurb so the curator can write a different blurb per
        # event. The landing page auto-rotates through them.
        #
        # Legacy compatibility: the old singular `event_id` + `blurb` keys
        # are still read in `_load` and merged into `picks` when present,
        # so existing data keeps working untouched.
        "picks": [],   # [{event_id: str, blurb: str}]
        "event_id": None,   # legacy singular
        "blurb": "",        # legacy singular
        "badge_text": "Editor's Pick",
    },
    "support_chat": {
        # Editable from the admin Settings tab so support staff can iterate
        # on the canned templates without a code deploy.
        "canned_replies": [
            "Hi! What's your booking ID?",
            "Could you send a screenshot of the issue?",
            "I'm looking into this now — one moment please.",
            "Your refund has been processed. It'll appear in 3-5 business days.",
            "We've resent your e-ticket — please check your inbox & spam.",
            "Is there anything else I can help with?",
            "Thanks for reaching out! Have a great day. 🎉",
        ],
        # Slack incoming webhook (e.g. https://hooks.slack.com/services/T…/B…/…)
        # When set, new visitor messages are posted here in addition to the
        # admin email alert. Leave empty to disable Slack notifications.
        "slack_webhook_url": "",
    },
}


def _normalize_picks(ep: dict) -> list[dict]:
    """Return a clean `picks` list, merging in the legacy singular `event_id`
    if present so saved-once-long-ago data still surfaces."""
    raw = ep.get("picks") or []
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        eid = (item.get("event_id") or "").strip()
        if not eid:
            continue
        out.append({"event_id": eid, "blurb": (item.get("blurb") or "").strip()})
    legacy_eid = (ep.get("event_id") or "").strip()
    if legacy_eid and not any(p["event_id"] == legacy_eid for p in out):
        out.insert(0, {"event_id": legacy_eid, "blurb": (ep.get("blurb") or "").strip()})
    return out


async def _load() -> dict:
    """Return the stored document, falling back to DEFAULTS for any missing keys."""
    doc = await db.site_settings.find_one({"_kind": "site"}, {"_id": 0}) or {}
    return {
        "about": {**DEFAULTS["about"], **(doc.get("about") or {})},
        "contact": {**DEFAULTS["contact"], **(doc.get("contact") or {})},
        "editor_pick": {**DEFAULTS["editor_pick"], **(doc.get("editor_pick") or {})},
        "support_chat": {**DEFAULTS["support_chat"], **(doc.get("support_chat") or {})},
        "updated_at": doc.get("updated_at"),
    }


@router.get("/site-settings")
async def public_site_settings():
    """Public read for About + Contact pages."""
    return await _load()


@router.get("/site-settings/editor-pick")
async def public_editor_pick():
    """Public read used by the landing-page hero. Now returns a `picks` array
    so the landing page can auto-rotate through multiple curator picks.

    Backward-compat: also returns the singular `event` / `blurb` keys
    pointing at the FIRST pick, so older clients keep working.
    """
    settings = await _load()
    ep = settings.get("editor_pick") or {}
    badge_text = ep.get("badge_text") or "Editor's Pick"
    picks_raw = _normalize_picks(ep)

    picks: list[dict] = []
    for p in picks_raw:
        ev = await db.events.find_one(
            {"event_id": p["event_id"], "status": {"$in": ["approved", "published"]}},
            {"_id": 0},
        )
        if not ev:
            continue  # stale pick, silently skip
        picks.append({"event": event_to_public(ev), "blurb": p.get("blurb", "")})

    first = picks[0] if picks else {"event": None, "blurb": ""}
    return {
        "picks": picks,
        "badge_text": badge_text,
        # Legacy single-pick fields:
        "event": first["event"],
        "blurb": first["blurb"],
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


class EditorPickItemIn(BaseModel):
    event_id: str
    blurb: str | None = None


class EditorPickIn(BaseModel):
    event_id: str | None = None  # legacy single — still accepted for backward compat
    blurb: str | None = None
    badge_text: str | None = None
    # New multi-pick payload — when set, fully replaces `picks`.
    picks: list[EditorPickItemIn] | None = None


class SupportChatSettingsIn(BaseModel):
    canned_replies: list[str] | None = None
    slack_webhook_url: str | None = None


class SettingsPatchIn(BaseModel):
    about: AboutIn | None = None
    contact: ContactIn | None = None
    editor_pick: EditorPickIn | None = None
    support_chat: SupportChatSettingsIn | None = None


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
        # When the admin sends `picks`, it fully replaces the array.
        if "picks" in ep_in and ep_in["picks"] is not None:
            ep_in["picks"] = [
                {"event_id": (p.get("event_id") or "").strip(),
                 "blurb": (p.get("blurb") or "").strip()}
                for p in ep_in["picks"]
                if isinstance(p, dict) and (p.get("event_id") or "").strip()
            ]
        new_editor_pick = {**(existing.get("editor_pick") or {}), **ep_in}
    else:
        new_editor_pick = existing.get("editor_pick") or {}

    # Support chat: canned templates + Slack webhook URL.
    if payload.support_chat is not None:
        sc_in = payload.support_chat.model_dump(exclude_unset=True)
        if "canned_replies" in sc_in and sc_in["canned_replies"] is not None:
            # Trim, drop empties, cap to 30 templates to keep the UI fast.
            sc_in["canned_replies"] = [s.strip() for s in sc_in["canned_replies"] if s and s.strip()][:30]
        if "slack_webhook_url" in sc_in:
            sc_in["slack_webhook_url"] = (sc_in["slack_webhook_url"] or "").strip()
        new_support_chat = {**(existing.get("support_chat") or {}), **sc_in}
    else:
        new_support_chat = existing.get("support_chat") or {}

    await db.site_settings.update_one(
        {"_kind": "site"},
        {"$set": {
            "_kind": "site",
            "about": new_about,
            "contact": new_contact,
            "editor_pick": new_editor_pick,
            "support_chat": new_support_chat,
            "updated_at": utc_now().isoformat(),
            "updated_by": user["user_id"],
        }},
        upsert=True,
    )
    return await _load()
