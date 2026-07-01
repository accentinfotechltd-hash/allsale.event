"""Firecrawl + LLM lead enrichment router (Mar 2026 VA-replacement automation).

Covers the full enrichment pipeline WITHOUT hitting Firecrawl / Emergent LLM
in CI — every external call is monkeypatched. Exercises:

  • Regex fast-path: personal email present on the Eventfinda listing →
    stamps `enriched_regex`, 85% confidence.
  • LLM fallback: only a generic info@ email on the listing, the venue's own
    website (discovered from a "Visit website" markdown link) surfaces a
    real bookings contact via the LLM → `enriched_llm` with confidence
    coming from the model.
  • Only generic addresses found anywhere → `enriched_generic_only`,
    40% confidence + warning note.
  • Firecrawl returns nothing → `firecrawl_failed_listing`, no email set.
  • Missing source_url → `no_source_url` short-circuit.
  • Batch endpoint respects `only_placeholder=True` — skips real emails.
  • Both endpoints 403 for non-admin.
  • Endpoints 503 when FIRECRAWL_API_KEY is missing.

Every test seeds + tears down its own lead docs so runs stay hermetic.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402
from routers import lead_enrichment as le  # noqa: E402


ADMIN = {"role": "admin", "user_id": "admin_x"}
ATTENDEE = {"role": "attendee", "user_id": "u_x"}


async def _seed_lead(**overrides):
    lead_id = overrides.pop("lead_id", f"lead_{uuid.uuid4().hex[:10]}")
    doc = {
        "lead_id": lead_id,
        "name": overrides.pop("name", "Test Venue"),
        "email": overrides.pop("email", f"research-needed+{lead_id}@allsale.events"),
        "kind": overrides.pop("kind", "organizer"),
        "source": overrides.pop("source", "eventfinda"),
        "source_url": overrides.pop("source_url", "https://www.eventfinda.co.nz/venue/test"),
        "status": overrides.pop("status", "new"),
        "created_at": utc_now().isoformat(),
        **overrides,
    }
    await db.recruitment_leads.insert_one(doc)
    return doc


async def _cleanup(lead_id):
    await db.recruitment_leads.delete_one({"lead_id": lead_id})


# ---------------------------------------------------------------------------
# Regex fast-path — a personal-looking email is on the Eventfinda listing.
# ---------------------------------------------------------------------------
async def test_regex_fast_path_finds_personal_email(monkeypatch):
    lead = await _seed_lead()
    try:
        # First call = Eventfinda listing; also has the personal email inline.
        listing_md = (
            "# Test Venue\n"
            "Contact us at [jane.smith@testvenue.co.nz](mailto:jane.smith@testvenue.co.nz).\n"
            "Also: info@testvenue.co.nz for general enquiries."
        )
        call_count = {"n": 0}

        async def fake_scrape(url, only_main=True):
            call_count["n"] += 1
            return listing_md

        async def fake_llm(md, name):  # must not be called on the fast path
            raise AssertionError("LLM should not be called when regex finds a personal email")

        monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")
        monkeypatch.setattr(le, "_firecrawl_scrape", fake_scrape)
        monkeypatch.setattr(le, "_llm_extract_contact", fake_llm)

        res = await le.enrich_one(lead["lead_id"], user=ADMIN)
        assert res["ok"] is True
        assert res["enrichment_status"] == "enriched_regex"
        assert res["email"] == "jane.smith@testvenue.co.nz"
        # Personal email path is 85% confident.
        assert res["enrichment_confidence"] == 85
        # Both the personal AND the generic should be recorded for audit.
        assert "info@testvenue.co.nz" in res["all_emails_found"]
        # Only the listing was scraped — no external website found in the markdown.
        assert call_count["n"] == 1

        # DB is updated too.
        after = await db.recruitment_leads.find_one({"lead_id": lead["lead_id"]}, {"_id": 0})
        assert after["email"] == "jane.smith@testvenue.co.nz"
        assert after["enrichment_status"] == "enriched_regex"
    finally:
        await _cleanup(lead["lead_id"])


# ---------------------------------------------------------------------------
# LLM fallback — listing has only info@, venue site linked, LLM finds owner.
# ---------------------------------------------------------------------------
async def test_llm_fallback_scrapes_venue_site_and_extracts_owner(monkeypatch):
    lead = await _seed_lead()
    try:
        listing_md = (
            "# Test Venue\n"
            "General enquiries: [info@testvenue.co.nz](mailto:info@testvenue.co.nz)\n"
            "[Visit website](https://testvenue.co.nz)"
        )
        contact_md = (
            "# Contact Test Venue\n"
            "For bookings, email Sarah Chen, Events Manager, at sarah@testvenue.co.nz.\n"
            "General enquiries: info@testvenue.co.nz\n"
        ) + ("\nPadding text " * 50)  # >200 chars so the contact-page probe accepts it

        scrape_calls = []

        async def fake_scrape(url, only_main=True):
            scrape_calls.append(url)
            if "eventfinda" in url:
                return listing_md
            if "testvenue.co.nz" in url:
                return contact_md
            return None

        async def fake_llm(md, name):
            assert "sarah@testvenue.co.nz" in md, "combined markdown should include contact page"
            return {
                "email": "sarah@testvenue.co.nz",
                "contact_name": "Sarah Chen",
                "contact_role": "Events Manager",
                "confidence": 92,
                "notes": "Explicit contact for bookings",
            }

        monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")
        monkeypatch.setattr(le, "_firecrawl_scrape", fake_scrape)
        monkeypatch.setattr(le, "_llm_extract_contact", fake_llm)

        res = await le.enrich_one(lead["lead_id"], user=ADMIN)
        assert res["enrichment_status"] == "enriched_llm"
        assert res["email"] == "sarah@testvenue.co.nz"
        assert res["contact_name"] == "Sarah Chen"
        assert res["contact_role"] == "Events Manager"
        assert res["enrichment_confidence"] == 92
        assert res["website_url"] == "https://testvenue.co.nz"
        # Listing + at least one contact-page probe.
        assert any("eventfinda" in u for u in scrape_calls)
        assert any("testvenue.co.nz" in u for u in scrape_calls)
    finally:
        await _cleanup(lead["lead_id"])


# ---------------------------------------------------------------------------
# Only generic addresses found — surface but flag confidence 40 + warning.
# ---------------------------------------------------------------------------
async def test_generic_only_email_gets_low_confidence(monkeypatch):
    lead = await _seed_lead()
    try:
        listing_md = "Contact: [info@somesite.com](mailto:info@somesite.com)"

        async def fake_scrape(url, only_main=True):
            return listing_md

        async def fake_llm(md, name):
            return {"email": None, "confidence": 0}  # LLM couldn't do better

        monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")
        monkeypatch.setattr(le, "_firecrawl_scrape", fake_scrape)
        monkeypatch.setattr(le, "_llm_extract_contact", fake_llm)

        res = await le.enrich_one(lead["lead_id"], user=ADMIN)
        assert res["enrichment_status"] == "enriched_generic_only"
        assert res["email"] == "info@somesite.com"
        assert res["enrichment_confidence"] == 40
        assert "generic" in (res["enrichment_notes"] or "").lower()
    finally:
        await _cleanup(lead["lead_id"])


# ---------------------------------------------------------------------------
# Firecrawl returns None → hard failure surfaced cleanly.
# ---------------------------------------------------------------------------
async def test_firecrawl_failure_reports_status(monkeypatch):
    lead = await _seed_lead()
    try:
        async def fake_scrape(url, only_main=True):
            return None

        monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")
        monkeypatch.setattr(le, "_firecrawl_scrape", fake_scrape)

        res = await le.enrich_one(lead["lead_id"], user=ADMIN)
        assert res["enrichment_status"] == "firecrawl_failed_listing"
        assert "email" not in res or not res.get("email")
    finally:
        await _cleanup(lead["lead_id"])


# ---------------------------------------------------------------------------
# Missing source_url → no scrape, clean status.
# ---------------------------------------------------------------------------
async def test_no_source_url_short_circuits(monkeypatch):
    lead = await _seed_lead(source_url=None)
    try:
        called = {"n": 0}

        async def fake_scrape(url, only_main=True):
            called["n"] += 1
            return None

        monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")
        monkeypatch.setattr(le, "_firecrawl_scrape", fake_scrape)

        res = await le.enrich_one(lead["lead_id"], user=ADMIN)
        assert res["enrichment_status"] == "no_source_url"
        assert called["n"] == 0
    finally:
        await _cleanup(lead["lead_id"])


# ---------------------------------------------------------------------------
# Batch endpoint respects only_placeholder — skips real emails.
# ---------------------------------------------------------------------------
async def test_batch_only_placeholder_skips_real_emails(monkeypatch):
    ph_lead = await _seed_lead()  # research-needed+…@allsale.events — placeholder
    real_lead = await _seed_lead(email="already-known@venue.com")
    try:
        listing_md = "Contact: [owner@newvenue.co.nz](mailto:owner@newvenue.co.nz)"

        seen_ids = []

        async def fake_scrape(url, only_main=True):
            return listing_md

        monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")
        monkeypatch.setattr(le, "_firecrawl_scrape", fake_scrape)

        # Wrap _enrich_one_lead to see which leads actually got processed.
        real = le._enrich_one_lead

        async def spy(doc):
            seen_ids.append(doc["lead_id"])
            return await real(doc)

        monkeypatch.setattr(le, "_enrich_one_lead", spy)

        payload = le.EnrichBatchIn(only_placeholder=True, limit=200)
        res = await le.enrich_batch(payload, user=ADMIN)
        # Placeholder lead processed; real-email lead skipped by the query filter.
        assert ph_lead["lead_id"] in seen_ids
        assert real_lead["lead_id"] not in seen_ids
        assert res["processed"] == len(seen_ids)
        assert res["summary"].get("enriched_regex", 0) >= 1
    finally:
        await _cleanup(ph_lead["lead_id"])
        await _cleanup(real_lead["lead_id"])


# ---------------------------------------------------------------------------
# Batch endpoint honours explicit lead_ids and ignores placeholder filter.
# ---------------------------------------------------------------------------
async def test_batch_explicit_lead_ids_ignore_placeholder_flag(monkeypatch):
    lead = await _seed_lead(email="realperson@venue.com")  # real email, NOT a placeholder
    try:
        async def fake_scrape(url, only_main=True):
            return "Contact: [new@venue.com](mailto:new@venue.com)"

        monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")
        monkeypatch.setattr(le, "_firecrawl_scrape", fake_scrape)

        payload = le.EnrichBatchIn(lead_ids=[lead["lead_id"]], only_placeholder=True)
        res = await le.enrich_batch(payload, user=ADMIN)
        # only_placeholder is ignored when lead_ids is set → real-email lead IS processed.
        assert res["processed"] == 1
        assert res["results"][0]["lead_id"] == lead["lead_id"]
    finally:
        await _cleanup(lead["lead_id"])


# ---------------------------------------------------------------------------
# Auth: both endpoints must reject non-admin callers with 403.
# ---------------------------------------------------------------------------
async def test_non_admin_gets_403(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")
    with pytest.raises(HTTPException) as ei:
        await le.enrich_one("does_not_matter", user=ATTENDEE)
    assert ei.value.status_code == 403

    with pytest.raises(HTTPException) as ei2:
        await le.enrich_batch(le.EnrichBatchIn(), user=ATTENDEE)
    assert ei2.value.status_code == 403


# ---------------------------------------------------------------------------
# Missing FIRECRAWL_API_KEY → 503 on both endpoints (admin-caller path).
# ---------------------------------------------------------------------------
async def test_missing_firecrawl_key_returns_503(monkeypatch):
    # Delete the key if it was loaded from .env.
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    with pytest.raises(HTTPException) as ei:
        await le.enrich_one("anything", user=ADMIN)
    assert ei.value.status_code == 503
    assert "FIRECRAWL" in ei.value.detail.upper()

    with pytest.raises(HTTPException) as ei2:
        await le.enrich_batch(le.EnrichBatchIn(), user=ADMIN)
    assert ei2.value.status_code == 503


# ---------------------------------------------------------------------------
# Helper unit tests — regex + website-link extraction, no I/O.
# ---------------------------------------------------------------------------
def test_clean_email_rejects_placeholders():
    assert le._clean_email("Jane@Example.com  ") is None  # example.com blocklist
    assert le._clean_email("research-needed+foo@allsale.events") is None
    assert le._clean_email("owner@venue.co.nz") == "owner@venue.co.nz"


def test_is_generic_email():
    assert le._is_generic_email("info@foo.com") is True
    assert le._is_generic_email("hello@foo.com") is True
    assert le._is_generic_email("jane@foo.com") is False


def test_extract_website_prefers_explicit_website_link():
    md = (
        "Some prose.\n"
        "[Visit website](https://testvenue.co.nz)\n"
        "[Facebook](https://facebook.com/testvenue)\n"
    )
    url = le._extract_website_from_markdown(md, "https://www.eventfinda.co.nz/venue/test")
    assert url == "https://testvenue.co.nz"


def test_extract_website_strips_markdown_title_attribute():
    # Real Firecrawl output — link with a title tooltip after the URL.
    md = '[Website](https://stonehenge-aotearoa.nz/ "Stonehenge Aotearoa")\n'
    url = le._extract_website_from_markdown(md, "https://www.eventfinda.co.nz/venue/stonehenge")
    assert url == "https://stonehenge-aotearoa.nz/"


def test_clean_url_helper():
    assert le._clean_url('https://example.com/ "Title"') == "https://example.com/"
    assert le._clean_url("https://example.com/") == "https://example.com/"
    assert le._clean_url("https://example.com,") == "https://example.com"
    assert le._clean_url("  https://example.com  ") == "https://example.com"


def test_extract_website_skips_socials_and_source_host():
    md = (
        "[Instagram](https://instagram.com/venue)\n"
        "[Facebook](https://facebook.com/venue)\n"
        "[Eventfinda listing](https://www.eventfinda.co.nz/other)\n"
        "[Book online](https://realvenue.co.nz/book)\n"
    )
    url = le._extract_website_from_markdown(md, "https://www.eventfinda.co.nz/venue/test")
    assert url == "https://realvenue.co.nz/book"


def test_extract_emails_dedupes_and_cleans():
    md = "Contact [jane@x.com](mailto:jane@x.com) or jane@x.com or bob@x.com "
    emails = le._extract_emails_from_markdown(md)
    assert emails == ["jane@x.com", "bob@x.com"]
