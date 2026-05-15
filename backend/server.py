"""AURA - Premium Event Ticketing Platform Backend.

A FastAPI backend for an Eventbrite/BookMyShow-style platform.
Features: Events, tiered tickets, interactive seat map, 10-min seat hold,
Stripe payments, QR e-tickets, organizer/admin dashboards.
"""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import uuid
import logging
import secrets
import asyncio
import base64
import io
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

import bcrypt
import jwt as pyjwt
import httpx
import qrcode
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Response, Query
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr, ConfigDict

from emergentintegrations.payments.stripe.checkout import (
    StripeCheckout,
    CheckoutSessionRequest,
)

# ----------------------------------------------------------------------------
# Config & Logging
# ----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("aura")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGO = "HS256"
STRIPE_API_KEY = os.environ["STRIPE_API_KEY"]
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]

HOLD_MINUTES = 10
SESSION_DAYS = 7

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
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


# ----------------------------------------------------------------------------
# Pydantic Models
# ----------------------------------------------------------------------------
class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "attendee"  # attendee | organizer


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email: str
    name: str
    role: str
    picture: Optional[str] = None


class EventIn(BaseModel):
    title: str
    description: str
    category: str
    venue: str
    city: str
    date: str  # ISO
    image_url: str
    banner_url: Optional[str] = None
    tiers: List[Dict[str, Any]] = Field(default_factory=list)  # [{name, price, capacity}]
    has_seatmap: bool = False
    seat_rows: int = 0
    seat_cols: int = 0
    seat_price: float = 0.0


class HoldIn(BaseModel):
    event_id: str
    tier_name: Optional[str] = None
    quantity: int = 1
    seats: Optional[List[str]] = None  # ["A-1","A-2"]


class CheckoutIn(BaseModel):
    booking_id: str
    origin_url: str


class GoogleSessionIn(BaseModel):
    session_id: str


# ----------------------------------------------------------------------------
# Auth Dependency
# ----------------------------------------------------------------------------
async def get_current_user(request: Request) -> dict:
    # 1) JWT cookie / Bearer header
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if token:
        try:
            payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
            user = await db.users.find_one({"user_id": payload["sub"]}, {"_id": 0, "password_hash": 0})
            if user:
                return user
        except pyjwt.PyJWTError:
            pass

    # 2) Emergent Google session cookie
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
                user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0, "password_hash": 0})
                if user:
                    return user

    raise HTTPException(status_code=401, detail="Not authenticated")


async def require_role(user: dict, *roles: str):
    if user.get("role") not in roles and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return user


# ----------------------------------------------------------------------------
# App + Router
# ----------------------------------------------------------------------------
app = FastAPI(title="AURA Event Ticketing API")
api = APIRouter(prefix="/api")


# ----------------------------------------------------------------------------
# Auth Endpoints
# ----------------------------------------------------------------------------
def _set_jwt_cookie(resp: Response, token: str):
    resp.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=SESSION_DAYS * 24 * 3600,
        path="/",
    )


def _set_session_cookie(resp: Response, token: str):
    resp.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=SESSION_DAYS * 24 * 3600,
        path="/",
    )


@api.post("/auth/register")
async def auth_register(payload: RegisterIn, response: Response):
    email = payload.email.lower().strip()
    existing = await db.users.find_one({"email": email})
    if existing:
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
    _set_jwt_cookie(response, token)
    return {
        "user_id": user_id,
        "email": email,
        "name": payload.name,
        "role": payload.role,
        "picture": None,
        "token": token,
    }


@api.post("/auth/login")
async def auth_login(payload: LoginIn, response: Response):
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not user.get("password_hash") or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(user["user_id"], email)
    _set_jwt_cookie(response, token)
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "picture": user.get("picture"),
        "token": token,
    }


@api.post("/auth/logout")
async def auth_logout(response: Response, request: Request):
    sess = request.cookies.get("session_token")
    if sess:
        await db.user_sessions.delete_one({"session_token": sess})
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


@api.get("/auth/me")
async def auth_me(user: dict = Depends(get_current_user)):
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "picture": user.get("picture"),
    }


