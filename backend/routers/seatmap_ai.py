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


SYSTEM_PROMPT = """You are a senior venue seat-layout analyst. Your job is to
read an image of a seat map / floor plan / cinema diagram and convert it into
a STRICT JSON describing the grid the audience actually sees.

OUTPUT JSON ONLY — no prose, no markdown fences, no commentary.

Schema:
{
  "rows": int,                    # total bookable rows (max 30)
  "cols": int,                    # WIDEST row's seat count (max 60). The grid is rectangular: if some rows are narrower, mark the missing positions as aisles.
  "aisles": [string],             # seat IDs that are NOT regular bookable seats. Format: "<RowLetter>-<ColNumber>" e.g. "A-5". This MUST include:
                                  #   - walkway / vertical aisle columns,
                                  #   - missing-seat slots when a row is narrower than the widest row,
                                  #   - wheelchair-accessible markers (♿ icons or blue tile with disabled symbol),
                                  #   - any "non-seat" tiles (stairs, pillars, screens, blocked positions).
  "sections": [                   # OPTIONAL groupings (e.g. VIP/Premium/General)
    {"name": "VIP", "color": "#EA580C", "seats": ["A-1","A-2","A-3"]}
  ],
  "curved": bool,                 # true if rows visually curve around a stage
  "confidence": float,            # 0.0–1.0 — how confident you are
  "notes": string                 # one short sentence summarising anything unusual
}

CRITICAL RULES — read carefully:
1. Row letters go A, B, C, ... from FRONT (closest to stage/screen) to BACK.
2. Column numbers go 1, 2, 3, ... left-to-right as the AUDIENCE faces the stage.
3. For NON-RECTANGULAR layouts (e.g. front rows wider than back rows), ALWAYS pad `cols` to the widest row and aggressively populate `aisles` for the empty positions in narrower rows. Example: if row A has seats 1-12 but row D only has 7 visible seats centred under it, those 7 are probably at columns 3-9 — mark D-1, D-2, D-10, D-11, D-12 as aisles.
4. Wheelchair markers (♿ icons, blue squares with disabled symbol) are NOT bookable. They go in `aisles`.
5. Walkway gaps between seat-blocks → mark the whole column as an aisle for every row.
6. Look at the OVERALL shape: cinemas often have a wider front + narrower back, or a uniform grid with one or two centre/side aisles. Identify which.
7. Sections: only include if you can see a clear visual cue (colour fill, label, raised platform). Otherwise return [].
8. If you cannot detect a clear grid at all, return rows=0 cols=0 and explain in `notes`.

THINK STEP-BY-STEP: count the widest row's seats first → that's `cols`. Count rows from front → that's `rows`. Then for each row, locate the empty positions and add them to `aisles`. Finally identify any other aisles.

Output JSON ONLY.
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
            text=(
                "Analyse this seat map. Return JSON exactly as specified. "
                "Pay special attention to:\n"
                "1. Non-rectangular layouts — if back rows are narrower than front rows, "
                "MARK the missing positions as aisles so the grid stays rectangular.\n"
                "2. Wheelchair-accessible markers (♿ icons / blue disabled-symbol squares) — "
                "they are aisles, not bookable seats.\n"
                "3. Any vertical column with no seat in any row — that whole column is an aisle.\n"
                "Output JSON only."
            ),
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
