"""Event endpoints: list, featured, categories, detail, create."""
import os
import uuid
from datetime import timedelta
from typing import Optional, Dict, Any
from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core import db, get_current_user, require_role, utc_now, event_to_public, compute_tier_effective_price, logger
from models import EventIn

router = APIRouter(tags=["events"])

# An event is considered "finished" and archived from public listings this many
# hours after its start `date`. We use a buffer (rather than `date < now`) so
# same-day events don't vanish the moment they start. 24h covers most multi-day
# festivals; tweak via env if you ever want shorter/longer.
EVENT_FINISHED_GRACE_HOURS = int(os.environ.get("EVENT_FINISHED_GRACE_HOURS", "24"))


def _event_finished_cutoff_iso() -> str:
    """Events with `date` older than this ISO string are considered finished."""
    return (utc_now() - timedelta(hours=EVENT_FINISHED_GRACE_HOURS)).isoformat()


def _is_event_past(event_date: Optional[str]) -> bool:
    if not event_date:
        return False
    return event_date < _event_finished_cutoff_iso()


async def _attach_face_avatars(items: list[dict]) -> None:
    """Decorate each event with `organizer_picture` and `featured_creators`.

    Buyers trust events more when they can see "who's running this" (the
    organizer logo) and "who's promoting it" (a small avatar strip of the
    creators driving sales via promo codes). This batches BOTH lookups into
    single queries so the listing endpoint stays cheap regardless of how many
    events come back.

    Mutates `items` in place. Safe to call with an empty list.
    """
    if not items:
        return

    # 1) Organizer avatars (one users.find for ALL events at once)
    organizer_ids = list({ev["organizer_id"] for ev in items if ev.get("organizer_id")})
    if organizer_ids:
        org_map: dict[str, str] = {}
        async for u in db.users.find(
            {"user_id": {"$in": organizer_ids}}, {"_id": 0, "user_id": 1, "picture": 1},
        ):
            if u.get("picture"):
                org_map[u["user_id"]] = u["picture"]
        for ev in items:
            pic = org_map.get(ev.get("organizer_id"))
            if pic:
                ev["organizer_picture"] = pic

    # 2) Up to 3 featured creators per event (creators with an active code)
    event_ids = [ev["event_id"] for ev in items]
    # Step 2a: pull active creator_id sets per event in one query
    code_pipeline = db.discount_codes.aggregate([
        {"$match": {
            "event_id": {"$in": event_ids},
            "creator_id": {"$exists": True, "$ne": None},
            "active": True,
        }},
        {"$group": {"_id": "$event_id", "creators": {"$addToSet": "$creator_id"}}},
    ])
    creators_by_event: dict[str, list[str]] = {}
    all_creator_ids: set[str] = set()
    async for row in code_pipeline:
        eid = row["_id"]
        cids = list(row.get("creators") or [])[:3]
        creators_by_event[eid] = cids
        all_creator_ids.update(cids)

    # Step 2b: fetch their avatars + display names (one query)
    creator_meta: dict[str, dict] = {}
    if all_creator_ids:
        async for prof in db.influencers.find(
            {"user_id": {"$in": list(all_creator_ids)}, "is_active": True},
            {"_id": 0, "user_id": 1, "display_name": 1, "avatar_url": 1},
        ):
            creator_meta[prof["user_id"]] = {
                "display_name": prof.get("display_name"),
                "avatar_url": prof.get("avatar_url"),
            }

    for ev in items:
        cids = creators_by_event.get(ev["event_id"]) or []
        if not cids:
            continue
        strip = []
        for cid in cids:
            meta = creator_meta.get(cid) or {}
            if meta.get("avatar_url") or meta.get("display_name"):
                strip.append({
                    "creator_id": cid,
                    "display_name": meta.get("display_name"),
                    "avatar_url": meta.get("avatar_url"),
                })
        if strip:
            ev["featured_creators"] = strip


