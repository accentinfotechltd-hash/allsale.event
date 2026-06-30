"""Auth endpoints: register, login, logout, me, google session."""
import re
import uuid
from datetime import timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from core import (
    db, get_current_user, hash_password, verify_password, utc_now,
    create_access_token, set_jwt_cookie, set_session_cookie, SESSION_DAYS,
)
from models import RegisterIn, LoginIn, GoogleSessionIn

router = APIRouter(prefix="/auth", tags=["auth"])

# Lenient international phone format: digits, optional + prefix, spaces,
# dashes, and brackets. Same regex used by PATCH /auth/me so the DB stays
# consistent regardless of which endpoint saved the number.
_PHONE_RE = re.compile(r"^[+0-9 ()\-]{6,20}$")



async def _notify_admins_of_signup(new_user: dict) -> None:
    """Email every admin whenever a new user signs up.

    Fire-and-forget — never blocks the signup response if email service is
    down or no admins are configured. Looks up admins on every signup so it
    picks up newly-created admins without a deploy. Honors each admin's
    `notification_email` override (handled inside `send_template`).
    """
    try:
        from emails import send_template_fireforget
        async for admin in db.users.find(
            {"role": "admin", "active": {"$ne": False}},
            {"_id": 0, "email": 1, "name": 1},
        ):
            if not admin.get("email"):
                continue
            send_template_fireforget(
                "admin_new_user_signup",
                admin["email"],
                {
                    "admin_name": admin.get("name") or "Admin",
                    "user_name": new_user.get("name") or new_user.get("email"),
                    "user_email": new_user.get("email"),
                    "role": new_user.get("role", "attendee"),
                    "auth_provider": new_user.get("auth_provider", "password"),
                },
                db,
            )
    except Exception as e:
        # Never block signup on a notification failure.
        from core import logger as _log
        _log.warning(f"[auth] _notify_admins_of_signup failed: {e}")



@router.post("/register")
async def register(payload: RegisterIn, response: Response):
    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    if payload.role not in ("attendee", "organizer"):
        raise HTTPException(status_code=400, detail="Invalid role")
    # Phone format check — same regex used by PATCH /auth/me so the DB stays
    # consistent regardless of which endpoint saved the number.
    phone = (payload.phone or "").strip()
    if not _PHONE_RE.match(phone):
        raise HTTPException(
            status_code=400,
            detail="Phone number looks invalid. Use digits with optional +, spaces, dashes or brackets.",
        )
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    doc = {
        "user_id": user_id,
        "email": email,
        "name": payload.name,
        "phone": phone,
        "role": payload.role,
        "password_hash": hash_password(payload.password),
        "picture": None,
        "created_at": utc_now().isoformat(),
        "auth_provider": "password",
    }
    await db.users.insert_one(doc)
    # Attach any pending team invitations addressed to this email
    try:
        from routers.team import attach_pending_team_invites
        await attach_pending_team_invites(doc)
    except Exception:
        pass
    # Notify all admins about the new signup (fire-and-forget, never blocks).
    await _notify_admins_of_signup(doc)
    # Fire welcome email #1 to organizers — fire-and-forget, never blocks signup.
    if payload.role == "organizer":
        try:
            from emails import send_template_fireforget
            send_template_fireforget(
                "organizer_welcome_1_signup",
                email,
                {"organizer_name": payload.name},
                db,
            )
        except Exception:
            pass
    token = create_access_token(user_id, email)
    set_jwt_cookie(response, token)
    return {
        "user_id": user_id, "email": email, "name": payload.name,
        "role": payload.role, "picture": None, "phone": phone, "token": token,
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
        "role": user["role"], "picture": user.get("picture"),
        "phone": user.get("phone"), "token": token,
    }



# ---------- One-shot admin password reset (env-var-gated) ----------
# When a deployment loses track of its admin password, the operator can set the
# environment variable `ADMIN_RESET_TOKEN` to a random string on Railway, then
# POST to this endpoint with that token + a new password. The endpoint never
# echoes the token back, and replies with a clear, debuggable JSON result so
# we can tell whether the env var is missing, the token mismatched, or the
# admin user record is in an unexpected state.
#
# Disable after use by deleting the `ADMIN_RESET_TOKEN` env var on Railway —
# the endpoint will then fail closed for everyone.
import os as _os
from models import LoginIn as _LoginIn  # noqa: F401 (avoid duplicate import shadow)


