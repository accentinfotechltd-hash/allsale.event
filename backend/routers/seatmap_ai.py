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
                                  #   - "non-seat" tiles (stairs, pillars, screens, blocked positions),
                                  #   - red "Sightline Issues / Not on Sale" tiles in cinema legends.
  "seat_categories": {            # OPTIONAL — per-seat category from the visible legend
                                  # Keys: "wheelchair", "house", "disabled", "vip", "premium".
                                  # Values: array of seat IDs ("A-1", "A-2", ...).
                                  # ONLY populate categories you can DEFINITIVELY tie to a colored
                                  # legend tile in the image. Empty {} if uncertain.
    "wheelchair": [string],
    "house": [string],
    "disabled": [string],
    "vip": [string],
    "premium": [string]
  },
  "sections": [                   # OPTIONAL groupings derived from labelled blocks
    {"name": "VIP", "color": "#EA580C", "seats": ["A-1","A-2","A-3"]}
  ],
  "legend_detected": bool,        # true if the image had a visible legend/key block
  "curved": bool,                 # true if rows visually curve around a stage
  "confidence": float,            # 0.0–1.0 — your honest estimate; cinema-style maps with
                                  # legends are HARD, be conservative (≤ 0.6 unless every
                                  # row and category is unambiguous)
  "notes": string                 # one short sentence summarising anything unusual
}

CRITICAL RULES — read carefully:
1. Row letters go A, B, C, ... from FRONT (closest to stage/screen) to BACK.
2. Column numbers go 1, 2, 3, ... left-to-right as the AUDIENCE faces the stage.
3. For NON-RECTANGULAR layouts (e.g. front rows wider than back rows), ALWAYS pad `cols` to the widest row and aggressively populate `aisles` for the empty positions in narrower rows. Example: if row A has seats 1-12 but row D only has 7 visible seats centred under it, those 7 are probably at columns 3-9 — mark D-1, D-2, D-10, D-11, D-12 as aisles.
4. Wheelchair markers (♿ icons, BLUE tile with disabled symbol, or a tile labelled "wheelchair space" in the legend) are BOOKABLE accessibility seats — list them in `seat_categories.wheelchair`, NOT aisles, unless they're clearly a gap.
5. Walkway gaps between seat-blocks → mark the whole column as an aisle for every row.
6. LEGEND PARSING (very important for cinema maps):
   - First scan the image for a "KEY" or "Legend" block. Map each colored swatch to its label.
   - Then read every seat tile's COLOR. Match colors to the legend.
   - GREEN tile labelled "Disabled" → `seat_categories.disabled`
   - YELLOW tile labelled "House" → `seat_categories.house`
   - BLUE tile labelled "Wheelchair" → `seat_categories.wheelchair`
   - WHITE tile labelled "Normal" → regular bookable, no category
   - RED tile labelled "Sightline Issues" → `aisles` (not on sale)
7. Sections: include if you can see a clear visual cue (colour fill, label, raised platform). Otherwise return [].
8. CONFIDENCE: be HONEST. If the image has a complex legend, irregular rows, or non-trivial color mapping, set confidence ≤ 0.6 and let the organizer correct. Overconfidence is worse than admitting uncertainty.
9. If you cannot detect a clear grid at all, return rows=0 cols=0 and explain in `notes`.

THINK STEP-BY-STEP:
  Step 1: Find the legend/key block (top-left of cinema maps usually).
  Step 2: Find the widest row in the seating area — that's `cols`. Count rows front→back → `rows`.
  Step 3: For each row, locate empty positions and add them to `aisles`.
  Step 4: For each colored tile, look up its category in the legend → populate `seat_categories`.
  Step 5: Set `legend_detected` and `confidence` honestly.

