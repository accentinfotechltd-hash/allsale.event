"""Allsale Events - Premium Event Ticketing Platform Backend.

Slim entrypoint: env load, FastAPI app, CORS, startup (indexes + storage + seed),
and router mounting. Endpoints live in routers/.
"""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import logging
import os

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
from routers import analytics as analytics_router


app = FastAPI(title="Allsale Events Ticketing API", version="1.0")

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
api.include_router(analytics_router.router)


@api.get("/")
async def root():
    return {"name": "Allsale Events Tickets API", "version": "1.0"}


@api.get("/health")
async def health():
    """Liveness probe for uptime monitoring + load balancers."""
    try:
        await db.command("ping")
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}


app.include_router(api)

# CORS: production should set CORS_ORIGINS as a comma-separated list of origins
# (e.g. "https://events.allsale.co.nz,https://www.allsale.co.nz"). Falls back
# to "*" for local dev / preview environments.
_origins_env = os.environ.get("CORS_ORIGINS", "*")
_origins = [o.strip() for o in _origins_env.split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    """Fast, non-blocking startup. Heavy work (network calls to object storage,
    seeding, slow index creation) is dispatched as a background task so the
    HTTP listener binds immediately and health checks pass.
    """
    import asyncio

    async def _heavy_startup():
        try:
            # Indexes — idempotent, fast on a fresh DB but can be slow on a
            # large existing one. Wrapped in try/except so a single failure
            # doesn't block the rest.
            index_specs = [
                (db.users, "email", {"unique": True}),
                (db.users, "user_id", {"unique": True}),
                (db.events, "event_id", {"unique": True}),
                (db.bookings, "booking_id", {"unique": True}),
                (db.bookings, [("event_id", 1), ("status", 1)], {"name": "event_status_idx"}),
                (db.bookings, "user_id", {}),
                (db.seat_holds, "booking_id", {}),
                (db.seat_holds, "expires_at", {}),
                (db.payment_transactions, "session_id", {"unique": True}),
                (db.user_sessions, "session_token", {"unique": True}),
                (db.seat_reservations, [("event_id", 1), ("seat_id", 1)],
                 {"unique": True, "name": "event_seat_unique"}),
                (db.seat_reservations, "booking_id", {}),
                (db.uploaded_files, "storage_path", {}),
                (db.discount_codes, [("created_by", 1), ("code", 1)], {"unique": True}),
                (db.discount_codes, "code", {}),
                (db.email_logs, [("created_at", -1)], {}),
                (db.email_logs, "status", {}),
                (db.email_logs, "template", {}),
                (db.payouts, "payout_id", {"unique": True}),
                (db.payouts, [("organizer_id", 1), ("status", 1)], {}),
                (db.payouts, "status", {}),
                (db.platform_settings, "key", {"unique": True}),
                (db.bookings, "payout_id", {}),
                (db.waitlist_entries, "waitlist_id", {"unique": True}),
                (db.waitlist_entries, [("event_id", 1), ("user_id", 1), ("status", 1)],
                 {"unique": True, "partialFilterExpression": {"status": "waiting"},
                  "name": "waitlist_unique_waiting"}),
                (db.waitlist_entries,
                 [("event_id", 1), ("status", 1), ("requested_at", 1)], {}),
                (db.waitlist_entries, [("user_id", 1), ("status", 1)], {}),
                (db.recommendation_cache, "user_id", {"unique": True}),
                (db.recommendation_cache, [("expires_at", 1)], {}),
                (db.event_views, [("event_id", 1), ("at", -1)], {}),
            ]
            for col, key, opts in index_specs:
                try:
                    await col.create_index(key, **opts)
                except Exception as ix_err:
                    logger.warning(f"index create failed for {key}: {ix_err}")

            # Object storage — synchronous HTTPS call; run in a thread so the
            # event loop isn't blocked even if Emergent storage is slow.
            try:
                await asyncio.to_thread(init_storage)
            except Exception as e:
                logger.warning(f"init_storage skipped: {e}")

            # Seed demo data unless disabled.
            if os.environ.get("SEED_DEMO", "true").lower() not in ("false", "0", "no"):
                try:
                    await seed_demo()
                except Exception as e:
                    logger.warning(f"seed_demo failed (continuing): {e}")
            else:
                logger.info("SEED_DEMO disabled — skipping demo data seed")
            logger.info("Allsale Events backend ready")
        except Exception as boot_err:  # last-resort guard
            logger.error(f"Startup background task error: {boot_err}")

    # Schedule but don't await — health-check responds while this runs.
    asyncio.create_task(_heavy_startup())
    logger.info("Allsale Events backend listening (background init running)")


@app.on_event("shutdown")
async def on_shutdown():
    mongo_client.close()