@router.get("/events")
async def list_events(
    q: Optional[str] = None,
    category: Optional[str] = None,
    city: Optional[str] = None,
    country: Optional[str] = None,
    past: bool = False,
    limit: int = 50,
):
    query: Dict[str, Any] = {"status": {"$in": ["approved", "published"]}}
    cutoff_iso = _event_finished_cutoff_iso()
    if past:
        # Finished events only — newest first so the most recent show up top.
        query["date"] = {"$lt": cutoff_iso}
        sort_spec = [("date", -1)]
    else:
        # Upcoming + still-running events (within the grace window).
        query["date"] = {"$gte": cutoff_iso}
        sort_spec = [("date", 1)]
    if q:
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"venue": {"$regex": q, "$options": "i"}},
        ]
    if category:
        query["category"] = category
    if city:
        query["city"] = {"$regex": city, "$options": "i"}
    if country:
        query["country"] = country.upper()
    cursor = db.events.find(query, {"_id": 0}).sort(sort_spec).limit(limit)
    items = [event_to_public(e) async for e in cursor]
    # Annotate events with waitlist_count (cheap aggregate) — only meaningful
    # for upcoming events; skip for past listings.
    if not past:
        for e in items:
            wcount = await db.waitlist_entries.count_documents(
                {"event_id": e["event_id"], "status": "waiting"}
            )
            if wcount > 0:
                e["waitlist_count"] = wcount
    else:
        for e in items:
            e["is_past"] = True
    # Annotate ratings (avg_stars + reviews count) in a single batched
    # aggregate. Past listings benefit most (most ratings live there), but
    # upcoming events that already ran a previous occurrence may also have
    # ratings — so we always run it.
    event_ids = [e["event_id"] for e in items]
    if event_ids:
        async for row in db.event_feedback.aggregate([
            {"$match": {"event_id": {"$in": event_ids}}},
            {"$group": {"_id": "$event_id", "avg": {"$avg": "$stars"}, "count": {"$sum": 1}}},
        ]):
            for e in items:
                if e["event_id"] == row["_id"] and row["count"] >= 3:
                    # Need at least 3 ratings before showing a badge — fewer
                    # than that and a single 1★ skews the average so much
                    # it's misleading to surface.
                    e["avg_stars"] = round(row["avg"], 1)
                    e["reviews_count"] = row["count"]
                    break
    # Annotate `is_boosted` based on `boosted_until` field. We compute this
    # server-side so the frontend doesn't have to know about clock skew.
    now_iso = utc_now().isoformat()
    for e in items:
        bu = e.get("boosted_until")
        e["is_boosted"] = bool(bu and bu > now_iso)

    # Enrich each event with the organizer's avatar URL and a tiny strip of
    # featured-creator avatars (the influencers actively promoting it via a
    # creator code). Both are batched 1-query operations — no N+1.
    await _attach_face_avatars(items)
    # Sort upcoming list to put featured/boosted events first, then by date.
    # `featured` and `is_boosted` are independent flags — featured is curated
    # by admins (long-term spotlight), boosted is purchased by the organizer
    # (short-term). Both ranked above unmarked events; ties break on date asc.
    if not past:
        items.sort(key=lambda x: (
            not x.get("featured", False),    # featured first (False sorts before True)
            not x.get("is_boosted", False),  # then boosted
            x.get("date") or "",             # then chronological
        ))
    return items


@router.get("/events/trending")
async def trending_events(limit: int = 12):
    """Currently-boosted events — powers the homepage 'Trending This Week'
    carousel. Server-side filter on `boosted_until > now` so we don't ship
    expired badges to the client; sort by `boosted_at` desc (newest boosts
    first) so the rail keeps rotating as organizers boost throughout the day.
    """
    cutoff_iso = _event_finished_cutoff_iso()
    now_iso = utc_now().isoformat()
    cursor = db.events.find(
        {
            "status": {"$in": ["approved", "published"]},
            "date": {"$gte": cutoff_iso},
            "boosted_until": {"$gt": now_iso},
        },
        {"_id": 0},
    ).sort("boosted_at", -1).limit(max(1, min(limit, 24)))
    items = []
    async for e in cursor:
        public = event_to_public(e)
        public["is_boosted"] = True
        items.append(public)
    await _attach_face_avatars(items)
    return items


