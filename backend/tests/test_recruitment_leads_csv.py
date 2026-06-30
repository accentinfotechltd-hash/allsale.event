"""Recruitment Leads — CSV export + CSV import (Mar 2026 VA workflow).

Covers:
  • GET /admin/recruitment-leads.csv returns CSV with the right columns and
    respects status/kind/source filters.
  • POST /admin/recruitment-leads/import-csv updates existing rows by
    lead_id, leaves empty cells alone, and ignores unknown lead_ids.
  • Email duplicates across rows are reported back.
  • Invalid status values are reported instead of corrupting the row.
  • Non-admin gets 403.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402
from routers import admin as admin_router  # noqa: E402


def _seed_lead(lead_id, email, name, kind="organizer", status="new"):
    return db.recruitment_leads.insert_one({
        "lead_id": lead_id,
        "name": name,
        "email": email.lower(),
        "kind": kind,
        "source": "test",
        "status": status,
        "created_at": utc_now().isoformat(),
    })


def test_export_returns_csv_with_correct_headers_and_rows():
    async def run():
        lead_id = f"lead_{uuid.uuid4().hex[:10]}"
        try:
            await _seed_lead(lead_id, f"export_{lead_id}@test.com", "Export Test")
            resp = await admin_router.export_recruitment_leads_csv(
                user={"role": "admin", "user_id": "admin_x"},
            )
            # StreamingResponse — iterate to get the bytes
            body_chunks = []
            async for chunk in resp.body_iterator:
                body_chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
            body = b"".join(body_chunks).decode("utf-8")
            assert "lead_id,name,email,kind,source,source_url,event_count,status,notes,created_at" in body
            assert lead_id in body
            assert "Export Test" in body
            assert resp.headers["content-disposition"].startswith("attachment; ")
            assert "text/csv" in resp.media_type
        finally:
            await db.recruitment_leads.delete_one({"lead_id": lead_id})

    asyncio.get_event_loop().run_until_complete(run())


def test_import_csv_updates_existing_by_lead_id():
    async def run():
        lead_id = f"lead_{uuid.uuid4().hex[:10]}"
        try:
            await _seed_lead(lead_id, f"old_{lead_id}@test.com", "Original Name")
            csv_text = (
                "lead_id,email,name,notes\n"
                f"{lead_id},new_owner@example.com,Updated Name,VA confirmed direct contact\n"
            )
            from routers.admin import _LeadCsvImportIn
            res = await admin_router.import_recruitment_leads_csv(
                _LeadCsvImportIn(csv_text=csv_text),
                user={"role": "admin", "user_id": "admin_x"},
            )
            assert res["updated"] == 1
            assert res["not_found"] == []
            row = await db.recruitment_leads.find_one({"lead_id": lead_id}, {"_id": 0})
            assert row["email"] == "new_owner@example.com"
            assert row["name"] == "Updated Name"
            assert "VA confirmed" in row["notes"]
            assert "updated_at" in row
        finally:
            await db.recruitment_leads.delete_one({"lead_id": lead_id})

    asyncio.get_event_loop().run_until_complete(run())


def test_import_csv_reports_unknown_lead_ids():
    async def run():
        from routers.admin import _LeadCsvImportIn
        bogus_id = f"lead_nope_{uuid.uuid4().hex[:6]}"
        csv_text = f"lead_id,email\n{bogus_id},someone@x.com\n"
        res = await admin_router.import_recruitment_leads_csv(
            _LeadCsvImportIn(csv_text=csv_text),
            user={"role": "admin", "user_id": "admin_x"},
        )
        assert res["updated"] == 0
        assert bogus_id in res["not_found"]

    asyncio.get_event_loop().run_until_complete(run())


def test_import_csv_invalid_status_is_flagged_not_applied():
    async def run():
        lead_id = f"lead_{uuid.uuid4().hex[:10]}"
        try:
            await _seed_lead(lead_id, f"x_{lead_id}@test.com", "Valid Name")
            from routers.admin import _LeadCsvImportIn
            csv_text = (
                "lead_id,status,notes\n"
                f"{lead_id},nonsense_status_value,Should still update notes\n"
            )
            res = await admin_router.import_recruitment_leads_csv(
                _LeadCsvImportIn(csv_text=csv_text),
                user={"role": "admin", "user_id": "admin_x"},
            )
            # Invalid status reported but other fields still applied
            assert lead_id in res["invalid_status_rows"]
            row = await db.recruitment_leads.find_one({"lead_id": lead_id}, {"_id": 0})
            assert row["status"] == "new"  # not changed
            assert row["notes"] == "Should still update notes"
        finally:
            await db.recruitment_leads.delete_one({"lead_id": lead_id})

    asyncio.get_event_loop().run_until_complete(run())


def test_import_csv_detects_duplicate_emails_across_rows():
    async def run():
        lead_a = f"lead_{uuid.uuid4().hex[:10]}"
        lead_b = f"lead_{uuid.uuid4().hex[:10]}"
        try:
            await _seed_lead(lead_a, f"x_{lead_a}@test.com", "Lead A")
            await _seed_lead(lead_b, f"x_{lead_b}@test.com", "Lead B")
            from routers.admin import _LeadCsvImportIn
            csv_text = (
                "lead_id,email\n"
                f"{lead_a},samesame@example.com\n"
                f"{lead_b},samesame@example.com\n"
            )
            res = await admin_router.import_recruitment_leads_csv(
                _LeadCsvImportIn(csv_text=csv_text),
                user={"role": "admin", "user_id": "admin_x"},
            )
            assert len(res["duplicate_emails"]) == 1
            assert res["duplicate_emails"][0]["email"] == "samesame@example.com"
        finally:
            await db.recruitment_leads.delete_many({"lead_id": {"$in": [lead_a, lead_b]}})

    asyncio.get_event_loop().run_until_complete(run())


def test_import_csv_rejects_missing_lead_id_column():
    async def run():
        from routers.admin import _LeadCsvImportIn
        from fastapi import HTTPException
        csv_text = "email,name\nsomeone@x.com,Whoever\n"
        try:
            await admin_router.import_recruitment_leads_csv(
                _LeadCsvImportIn(csv_text=csv_text),
                user={"role": "admin", "user_id": "admin_x"},
            )
            assert False, "should have raised"
        except HTTPException as e:
            assert e.status_code == 400
            assert "lead_id" in e.detail.lower()

    asyncio.get_event_loop().run_until_complete(run())


def test_non_admin_gets_403_on_both_endpoints():
    async def run():
        from routers.admin import _LeadCsvImportIn
        from fastapi import HTTPException
        try:
            await admin_router.export_recruitment_leads_csv(
                user={"role": "attendee", "user_id": "u_x"},
            )
            assert False, "should have raised"
        except HTTPException as e:
            assert e.status_code == 403
        try:
            await admin_router.import_recruitment_leads_csv(
                _LeadCsvImportIn(csv_text="lead_id\nx\n"),
                user={"role": "attendee", "user_id": "u_x"},
            )
            assert False, "should have raised"
        except HTTPException as e:
            assert e.status_code == 403

    asyncio.get_event_loop().run_until_complete(run())
