"""Shared core: config, db, helpers, auth dependency."""
import os
import io
import base64
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import bcrypt
import jwt as pyjwt
import qrcode
from fastapi import HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("aura")

ROOT_DIR = Path(__file__).parent

# Read DB env vars defensively — a missing key here would raise KeyError at
# import time BEFORE any logging happens, which produces a silent container
# crash with no diagnostic output. Print to stdout directly so even early
# failures are visible in container logs.
import sys as _sys
mongo_url = os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
db_name = os.environ.get("DB_NAME") or "test_database"
print(f"[core] MONGO_URL set: {'yes' if os.environ.get('MONGO_URL') else 'FALLBACK to localhost (env missing)'}", flush=True)
print(f"[core] DB_NAME: {db_name}", flush=True)
try:
    mongo_client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
    db = mongo_client[db_name]
    print(f"[core] motor client created OK", flush=True)
except Exception as _db_err:
    print(f"[core] CRITICAL: failed to init Mongo client: {_db_err}", flush=True)
    _sys.stdout.flush()
    raise

# JWT_SECRET should ALWAYS be set in production via env var. Fall back to a
# deterministic dev value only for local/preview where the env var may be
# absent — failing fast in prod is worse than running with a known default.
JWT_SECRET = os.environ.get("JWT_SECRET") or "dev-only-jwt-secret-CHANGE-IN-PRODUCTION"
JWT_ALGO = "HS256"
# Stripe key is read at module import but only USED at request time, so a
# missing/placeholder value won't crash startup. Per-request handlers raise
# the right HTTP error if Stripe is unconfigured.
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY") or ""
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL") or "admin@allsale.events"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or "admin123"

HOLD_MINUTES = 10
SESSION_DAYS = 7

ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MIME_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".webp": "image/webp",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "type": "access",
        "exp": utc_now() + timedelta(days=SESSION_DAYS),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def gen_qr_data_url(payload: str) -> str:
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def event_to_public(e: dict) -> dict:
    e.pop("_id", None)
    # Ensure currency is always present so the frontend can format prices safely
    if not e.get("currency"):
        e["currency"] = "NZD"
    # Default country to NZ for legacy events created before country was a field
    if not e.get("country"):
        e["country"] = "NZ"
    return e


def seat_section_for_row(event: dict, row_idx: int) -> Optional[dict]:
    """Return the section dict (with optional `price`) that contains a given row.

    `seatmap_sections` is sorted by `after_row`. A row belongs to the FIRST
    section whose `after_row` >= row_idx. If no section matches, the seat is
    in the "front" zone (rows above any section); pricing falls back to the
    event-level `seat_price`.
    """
    sections = event.get("seatmap_sections") or []
    if not sections:
        return None
    # Sort defensively in case organizer entered them out of order
    sorted_secs = sorted(sections, key=lambda s: s.get("after_row", 0))
    # Front zone: rows 0..first.after_row inclusive
    # Section 1: rows first.after_row+1..second.after_row inclusive
    boundaries = [-1] + [s.get("after_row", 0) for s in sorted_secs] + [10**6]
    for idx in range(1, len(boundaries)):
        if boundaries[idx - 1] < row_idx <= boundaries[idx]:
            # idx 1 → front zone (no section)
            if idx - 1 == 0:
                return None
            return sorted_secs[idx - 2]
    return None


def seat_price_for(event: dict, seat_id: str) -> float:
    """Return per-seat price. If a section has a custom `price`, use it; else
    fall back to the event-level `seat_price`. Format: "A-5" → row letter A (0).
    """
    try:
        row_letter = seat_id.split("-", 1)[0]
        row_idx = ord(row_letter.upper()) - ord("A")
    except Exception:
        return float(event.get("seat_price", 0))
    section = seat_section_for_row(event, row_idx)
    if section and section.get("price") is not None:
        try:
            return float(section["price"])
        except (TypeError, ValueError):
            pass
    return float(event.get("seat_price", 0))


def compute_tier_effective_price(event: dict, tier: dict, sold: int) -> tuple[float, bool]:
    """Apply dynamic pricing if enabled for this event.
    Returns (price, surging). Surge fires when remaining ≤ threshold_pct of capacity.
    """
    cfg = (event.get("dynamic_pricing") or {}) if isinstance(event.get("dynamic_pricing"), dict) else {}
    if not cfg.get("enabled"):
        return float(tier.get("price", 0)), False
    capacity = max(1, int(tier.get("capacity", 0)))
    remaining_pct = max(0.0, (capacity - sold) / capacity * 100)
    threshold = float(cfg.get("surge_threshold_pct", 30))  # surge when ≤30% left
    if remaining_pct > threshold:
        return float(tier.get("price", 0)), False
    multiplier = float(cfg.get("surge_multiplier", 1.2))
    multiplier = max(1.0, min(multiplier, 3.0))
    return round(float(tier.get("price", 0)) * multiplier, 2), True


def booking_to_public(b: dict) -> dict:
    b.pop("_id", None)
    return b


async def get_current_user(request: Request) -> dict:
    """Auth dependency: accepts JWT (cookie or Bearer) OR Emergent session_token (cookie or Bearer)."""
    # 1) JWT (cookie or Bearer header)
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if token:
        try:
            payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
            user = await db.users.find_one(
                {"user_id": payload["sub"]}, {"_id": 0, "password_hash": 0}
            )
            if user:
                if user.get("active") is False:
                    raise HTTPException(status_code=403, detail="Account suspended")
                return user
        except pyjwt.PyJWTError:
            pass

    # 2) Emergent Google session (cookie or Bearer header)
    sess_tok = request.cookies.get("session_token")
    if not sess_tok:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            sess_tok = auth[7:]
    if sess_tok:
        session = await db.user_sessions.find_one({"session_token": sess_tok}, {"_id": 0})
        if session:
            exp = session.get("expires_at")
            if isinstance(exp, str):
                exp = datetime.fromisoformat(exp)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp >= utc_now():
                user = await db.users.find_one(
                    {"user_id": session["user_id"]}, {"_id": 0, "password_hash": 0}
                )
                if user:
                    if user.get("active") is False:
                        raise HTTPException(status_code=403, detail="Account suspended")
                    return user

    raise HTTPException(status_code=401, detail="Not authenticated")


async def get_current_user_optional(request: Request) -> Optional[dict]:
    """Same as get_current_user but returns None instead of 401 for anonymous callers.
    Used by routes like view-tracking that should work for logged-out visitors too.
    """
    try:
        return await get_current_user(request)
    except HTTPException as e:
        if e.status_code == 401:
            return None
        raise


async def require_role(user: dict, *roles: str):
    if user.get("role") not in roles and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return user


def set_jwt_cookie(resp, token: str):
    resp.set_cookie(
        key="access_token", value=token, httponly=True, secure=True,
        samesite="none", max_age=SESSION_DAYS * 24 * 3600, path="/",
    )


def set_session_cookie(resp, token: str):
    resp.set_cookie(
        key="session_token", value=token, httponly=True, secure=True,
        samesite="none", max_age=SESSION_DAYS * 24 * 3600, path="/",
    )