@router.get("/events/featured")
async def featured_events():
    cutoff_iso = _event_finished_cutoff_iso()
    base_q = {
        "status": {"$in": ["approved", "published"]},
        "date": {"$gte": cutoff_iso},
    }
    cursor = db.events.find({**base_q, "featured": True}, {"_id": 0}).limit(6)
    items = [event_to_public(e) async for e in cursor]
    if not items:
        cursor = db.events.find(base_q, {"_id": 0}).sort("date", 1).limit(6)
        items = [event_to_public(e) async for e in cursor]
    await _attach_face_avatars(items)
    return items


@router.get("/events/categories")
async def event_categories():
    return [
        {"id": "movies", "name": "Movies", "image": "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=800"},
        {"id": "music", "name": "Music", "image": "https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=800"},
        {"id": "comedy", "name": "Comedy", "image": "https://images.unsplash.com/photo-1527224538127-2104bb71c51b?w=800"},
        {"id": "sports", "name": "Sports", "image": "https://images.unsplash.com/photo-1471295253337-3ceaaedca402?w=800"},
        {"id": "theater", "name": "Theater", "image": "https://images.unsplash.com/photo-1503095396549-807759245b35?w=800"},
        {"id": "tech", "name": "Tech & Conferences", "image": "https://images.unsplash.com/photo-1540575467063-178a50c2df87?w=800"},
        {"id": "workshops", "name": "Workshops", "image": "https://images.unsplash.com/photo-1552581234-26160f608093?w=800"},
        {"id": "festivals", "name": "Festivals", "image": "https://images.unsplash.com/photo-1459749411175-04bf5292ceea?w=800"},
        {"id": "arts", "name": "Arts & Culture", "image": "https://images.unsplash.com/photo-1547891654-e66ed7ebb968?w=800"},
    ]


@router.get("/events/stats/public")
async def public_event_stats():
    """Cheap public counter used by the landing-page hero chip
    ("Live · N events on sale"). Counts only approved + future events so the
    number always represents tickets a visitor can actually buy right now.
    """
    now_iso = utc_now().isoformat()
    live_count = await db.events.count_documents({
        "status": {"$in": ["approved", "published"]},
        "date": {"$gte": now_iso},
    })
    return {"live_events": live_count}


