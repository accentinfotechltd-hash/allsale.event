"""CI-only seed script — creates the test users the pytest suite relies on.

Never called from production startup. Only invoked by the GitHub Actions
workflow (or manually) after the app starts against a fresh MongoDB.

Idempotent: uses `update_one(..., upsert=True)` so re-runs are safe.

Users created:
  - admin@allsale.events           (password: admin123) — role=admin
  - orgtester@allsale.events       (password: orgtest123) — role=organizer
  - Note: attendee@allsale.events is intentionally NOT seeded — the tests
    that need an attendee mint one on the fly via /auth/register.

Run from /app/backend:
    python scripts/seed_ci_test_users.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from core import db, hash_password, utc_now  # noqa: E402


TEST_USERS = [
    {
        "email": "admin@allsale.events",
        "password": "admin123",
        "name": "Allsale Events Admin",
        "role": "admin",
    },
    {
        "email": "orgtester@allsale.events",
        "password": "orgtest123",
        "name": "Org Tester",
        "role": "organizer",
    },
]


async def main() -> int:
    created = 0
    updated = 0
    for u in TEST_USERS:
        existing = await db.users.find_one({"email": u["email"]}, {"_id": 0, "user_id": 1})
        user_id = existing["user_id"] if existing else f"user_{uuid.uuid4().hex[:12]}"
        doc = {
            "user_id": user_id,
            "email": u["email"],
            "name": u["name"],
            "role": u["role"],
            "password_hash": hash_password(u["password"]),
            "picture": None,
            "created_at": utc_now().isoformat(),
            "auth_provider": "password",
        }
        r = await db.users.update_one(
            {"email": u["email"]},
            {"$set": doc},
            upsert=True,
        )
        if r.upserted_id is not None:
            created += 1
        elif r.modified_count:
            updated += 1
    print(f"[seed_ci_test_users] created={created} updated={updated} total={len(TEST_USERS)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
