"""Recruitment lead enrichment via Firecrawl + LLM extraction.

Workflow per lead:
  1. Scrape the source_url (Eventfinda listing) via Firecrawl → markdown.
  2. Regex-extract emails + detect the venue's own website URL from the page.
  3. If a website URL was found, scrape THAT page's contact section → markdown.
  4. Regex sweep on the combined markdown for `mailto:` + `foo@bar.com`.
  5. If regex found nothing OR only found generic addresses (info@, admin@),
     fall back to an LLM prompt (Claude Sonnet 4.5 via Emergent LLM key) that
     picks the best "book-a-show" contact + returns owner/manager name +
     confidence score.
  6. Stamp the enriched fields on the lead doc. Never auto-send the flyer —
     admin reviews then hits the existing Send flyer button.

The whole enrichment is idempotent: re-running on an already-enriched lead
overwrites with fresh data.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import db, get_current_user, utc_now

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/recruitment-leads", tags=["recruitment-leads-enrich"])


# --- Firecrawl SDK (lazy import so a missing env doesn't crash boot) --------
try:
    from firecrawl import Firecrawl as _FirecrawlApp  # type: ignore
    _FIRECRAWL_AVAILABLE = True
except ImportError:  # pragma: no cover
    try:
        from firecrawl import FirecrawlApp as _FirecrawlApp  # type: ignore
        _FIRECRAWL_AVAILABLE = True
    except ImportError:
        _FirecrawlApp = None
        _FIRECRAWL_AVAILABLE = False


# --- LLM chain (fallback for tricky pages) ---------------------------------
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
    _LLM_AVAILABLE = True
except ImportError:  # pragma: no cover
    LlmChat = None  # type: ignore
    UserMessage = None  # type: ignore
    _LLM_AVAILABLE = False


# --- Regex patterns --------------------------------------------------------
_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])"
    r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
    r"(?![A-Za-z0-9._%+-])"
)
_MAILTO_RE = re.compile(r"mailto:([^\s\"'<>?]+)", re.IGNORECASE)
_WEBSITE_LINK_RE = re.compile(
    r"\[(?:visit\s+website|official\s+website|website|our\s+website)\]"
    r"\(([^)]+)\)",
    re.IGNORECASE,
)
_ANY_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")

# Skip Eventfinda-internal + support/tracking domains.
_SKIP_DOMAINS = {
    "eventfinda.co.nz", "eventfinda.com.au", "eventfinda.com",
    "facebook.com", "twitter.com", "x.com", "instagram.com",
    "youtube.com", "linkedin.com", "tiktok.com",
    "google.com", "maps.google.com",
    "allsale.events",
}
# Emails that don't identify a specific owner — flag as "generic".
_GENERIC_LOCAL_PARTS = {
    "info", "hello", "contact", "admin", "support", "enquiries",
    "reception", "office", "sales", "team",
}


def _clean_email(raw: str) -> Optional[str]:
    e = raw.strip().strip(".,;:()<>\"'").lower()
    # Reject placeholder / obviously-wrong strings.
    if not e or "@" not in e or e.endswith("."):
        return None
    if e.startswith("research-needed"):
        return None
    if e.endswith("@allsale.events") or e.endswith("@example.com") or e.endswith("@test.com"):
        return None
    return e


def _is_generic_email(email: str) -> bool:
    local = email.split("@", 1)[0]
    return local in _GENERIC_LOCAL_PARTS


def _extract_website_from_markdown(md: str, source_url: str) -> Optional[str]:
    """Find the venue's own website in Firecrawl markdown output.

    Priority: (1) an explicit "Visit website" / "Official website" link,
    (2) any external link that's not on _SKIP_DOMAINS and shares no words
    with the source_url host.
    """
    m = _WEBSITE_LINK_RE.search(md)
    if m:
        return m.group(1).strip()

    source_host = urlparse(source_url).netloc.lower()
    for label, href in _ANY_LINK_RE.findall(md):
        try:
            host = urlparse(href).netloc.lower()
        except Exception:
            continue
        if not host or host == source_host:
            continue
        if any(host == d or host.endswith("." + d) for d in _SKIP_DOMAINS):
            continue
        # Ignore obvious CDNs / assets.
        if host.startswith(("cdn.", "static.", "assets.", "img.")):
            continue
        return href
    return None


def _extract_emails_from_markdown(md: str) -> List[str]:
    """Return de-duped, cleaned emails from a page markdown blob."""
    found: List[str] = []
    for raw in _MAILTO_RE.findall(md):
        c = _clean_email(raw)
        if c and c not in found:
            found.append(c)
    for raw in _EMAIL_RE.findall(md):
        c = _clean_email(raw)
        if c and c not in found:
            found.append(c)
    return found


async def _firecrawl_scrape(url: str, only_main: bool = True) -> Optional[str]:
    """Return markdown for a URL, or None on any failure. Never raises."""
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key or not _FIRECRAWL_AVAILABLE:
        return None
    try:
        client = _FirecrawlApp(api_key=api_key)
        # Firecrawl SDK is sync — offload to a thread so we don't block the loop.
        def _run() -> Optional[str]:
            try:
                # SDK 4.x API — scrape_url takes formats as kwargs
                res = client.scrape_url(url, formats=["markdown"], only_main_content=only_main)
                # Result shape: object with .markdown OR dict with "markdown"
                if hasattr(res, "markdown"):
                    return getattr(res, "markdown") or ""
                if isinstance(res, dict):
                    return (
                        res.get("markdown")
                        or (res.get("data") or {}).get("markdown")
                        or ""
                    )
                return ""
            except TypeError:
                # Older SDK (< 4.x) uses `params={"formats": [...]}`
                res = client.scrape_url(url, params={"formats": ["markdown"], "onlyMainContent": only_main})
                if isinstance(res, dict):
                    return (
                        res.get("markdown")
                        or (res.get("data") or {}).get("markdown")
                        or ""
                    )
                return ""
        return await asyncio.to_thread(_run)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[enrich] firecrawl failed for %s: %s", url, str(exc)[:200])
        return None


async def _llm_extract_contact(page_markdown: str, venue_name: str) -> Dict[str, Any]:
    """Ask Claude Sonnet to extract the best booking contact. Returns dict
    with keys: email, contact_name, contact_role, confidence, notes. If the
    LLM is unavailable or fails, returns an empty dict.
    """
    if not _LLM_AVAILABLE:
        return {}
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return {}
    system = (
        "You extract a single best 'bookings inquiry' email address from a "
        "venue's web page. Return ONLY a JSON object matching this schema:\n"
        '{"email": string|null, "contact_name": string|null, '
        '"contact_role": string|null, "confidence": int 0-100, "notes": string}\n'
        "- confidence 90-100: mailto link or explicit 'Contact us' section\n"
        "- confidence 60-89: email in body text near a name/role\n"
        "- confidence 30-59: only a generic info@ / hello@ address found\n"
        "- confidence 0-29: nothing usable — return email=null\n"
        "Never invent an email. If nothing plausible is on the page, return null."
    )
    user = (
        f"Venue: {venue_name}\n\n"
        f"Contact page markdown (may be trimmed):\n---\n{page_markdown[:6000]}\n---\n\n"
        "Return only the JSON object, nothing else."
    )
    try:
        import uuid as _uuid
        chat = LlmChat(
            api_key=key,
            session_id=f"lead_enrich_{_uuid.uuid4().hex[:10]}",
            system_message=system,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        raw = await chat.send_message(UserMessage(text=user))
        text = str(raw or "").strip()
        # Strip common markdown code fences the LLM sometimes adds.
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```\s*$", "", text)
        import json as _json
        parsed = _json.loads(text)
        if not isinstance(parsed, dict):
            return {}
        # Sanitise: clean the email, cap confidence.
        email = _clean_email(parsed.get("email") or "") if parsed.get("email") else None
        return {
            "email": email,
            "contact_name": (parsed.get("contact_name") or "").strip() or None,
            "contact_role": (parsed.get("contact_role") or "").strip() or None,
            "confidence": max(0, min(100, int(parsed.get("confidence") or 0))),
            "notes": (parsed.get("notes") or "").strip()[:200],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("[enrich] LLM extract failed: %s", str(exc)[:200])
        return {}


async def _enrich_one_lead(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Return the fields to $set on the lead doc. Includes an
    `enrichment_status` telling the caller what happened."""
    lead_id = lead["lead_id"]
    source_url = lead.get("source_url")
    if not source_url:
        return {
            "enrichment_status": "no_source_url",
            "enrichment_attempted_at": utc_now().isoformat(),
        }

    # Step 1 — Scrape the source URL (Eventfinda listing).
    listing_md = await _firecrawl_scrape(source_url, only_main=True)
    if not listing_md:
        return {
            "enrichment_status": "firecrawl_failed_listing",
            "enrichment_attempted_at": utc_now().isoformat(),
        }

    # Step 2 — Find the venue's own website inside the listing.
    website_url = _extract_website_from_markdown(listing_md, source_url)

    # Step 3 — If we found a website, scrape its contact page too.
    combined_md = listing_md
    if website_url:
        # Try /contact first, then the root; whichever returns content.
        contact_md = None
        for path in ("/contact", "/contact-us", "/contacts", ""):
            candidate = urljoin(website_url, path) if path else website_url
            contact_md = await _firecrawl_scrape(candidate, only_main=True)
            if contact_md and len(contact_md.strip()) > 200:
                break
        if contact_md:
            combined_md = listing_md + "\n\n---\n\n" + contact_md

    # Step 4 — Regex sweep.
    regex_emails = _extract_emails_from_markdown(combined_md)
    non_generic = [e for e in regex_emails if not _is_generic_email(e)]

    update: Dict[str, Any] = {
        "website_url": website_url,
        "all_emails_found": regex_emails,
        "enrichment_source": "firecrawl",
        "enrichment_attempted_at": utc_now().isoformat(),
    }

    # Fast path: found a personal (non-generic) email via regex.
    if non_generic:
        chosen = non_generic[0]
        update.update({
            "email": chosen,
            "enrichment_confidence": 85,
            "enrichment_status": "enriched_regex",
        })
        return update

    # Step 5 — LLM fallback (uses the venue site's markdown if available,
    # else the Eventfinda listing).
    llm_data = await _llm_extract_contact(combined_md, lead.get("name") or source_url)
    if llm_data.get("email"):
        update.update({
            "email": llm_data["email"],
            "contact_name": llm_data.get("contact_name"),
            "contact_role": llm_data.get("contact_role"),
            "enrichment_confidence": int(llm_data.get("confidence") or 50),
            "enrichment_notes": llm_data.get("notes"),
            "enrichment_status": "enriched_llm",
        })
        return update

    # Nothing usable — but we DID find a generic email, so surface it as a fallback.
    if regex_emails:
        update.update({
            "email": regex_emails[0],
            "enrichment_confidence": 40,
            "enrichment_notes": "Only a generic address was found — review before sending.",
            "enrichment_status": "enriched_generic_only",
        })
        return update

    # Nothing found at all.
    update.update({
        "enrichment_confidence": 0,
        "enrichment_status": "no_email_found",
        "enrichment_notes": (
            "No email on listing or venue website. Try manual research."
            if website_url else
            "No linked website on the Eventfinda listing. Try manual research."
        ),
    })
    return update


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------
def _admin_only(user: Dict[str, Any]) -> None:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")