@router.get("/events/countries")
async def public_event_countries():
    """Distinct country codes that currently have at least one approved
    upcoming event. Frontend uses this to populate the country filter on
    the Browse page (so we never show countries with zero events).
    """
    cutoff_iso = _event_finished_cutoff_iso()
    pipeline = [
        {"$match": {
            "status": {"$in": ["approved", "published"]},
            "date": {"$gte": cutoff_iso},
        }},
        {"$group": {"_id": {"$ifNull": ["$country", "NZ"]}, "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    out = []
    async for row in db.events.aggregate(pipeline):
        out.append({"country": row["_id"] or "NZ", "count": row["count"]})
    return out


@router.get("/events/{event_id}")
async def get_event(event_id: str):
    e = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="Event not found")
    if e.get("has_seatmap"):
        now_iso = utc_now().isoformat()
        booked_seats = []
        held_seats = []
        async for r in db.seat_reservations.find(
            {"event_id": event_id, "status": {"$in": ["booked", "blocked"]}}, {"_id": 0, "seat_id": 1},
        ):
            booked_seats.append(r["seat_id"])
        async for r in db.seat_reservations.find(
            {"event_id": event_id, "status": "held", "expires_at": {"$gte": now_iso}},
            {"_id": 0, "seat_id": 1},
        ):
            held_seats.append(r["seat_id"])
        e["booked_seats"] = booked_seats
        e["held_seats"] = held_seats
        # Sold-out = every non-aisle seat is locked
        rows = e.get("seat_rows", 0)
        cols = e.get("seat_cols", 0)
        aisles = set(e.get("aisles") or [])
        total_non_aisle = max(0, rows * cols - len(aisles))
        locked = len({*booked_seats, *held_seats})
        e["sold_out"] = total_non_aisle > 0 and locked >= total_non_aisle
    else:
        # For tier-based events, compute sold/remaining per tier and aggregate sold_out flag
        now_iso = utc_now().isoformat()
        tier_status = []
        any_remaining = False
        any_surging = False
        for t in e.get("tiers", []):
            sold = 0
            async for b in db.bookings.find(
                {"event_id": event_id, "tier_name": t["name"], "status": {"$in": ["paid", "confirmed", "pending"]}},
                {"_id": 0, "quantity": 1, "hold_expires_at": 1, "status": 1},
            ):
                if b.get("status") == "pending" and (b.get("hold_expires_at") or "") < now_iso:
                    continue
                sold += b.get("quantity", 0)
            remaining = max(0, t.get("capacity", 0) - sold)
            if remaining > 0:
                any_remaining = True
            eff_price, surging = compute_tier_effective_price(e, t, sold)
            if surging:
                any_surging = True
                t["effective_price"] = eff_price
                t["surging"] = True
            tier_status.append({"name": t["name"], "sold": sold, "remaining": remaining, "effective_price": eff_price, "surging": surging})
        e["tier_status"] = tier_status
        e["sold_out"] = (not any_remaining) and bool(e.get("tiers"))
        e["surging"] = any_surging
    e["is_past"] = _is_event_past(e.get("date"))
    # Annotate avg rating + review count for the badge on Event Detail
    agg = await db.event_feedback.aggregate([
        {"$match": {"event_id": event_id}},
        {"$group": {"_id": None, "avg": {"$avg": "$stars"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    if agg and agg[0]["count"] >= 3:
        e["avg_stars"] = round(agg[0]["avg"], 1)
        e["reviews_count"] = agg[0]["count"]
    # Boost flag
    bu = e.get("boosted_until")
    e["is_boosted"] = bool(bu and bu > utc_now().isoformat())
    return event_to_public(e)


def _event_is_paid(tiers: list) -> bool:
    """An event is `paid` if at least one tier has a positive price.

    Used to decide whether the organizer MUST connect Stripe Connect before
    publishing (free events skip the Stripe gate entirely).
    """
    for t in tiers or []:
        try:
            if float(t.get("price", 0) or 0) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


async def _send_stripe_required_reminder(user: dict, event_title: str, onboarding_origin: str) -> None:
    """Fire-and-forget reminder email when an organizer tries to publish a paid
    event without a working Stripe Connect payout account. One-shot per attempt
    — the user pulls the trigger on each publish click, so we don't throttle.
    """
    try:
        from emails import send_template_fireforget
        send_template_fireforget(
            "organizer_stripe_required",
            user.get("email"),
            {
                "organizer_name": user.get("name") or "there",
                "event_title": event_title or "your event",
                "onboarding_url": f"{onboarding_origin.rstrip('/')}/organizer?stripe_return=1",
            },
            db,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[events] stripe-required reminder dispatch failed: {exc}")


@router.post("/events")
async def create_event(payload: EventIn, request: Request, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    event_id = f"evt_{uuid.uuid4().hex[:12]}"

    # Stripe Connect gate: organizers MUST have a working payout account
    # before they can publish a PAID event. Free events skip this check.
    # Admins are trusted (they can create on behalf of an organizer who is
    # still onboarding — that organizer will get their own payout reminder
    # via the "admin_created_event_for_you" flow downstream).
    if user.get("role") != "admin" and _event_is_paid(payload.tiers):
        if not bool(user.get("stripe_payouts_enabled")):
            origin = request.headers.get("origin") or "https://www.allsale.events"
            await _send_stripe_required_reminder(user, payload.title, origin)
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "stripe_payouts_required",
                    "message": (
                        "Connect your bank account on Stripe before publishing a "
                        "paid event — payouts can't reach you otherwise. We've "
                        "emailed you a 1-click onboarding link."
                    ),
                    "onboarding_path": "/organizer",
                },
            )

    # Admin-only: create on behalf of another organizer. The event gets
    # attributed to that organizer (organizer_id + organizer_name) and lands
    # on their dashboard. The organizer receives an email notification.
    organizer_id = user["user_id"]
    organizer_name = user["name"]
    created_on_behalf = False
    if user.get("role") == "admin" and (payload.on_behalf_of_organizer_id or "").strip():
        target = await db.users.find_one(
            {"user_id": payload.on_behalf_of_organizer_id.strip()},
            {"_id": 0, "user_id": 1, "name": 1, "email": 1, "role": 1},
        )
        if not target:
            raise HTTPException(status_code=404, detail="Target organizer not found")
        if target.get("role") not in ("organizer", "admin"):
            raise HTTPException(status_code=400, detail="Target user is not an organizer")
        organizer_id = target["user_id"]
        organizer_name = target.get("name") or "Organizer"
        created_on_behalf = True

    doc = {
        "event_id": event_id,
        "organizer_id": organizer_id,
        "organizer_name": organizer_name,
        "title": payload.title,
        "description": payload.description,
        "category": payload.category,
        "venue": payload.venue,
        "city": payload.city,
        "country": (payload.country or "NZ").upper(),
        "timezone": payload.timezone,
        "date": payload.date,
        "end_date": payload.end_date,
        "image_url": payload.image_url,
        "banner_url": payload.banner_url or payload.image_url,
        "promo_video_url": payload.promo_video_url,
        "poster_url": payload.poster_url,
        "currency": (payload.currency or "NZD").upper(),
        "tiers": payload.tiers,
        "has_seatmap": payload.has_seatmap,
        "seat_rows": payload.seat_rows,
        "seat_cols": payload.seat_cols,
        "seat_price": payload.seat_price,
        "aisles": payload.aisles,
        "seat_map_image_url": payload.seat_map_image_url,
        "seatmap_curved": payload.seatmap_curved,
        "seatmap_numbering_rtl": payload.seatmap_numbering_rtl,
        "seatmap_sections": payload.seatmap_sections,
        "seatmap_categories": payload.seatmap_categories or {},
        "seatmap_category_prices": payload.seatmap_category_prices or {},
        "seatmap_row_offsets": payload.seatmap_row_offsets or {},
        "seatmap_custom_labels": payload.seatmap_custom_labels or {},
        "seatmap_backdrop_opacity": payload.seatmap_backdrop_opacity,
        "seatmap_backdrop_offset_y": payload.seatmap_backdrop_offset_y,
        "seatmap_backdrop_offset_x": payload.seatmap_backdrop_offset_x,
        "seatmap_backdrop_scale": payload.seatmap_backdrop_scale,
        "refund_policy": payload.refund_policy,
        "auto_promo_disabled": bool(payload.auto_promo_disabled),
        "affiliate_program_open": bool(payload.affiliate_program_open),
        "affiliate_default_commission_pct": float(payload.affiliate_default_commission_pct),
        "group_discount": payload.group_discount or None,
        "status": "approved" if user.get("role") == "admin" else "pending",
        "featured": False,
        "created_at": utc_now().isoformat(),
    }
    if created_on_behalf:
        doc["created_by_admin_id"] = user["user_id"]
        doc["created_by_admin_name"] = user.get("name") or "Admin"
    await db.events.insert_one(doc)
    # Notify the target organizer when an admin created an event for them.
    if created_on_behalf:
        try:
            from emails import send_template_fireforget
            cms = await db.platform_settings.find_one({"key": "cms"}, {"_id": 0}) or {}
            origin = (cms.get("public_origin") or "https://www.allsale.events").rstrip("/")
            send_template_fireforget(
                "admin_created_event_for_you",
                target.get("email"),
                {
                    "organizer_name": organizer_name,
                    "event_title": doc["title"],
                    "event_id": event_id,
                    "event_url": f"{origin}/events/{event_id}",
                    "edit_url": f"{origin}/organizer/events/{event_id}/edit",
                    "admin_name": user.get("name") or "An admin",
                    "venue": f"{doc.get('venue','')}, {doc.get('city','')}",
                    "event_date_iso": doc["date"],
                },
                db,
            )
        except Exception as exc:  # pragma: no cover
            from core import logger as _log
            _log.warning(f"[events] organizer on-behalf notify failed: {exc}")
    # Notify all admins when a new event lands in the moderation queue.
    if doc["status"] == "pending":
        try:
            from emails import send_template_fireforget
            cms = await db.platform_settings.find_one({"key": "cms"}, {"_id": 0}) or {}
            origin = (cms.get("public_origin") or "https://www.allsale.events").rstrip("/")
            admin_url = f"{origin}/admin"
            async for admin in db.users.find(
                {"role": "admin"}, {"_id": 0, "email": 1, "name": 1}
            ):
                send_template_fireforget(
                    "admin_new_event_submitted",
                    admin.get("email"),
                    {
                        "admin_name": admin.get("name") or "Admin",
                        "event_title": doc["title"],
                        "organizer_name": doc.get("organizer_name") or "Organizer",
                        "venue": f"{doc.get('venue','')}, {doc.get('city','')}",
                        "event_date_iso": doc["date"],
                        "admin_url": admin_url,
                    },
                    db,
                )
        except Exception as exc:  # pragma: no cover
            from core import logger as _log
            _log.warning(f"[events] admin notify failed: {exc}")
    return event_to_public(doc)


@router.patch("/events/{event_id}")
async def update_event(event_id: str, payload: dict, user: dict = Depends(get_current_user)):
    """Edit an event. Owner, admin or team members with manager+ rights can edit.

    Body is a partial dict of EventIn-compatible fields. Unknown keys are
    silently dropped to keep this forgiving for the frontend.
    """
    from routers.team import user_can_manage_event
    await require_role(user, "organizer", "admin")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if not await user_can_manage_event(user, event, required="manager"):
        raise HTTPException(status_code=403, detail="Not your event")

    EDITABLE = {
        "title", "description", "category", "venue", "city", "country", "timezone", "date", "end_date",
        "image_url", "banner_url", "promo_video_url", "poster_url", "tiers",
        "has_seatmap", "seat_rows", "seat_cols", "seat_price",
        "aisles", "seat_map_image_url",
        "seatmap_curved", "seatmap_numbering_rtl", "seatmap_sections", "seatmap_categories", "seatmap_category_prices", "seatmap_row_offsets", "seatmap_custom_labels",
        "seatmap_backdrop_opacity", "seatmap_backdrop_offset_y",
        "seatmap_backdrop_offset_x", "seatmap_backdrop_scale",
        "currency", "refund_policy", "auto_promo_disabled",
        "affiliate_program_open", "affiliate_default_commission_pct",
        "group_discount",
    }
    update = {k: v for k, v in (payload or {}).items() if k in EDITABLE}
    if not update:
        raise HTTPException(status_code=400, detail="No editable fields provided")

    # Stripe Connect gate (mirror of the create-event check). If this PATCH
    # raises an event from free → paid, the organizer needs working payouts.
    if (
        "tiers" in update
        and user.get("role") != "admin"
        and _event_is_paid(update["tiers"])
        and not bool(user.get("stripe_payouts_enabled"))
    ):
        from fastapi import Request as _Req  # local import for type only
        # We don't have the Request object here; use the platform default for
        # the onboarding link domain — good enough for the reminder email.
        cms = await db.platform_settings.find_one({"key": "cms"}, {"_id": 0}) or {}
        origin = (cms.get("public_origin") or "https://www.allsale.events").rstrip("/")
        await _send_stripe_required_reminder(user, event.get("title", ""), origin)
        raise HTTPException(
            status_code=402,
            detail={
                "code": "stripe_payouts_required",
                "message": (
                    "Connect your bank account on Stripe before turning this "
                    "into a paid event — payouts can't reach you otherwise. "
                    "We've emailed you a 1-click onboarding link."
                ),
                "onboarding_path": "/organizer",
            },
        )

    update["updated_at"] = utc_now().isoformat()
    update["updated_by"] = user["user_id"]

    await db.events.update_one({"event_id": event_id}, {"$set": update})
    refreshed = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    return event_to_public(refreshed)


@router.delete("/events/{event_id}")
async def delete_event(event_id: str, user: dict = Depends(get_current_user)):
    """Delete an event AND all of its bookings, holds, seat-blocks, scanner tokens,
    team grants. Only the owner or an admin can delete.

    NOTE: We refuse to delete events that already have paid bookings unless the
    caller is an admin — the organizer must refund first, or escalate to admin.
    """
    await require_role(user, "organizer", "admin")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    is_owner = event.get("organizer_id") == user["user_id"]
    is_admin = user.get("role") == "admin"
    if not (is_owner or is_admin):
        raise HTTPException(status_code=403, detail="Only the event owner or an admin can delete")

    paid_count = await db.bookings.count_documents({"event_id": event_id, "status": "paid"})
    if paid_count > 0 and not is_admin:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete — {paid_count} paid booking(s) exist. Refund first or ask an admin.",
        )

    # Cascade-clean any artefacts so the DB doesn't hoard orphans
    cascade = {
        "bookings": await db.bookings.delete_many({"event_id": event_id}),
        "seat_reservations": await db.seat_reservations.delete_many({"event_id": event_id}),
        "seat_holds": await db.seat_holds.delete_many({"event_id": event_id}),
        "scanner_tokens": await db.scanner_tokens.delete_many({"event_id": event_id}),
        "team_members_event": await db.team_members.delete_many({"event_id": event_id, "scope": "event"}),
        "waitlist": await db.waitlist.delete_many({"event_id": event_id}),
        "discount_codes": await db.discount_codes.delete_many({"event_id": event_id}),
    }
    await db.events.delete_one({"event_id": event_id})

    return {
        "deleted": event_id,
        "title": event.get("title"),
        "cascade": {k: r.deleted_count for k, r in cascade.items()},
    }



class DynamicPricingIn(BaseModel):
    enabled: bool
    surge_threshold_pct: float = Field(default=30.0, ge=5, le=90)
    surge_multiplier: float = Field(default=1.2, ge=1.01, le=3.0)


@router.patch("/organizer/events/{event_id}/dynamic-pricing")
async def set_dynamic_pricing(event_id: str, payload: DynamicPricingIn, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event["organizer_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your event")
    await db.events.update_one(
        {"event_id": event_id},
        {"$set": {"dynamic_pricing": {
            "enabled": payload.enabled,
            "surge_threshold_pct": payload.surge_threshold_pct,
            "surge_multiplier": payload.surge_multiplier,
        }}},
    )
    return {"ok": True, "dynamic_pricing": payload.model_dump()}


# Boost duration (hours) and minimum interval between boosts for the same
# event. Free MVP: organizer self-boosts; we throttle so they don't spam
# the "🔥 Trending" badge into uselessness.
BOOST_DURATION_HOURS = int(os.environ.get("BOOST_DURATION_HOURS", "72"))
BOOST_COOLDOWN_HOURS = int(os.environ.get("BOOST_COOLDOWN_HOURS", "168"))  # 7 days


@router.post("/organizer/events/{event_id}/boost")
async def boost_event(event_id: str, user: dict = Depends(get_current_user)):
    """Self-serve boost — flips the 'is_boosted' flag on this event for
    BOOST_DURATION_HOURS so it shows a 🔥 Trending badge on cards.

    Cooldown: BOOST_COOLDOWN_HOURS between boosts per event, to avoid badge
    spam. Free for organizers; paid tiers can be layered on later by reading
    a `paid` flag off the event."""
    await require_role(user, "organizer", "admin")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event["organizer_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your event")

    now = utc_now()
    last_started = event.get("boosted_at")
    if last_started:
        from datetime import datetime
        try:
            prev = datetime.fromisoformat(last_started.replace("Z", "+00:00"))
            elapsed = (now - prev).total_seconds() / 3600
            if elapsed < BOOST_COOLDOWN_HOURS:
                remaining = int(BOOST_COOLDOWN_HOURS - elapsed)
                raise HTTPException(
                    status_code=429,
                    detail=f"Boost on cooldown — try again in {remaining} hour(s)",
                )
        except ValueError:
            pass  # malformed ISO, treat as no prior boost

    until = (now + timedelta(hours=BOOST_DURATION_HOURS)).isoformat()
    await db.events.update_one(
        {"event_id": event_id},
        {"$set": {"boosted_at": now.isoformat(), "boosted_until": until}},
    )
    return {
        "ok": True,
        "boosted_until": until,
        "duration_hours": BOOST_DURATION_HOURS,
        "next_boost_available_in_hours": BOOST_COOLDOWN_HOURS,
    }


# ---------------------------------------------------------------------------
# Paid Boost — Stripe-backed premium promotion tiers
# ---------------------------------------------------------------------------
# Tiered pricing — organizers pick a duration. We charge upfront via Stripe
# Checkout and only flip `boosted_until` on webhook success.
BOOST_TIERS = {
    "1day":  {"hours": 24,   "price": 15.0, "label": "1 day"},
    "3days": {"hours": 72,   "price": 35.0, "label": "3 days"},
    "1week": {"hours": 168,  "price": 75.0, "label": "1 week"},
}


@router.get("/organizer/events/{event_id}/boost/tiers")
async def get_boost_tiers(event_id: str, user: dict = Depends(get_current_user)):
    """Public-to-organizer endpoint listing the paid boost options + the free
    self-serve fallback. Frontend renders this as a 4-card picker."""
    return {
        "currency": "NZD",
        "tiers": [
            {"id": tid, **t} for tid, t in BOOST_TIERS.items()
        ],
        "free_duration_hours": BOOST_DURATION_HOURS,
    }


class PaidBoostIn(BaseModel):
    tier: str
    origin_url: str


@router.post("/organizer/events/{event_id}/boost/checkout")
async def create_paid_boost_checkout(event_id: str, payload: PaidBoostIn, request: Request, user: dict = Depends(get_current_user)):
    """Create a Stripe Checkout session for a paid Boost. The actual flag flip
    happens on the Stripe webhook (`finalize_paid_boost` below)."""
    await require_role(user, "organizer", "admin")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event["organizer_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your event")
    tier = BOOST_TIERS.get(payload.tier)
    if not tier:
        raise HTTPException(status_code=400, detail="Invalid boost tier")
    try:
        from emergentintegrations.payments.stripe.checkout import (
            StripeCheckout, CheckoutSessionRequest,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="Payments are temporarily unavailable") from exc
    from core import STRIPE_API_KEY
    host_url = str(request.base_url)
    fwd_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if fwd_proto == "https" and host_url.startswith("http://"):
        host_url = "https://" + host_url[len("http://"):]
    webhook_url = (os.environ.get("STRIPE_WEBHOOK_URL") or "").strip() or f"{host_url}api/webhook/stripe"
    stripe = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
    req = CheckoutSessionRequest(
        amount=float(tier["price"]),
        currency="nzd",
        success_url=f"{payload.origin_url}/organizer?boost_success=1&event={event_id}",
        cancel_url=f"{payload.origin_url}/organizer",
        metadata={
            "kind": "paid_boost",
            "event_id": event_id,
            "tier": payload.tier,
            "hours": str(tier["hours"]),
            "organizer_id": user["user_id"],
        },
    )
    session = await stripe.create_checkout_session(req)
    return {"url": session.url, "session_id": session.session_id, "amount": tier["price"], "hours": tier["hours"]}


async def finalize_paid_boost(meta: Dict[str, Any]) -> bool:
    """Webhook-time hook: flip the event's boost flags once Stripe confirms."""
    event_id = meta.get("event_id")
    hours = int(meta.get("hours") or BOOST_DURATION_HOURS)
    if not event_id:
        return False
    now = utc_now()
    until = (now + timedelta(hours=hours)).isoformat()
    res = await db.events.update_one(
        {"event_id": event_id},
        {"$set": {
            "boosted_at": now.isoformat(),
            "boosted_until": until,
            "last_boost_kind": "paid",
            "last_boost_tier": meta.get("tier"),
        }},
    )
    logger.info(f"[boost] paid boost activated for event {event_id} until {until}")
    return res.modified_count > 0
