"""Regression tests for the `notification_email` re-routing layer.

When a user record has `notification_email` set, every outbound email targeted
at their login `email` must be transparently routed to that override address
(and logged with `to_requested` preserving the original).

Both scenarios live in a single async block so the shared motor client stays
bound to one event loop.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db, utc_now  # noqa: E402
from emails import send_template  # noqa: E402


def test_notification_email_routing_end_to_end():
    """Cover both routed and pass-through paths in one asyncio.run so the
    motor client doesn't see a closed event loop between cases."""
    login_email = f"reroute_test_{uuid.uuid4().hex[:8]}@allsale.events"
    notify_email = "allsaletickets+reroute_test@gmail.com"
    plain_email = f"plain_test_{uuid.uuid4().hex[:8]}@allsale.events"

    async def _run():
        await db.users.insert_many([
            {
                "user_id": f"user_reroute_{uuid.uuid4().hex[:8]}",
                "email": login_email,
                "name": "Reroute Test",
                "role": "organizer",
                "created_at": utc_now().isoformat(),
                "notification_email": notify_email,
            },
            {
                "user_id": f"user_plain_{uuid.uuid4().hex[:8]}",
                "email": plain_email,
                "name": "Plain Test",
                "role": "attendee",
                "created_at": utc_now().isoformat(),
            },
        ])

        try:
            # Case A — override IS set → must re-route
            await send_template(
                "admin_blast", login_email,
                {"user_name": "Reroute Test", "subject": "Routing test", "body": "x"},
                db,
            )
            log_a = await db.email_logs.find_one(
                {"to_requested": login_email}, sort=[("created_at", -1)],
            )
            assert log_a is not None, "email_logs row not written for routed case"
            assert log_a.get("to") == notify_email, \
                f"expected re-route to {notify_email}, got {log_a.get('to')}"
            assert log_a.get("to_requested") == login_email

            # Case B — no override → straight passthrough
            await send_template(
                "admin_blast", plain_email,
                {"user_name": "Plain", "subject": "Passthrough", "body": "x"},
                db,
            )
            log_b = await db.email_logs.find_one(
                {"to_requested": plain_email}, sort=[("created_at", -1)],
            )
            assert log_b is not None, "email_logs row not written for passthrough case"
            assert log_b.get("to") == plain_email
            assert log_b.get("to_requested") == plain_email
        finally:
            await db.users.delete_many({"email": {"$in": [login_email, plain_email]}})
            await db.email_logs.delete_many(
                {"to_requested": {"$in": [login_email, plain_email]}}
            )

    asyncio.run(_run())
