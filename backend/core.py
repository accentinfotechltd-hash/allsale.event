"""Shared core: config, db, helpers, auth dependency."""
import os
import io
import base64
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import bcrypt
import jwt as pyjwt
import qrcode
from fastapi import HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("aura")

ROOT_DIR = Path(__file__).parent

mongo_url = os.environ["MONGO_URL"]
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[os.environ["DB_NAME"]]

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGO = "HS256"
STRIPE_API_KEY = os.environ["STRIPE_API_KEY"]
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]

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
    return e


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