class _AdminResetIn(BaseModel):
    token: str
    new_password: str
    email: str | None = None  # defaults to ADMIN_EMAIL env / "admin@allsale.events"


@router.post("/admin-reset")
async def admin_reset(payload: _AdminResetIn):
    """Reset the admin password using a server-side shared secret token.

    Returns one of:
    - `{ok: true, ...}` on success
    - `{ok: false, reason: "..."}` with a human-readable diagnosis otherwise.
    Always responds with HTTP 200 so the frontend / curl can read the
    `reason` field reliably (no CORS or status-code juggling needed).
    """
    server_token = (_os.environ.get("ADMIN_RESET_TOKEN") or "").strip()
    if not server_token:
        return {"ok": False, "reason": "ADMIN_RESET_TOKEN env var is not set on the server"}
    if len(server_token) < 8:
        return {"ok": False, "reason": "ADMIN_RESET_TOKEN must be at least 8 characters"}
    if not payload.token or payload.token.strip() != server_token:
        return {"ok": False, "reason": "Token mismatch — paste the exact value from Railway"}
    if not payload.new_password or len(payload.new_password) < 6:
        return {"ok": False, "reason": "new_password must be at least 6 characters"}
    admin_email = (
        (payload.email or "").lower().strip()
        or (_os.environ.get("ADMIN_EMAIL") or "admin@allsale.events").lower().strip()
    )
    admin = await db.users.find_one({"email": admin_email})
    if not admin:
        return {"ok": False, "reason": f"No admin user found for {admin_email}"}
    if admin.get("role") != "admin":
        return {"ok": False, "reason": f"User {admin_email} is not an admin"}
    await db.users.update_one(
        {"email": admin_email},
        {"$set": {
            "password_hash": hash_password(payload.new_password),
            "password_reset_at": utc_now().isoformat(),
            "auth_provider": "password",
        }},
    )
    return {
        "ok": True,
        "email": admin_email,
        "message": "Password updated. Sign in now, then REMOVE the ADMIN_RESET_TOKEN env var on Railway.",
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
        # Stripe Connect onboarding status — surfaced so the organizer
        # dashboard can render the right CTA (Connect / Continue / Verified).
        "stripe_account_id": user.get("stripe_account_id"),
        "stripe_charges_enabled": bool(user.get("stripe_charges_enabled")),
        "stripe_payouts_enabled": bool(user.get("stripe_payouts_enabled")),
        "stripe_details_submitted": bool(user.get("stripe_details_submitted")),
    }


# ---------- Profile editing ----------
from pydantic import EmailStr


class ProfileUpdateIn(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    picture: str | None = None  # data URL or hosted URL
    notification_prefs: dict | None = None


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


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


@router.put("/change-password")
async def change_password(payload: ChangePasswordIn, request: Request, user: dict = Depends(get_current_user)):
    """Allow a logged-in user (partner, organizer, attendee, admin) to rotate
    their password.

    Verifies the current password hash, then sets the new one. Used primarily
    by marketing-lead partners who were issued a temporary password via the
    invitation email and want to replace it. Google-only accounts (no
    `password_hash`) cannot use this — they must keep using Google sign-in.
    """
    # `get_current_user` strips `password_hash` for safety — refetch it.
    full = await db.users.find_one({"user_id": user["user_id"]})
    if not full or not full.get("password_hash"):
        raise HTTPException(
            status_code=400,
            detail="This account signs in with Google — no password to change.",
        )
    if not payload.current_password or not payload.new_password:
        raise HTTPException(status_code=400, detail="Both passwords are required")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="New password must be different from current password")
    if not verify_password(payload.current_password, full["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    now = utc_now()
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "password_hash": hash_password(payload.new_password),
            "password_reset_at": now.isoformat(),
        }},
    )

    # Confirmation alert — security best practice. Fire-and-forget so a
    # Resend outage never breaks the password rotation flow itself.
    try:
        from emails import send_template_fireforget
        # Best-effort client fingerprint: first IP in X-Forwarded-For (proxy
        # chain), falling back to the direct connection IP. Truncated UA.
        xff = request.headers.get("x-forwarded-for") or ""
        ip = (xff.split(",")[0].strip() if xff else (request.client.host if request.client else ""))
        ua = (request.headers.get("user-agent") or "")[:140]
        send_template_fireforget(
            "password_changed_alert",
            full["email"],
            {
                "user_name": full.get("name") or "there",
                "changed_at": now.isoformat(),
                "changed_at_human": now.strftime("%a, %b %-d %Y · %-I:%M %p UTC"),
                "ip": ip,
                "user_agent": ua,
            },
            db,
        )
    except Exception:  # pragma: no cover — never break password change on email failure
        pass

    return {"ok": True, "message": "Password updated successfully"}


