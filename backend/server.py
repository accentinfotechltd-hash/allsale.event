"""AURA - Premium Event Ticketing Platform Backend.

Slim entrypoint: env load, FastAPI app, CORS, startup (indexes + storage + seed),
and router mounting. Endpoints live in routers/.
"""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import logging

from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

# Configure logging BEFORE importing modules that may use logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("aura")

# Local imports (after dotenv + logging)
from core import db, mongo_client
from storage import init_storage
from seed import seed_demo
from routers import auth as auth_router
from routers import events as events_router
from routers import bookings as bookings_router
from routers import payments as payments_router
from routers import uploads as uploads_router
from routers import admin as admin_router
from routers import organizer as organizer_router
from routers import discount_codes as discount_codes_router
from routers import payouts as payouts_router
from routers import waitlist as waitlist_router
from routers import recommendations as recommendations_router
from routers import ws_seats as ws_seats_router


app = FastAPI(title="AURA Event Ticketing API", version="1.0")

# Mount all routers under /api
api = APIRouter(prefix="/api")
api.include_router(auth_router.router)
api.include_router(events_router.router)
api.include_router(bookings_router.router)
api.include_router(payments_router.router)
api.include_router(uploads_router.router)
api.include_router(admin_router.router)
api.include_router(organizer_router.router)
api.include_router(discount_codes_router.router)
api.include_router(payouts_router.router)
api.include_router(waitlist_router.router)
api.include_router(recommendations_router.router)
api.include_router(ws_seats_router.router)


@api.get("/")
async def root():
    return {"name": "AURA Tickets API", "version": "1.0"}


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)
    await db.events.create_index("event_id", unique=True)
    await db.bookings.create_index("booking_id", unique=True)
    # Compound index for fast analytics aggregation (filters by event_id + status)
    await db.bookings.create_index([("event_id", 1), ("status", 1)], name="event_status_idx")
    # Index user_id for /me/bookings queries
    await db.bookings.create_index("user_id")
    await db.seat_holds.create_index("booking_id")
    await db.seat_holds.create_index("expires_at")
    await db.payment_transactions.create_index("session_id", unique=True)
    await db.user_sessions.create_index("session_token", unique=True)
    # Unique compound index for atomic seat reservation (no double-booking)
    await db.seat_reservations.create_index(
        [("event_id", 1), ("seat_id", 1)], unique=True, name="event_seat_unique"
    )
    await db.seat_reservations.create_index("booking_id")
    await db.uploaded_files.create_index("storage_path")
    await db.discount_codes.create_index([("created_by", 1), ("code", 1)], unique=True)
    await db.discount_codes.create_index("code")
    await db.email_logs.create_index([("created_at", -1)])
    await db.email_logs.create_index("status")
    await db.email_logs.create_index("template")
    await db.payouts.create_index("payout_id", unique=True)
    await db.payouts.create_index([("organizer_id", 1), ("status", 1)])
    await db.payouts.create_index("status")
    await db.platform_settings.create_index("key", unique=True)
    await db.bookings.create_index("payout_id")
    await db.waitlist_entries.create_index("waitlist_id", unique=True)
    # Unique compound: one "waiting" entry per (event, user) — duplicates rejected.
    await db.waitlist_entries.create_index(
        [("event_id", 1), ("user_id", 1), ("status", 1)], unique=True,
        partialFilterExpression={"status": "waiting"}, name="waitlist_unique_waiting",
    )
    await db.waitlist_entries.create_index([("event_id", 1), ("status", 1), ("requested_at", 1)])
    await db.waitlist_entries.create_index([("user_id", 1), ("status", 1)])
    await db.recommendation_cache.create_index("user_id", unique=True)
    await db.recommendation_cache.create_index([("expires_at", 1)])
    init_storage()
    await seed_demo()
    logger.info("AURA backend ready")


@app.on_event("shutdown")
async def on_shutdown():
    mongo_client.close()
