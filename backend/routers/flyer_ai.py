"""AI flyer text generator.

Auto-generates a punchy 3-line text overlay (headline, tagline, CTA) for an
event's social flyer using the Emergent LLM Key. Organizers + admins of the
event can call it. The frontend then renders the lines on the flyer canvas
and lets the user fine-tune before downloading.

Robustness strategy: tries Gemini first (best copywriting quality), falls
back to OpenAI gpt-5.2 on auth/quota errors, and finally falls back to a
hand-crafted template based on the event title so the button never returns
a hard failure to the organizer.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from emergentintegrations.llm.chat import LlmChat, UserMessage

from core import db, get_current_user

logger = logging.getLogger("aura.flyer_ai")
router = APIRouter(tags=["flyer-ai"])


SYSTEM_PROMPT_TEMPLATE = """You are a senior copywriter writing 3-line headlines for
social media event flyers (Instagram square/story/landscape).

OUTPUT STRICT JSON ONLY — no prose, no markdown fences, no commentary.

Schema:
{{
  "headline": str,   // PUNCHY 3-6 words. ALL CAPS optional. No emojis. No quotes. The hook.
  "tagline":  str,   // ONE short sentence (max 12 words) describing the vibe / who it's for.
  "cta":      str    // 2-4 words. Action verb. e.g. "BOOK YOUR SEAT", "GRAB TICKETS", "LIMITED ENTRY"
}}

Rules:
- DO NOT restate the event date, venue or city — the AI text sits next to that info
  in the design.
- DO NOT use clichés like "Don't miss out", "An evening to remember".
- Headline should feel custom to the genre (music, sport, comedy, conference, etc.).
- Match the energy of the title. Concert = electric. Conference = sharp.
- If the title is in Hindi/Gujarati/other script, write English copy that complements it (do not translate).
- ASCII only. No smart quotes, no em-dashes — use regular hyphens.

STYLE DIRECTION: {style_brief}
"""

STYLE_BRIEFS = {
    "punchy": (
        "PUNCHY — short, impactful, ALL-CAPS-friendly. Think rock concert poster, "
        "sports billboard, hype announcement. Use power verbs and visceral imagery. "
        "Headline must feel like a chant. CTA is a command (e.g. 'GRAB TICKETS', 'LOCK IT IN')."
    ),
    "elegant": (
        "ELEGANT — refined, editorial, restrained. Think Vogue cover, gala invitation, "
        "boutique jazz night. Use sophisticated vocabulary, mixed case (Title Case for headline), "
        "and quiet confidence. CTA is gracious (e.g. 'Reserve Your Seat', 'Save the Date')."
    ),
    "mysterious": (
        "MYSTERIOUS — intriguing, suggestive, slightly cryptic. Think indie film teaser, "
        "underground rave, immersive theatre. Use evocative imagery, sentence fragments, "
        "and leave something unsaid. CTA hints at scarcity (e.g. 'Step Inside', 'If You Know')."
    ),
}


def _system_prompt(style: str) -> str:
    """Build the system prompt for the requested style. Falls back to a
    neutral brief if the style id is unknown (so frontend can add new styles
    later without backend changes)."""
    brief = STYLE_BRIEFS.get(
        style,
        "Default house style — confident, modern, audience-aware. Avoid over-doing any one register.",
    )
    return SYSTEM_PROMPT_TEMPLATE.format(style_brief=brief)


def _strip_json(s: str) -> str:
    """Drop ``` fences and leading prose so json.loads can parse."""
    s = re.sub(r"^```(?:json)?", "", s.strip(), flags=re.I).strip()
    s = re.sub(r"```$", "", s).strip()
    # Pull out the first {...} block if there's still surrounding text.
    m = re.search(r"\{[\s\S]*\}", s)
    return m.group(0) if m else s


@router.post("/events/{event_id}/flyer/generate-text")
async def generate_flyer_text(
    event_id: str,
    style: str = "default",
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Generate flyer text. Optional `?style=punchy|elegant|mysterious|default`
    so the "Surprise me" frontend button can rotate through preset voices
    on each click without restating the system prompt server-side.
    """
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

    # Try a chain of models so a transient outage on one provider doesn't
    # break the feature. Each candidate is (provider, model).
    MODEL_CHAIN = [
        ("gemini", "gemini-2.5-flash"),  # primary: fast + cheap, great for copy
        ("gemini", "gemini-2.5-pro"),    # quality fallback
        ("openai", "gpt-5.2"),           # final fallback if Google is down
    ]

    raw = None
    last_err: Exception | None = None
    sys_prompt = _system_prompt(style)
    for provider, model in MODEL_CHAIN:
        try:
            chat = LlmChat(
                api_key=key,
                session_id=f"flyer_text_{uuid.uuid4().hex[:10]}",
                system_message=sys_prompt,
            ).with_model(provider, model)
            raw = await chat.send_message(UserMessage(text=user_text))
            break
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            logger.warning("[flyer-ai] %s/%s failed: %s", provider, model, str(exc)[:200])
            # Authentication failures will hit every model identically (we
            # share one Emergent LLM key) — don't burn 3× latency proving it.
            # emergentintegrations wraps provider errors so the type name and
            # substrings vary; check broadly across the wrapped message too.
            exc_str = (str(exc) + " " + type(exc).__name__).lower()
            if any(s in exc_str for s in (
                "authenticationerror", "invalid api key", "incorrect api key",
                "unauthorized", "invalid_api_key",
            )):
                logger.error("[flyer-ai] auth error — short-circuiting model chain")
                break
            continue

    if raw is None:
        # All models failed — return a graceful template instead of a 500 so
        # the organizer still gets something useful on screen. Surface the
        # underlying error in logs only, not back to the buyer-facing UI.
        logger.error("[flyer-ai] all models failed for event %s: %s", event_id, last_err)
        title = (event.get("title") or "LIVE TONIGHT").upper()[:60]
        fallback_taglines = [
            "An unmissable night you'll remember forever.",
            "Doors open soon — secure your spot now.",
            "Limited tickets. Big energy. Don't miss it.",
        ]
        return {
            "headline": title,
            "tagline": fallback_taglines[hash(event_id) % len(fallback_taglines)],
            "cta": "BOOK NOW",
            "ai_fallback": True,
            "style": style,
        }

    try:
        parsed = json.loads(_strip_json(raw if isinstance(raw, str) else str(raw)))
    except Exception as exc:
        logger.error("[flyer-ai] parse failed: %s | raw=%s", exc, str(raw)[:200])
        raise HTTPException(status_code=502, detail="The AI returned unexpected output — please try again") from exc

    # Clean + size-limit the 3 fields so a misbehaving model can't break our layout.
    headline = str(parsed.get("headline") or "").strip()[:60]
    tagline = str(parsed.get("tagline") or "").strip()[:140]
    cta = str(parsed.get("cta") or "").strip()[:30]

    if not headline:
        # Last-ditch fallback so the button never returns an empty result.
        headline = (event.get("title") or "LIVE TONIGHT").upper()[:60]
    if not cta:
        cta = "GRAB TICKETS"

    return {"headline": headline, "tagline": tagline, "cta": cta, "style": style}
