"""Seatmap templates — let organizers save a tuned seat layout once and reuse
it across recurring shows.

Mechanics:
  • Stored in `seatmap_templates`. Keyed by `template_id` (uuid-ish).
  • Owned per-organizer; only the owner can list / load / delete.
  • A "snapshot" is just the subset of Event seatmap fields. No bookings, no
    capacities, no prices that change between shows. Categories, custom
    labels and row offsets are preserved verbatim — that's the whole point.
  • Applying a template to an event REPLACES the event's seatmap fields.
    Guarded: only allowed when the event has zero paid/confirmed bookings
    (otherwise existing tickets could end up pointing at non-existent seats).
"""
from __future__ import annotations

import uuid
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import db, get_current_user, utc_now, logger

router = APIRouter(tags=["seatmap_templates"])


# Fields we snapshot from an event / form payload. Keep in sync with the
# Event model in models.py — these are the ones that define the visual /
# selection behaviour of a venue layout, independent of pricing.
TEMPLATE_FIELDS = (
    "seat_rows", "seat_cols",
    "aisles",
    "seatmap_curved", "seatmap_numbering_rtl",
    "seatmap_sections", "seatmap_categories",
    "seatmap_category_prices",
    "seatmap_row_offsets", "seatmap_custom_labels",
    "seat_price",  # default price — convenient to bring along
    "seat_map_image_url",
    "seatmap_backdrop_opacity", "seatmap_backdrop_offset_y",
    "seatmap_backdrop_offset_x", "seatmap_backdrop_scale",
)


class TemplateSaveIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    layout: Dict[str, Any] = Field(default_factory=dict)


def _strip(d: Dict[str, Any]) -> Dict[str, Any]:
    """Return only the whitelisted seatmap fields from a larger dict."""
    return {k: d[k] for k in TEMPLATE_FIELDS if k in d}


@router.get("/organizer/seatmap-templates")
async def list_my_templates(user: dict = Depends(get_current_user)) -> List[Dict[str, Any]]:
    """List my saved layout templates (newest first)."""
    cur = db.seatmap_templates.find({"owner_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1)
    return [doc async for doc in cur]


@router.post("/organizer/seatmap-templates")
async def save_template(payload: TemplateSaveIn, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Save the supplied layout under a name."""
    if user.get("role") not in ("organizer", "admin"):
        raise HTTPException(status_code=403, detail="Organizer-only")
    layout = _strip(payload.layout or {})
    if not layout.get("seat_rows") or not layout.get("seat_cols"):
        raise HTTPException(status_code=400, detail="Layout must have seat_rows and seat_cols set")
    template_id = f"tmpl_{uuid.uuid4().hex[:12]}"
    now = utc_now().isoformat()
    doc = {
        "template_id": template_id,
        "owner_id": user["user_id"],
        "name": payload.name.strip(),
        "layout": layout,
        "created_at": now,
        "updated_at": now,
    }
    await db.seatmap_templates.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/organizer/seatmap-templates/{template_id}")
async def get_template(template_id: str, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    doc = await db.seatmap_templates.find_one({"template_id": template_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Template not found")
    if doc["owner_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return doc


@router.delete("/organizer/seatmap-templates/{template_id}")
async def delete_template(template_id: str, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    doc = await db.seatmap_templates.find_one({"template_id": template_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Template not found")
    if doc["owner_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    await db.seatmap_templates.delete_one({"template_id": template_id})
    return {"ok": True}


class ApplyTemplateIn(BaseModel):
    template_id: str
    event_id: str


@router.post("/organizer/seatmap-templates/apply")
async def apply_template(payload: ApplyTemplateIn, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Copy a template's seatmap fields onto an existing event.

    Guard: the event must have zero confirmed/paid bookings, otherwise we'd
    risk leaving existing tickets pointing at seats that no longer exist.
    """
    doc = await db.seatmap_templates.find_one({"template_id": payload.template_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Template not found")
    if doc["owner_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    event = await db.events.find_one({"event_id": payload.event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.get("organizer_id") != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your event")
    bookings_count = await db.bookings.count_documents(
        {"event_id": payload.event_id, "status": {"$in": ["paid", "confirmed"]}}
    )
    if bookings_count > 0:
        raise HTTPException(
            status_code=409,
            detail="Event already has bookings — change the layout on a new event instead, "
                   "or refund the existing tickets first.",
        )
    update = {"has_seatmap": True, **_strip(doc["layout"])}
    await db.events.update_one({"event_id": payload.event_id}, {"$set": update})
    logger.info(f"[seatmap-template] applied {payload.template_id} to {payload.event_id}")
    return {"ok": True, "applied_fields": list(update.keys())}



# ---------------------------------------------------------------------------
# Door-sign PDF — printable, one A4 page per row, for ushers on the night of.
# ---------------------------------------------------------------------------
@router.get("/organizer/events/{event_id}/door-signs.pdf")
async def door_signs_pdf(event_id: str, user: dict = Depends(get_current_user)):
    from fastapi.responses import Response
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.get("organizer_id") != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your event")
    if not event.get("has_seatmap"):
        raise HTTPException(status_code=400, detail="Door signs are only available for events with a seatmap")
    from door_sign_pdf import build_door_sign_pdf
    pdf_bytes, filename = build_door_sign_pdf(event)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