# Emergent Google Auth — exchange session_id for session_token, fetch profile
# REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
@api.post("/auth/google-session")
async def auth_google_session(payload: GoogleSessionIn, response: Response):
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
            {"email": email},
            {"$set": {"name": name, "picture": picture}},
        )
        user_id = user["user_id"]
        role = user["role"]
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        role = "attendee"
        await db.users.insert_one(
            {
                "user_id": user_id,
                "email": email,
                "name": name,
                "picture": picture,
                "role": role,
                "created_at": utc_now().isoformat(),
                "auth_provider": "google",
            }
        )

    # Store session
    await db.user_sessions.insert_one(
        {
            "user_id": user_id,
            "session_token": session_token,
            "expires_at": (utc_now() + timedelta(days=SESSION_DAYS)).isoformat(),
            "created_at": utc_now().isoformat(),
        }
    )
    _set_session_cookie(response, session_token)
    return {
        "user_id": user_id,
        "email": email,
        "name": name,
        "picture": picture,
        "role": role,
    }


# ----------------------------------------------------------------------------
# Events
# ----------------------------------------------------------------------------
@api.get("/events")
async def list_events(
    q: Optional[str] = None,
    category: Optional[str] = None,
    city: Optional[str] = None,
    limit: int = 50,
):
    query: Dict[str, Any] = {"status": {"$in": ["approved", "published"]}}
    if q:
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"venue": {"$regex": q, "$options": "i"}},
        ]
    if category:
        query["category"] = category
    if city:
        query["city"] = {"$regex": city, "$options": "i"}
    cursor = db.events.find(query, {"_id": 0}).sort("date", 1).limit(limit)
    return [event_to_public(e) async for e in cursor]


@api.get("/events/featured")
async def featured_events():
    cursor = db.events.find(
        {"status": {"$in": ["approved", "published"]}, "featured": True},
        {"_id": 0},
    ).limit(6)
    items = [event_to_public(e) async for e in cursor]
    if not items:
        cursor = db.events.find({"status": {"$in": ["approved", "published"]}}, {"_id": 0}).limit(6)
        items = [event_to_public(e) async for e in cursor]
    return items


@api.get("/events/categories")
async def event_categories():
    return [
        {"id": "music", "name": "Music", "image": "https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=800"},
        {"id": "comedy", "name": "Comedy", "image": "https://images.unsplash.com/photo-1527224538127-2104bb71c51b?w=800"},
        {"id": "sports", "name": "Sports", "image": "https://images.unsplash.com/photo-1471295253337-3ceaaedca402?w=800"},
        {"id": "theater", "name": "Theater", "image": "https://images.unsplash.com/photo-1503095396549-807759245b35?w=800"},
        {"id": "tech", "name": "Tech & Conferences", "image": "https://images.unsplash.com/photo-1540575467063-178a50c2df87?w=800"},
        {"id": "workshops", "name": "Workshops", "image": "https://images.unsplash.com/photo-1552581234-26160f608093?w=800"},
        {"id": "festivals", "name": "Festivals", "image": "https://images.unsplash.com/photo-1459749411175-04bf5292ceea?w=800"},
        {"id": "arts", "name": "Arts & Culture", "image": "https://images.unsplash.com/photo-1547891654-e66ed7ebb968?w=800"},
    ]


@api.get("/events/{event_id}")
async def get_event(event_id: str):
    e = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="Event not found")
    # Compute live seat status if seatmap
    if e.get("has_seatmap"):
        now = utc_now()
        held = await db.seat_holds.find(
            {"event_id": event_id, "expires_at": {"$gte": now.isoformat()}},
            {"_id": 0},
        ).to_list(2000)
        booked_seats = set()
        async for b in db.bookings.find(
            {"event_id": event_id, "status": {"$in": ["paid", "confirmed"]}},
            {"_id": 0},
        ):
            booked_seats.update(b.get("seats", []) or [])
        held_seats = set()
        for h in held:
            held_seats.update(h.get("seats", []) or [])
        e["booked_seats"] = list(booked_seats)
        e["held_seats"] = list(held_seats)
    return event_to_public(e)