Output JSON ONLY.
"""


class DetectIn(BaseModel):
    file_id: str
    apply: bool = False  # if True, ALSO write the result to the event in one shot
    event_id: Optional[str] = None  # required when apply=True


class DescribeIn(BaseModel):
    """Plain-English layout description. Used as a fallback when vision fails."""
    text: str


@router.post("/describe")
async def describe_layout(payload: DescribeIn, user: dict = Depends(get_current_user)):
    """Turn an organizer's English description into the same structured JSON
    that /detect returns. Vastly more reliable than vision for tricky venues.

    Example input:
      "9 rows. Rows A-C have 12 seats. Rows D-I have 9 seats centred under them.
       Wheelchair positions at C-1 and C-11."
    """
    await require_role(user, "organizer", "admin")
    text = (payload.text or "").strip()
    if len(text) < 12:
        raise HTTPException(status_code=400, detail="Describe your layout in at least a sentence")
    if len(text) > 4000:
        raise HTTPException(status_code=400, detail="Description too long (max 4000 chars)")

    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        raise HTTPException(status_code=500, detail="LLM key not configured")

    try:
        chat = LlmChat(
            api_key=key,
            session_id=f"seatmap_text_{uuid.uuid4().hex[:10]}",
            system_message=SYSTEM_PROMPT,
        ).with_model("gemini", "gemini-2.5-pro")
        raw = await chat.send_message(UserMessage(
            text=(
                "The organizer describes their venue below. Convert this into the JSON "
                "schema from your system prompt. If they describe asymmetric rows, "
                "pick `cols` = widest row count and mark missing positions in narrower "
                "rows as aisles. Pay attention to seat ranges like 'C-1 to C-12'.\n\n"
                f"DESCRIPTION:\n{text}\n\nOutput JSON only."
            ),
        ))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM failed: {exc}") from exc

    try:
        parsed = json.loads(_strip_json(raw if isinstance(raw, str) else str(raw)))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not parse output: {exc}") from exc

    return {
        "rows": max(0, min(30, int(parsed.get("rows", 0) or 0))),
        "cols": max(0, min(60, int(parsed.get("cols", 0) or 0))),
        "aisles": [str(a) for a in (parsed.get("aisles") or []) if isinstance(a, str)],
        "seat_categories": _clean_categories(parsed.get("seat_categories")),
        "sections": parsed.get("sections") if isinstance(parsed.get("sections"), list) else [],
        "curved": bool(parsed.get("curved", False)),
        "legend_detected": bool(parsed.get("legend_detected", False)),
        "confidence": float(parsed.get("confidence", 0.9) or 0.9),
        "notes": str(parsed.get("notes", "") or "")[:280],
    }


CATEGORY_KEYS = ("wheelchair", "house", "disabled", "vip", "premium")


def _clean_categories(raw) -> dict:
    """Coerce the `seat_categories` field into our canonical shape, dropping
    unknown keys + non-string seat IDs. Always returns a dict so the frontend
    can rely on its presence."""
    out = {k: [] for k in CATEGORY_KEYS}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        if k not in CATEGORY_KEYS or not isinstance(v, list):
            continue
        out[k] = [str(s) for s in v if isinstance(s, str)]
    return out


# Range pattern used by the deterministic parser. Matches "A-1", "A1", and
# range syntax "A1-A5" / "A:1-5". Stored as a module constant so the parser
# is fast and the regex compiles once.
_RANGE_RE = re.compile(
    r"\b([A-Z])\s*[:\-]?\s*(\d+)(?:\s*-\s*([A-Z]?)\s*(\d+))?\b"
)


def _expand_range(row1: str, n1: int, row2: str, n2: int) -> list[str]:
    """Expand 'A 1-5' → A-1..A-5, 'A1-B3' → A-1..A-rest, B-1..B-3."""
    if not row2 or row2 == row1:
        lo, hi = sorted((n1, n2 or n1))
        return [f"{row1}-{n}" for n in range(lo, hi + 1)]
    # cross-row range — uncommon, treat as A-n1, then anything in between rows,
    # then B-n2. We DON'T expand the middle because we don't know each row's
    # width yet. Caller handles that via the rows/cols context.
    return [f"{row1}-{n1}", f"{row2}-{n2}"]


def parse_text_layout(text: str) -> dict:
    """Deterministic offline parser for organizer-described layouts.

    Falls back to the LLM `/describe` endpoint when the text doesn't look
    structured. Accepts patterns like:
        Row A: 1-15 (wheelchair 1-2, 12-15; house 6-11)
        B: 1-2 aisle, 3-12
        C-E: 1-10
        F-G: 1-10 disabled
        H: 1-4 disabled, 5 wheelchair, aisle 6-8, 9 wheelchair, 10 disabled

    Returns the same schema as /detect.
    """
    rows_data: dict[str, dict] = {}  # row_letter -> {seats: [int], cats: {cat: set[int]}, aisles: set[int]}
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    for ln in lines:
        # Allow "Row A:" or "A:" or "A-C:" prefix
        head_m = re.match(r"^(?:row\s+)?([A-Z])(?:\s*-\s*([A-Z]))?\s*[:\.]?\s*(.*)$", ln, re.I)
        if not head_m:
            continue
        r1 = head_m.group(1).upper()
        r2 = (head_m.group(2) or r1).upper()
        rest = head_m.group(3) or ""
        rest_lower = rest.lower()
        if not rest_lower:
            continue
        # Determine row letters in this line
        row_letters = [chr(c) for c in range(ord(r1), ord(r2) + 1)]
        # Split clauses by comma OR semicolon. Each clause assigns a category
        # to a number-range (or marks aisle).
        clauses = re.split(r"[,;]", rest_lower)
        # Parse the FIRST clause as the default seat range if it's only digits/range.
        # We accumulate per row in row_letters.
        for letter in row_letters:
            rdata = rows_data.setdefault(letter, {"seats": set(), "cats": {}, "aisles": set()})
            for clause in clauses:
                clause = clause.strip()
                if not clause:
                    continue
                # Detect category keyword in this clause
                cat = None
                for k in CATEGORY_KEYS + ("aisle", "normal"):
                    if k in clause:
                        cat = k
                        break
                # Pull all int ranges from the clause: "1-15" or "6, 9, 10" or "1-2"
                nums: list[int] = []
                for m in re.finditer(r"(\d+)\s*-\s*(\d+)|(\d+)", clause):
                    if m.group(1) is not None:
                        a, b = int(m.group(1)), int(m.group(2))
                        lo, hi = (a, b) if a <= b else (b, a)
                        nums.extend(range(lo, hi + 1))
                    else:
                        nums.append(int(m.group(3)))
                if not nums:
                    continue
                if cat == "aisle":
                    rdata["aisles"].update(nums)
                else:
                    rdata["seats"].update(nums)
                    if cat and cat not in ("normal",):
                        rdata["cats"].setdefault(cat, set()).update(nums)
    if not rows_data:
        return {"rows": 0, "cols": 0, "aisles": [], "seat_categories": {k: [] for k in CATEGORY_KEYS}, "sections": [], "curved": False, "legend_detected": False, "confidence": 0.0, "notes": "Could not parse — try the AI describe endpoint."}

    # Drop rows where neither seats nor aisles were extracted (false-positive
    # row-letter matches on non-layout prose like "this is not a seat map").
    rows_data = {k: v for k, v in rows_data.items() if v["seats"] or v["aisles"]}
    if not rows_data:
        return {"rows": 0, "cols": 0, "aisles": [], "seat_categories": {k: [] for k in CATEGORY_KEYS}, "sections": [], "curved": False, "legend_detected": False, "confidence": 0.0, "notes": "Could not parse — try the AI describe endpoint."}

    sorted_letters = sorted(rows_data.keys())
    rows = len(sorted_letters)
    max_col = max((max(d["seats"] | d["aisles"]) if (d["seats"] or d["aisles"]) else 0)
                  for d in rows_data.values())
    cols = max_col
    aisles: list[str] = []
    cats: dict[str, list[str]] = {k: [] for k in CATEGORY_KEYS}
    for letter in sorted_letters:
        rdata = rows_data[letter]
        all_present = rdata["seats"] | rdata["aisles"]
        for c in range(1, cols + 1):
            sid = f"{letter}-{c}"
            if c in rdata["aisles"]:
                aisles.append(sid)
            elif c not in all_present:
                # missing in narrower row → aisle (per schema convention)
                aisles.append(sid)
        for cat, nums in rdata["cats"].items():
            if cat in cats:
                cats[cat].extend(f"{letter}-{n}" for n in sorted(nums))
    return {
        "rows": rows,
        "cols": cols,
        "aisles": sorted(set(aisles)),
        "seat_categories": cats,
        "sections": [],
        "curved": False,
        "legend_detected": False,
        "confidence": 0.95,  # deterministic parse is high-confidence by definition
        "notes": "Parsed from text",
    }


class TextLayoutIn(BaseModel):
    text: str


@router.post("/parse-text")
async def parse_text_layout_endpoint(payload: TextLayoutIn, user: dict = Depends(get_current_user)):
    """Fast, free, offline layout parser. Try this first — falls back to
    /describe (LLM) only when this can't extract a grid."""
    await require_role(user, "organizer", "admin")
    text = (payload.text or "").strip()
    if len(text) < 5:
        raise HTTPException(status_code=400, detail="Describe your layout in at least a sentence")
    if len(text) > 4000:
        raise HTTPException(status_code=400, detail="Description too long (max 4000 chars)")
    return parse_text_layout(text)


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
        "seat_categories": _clean_categories(parsed.get("seat_categories")),
        "sections": sections,
        "curved": bool(parsed.get("curved", False)),
        "legend_detected": bool(parsed.get("legend_detected", False)),
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
                "seatmap_categories": result["seat_categories"],
                "seat_map_image_url": f"/api/files/{payload.file_id}",
                "seatmap_detected_at": payload.file_id,  # poor man's audit
            }},
        )
        result["applied"] = True
    return result
