"""AI-powered event recommendations using Emergent LLM.

Endpoint: `GET /api/me/recommendations` — returns 3–5 personalized event
recommendations for the current user based on their past bookings (category +
city affinity) and currently available approved events. Each recommendation
includes a one-line reason. Cached per user for 1 hour in `recommendation_cache`.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import timedelta

from fastapi import APIRouter, Depends
from emergentintegrations.llm.chat import LlmChat, UserMessage

from core import db, get_current_user, utc_now, event_to_public

logger = logging.getLogger("aura.recs")
router = APIRouter(tags=["recommendations"])

CACHE_TTL = timedelta(hours=1)
MAX_CONTEXT_EVENTS = 30  # cap to avoid huge prompts
MAX_PAST_BOOKINGS = 20


def _cache_key(user_id: str) -> str:
    return f"recs:{user_id}"


@router.get("/me/recommendations")
async def my_recommendations(user: dict = Depends(get_current_user)):
    """Return 3-5 personalized event recommendations with a "why" for each."""
    cached = await db.recommendation_cache.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if cached and cached.get("expires_at", "") > utc_now().isoformat():
        return {"items": cached.get("items", []), "cached": True}

    # Pull past bookings (most recent 20 for context)
    past = []
    async for b in db.bookings.find(
        {"user_id": user["user_id"], "status": "paid"},
        {"_id": 0, "event_id": 1, "event_title": 1, "tier_name": 1, "paid_at": 1},
    ).sort("paid_at", -1).limit(MAX_PAST_BOOKINGS):
        past.append(b)

    past_event_ids = [b["event_id"] for b in past]
    past_event_meta = []
    if past_event_ids:
        async for e in db.events.find({"event_id": {"$in": past_event_ids}}, {"_id": 0, "event_id": 1, "title": 1, "category": 1, "city": 1}):
            past_event_meta.append(e)

    # Candidate events: approved + future + not already booked
    candidates = []
    async for e in db.events.find(
        {"status": "approved", "event_id": {"$nin": past_event_ids}},
        {"_id": 0},
    ).sort("date", 1).limit(MAX_CONTEXT_EVENTS):
        candidates.append(event_to_public(e))

    if not candidates:
        return {"items": [], "cached": False, "reason": "No upcoming events available"}

    # Trending fallback if user has no booking history yet — return first 5 by date
    if not past:
        items = [
            {"event_id": e["event_id"], "reason": "Popular pick — trending right now."}
            for e in candidates[:5]
        ]
        enriched = await _enrich(items)
        await _write_cache(user["user_id"], enriched)
        return {"items": enriched, "cached": False, "reason": "trending"}

    try:
        items = await _ask_llm(user, past_event_meta, candidates)
    except Exception as e:
        logger.error(f"[recs] LLM failed for {user['user_id']}: {e}")
        # Graceful fallback: by category overlap heuristic
        prefer_cats = {p.get("category") for p in past_event_meta if p.get("category")}
        scored = []
        for c in candidates:
            score = 1 if c.get("category") in prefer_cats else 0
            scored.append((score, c))
        scored.sort(key=lambda s: -s[0])
        items = [
            {"event_id": c["event_id"], "reason": f"Similar to your past {c.get('category')} bookings." if score else "You might also like this."}
            for score, c in scored[:5]
        ]

    enriched = await _enrich(items)
    await _write_cache(user["user_id"], enriched)
    return {"items": enriched, "cached": False}


async def _ask_llm(user: dict, past_event_meta: list[dict], candidates: list[dict]) -> list[dict]:
    """Send compact JSON to LLM and parse a strict JSON list back."""
    api_key = os.environ.get("EMERGENT_LLM_KEY") or ""
    if not api_key:
        raise RuntimeError("EMERGENT_LLM_KEY not configured")

    # Compact representations to keep prompt small
    past_brief = [{"title": p["title"], "category": p.get("category"), "city": p.get("city")} for p in past_event_meta]
    cand_brief = [{
        "event_id": c["event_id"],
        "title": c["title"],
        "category": c.get("category"),
        "city": c.get("city"),
        "date": c.get("date"),
    } for c in candidates]

    system = (
        "You are Allsale Events' recommendation engine. Given a user's past event "
        "bookings and a list of available upcoming events, pick 3 to 5 events the "
        "user would most likely enjoy. Prefer overlap with their past category and "
        "city. Return STRICT JSON: an array of objects with two keys: 'event_id' "
        "(exact match from candidates) and 'reason' (one short sentence, <= 15 "
        "words, friendly tone, no quotes). No prose outside the array."
    )

    chat = LlmChat(
        api_key=api_key,
        session_id=f"recs-{user['user_id']}-{utc_now().date()}",
        system_message=system,
    ).with_model("openai", "gpt-5.1")

    payload = {
        "past_bookings": past_brief,
        "candidate_events": cand_brief,
    }

    resp = await chat.send_message(UserMessage(text=json.dumps(payload)))
    text = resp.strip()
    # Strip code fences if present
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip().rstrip("`").strip()
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise ValueError("LLM did not return a list")

    candidate_ids = {c["event_id"] for c in candidates}
    cleaned = []
    for item in parsed:
        if isinstance(item, dict) and item.get("event_id") in candidate_ids:
            cleaned.append({
                "event_id": item["event_id"],
                "reason": (item.get("reason") or "").strip()[:140],
            })
        if len(cleaned) >= 5:
            break
    if not cleaned:
        raise ValueError("LLM picked no valid event_ids")
    return cleaned


async def _enrich(items: list[dict]) -> list[dict]:
    """Attach the full event dict to each recommendation."""
    event_ids = [i["event_id"] for i in items]
    by_id = {}
    async for e in db.events.find({"event_id": {"$in": event_ids}}, {"_id": 0}):
        by_id[e["event_id"]] = event_to_public(e)
    out = []
    for i in items:
        ev = by_id.get(i["event_id"])
        if ev:
            out.append({"event": ev, "reason": i["reason"]})
    return out


async def _write_cache(user_id: str, items: list[dict]) -> None:
    await db.recommendation_cache.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "items": items,
            "generated_at": utc_now().isoformat(),
            "expires_at": (utc_now() + CACHE_TTL).isoformat(),
        }},
        upsert=True,
    )
