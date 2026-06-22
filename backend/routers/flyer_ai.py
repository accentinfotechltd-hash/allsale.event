"""AI flyer text generator.

Auto-generates a punchy 3-line text overlay (headline, tagline, CTA) for an
event's social flyer using the Emergent LLM Key (Gemini). Organizers + admins
of the event can call it. The frontend then renders the lines on the flyer
canvas and lets the user fine-tune before downloading.

Why this exists: most organizers upload a stock photo as the cover image
(not a fully-designed poster). On the social flyer, those photos look bland
without a headline. Asking the AI to write a 4-6 word punch + a one-line
tagline keeps the design consistent and saves the organizer 10 minutes per
event.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from emergentintegrations.llm.chat import LlmChat, UserMessage

from core import db, get_current_user

router = APIRouter(tags=["flyer-ai"])


SYSTEM_PROMPT = """You are a senior copywriter writing 3-line headlines for
social media event flyers (Instagram square/story/landscape).

OUTPUT STRICT JSON ONLY — no prose, no markdown fences, no commentary.

Schema:
{
  "headline": str,   // PUNCHY 3-6 words. ALL CAPS optional. No emojis. No quotes. The hook.
  "tagline":  str,   // ONE short sentence (max 12 words) describing the vibe / who it's for.
  "cta":      str    // 2-4 words. Action verb. e.g. "BOOK YOUR SEAT", "GRAB TICKETS", "LIMITED ENTRY"
}

Rules:
- DO NOT restate the event date, venue or city — the AI text sits next to that info
  in the design.
- DO NOT use clichés like "Don't miss out", "An evening to remember".
- Headline should feel custom to the genre (music, sport, comedy, conference, etc.).
- Match the energy of the title. Concert = electric. Conference = sharp.
- If the title is in Hindi/Gujarati/other script, write English copy that complements it (do not translate).
- ASCII only. No smart quotes, no em-dashes — use regular hyphens.
"""


def _strip_json(s: str) -> str:
    """Drop ``` fences and leading prose so json.loads can parse."""
    s = re.sub(r"^```(?:json)?", "", s.strip(), flags=re.I).strip()
    s = re.sub(r"```$", "", s).strip()
    # Pull out the first {...} block if there's still surrounding text.
    m = re.search(r"\{[\s\S]*\}", s)
    return m.group(0) if m else s


@router.post("/events/{event_id}/flyer/generate-text")
async def generate_flyer_text(
    event_id: str, user: dict = Depends(get_current_user)
) -> Dict[str, str]:
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    # Authorize: organizer of the event OR admin.
    is_admin = user.get("role") == "admin"
    is_owner = event.get("organizer_id") == user.get("user_id") or event.get(
        "on_behalf_of_organizer_id"
    ) == user.get("user_id")
    if not (is_admin or is_owner):
        raise HTTPException(status_code=403, detail="Only the event organizer can generate flyer text")

    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise HTTPException(status_code=500, detail="LLM key not configured")

    # Strip HTML from description if rich text — feeds clean context to the model.
    raw_desc = (event.get("description") or "").strip()
    desc = re.sub(r"<[^>]+>", " ", raw_desc)
    desc = re.sub(r"\s+", " ", desc)[:900]

    user_text = (
        f"EVENT TITLE: {event.get('title', '')}\n"
        f"CATEGORY/TAGS: {', '.join(event.get('tags') or []) or 'live event'}\n"
        f"DESCRIPTION: {desc or '(none provided)'}\n\n"
        "Write the 3 lines now. Output the JSON only."
    )

    try:
        chat = LlmChat(
            api_key=key,
            session_id=f"flyer_text_{uuid.uuid4().hex[:10]}",
            system_message=SYSTEM_PROMPT,
        ).with_model("gemini", "gemini-2.5-pro")
        raw = await chat.send_message(UserMessage(text=user_text))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI failed: {exc}") from exc

    try:
        parsed = json.loads(_strip_json(raw if isinstance(raw, str) else str(raw)))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not parse AI output: {exc}") from exc

    # Clean + size-limit the 3 fields so a misbehaving model can't break our layout.
    headline = str(parsed.get("headline") or "").strip()[:60]
    tagline = str(parsed.get("tagline") or "").strip()[:140]
    cta = str(parsed.get("cta") or "").strip()[:30]

    if not headline:
        # Last-ditch fallback so the button never returns an empty result.
        headline = (event.get("title") or "LIVE TONIGHT").upper()[:60]
    if not cta:
        cta = "GRAB TICKETS"

    return {"headline": headline, "tagline": tagline, "cta": cta}
