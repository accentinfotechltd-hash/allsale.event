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
import sys

from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

# Configure logging BEFORE importing modules that may use logger
# Force stdout so K8s log collector captures it (basicConfig defaults to stderr).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
    force=True,
)
logger = logging.getLogger("aura")

# Flush every log line immediately so we see startup progress even if the
# process crashes seconds later.
sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
sys.stderr.reconfigure(line_buffering=True)  # type: ignore[attr-defined]

# Early boot diagnostics — visible in K8s logs even if a later import crashes.
logger.info(f"[boot] python {sys.version.split()[0]}")
logger.info(f"[boot] MONGO_URL set: {'yes' if os.environ.get('MONGO_URL') else 'NO'}")
logger.info(f"[boot] DB_NAME: {os.environ.get('DB_NAME', '<missing>')}")
logger.info(f"[boot] JWT_SECRET set: {'yes' if os.environ.get('JWT_SECRET') else 'no'}")
logger.info(f"[boot] STRIPE_API_KEY set: {'yes' if os.environ.get('STRIPE_API_KEY') else 'no'}")
logger.info(f"[boot] RESEND_API_KEY set: {'yes' if os.environ.get('RESEND_API_KEY') else 'no'}")
logger.info(f"[boot] EMERGENT_LLM_KEY set: {'yes' if os.environ.get('EMERGENT_LLM_KEY') else 'no'}")

# Local imports (after dotenv + logging)
from core import db, mongo_client
from storage import init_storage
from seed import seed_demo


def _safe_import_router(module_path: str, attr: str = "router"):
    """Try to import a router module; return (router, None) on success or
    (None, error_msg) on failure. Used so a single optional integration
    (Stripe, LLM, Resend) failing to import in production doesn't crash
    the entire backend — the rest of the API stays up.
    """
    try:
        mod = __import__(module_path, fromlist=[attr])
        return getattr(mod, attr), None
    except Exception as e:  # pragma: no cover - hit only when deps missing
        logger.error(f"[boot] router import failed: {module_path} → {e}")
        return None, f"{module_path}: {e}"


# All routers loaded via safe wrapper — any module-level ImportError logs
# clearly and skips just that router instead of crashing the entire app.
_routers = {}
for _name in [
    "auth", "events", "bookings", "payments", "uploads", "admin",
    "organizer", "discount_codes", "payouts", "waitlist",
    "recommendations", "ws_seats", "analytics", "downloads", "team",
]:
    r, err = _safe_import_router(f"routers.{_name}")
    if r is not None:
        _routers[_name] = r
        logger.info(f"[boot] router loaded: {_name}")
    else:
        logger.error(f"[boot] router SKIPPED: {_name} ({err})")


app = FastAPI(title="Allsale Events Ticketing API", version="1.0")

# Mount loaded routers under /api
api = APIRouter(prefix="/api")
for _r in _routers.values():
    api.include_router(_r)


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

            # Always run seed_demo — it always seeds users (admin/organizer/attendee),
            # and only seeds demo events when SEED_DEMO is explicitly enabled.
            try:
                await seed_demo()
            except Exception as e:
                logger.warning(f"seed_demo failed (continuing): {e}")
            logger.info("Allsale Events backend ready")
        except Exception as boot_err:  # last-resort guard
            logger.error(f"Startup background task error: {boot_err}")

    # Schedule but don't await — health-check responds while this runs.
    asyncio.create_task(_heavy_startup())

    # Background scheduler: hourly reminders + weekly digest.
    try:
        from scheduler import scheduler_loop
        asyncio.create_task(scheduler_loop(db))
        logger.info("[boot] scheduler started")
    except Exception as sch_err:
        logger.error(f"[boot] scheduler failed to start: {sch_err}")

    logger.info("Allsale Events backend listening (background init running)")


@app.on_event("shutdown")
async def on_shutdown():
    mongo_client.close()