class GoogleCodeIn(BaseModel):
    code: str
    redirect_uri: str  # client-built via window.location.origin + "/auth/callback"


# Custom Google OAuth (authorization code flow) — uses the user's OWN
# Google Cloud Console Client ID + Secret so the consent screen shows
# `allsale.events`, not the platform's branding.
# REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
@router.post("/google-code")
async def google_code(payload: GoogleCodeIn, response: Response):
    import os as _os
    client_id = _os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = _os.environ.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")

    async with httpx.AsyncClient(timeout=15) as hc:
        token_resp = await hc.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": payload.code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": payload.redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=401, detail=f"Token exchange failed: {token_resp.text[:200]}")
        tok = token_resp.json()
        access_token = tok.get("access_token")
        if not access_token:
            raise HTTPException(status_code=401, detail="No access token returned")

        profile_resp = await hc.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if profile_resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Failed to fetch Google profile")
        data = profile_resp.json()

    email = (data.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(status_code=400, detail="No email returned from Google")
    name = data.get("name") or email.split("@")[0]
    picture = data.get("picture")

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
        new_user_doc = {
            "user_id": user_id, "email": email, "name": name, "picture": picture,
            "role": role, "created_at": utc_now().isoformat(), "auth_provider": "google",
        }
        await db.users.insert_one(new_user_doc)
        try:
            from routers.team import attach_pending_team_invites
            await attach_pending_team_invites(new_user_doc)
        except Exception:
            pass
        # Notify all admins about the new Google signup
        await _notify_admins_of_signup(new_user_doc)

    session_token = uuid.uuid4().hex + uuid.uuid4().hex
    await db.user_sessions.insert_one({
        "user_id": user_id, "session_token": session_token,
        "expires_at": (utc_now() + timedelta(days=SESSION_DAYS)).isoformat(),
        "created_at": utc_now().isoformat(),
    })
    set_session_cookie(response, session_token)
    # Also mint a JWT for the API client to put in Authorization headers
    jwt_token = create_access_token(user_id, email)
    set_jwt_cookie(response, jwt_token)
    # Re-read the user to pick up `phone` (and any other PATCHed fields) so
    # PhoneCaptureGate doesn't immediately re-prompt users who already saved
    # their number during a previous session.
    refreshed = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return {
        "user_id": user_id, "email": email, "name": name, "picture": picture,
        "role": role, "phone": (refreshed or {}).get("phone"), "token": jwt_token,
    }


# Emergent Google Auth — kept for legacy preview/dev fallback only.
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
        new_user_doc = {
            "user_id": user_id, "email": email, "name": name, "picture": picture,
            "role": role, "created_at": utc_now().isoformat(), "auth_provider": "google",
        }
        await db.users.insert_one(new_user_doc)
        # Attach any pending team invitations for this email
        try:
            from routers.team import attach_pending_team_invites
            await attach_pending_team_invites(new_user_doc)
        except Exception:
            pass
        # Notify all admins about the new Google signup (legacy Emergent path)
        await _notify_admins_of_signup(new_user_doc)

    await db.user_sessions.insert_one({
        "user_id": user_id, "session_token": session_token,
        "expires_at": (utc_now() + timedelta(days=SESSION_DAYS)).isoformat(),
        "created_at": utc_now().isoformat(),
    })
    set_session_cookie(response, session_token)
    # Re-read to surface `phone` so PhoneCaptureGate doesn't re-prompt users
    # who already saved their number during a previous session.
    refreshed = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return {
        "user_id": user_id, "email": email, "name": name, "picture": picture,
        "role": role, "phone": (refreshed or {}).get("phone"),
    }


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
    # Welcome them as a new organizer.
    try:
        from emails import send_template_fireforget
        send_template_fireforget(
            "organizer_welcome_1_signup",
            user.get("email"),
            {"organizer_name": user.get("name") or "there"},
            db,
        )
    except Exception:
        pass
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
