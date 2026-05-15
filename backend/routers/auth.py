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
    }


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