@api.post("/events")
async def create_event(payload: EventIn, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    doc = {
        "event_id": event_id,
        "organizer_id": user["user_id"],
        "organizer_name": user["name"],
        "title": payload.title,
        "description": payload.description,
        "category": payload.category,
        "venue": payload.venue,
        "city": payload.city,
        "date": payload.date,
        "image_url": payload.image_url,
        "banner_url": payload.banner_url or payload.image_url,
        "tiers": payload.tiers,
        "has_seatmap": payload.has_seatmap,
        "seat_rows": payload.seat_rows,
        "seat_cols": payload.seat_cols,
        "seat_price": payload.seat_price,
        "status": "approved" if user.get("role") == "admin" else "pending",
        "featured": False,
        "created_at": utc_now().isoformat(),
    }
    await db.events.insert_one(doc)
    return event_to_public(doc)


# ----------------------------------------------------------------------------
# Bookings & Seat Hold
# ----------------------------------------------------------------------------
@api.post("/bookings/hold")
async def create_hold(payload: HoldIn, user: dict = Depends(get_current_user)):
    event = await db.events.find_one({"event_id": payload.event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    expires = utc_now() + timedelta(minutes=HOLD_MINUTES)
    booking_id = f"bkg_{uuid.uuid4().hex[:12]}"

    if event.get("has_seatmap"):
        seats = payload.seats or []
        if not seats:
            raise HTTPException(status_code=400, detail="No seats selected")

        # Check seat availability atomically
        now = utc_now()
        booked = set()
        async for b in db.bookings.find(
            {"event_id": payload.event_id, "status": {"$in": ["paid", "confirmed"]}},
            {"_id": 0},
        ):
            booked.update(b.get("seats", []) or [])
        held = []
        async for h in db.seat_holds.find(
            {"event_id": payload.event_id, "expires_at": {"$gte": now.isoformat()}},
            {"_id": 0},
        ):
            held.extend(h.get("seats", []) or [])
        held_set = set(held)
        unavailable = [s for s in seats if s in booked or s in held_set]
        if unavailable:
            raise HTTPException(status_code=409, detail=f"Seats unavailable: {unavailable}")

        amount = round(event.get("seat_price", 0.0) * len(seats), 2)
        tier_name = "Seat Selection"
        quantity = len(seats)
    else:
        tier = next((t for t in event.get("tiers", []) if t.get("name") == payload.tier_name), None)
        if not tier:
            raise HTTPException(status_code=400, detail="Invalid tier")
        quantity = payload.quantity
        if quantity < 1 or quantity > 10:
            raise HTTPException(status_code=400, detail="Quantity 1-10")
        # Check capacity vs paid bookings + active holds for this tier
        sold = 0
        async for b in db.bookings.find(
            {"event_id": payload.event_id, "tier_name": payload.tier_name, "status": {"$in": ["paid", "confirmed"]}},
            {"_id": 0},
        ):
            sold += b.get("quantity", 0)
        held_qty = 0
        async for h in db.seat_holds.find(
            {"event_id": payload.event_id, "tier_name": payload.tier_name, "expires_at": {"$gte": utc_now().isoformat()}},
            {"_id": 0},
        ):
            held_qty += h.get("quantity", 0)
        if sold + held_qty + quantity > tier.get("capacity", 0):
            raise HTTPException(status_code=409, detail="Sold out for this tier")
        amount = round(tier["price"] * quantity, 2)
        tier_name = payload.tier_name
        seats = []

    hold_doc = {
        "booking_id": booking_id,
        "event_id": payload.event_id,
        "user_id": user["user_id"],
        "tier_name": tier_name,
        "quantity": quantity,
        "seats": seats,
        "expires_at": expires.isoformat(),
        "created_at": utc_now().isoformat(),
    }
    await db.seat_holds.insert_one(hold_doc)

    booking_doc = {
        "booking_id": booking_id,
        "event_id": payload.event_id,
        "event_title": event["title"],
        "event_date": event["date"],
        "event_venue": event["venue"],
        "event_image": event["image_url"],
        "user_id": user["user_id"],
        "user_email": user["email"],
        "user_name": user["name"],
        "tier_name": tier_name,
        "quantity": quantity,
        "seats": seats,
        "amount": amount,
        "currency": "usd",
        "status": "pending",
        "hold_expires_at": expires.isoformat(),
        "created_at": utc_now().isoformat(),
    }
    await db.bookings.insert_one(booking_doc)

    return booking_to_public(booking_doc)


@api.get("/bookings/{booking_id}")
async def get_booking(booking_id: str, user: dict = Depends(get_current_user)):
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Booking not found")
    if b["user_id"] != user["user_id"] and user.get("role") not in ("admin",):
        raise HTTPException(status_code=403, detail="Forbidden")
    if b.get("status") == "paid" and not b.get("qr_code"):
        qr_payload = f"AURA|{b['booking_id']}|{b['event_id']}|{b['user_id']}"
        b["qr_code"] = gen_qr_data_url(qr_payload)
        await db.bookings.update_one({"booking_id": booking_id}, {"$set": {"qr_code": b["qr_code"]}})
    return booking_to_public(b)


@api.get("/me/bookings")
async def my_bookings(user: dict = Depends(get_current_user)):
    items = []
    async for b in db.bookings.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1):
        items.append(b)
    return items


# ----------------------------------------------------------------------------
# Stripe Checkout
# ----------------------------------------------------------------------------
@api.post("/checkout/session")
async def checkout_session(payload: CheckoutIn, request: Request, user: dict = Depends(get_current_user)):
    booking = await db.bookings.find_one({"booking_id": payload.booking_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    if booking["status"] == "paid":
        raise HTTPException(status_code=400, detail="Already paid")

    # Check hold still active
    exp = booking["hold_expires_at"]
    if isinstance(exp, str):
        exp = datetime.fromisoformat(exp)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < utc_now():
        raise HTTPException(status_code=410, detail="Hold expired")

    host_url = str(request.base_url)
    webhook_url = f"{host_url}api/webhook/stripe"
    stripe = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)

    success_url = f"{payload.origin_url}/checkout/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{payload.origin_url}/checkout/{payload.booking_id}"
    req = CheckoutSessionRequest(
        amount=float(booking["amount"]),
        currency="usd",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "booking_id": booking["booking_id"],
            "event_id": booking["event_id"],
            "user_id": user["user_id"],
        },
    )
    session = await stripe.create_checkout_session(req)

    await db.payment_transactions.insert_one(
        {
            "session_id": session.session_id,
            "booking_id": booking["booking_id"],
            "user_id": user["user_id"],
            "amount": booking["amount"],
            "currency": "usd",
            "metadata": req.metadata,
            "payment_status": "pending",
            "status": "initiated",
            "created_at": utc_now().isoformat(),
        }
    )
    return {"url": session.url, "session_id": session.session_id}


@api.get("/checkout/status/{session_id}")
async def checkout_status(session_id: str, user: dict = Depends(get_current_user)):
    tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="Tx not found")
    if tx["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    # If already final, just return
    if tx["payment_status"] in ("paid", "expired", "failed"):
        return {"status": tx["status"], "payment_status": tx["payment_status"], "booking_id": tx["booking_id"]}

    stripe = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url="")
    s = await stripe.get_checkout_status(session_id)
    new_status = s.status
    new_pay = s.payment_status
    await db.payment_transactions.update_one(
        {"session_id": session_id},
        {"$set": {"status": new_status, "payment_status": new_pay, "updated_at": utc_now().isoformat()}},
    )

    if new_pay == "paid" and tx["payment_status"] != "paid":
        # Mark booking paid (atomic guard)
        result = await db.bookings.update_one(
            {"booking_id": tx["booking_id"], "status": {"$ne": "paid"}},
            {"$set": {"status": "paid", "paid_at": utc_now().isoformat()}},
        )
        if result.modified_count > 0:
            # Remove hold
            await db.seat_holds.delete_many({"booking_id": tx["booking_id"]})
            # Generate QR
            qr_payload = f"AURA|{tx['booking_id']}"
            await db.bookings.update_one(
                {"booking_id": tx["booking_id"]},
                {"$set": {"qr_code": gen_qr_data_url(qr_payload)}},
            )
            logger.info(f"[EMAIL MOCKED] Booking confirmation sent to {tx['user_id']} for {tx['booking_id']}")

    return {"status": new_status, "payment_status": new_pay, "booking_id": tx["booking_id"]}


@api.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    body = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    stripe = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url="")
    try:
        evt = await stripe.handle_webhook(body, sig)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"ok": False}
    if evt.payment_status == "paid" and evt.session_id:
        booking_id = (evt.metadata or {}).get("booking_id")
        if booking_id:
            result = await db.bookings.update_one(
                {"booking_id": booking_id, "status": {"$ne": "paid"}},
                {"$set": {"status": "paid", "paid_at": utc_now().isoformat()}},
            )
            if result.modified_count > 0:
                await db.seat_holds.delete_many({"booking_id": booking_id})
                qr_payload = f"AURA|{booking_id}"
                await db.bookings.update_one(
                    {"booking_id": booking_id},
                    {"$set": {"qr_code": gen_qr_data_url(qr_payload)}},
                )
                await db.payment_transactions.update_one(
                    {"session_id": evt.session_id},
                    {"$set": {"payment_status": "paid", "status": "complete"}},
                )
    return {"ok": True}


