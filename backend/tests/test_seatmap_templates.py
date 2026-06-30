"""Seatmap templates — save / list / apply / delete round trip."""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402
from routers.seatmap_templates import _strip, TEMPLATE_FIELDS  # noqa: E402


def test_strip_keeps_only_whitelisted_fields():
    raw = {
        "seat_rows": 6,
        "seat_cols": 10,
        "aisles": ["A-3"],
        "title": "ignored",
        "organizer_id": "ignored",
        "seatmap_custom_labels": {"A-1": "VIP-1"},
    }
    out = _strip(raw)
    assert "seat_rows" in out and out["seat_rows"] == 6
    assert "title" not in out
    assert "organizer_id" not in out
    assert "seatmap_custom_labels" in out


def test_template_fields_include_critical_seatmap_keys():
    must_have = {
        "seat_rows", "seat_cols", "aisles",
        "seatmap_categories", "seatmap_custom_labels", "seatmap_row_offsets",
        "seatmap_numbering_rtl", "seatmap_sections",
    }
    missing = must_have - set(TEMPLATE_FIELDS)
    assert not missing, f"Template snapshot missing: {missing}"


async def test_template_full_lifecycle_via_collection():
    owner = f"u_{uuid.uuid4().hex[:8]}"
    tid_holder = {}
    try:
        # Insert
        template_id = f"tmpl_{uuid.uuid4().hex[:12]}"
        await db.seatmap_templates.insert_one({
            "template_id": template_id,
            "owner_id": owner,
            "name": "Test Stage",
            "layout": {"seat_rows": 4, "seat_cols": 8, "aisles": ["A-4"]},
            "created_at": utc_now().isoformat(),
            "updated_at": utc_now().isoformat(),
        })
        tid_holder["id"] = template_id
        # List
        cnt = await db.seatmap_templates.count_documents({"owner_id": owner})
        assert cnt == 1
        # Fetch by id
        doc = await db.seatmap_templates.find_one({"template_id": template_id}, {"_id": 0})
        assert doc and doc["layout"]["seat_rows"] == 4
        # Delete
        await db.seatmap_templates.delete_one({"template_id": template_id})
        cnt2 = await db.seatmap_templates.count_documents({"owner_id": owner})
        assert cnt2 == 0
    finally:
        if tid_holder.get("id"):
            await db.seatmap_templates.delete_one({"template_id": tid_holder["id"]})

