"""Seat-map auto-detection via Gemini Vision.

Organizer uploads a venue layout image (already stored in MongoDB via /uploads)
and this endpoint asks Gemini 2.5 Pro to extract a structured seat layout
(rows, columns, aisles, sections). Returns a JSON the form can apply.

The flow:
    1. Frontend uploads image → gets file_id (existing /uploads).
    2. Frontend POSTs file_id to /organizer/seatmap/detect.
    3. We pull the bytes from MongoDB, write to a temp file, hand it to
       Gemini via emergentintegrations.
    4. We parse the model's JSON reply, validate it, and return the layout.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import db, get_current_user, require_role
from emergentintegrations.llm.chat import (
    LlmChat,
    UserMessage,
    FileContentWithMimeType,
)

router = APIRouter(prefix="/organizer/seatmap", tags=["organizer-seatmap"])


SYSTEM_PROMPT = """You are a venue seat-layout analyst.
Given an image of a seat map / floor plan / theatre diagram, return a strict
JSON object describing the layout. Output JSON only — no prose, no markdown
fences.

Schema:
{
  "rows": int,                    # total number of rows you can count
  "cols": int,                    # the widest row's seat count (assume rectangular grid)
  "aisles": [string],             # seat IDs that are aisle/walkway markers (NOT bookable). Format "<RowLetter>-<ColNumber>", e.g. "A-5"
  "sections": [                   # optional groupings (e.g. VIP vs General)
    {"name": "VIP", "color": "#EA580C", "seats": ["A-1","A-2","A-3"]}
  ],
  "curved": bool,                 # true if rows curve around a stage; false for a flat grid
  "confidence": float,            # 0.0-1.0 — how confident you are
  "notes": string                 # one short sentence explaining anything odd
}

Rules:
- Row letters go A, B, C, ... from FRONT (closest to stage/screen) to BACK.
- Column numbers go 1, 2, 3, ... left to right.
- If you cannot detect a clear grid, set rows=0 cols=0 and explain in "notes".
- Maximum row count: 30. Maximum cols: 60. If a venue is bigger, return your best estimate inside those caps.
- Aisles are unseated walkway gaps. Look for vertical strips with no seat circles.
- Sections: only include if visually distinct (color block, label, raised area). Otherwise return [].
- If there are stage indicators ("STAGE"/"SCREEN"), interpret seat numbering relative to those.
- Output JSON ONLY.
"""


class DetectIn(BaseModel):
    file_id: str
    apply: bool = False  # if True, ALSO write the result to the event in one shot
    event_id: Optional[str] = None  # required when apply=True


def _strip_json(s: str) -> str:
    """Strip ``` fences a stubborn model might add even after we asked nicely."""
    s = s.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", s, re.S)
    return m.group(1) if m else s


@router.post("/detect")
async def detect_seatmap(payload: DetectIn, user: dict = Depends(get_current_user)):
    """Run Gemini Vision on a previously-uploaded seatmap image."""
    await require_role(user, "organizer", "admin")

    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise HTTPException(status_code=500, detail="LLM key not configured")

    rec = await db.uploaded_files.find_one(
        {"$or": [{"file_id": payload.file_id}, {"storage_path": payload.file_id}]},
        {"_id": 0},
    )
    if not rec or not rec.get("data"):
        raise HTTPException(status_code=404, detail="Uploaded image not found")

    ctype = rec.get("content_type", "image/jpeg")
    if not ctype.startswith("image/"):
        raise HTTPException(status_code=400, detail="File is not an image")
    if ctype in ("image/heic", "image/heif", "image/svg+xml", "image/bmp"):
        raise HTTPException(status_code=400, detail="Unsupported image format — use JPEG, PNG, or WEBP")

    # Drop bytes to a temp file because emergentintegrations' Gemini path
    # accepts FileContentWithMimeType pointing to a local file.
    suffix = {"image/png": ".png", "image/webp": ".webp"}.get(ctype, ".jpg")
    with tempfile.NamedTemporaryFile(prefix="seatmap_", suffix=suffix, delete=False) as f:
        f.write(rec["data"])
        tmp_path = f.name

    try:
        chat = LlmChat(
            api_key=key,
            session_id=f"seatmap_{uuid.uuid4().hex[:10]}",
            system_message=SYSTEM_PROMPT,
        ).with_model("gemini", "gemini-2.5-pro")

        image = FileContentWithMimeType(file_path=tmp_path, mime_type=ctype)
        msg = UserMessage(
            text="Analyse this seat map and return the JSON layout exactly as specified.",
            file_contents=[image],
        )
        raw = await chat.send_message(msg)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Vision model failed: {exc}") from exc
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    # Parse JSON from response (model may have wrapped in fences despite instruction)
    try:
        parsed = json.loads(_strip_json(raw if isinstance(raw, str) else str(raw)))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Could not parse model output: {exc}") from exc

    # Sanity-clamp values
    rows = max(0, min(30, int(parsed.get("rows", 0) or 0)))
    cols = max(0, min(60, int(parsed.get("cols", 0) or 0)))
    aisles = [str(a) for a in (parsed.get("aisles") or []) if isinstance(a, str)]
    sections = parsed.get("sections") or []
    if not isinstance(sections, list):
        sections = []

    result = {
        "rows": rows,
        "cols": cols,
        "aisles": aisles,
        "sections": sections,
        "curved": bool(parsed.get("curved", False)),
        "confidence": float(parsed.get("confidence", 0.0) or 0.0),
        "notes": str(parsed.get("notes", "") or "")[:280],
    }

    # Optionally apply to the event in one go
    if payload.apply:
        if not payload.event_id:
            raise HTTPException(status_code=400, detail="event_id required to apply")
        event = await db.events.find_one({"event_id": payload.event_id}, {"_id": 0})
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        if event.get("organizer_id") != user["user_id"] and user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Not your event")
        await db.events.update_one(
            {"event_id": payload.event_id},
            {"$set": {
                "has_seatmap": rows > 0 and cols > 0,
                "seat_rows": result["rows"],
                "seat_cols": result["cols"],
                "aisles": result["aisles"],
                "seatmap_sections": result["sections"],
                "seatmap_curved": result["curved"],
                "seat_map_image_url": f"/api/files/{payload.file_id}",
                "seatmap_detected_at": payload.file_id,  # poor man's audit
            }},
        )
        result["applied"] = True
    return result
