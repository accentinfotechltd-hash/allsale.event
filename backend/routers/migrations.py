"""Event-migration helpers — pull a public event listing from a competitor's
site and return a normalized payload the frontend can drop into the
create-event form.

Currently supports: Eventbrite (.com / .co.nz). The flow is read-only —
we never store the source URL on the event, never copy buyer data, and
never call any private API. We just parse the public JSON-LD structured
data that Eventbrite itself publishes for Google rich snippets.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import get_current_user

router = APIRouter(prefix="/migrate", tags=["migrate"])

# Generous timeout because Eventbrite pages are ~200KB.
_FETCH_TIMEOUT = 15.0
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
# Hard limit on payload size — protects us from arbitrary remote servers.
_MAX_BYTES = 5 * 1024 * 1024


class _EventbriteIn(BaseModel):
    url: str


def _validate_url(raw: str) -> str:
    """Validate the URL is a real Eventbrite event URL. Anything else is
    rejected — this endpoint is not a general-purpose web fetcher.
    """
    try:
        parsed = urllib.parse.urlparse(raw.strip())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid URL: {exc}") from exc
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="URL must start with http(s)://")
    host = (parsed.hostname or "").lower()
    if not host.endswith("eventbrite.com") and not host.endswith("eventbrite.co.nz"):
        raise HTTPException(status_code=400, detail="Only Eventbrite event URLs are supported")
    # Eventbrite event URLs use the path `/e/SLUG-tickets-NUMBER` or `/e/NUMBER`.
    if "/e/" not in parsed.path:
        raise HTTPException(
            status_code=400,
            detail="That doesn't look like an event URL. Use the format eventbrite.com/e/your-event-tickets-12345",
        )
    return raw.strip()


def _coerce_list(v: Any) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def _extract_event_from_jsonld(html: str) -> Optional[dict]:
    """Find the `Event` JSON-LD block on the page and return it."""
    soup = BeautifulSoup(html, "lxml")
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.string or "{}")
        except Exception:
            continue
        for item in _coerce_list(payload):
            if isinstance(item, dict) and item.get("@type") == "Event":
                return item
    return None


def _normalize_offer(offer: dict, default_currency: str) -> Optional[dict]:
    """Convert one schema.org Offer object into an Allsale tier draft.

    Eventbrite emits offers with name, price, priceCurrency, availability.
    Skip free/RSVP placeholders and donation tiers (we'll surface those
    separately in a future iteration).
    """
    name = (offer.get("name") or "").strip()
    if not name or name.lower() in {"free", "rsvp", "donation"}:
        return None
    raw_price = offer.get("price")
    try:
        price = float(raw_price)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    return {
        "name": name[:60],
        "price": round(price, 2),
        "currency": (offer.get("priceCurrency") or default_currency or "NZD").upper(),
        "available": "SoldOut" not in str(offer.get("availability", "")),
    }


def _normalize_event(raw: dict) -> dict:
    """Map Eventbrite's JSON-LD Event object to the Allsale create-event
    payload. Drop fields we don't trust (we never copy organizer info /
    descriptions verbatim without showing them to the user)."""
    name = (raw.get("name") or "").strip()
    description = (raw.get("description") or "").strip()

    # Date — schema.org uses ISO8601 with timezone. Keep both start and end.
    start_date = raw.get("startDate")
    end_date = raw.get("endDate")

    # Venue
    loc = raw.get("location") or {}
    if isinstance(loc, list):
        loc = next((x for x in loc if isinstance(x, dict)), {})
    venue_name = (loc.get("name") or "").strip() if isinstance(loc, dict) else ""
    addr = loc.get("address") if isinstance(loc, dict) else None
    venue_address = ""
    venue_city = ""
    venue_country = ""
    if isinstance(addr, dict):
        parts = [addr.get("streetAddress"), addr.get("addressLocality"),
                 addr.get("postalCode"), addr.get("addressRegion")]
        venue_address = ", ".join(p for p in parts if p)
        venue_city = (addr.get("addressLocality") or "").strip()
        venue_country = (addr.get("addressCountry") or "").strip()
    elif isinstance(addr, str):
        venue_address = addr

    # Image
    image = raw.get("image")
    if isinstance(image, list):
        image = next((x for x in image if isinstance(x, str)), "")
    image_url = (image or "").strip()

    # Organizer (display only — we won't recreate it)
    org = raw.get("organizer") or {}
    if isinstance(org, list):
        org = next((x for x in org if isinstance(x, dict)), {})
    organizer_name = (org.get("name") or "").strip() if isinstance(org, dict) else ""

    # Currency — pick from offers if present, otherwise guess from country.
    offers = _coerce_list(raw.get("offers"))
    default_currency = ""
    for o in offers:
        if isinstance(o, dict) and o.get("priceCurrency"):
            default_currency = o["priceCurrency"].upper()
            break
    if not default_currency:
        default_currency = "NZD" if venue_country.upper() in ("NZ", "NEW ZEALAND") else "NZD"

    # Tiers
    tiers = []
    for o in offers:
        if isinstance(o, dict):
            t = _normalize_offer(o, default_currency)
            if t:
                tiers.append(t)

    return {
        "title": name[:200],
        "description": description[:2000],
        "start_date": start_date,
        "end_date": end_date,
        "venue_name": venue_name[:120],
        "venue_address": venue_address[:200],
        "city": venue_city[:80],
        "country": venue_country[:40],
        "image_url": image_url,
        "currency": default_currency,
        "tiers": tiers,
        "source_organizer_name": organizer_name[:120],
    }


@router.post("/eventbrite")
async def migrate_from_eventbrite(payload: _EventbriteIn, user: dict = Depends(get_current_user)):
    """Pull a public Eventbrite event listing and return the Allsale-shaped
    draft payload. Requires login — only organisers actively migrating
    their own listings should use this.
    """
    # Allow any logged-in user role to call this (attendees may also be
    # organisers-to-be who haven't upgraded yet). We never need elevated
    # permissions to read public HTML.
    if not user:
        raise HTTPException(status_code=401, detail="Login required")

    url = _validate_url(payload.url)

    try:
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": _UA})
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Couldn't reach Eventbrite: {exc}") from exc

    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="Eventbrite returned 404 — the event link looks dead.")
    if r.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Eventbrite returned HTTP {r.status_code}. Try again later or paste a different link.",
        )

    body = r.text
    if len(body.encode("utf-8", errors="ignore")) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="Page is too large to import")

    raw = _extract_event_from_jsonld(body)
    if not raw:
        # Fallback for cases where Eventbrite changed their markup or the
        # event renders client-side. We can still get the title from <title>
        # but ticket tiers are gone. Better to error so the user knows.
        soup = BeautifulSoup(body, "lxml")
        title_el = soup.find("title")
        fallback_title = (title_el.get_text() if title_el else "").split("|")[0].strip()
        if not fallback_title:
            raise HTTPException(
                status_code=422,
                detail="Couldn't read this Eventbrite event. The link may be private or the page format changed.",
            )
        return {
            "title": fallback_title,
            "description": "",
            "start_date": None,
            "end_date": None,
            "venue_name": "",
            "venue_address": "",
            "city": "",
            "country": "",
            "image_url": "",
            "currency": "NZD",
            "tiers": [],
            "source_organizer_name": "",
            "_warning": "Only the title could be imported — Eventbrite didn't expose structured data on this page.",
        }

    draft = _normalize_event(raw)
    draft["_source"] = "eventbrite"
    draft["_source_url"] = url
    return draft
