"""Auth endpoints: register, login, logout, me, google session."""
import uuid
from datetime import timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from core import (
    db, get_current_user, hash_password, verify_password, utc_now,
    create_access_token, set_jwt_cookie, set_session_cookie, SESSION_DAYS,
)
from models import RegisterIn, LoginIn, GoogleSessionIn

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def register(payload: RegisterIn, response: Response):
    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    if payload.role not in ("attendee", "organizer"):
        raise HTTPException(status_code=400, detail="Invalid role")
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    doc = {
        "user_id": user_id,
        "email": email,
        "name": payload.name,
        "role": payload.role,
        "password_hash": hash_password(payload.password),
        "picture": None,
        "created_at": utc_now().isoformat(),
        "auth_provider": "password",
    }
    await db.users.insert_one(doc)
    token = create_access_token(user_id, email)
    set_jwt_cookie(response, token)
    return {
        "user_id": user_id, "email": email, "name": payload.name,
        "role": payload.role, "picture": None, "token": token,
    }


@router.post("/login")
async def login(payload: LoginIn, response: Response):
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not user.get("password_hash") or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.get("active") is False:
        raise HTTPException(status_code=403, detail="Account suspended. Contact support.")
    token = create_access_token(user["user_id"], email)
    set_jwt_cookie(response, token)
    return {
        "user_id": user["user_id"], "email": user["email"], "name": user["name"],
        "role": user["role"], "picture": user.get("picture"), "token": token,
    }


@router.post("/logout")
async def logout(response: Response, request: Request):
    sess = request.cookies.get("session_token")
    if sess:
        await db.user_sessions.delete_one({"session_token": sess})
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return {
        "user_id": user["user_id"], "email": user["email"], "name": user["name"],
        "role": user["role"], "picture": user.get("picture"),
        "phone": user.get("phone"),
        "notification_prefs": user.get("notification_prefs") or {
            "email_booking": True, "email_reminders": True, "email_marketing": False,
        },
    }


# ---------- Profile editing ----------
from pydantic import BaseModel, EmailStr
import re


class ProfileUpdateIn(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    picture: str | None = None  # data URL or hosted URL
    notification_prefs: dict | None = None


_PHONE_RE = re.compile(r"^[+0-9 ()\-]{6,20}$")


@router.patch("/me")
async def update_me(payload: ProfileUpdateIn, user: dict = Depends(get_current_user)):
    """Edit profile fields. Email change is allowed but must be unique.
    Phone is validated loosely (digits/+/-/space). All future booking emails
    automatically route to the new address because email is read at booking time.
    """
    update: dict = {}
    if payload.name is not None:
        nm = payload.name.strip()
        if not nm:
            raise HTTPException(status_code=400, detail="Name cannot be empty")
        update["name"] = nm
    if payload.email is not None:
        new_email = str(payload.email).lower().strip()
        if new_email != user["email"]:
            clash = await db.users.find_one({"email": new_email, "user_id": {"$ne": user["user_id"]}})
            if clash:
                raise HTTPException(status_code=400, detail="That email is already taken")
            update["email"] = new_email
    if payload.phone is not None:
        ph = payload.phone.strip()
        if ph and not _PHONE_RE.match(ph):
            raise HTTPException(status_code=400, detail="Phone format looks invalid")
        update["phone"] = ph or None
    if payload.picture is not None:
        update["picture"] = payload.picture or None
    if payload.notification_prefs is not None:
        # whitelist keys to avoid stuffing arbitrary data
        allowed = {"email_booking", "email_reminders", "email_marketing", "email_cancellations"}
        prefs = {k: bool(v) for k, v in payload.notification_prefs.items() if k in allowed}
        update["notification_prefs"] = prefs

    if not update:
        return {"updated": False, **{k: v for k, v in user.items() if k not in ("_id", "password_hash")}}

    update["profile_updated_at"] = utc_now().isoformat()
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": update})
    refreshed = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "password_hash": 0})
    return {"updated": True, **refreshed}


# Emergent Google Auth — exchange session_id for session_token, fetch profile
# REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
@router.post("/google-session")
async def google_session(payload: GoogleSessionIn, response: Response):
    async with httpx.AsyncClient(timeout=15) as hc:
        r = await hc.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": payload.session_id},
        )
        if r.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid session")
        data = r.json()

    email = (data.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(status_code=400, detail="No email returned")
    name = data.get("name") or email.split("@")[0]
    picture = data.get("picture")
    session_token = data["session_token"]

    user = await db.users.find_one({"email": email}, {"_id": 0})
    if user:
        await db.users.update_one(
            {"email": email}, {"$set": {"name": name, "picture": picture}},
        )
        user_id = user["user_id"]
        role = user["role"]
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        role = "attendee"
        await db.users.insert_one({
            "user_id": user_id, "email": email, "name": name, "picture": picture,
            "role": role, "created_at": utc_now().isoformat(), "auth_provider": "google",
        })

    await db.user_sessions.insert_one({
        "user_id": user_id, "session_token": session_token,
        "expires_at": (utc_now() + timedelta(days=SESSION_DAYS)).isoformat(),
        "created_at": utc_now().isoformat(),
    })
    set_session_cookie(response, session_token)
    return {"user_id": user_id, "email": email, "name": name, "picture": picture, "role": role}


@router.post("/become-organizer")
async def become_organizer(user: dict = Depends(get_current_user)):
    """Upgrade an attendee to organizer in one click.

    Idempotent — calling repeatedly is safe. Admins stay admin (role unchanged).
    Returns the refreshed user dict so the frontend can update local state.
    """
    if user.get("role") == "admin":
        return {**{k: v for k, v in user.items() if k != "password_hash"}, "upgraded": False}
    if user.get("role") == "organizer":
        return {**{k: v for k, v in user.items() if k != "password_hash"}, "upgraded": False}
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"role": "organizer", "upgraded_at": utc_now().isoformat()}},
    )
    refreshed = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "password_hash": 0})
    return {**refreshed, "upgraded": True}


@router.post("/switch-to-attendee")
async def switch_to_attendee(user: dict = Depends(get_current_user)):
    """Downgrade an organizer back to a regular attendee account.

    Idempotent — calling repeatedly is safe. Admins cannot switch
    (they remain admin). Past events stay owned by the user and become
    visible again the moment they switch back via /become-organizer.
    """
    if user.get("role") == "admin":
        return {**{k: v for k, v in user.items() if k not in ("password_hash", "_id")}, "switched": False}
    if user.get("role") == "attendee":
        return {**{k: v for k, v in user.items() if k not in ("password_hash", "_id")}, "switched": False}
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"role": "attendee", "downgraded_at": utc_now().isoformat()}},
    )
    refreshed = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "password_hash": 0})
    return {**refreshed, "switched": True}