# ----------------------------------------------------------------------------
# Organizer Dashboard
# ----------------------------------------------------------------------------
@api.get("/organizer/events")
async def org_events(user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    cursor = db.events.find({"organizer_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1)
    return [event_to_public(e) async for e in cursor]


@api.get("/organizer/analytics")
async def org_analytics(user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    events = await db.events.find({"organizer_id": user["user_id"]}, {"_id": 0}).to_list(500)
    event_ids = [e["event_id"] for e in events]
    bookings = []
    async for b in db.bookings.find(
        {"event_id": {"$in": event_ids}, "status": "paid"},
        {"_id": 0},
    ):
        bookings.append(b)
    total_revenue = sum(b.get("amount", 0) for b in bookings)
    tickets_sold = sum(b.get("quantity", 0) for b in bookings)

    # Group by event
    per_event = {}
    for b in bookings:
        eid = b["event_id"]
        if eid not in per_event:
            per_event[eid] = {"event_id": eid, "title": b["event_title"], "revenue": 0, "tickets": 0}
        per_event[eid]["revenue"] += b.get("amount", 0)
        per_event[eid]["tickets"] += b.get("quantity", 0)

    # Time series last 14 days
    series = {}
    for b in bookings:
        d = (b.get("paid_at") or b.get("created_at", ""))[:10]
        series[d] = series.get(d, 0) + b.get("amount", 0)
    series_list = [{"date": k, "revenue": round(v, 2)} for k, v in sorted(series.items())][-14:]

    return {
        "total_revenue": round(total_revenue, 2),
        "tickets_sold": tickets_sold,
        "events_count": len(events),
        "per_event": list(per_event.values()),
        "series": series_list,
    }


@api.get("/organizer/events/{event_id}/attendees")
async def org_attendees(event_id: str, user: dict = Depends(get_current_user)):
    await require_role(user, "organizer", "admin")
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event["organizer_id"] != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    items = []
    async for b in db.bookings.find({"event_id": event_id, "status": "paid"}, {"_id": 0}):
        items.append(b)
    return items


# ----------------------------------------------------------------------------
# Admin
# ----------------------------------------------------------------------------
@api.get("/admin/events")
async def admin_events(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    cursor = db.events.find({}, {"_id": 0}).sort("created_at", -1)
    return [event_to_public(e) async for e in cursor]


@api.post("/admin/events/{event_id}/approve")
async def admin_approve(event_id: str, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    await db.events.update_one({"event_id": event_id}, {"$set": {"status": "approved"}})
    return {"ok": True}


@api.post("/admin/events/{event_id}/reject")
async def admin_reject(event_id: str, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    await db.events.update_one({"event_id": event_id}, {"$set": {"status": "rejected"}})
    return {"ok": True}


@api.post("/admin/events/{event_id}/feature")
async def admin_feature(event_id: str, user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    e = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    await db.events.update_one({"event_id": event_id}, {"$set": {"featured": not e.get("featured", False)}})
    return {"ok": True}


# ----------------------------------------------------------------------------
# Seed Demo Data
# ----------------------------------------------------------------------------
DEMO_EVENTS = [
    {
        "title": "Midnight Echoes — Live in Concert",
        "category": "music",
        "city": "Auckland",
        "venue": "Spark Arena",
        "description": "An immersive sonic journey under neon lights. Featuring Midnight Echoes with full band, strings, and synths. Doors at 7pm. Limited VIP front-row available.",
        "image_url": "https://images.unsplash.com/photo-1470229722913-7c0e2dbbafd3?w=1200",
        "banner_url": "https://images.unsplash.com/photo-1470229722913-7c0e2dbbafd3?w=1920",
        "tiers": [
            {"name": "Early Bird", "price": 45.0, "capacity": 100},
            {"name": "General", "price": 75.0, "capacity": 500},
            {"name": "VIP", "price": 180.0, "capacity": 50},
        ],
        "featured": True,
    },
    {
        "title": "Stand-Up Saturday: The Roast",
        "category": "comedy",
        "city": "Wellington",
        "venue": "The Opera House",
        "description": "Six of NZ's sharpest comedians take the stage for a no-holds-barred night of stand-up, improv, and live audience roasting.",
        "image_url": "https://images.unsplash.com/photo-1527224538127-2104bb71c51b?w=1200",
        "banner_url": "https://images.unsplash.com/photo-1527224538127-2104bb71c51b?w=1920",
        "has_seatmap": True,
        "seat_rows": 8,
        "seat_cols": 12,
        "seat_price": 55.0,
        "tiers": [],
        "featured": True,
    },
    {
        "title": "AllBlacks vs Wallabies — Bledisloe Cup",
        "category": "sports",
        "city": "Auckland",
        "venue": "Eden Park",
        "description": "The biggest rivalry in rugby returns. Witness history at Eden Park as the All Blacks battle the Wallabies for the Bledisloe Cup.",
        "image_url": "https://images.unsplash.com/photo-1517649763962-0c623066013b?w=1200",
        "banner_url": "https://images.unsplash.com/photo-1517649763962-0c623066013b?w=1920",
        "tiers": [
            {"name": "General", "price": 95.0, "capacity": 2000},
            {"name": "Premium", "price": 220.0, "capacity": 400},
            {"name": "Corporate Box", "price": 650.0, "capacity": 20},
        ],
        "featured": True,
    },
    {
        "title": "Hamilton — The Musical",
        "category": "theater",
        "city": "Auckland",
        "venue": "Civic Theatre",
        "description": "The award-winning Broadway musical comes to Auckland for a limited season. A revolutionary story told through hip-hop, R&B, and pop.",
        "image_url": "https://images.unsplash.com/photo-1503095396549-807759245b35?w=1200",
        "banner_url": "https://images.unsplash.com/photo-1503095396549-807759245b35?w=1920",
        "has_seatmap": True,
        "seat_rows": 10,
        "seat_cols": 14,
        "seat_price": 120.0,
        "tiers": [],
        "featured": False,
    },
    {
        "title": "Future//Stack — Devs Conference 2026",
        "category": "tech",
        "city": "Wellington",
        "venue": "TSB Arena",
        "description": "Two days of talks, workshops, and demos from the world's leading developers. Topics: AI, edge computing, Rust, distributed systems.",
        "image_url": "https://images.unsplash.com/photo-1540575467063-178a50c2df87?w=1200",
        "banner_url": "https://images.unsplash.com/photo-1540575467063-178a50c2df87?w=1920",
        "tiers": [
            {"name": "Early Bird", "price": 199.0, "capacity": 200},
            {"name": "General", "price": 349.0, "capacity": 1000},
            {"name": "VIP Pass", "price": 899.0, "capacity": 50},
        ],
        "featured": True,
    },
    {
        "title": "Ceramics Studio Weekend",
        "category": "workshops",
        "city": "Christchurch",
        "venue": "The Clay House",
        "description": "Two days of hands-on ceramics with master potter Lena Voss. All materials included. Take home three finished pieces.",
        "image_url": "https://images.unsplash.com/photo-1565193566173-7a0ee3dbe261?w=1200",
        "banner_url": "https://images.unsplash.com/photo-1565193566173-7a0ee3dbe261?w=1920",
        "tiers": [
            {"name": "Workshop Pass", "price": 145.0, "capacity": 20},
        ],
        "featured": False,
    },
    {
        "title": "Splendour Open Air Festival",
        "category": "festivals",
        "city": "Queenstown",
        "venue": "Lake Wakatipu Grounds",
        "description": "Three stages, 40+ artists, sunset over the lake. The South Island's biggest open-air music festival returns for its 8th year.",
        "image_url": "https://images.unsplash.com/photo-1459749411175-04bf5292ceea?w=1200",
        "banner_url": "https://images.unsplash.com/photo-1459749411175-04bf5292ceea?w=1920",
        "tiers": [
            {"name": "Day Pass", "price": 89.0, "capacity": 3000},
            {"name": "Weekend Pass", "price": 199.0, "capacity": 2000},
            {"name": "VIP Camping", "price": 499.0, "capacity": 100},
        ],
        "featured": True,
    },
    {
        "title": "Modernism Reframed — Art Exhibit",
        "category": "arts",
        "city": "Auckland",
        "venue": "Auckland Art Gallery",
        "description": "A curated retrospective of 20th-century modernist works. Guided tours hourly. Wine reception included.",
        "image_url": "https://images.unsplash.com/photo-1547891654-e66ed7ebb968?w=1200",
        "banner_url": "https://images.unsplash.com/photo-1547891654-e66ed7ebb968?w=1920",
        "tiers": [
            {"name": "General", "price": 28.0, "capacity": 500},
            {"name": "Member", "price": 18.0, "capacity": 200},
        ],
        "featured": False,
    },
]


async def seed_demo():
    # Admin user
    if not await db.users.find_one({"email": ADMIN_EMAIL}):
        await db.users.insert_one(
            {
                "user_id": f"user_{uuid.uuid4().hex[:12]}",
                "email": ADMIN_EMAIL,
                "name": "AURA Admin",
                "role": "admin",
                "password_hash": hash_password(ADMIN_PASSWORD),
                "picture": None,
                "created_at": utc_now().isoformat(),
                "auth_provider": "password",
            }
        )
    # Demo organizer
    org = await db.users.find_one({"email": "organizer@aura.events"})
    if not org:
        org_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one(
            {
                "user_id": org_id,
                "email": "organizer@aura.events",
                "name": "AURA Productions",
                "role": "organizer",
                "password_hash": hash_password("organizer123"),
                "picture": None,
                "created_at": utc_now().isoformat(),
                "auth_provider": "password",
            }
        )
    else:
        org_id = org["user_id"]

    # Demo attendee
    if not await db.users.find_one({"email": "attendee@aura.events"}):
        await db.users.insert_one(
            {
                "user_id": f"user_{uuid.uuid4().hex[:12]}",
                "email": "attendee@aura.events",
                "name": "Demo Attendee",
                "role": "attendee",
                "password_hash": hash_password("attendee123"),
                "picture": None,
                "created_at": utc_now().isoformat(),
                "auth_provider": "password",
            }
        )

    # Events
    if await db.events.count_documents({}) == 0:
        for i, e in enumerate(DEMO_EVENTS):
            date = utc_now() + timedelta(days=15 + i * 7)
            doc = {
                "event_id": f"evt_{uuid.uuid4().hex[:12]}",
                "organizer_id": org_id,
                "organizer_name": "AURA Productions",
                "title": e["title"],
                "description": e["description"],
                "category": e["category"],
                "venue": e["venue"],
                "city": e["city"],
                "date": date.isoformat(),
                "image_url": e["image_url"],
                "banner_url": e["banner_url"],
                "tiers": e.get("tiers", []),
                "has_seatmap": e.get("has_seatmap", False),
                "seat_rows": e.get("seat_rows", 0),
                "seat_cols": e.get("seat_cols", 0),
                "seat_price": e.get("seat_price", 0.0),
                "status": "approved",
                "featured": e.get("featured", False),
                "created_at": utc_now().isoformat(),
            }
            await db.events.insert_one(doc)
        logger.info("Seeded demo events")


@app.on_event("startup")
async def on_startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)
    await db.events.create_index("event_id", unique=True)
    await db.bookings.create_index("booking_id", unique=True)
    await db.seat_holds.create_index("booking_id")
    await db.seat_holds.create_index("expires_at")
    await db.payment_transactions.create_index("session_id", unique=True)
    await db.user_sessions.create_index("session_token", unique=True)
    await seed_demo()
    logger.info("AURA backend ready")


@api.get("/")
async def root():
    return {"name": "AURA Tickets API", "version": "1.0"}


# Include router + CORS
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def on_shutdown():
    client.close()