class EnrichBatchIn(BaseModel):
    lead_ids: Optional[List[str]] = None   # None → enrich all "new" placeholder leads
    limit: int = 50                         # safety cap per call
    only_placeholder: bool = True           # skip already-real emails


@router.post("/{lead_id}/enrich")
async def enrich_one(lead_id: str, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    _admin_only(user)
    if not os.environ.get("FIRECRAWL_API_KEY"):
        raise HTTPException(status_code=503, detail="FIRECRAWL_API_KEY not configured")

    lead = await db.recruitment_leads.find_one({"lead_id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    update = await _enrich_one_lead(lead)
    await db.recruitment_leads.update_one(
        {"lead_id": lead_id},
        {"$set": {**update, "updated_at": utc_now().isoformat()}},
    )
    return {"ok": True, "lead_id": lead_id, **update}


@router.post("/enrich-batch")
async def enrich_batch(payload: EnrichBatchIn, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Bulk-enrich up to `limit` leads. Runs 4 lead pipelines concurrently to
    stay within Firecrawl's default 5 req/s budget."""
    _admin_only(user)
    if not os.environ.get("FIRECRAWL_API_KEY"):
        raise HTTPException(status_code=503, detail="FIRECRAWL_API_KEY not configured")

    # Build the target list.
    query: Dict[str, Any] = {}
    if payload.lead_ids:
        query["lead_id"] = {"$in": payload.lead_ids}
    else:
        query["status"] = "new"
        if payload.only_placeholder:
            query["email"] = {"$regex": "^research-needed"}
    cur = db.recruitment_leads.find(query, {"_id": 0}).limit(max(1, min(payload.limit, 200)))
    leads = [doc async for doc in cur]
    if not leads:
        return {"ok": True, "processed": 0, "results": [], "message": "No matching leads."}

    sem = asyncio.Semaphore(4)  # cap concurrency for Firecrawl

    async def _wrap(l: Dict[str, Any]) -> Dict[str, Any]:
        async with sem:
            up = await _enrich_one_lead(l)
            await db.recruitment_leads.update_one(
                {"lead_id": l["lead_id"]},
                {"$set": {**up, "updated_at": utc_now().isoformat()}},
            )
            return {"lead_id": l["lead_id"], "name": l.get("name"), **up}

    results = await asyncio.gather(*[_wrap(l) for l in leads], return_exceptions=False)

    # Summary counts for the toast on the UI side.
    summary: Dict[str, int] = {}
    for r in results:
        s = r.get("enrichment_status") or "unknown"
        summary[s] = summary.get(s, 0) + 1

    return {"ok": True, "processed": len(results), "summary": summary, "results": results}
