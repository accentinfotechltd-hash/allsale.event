"""Emergency admin password reset — run from a Railway shell.

USAGE (from the Railway container shell, inside /app/backend):
    python scripts/reset_admin.py NEW_PASSWORD_HERE

It bypasses every env-var pipeline (Railway/Docker variable expansion, quote
stripping, etc.) and writes the hash directly to MongoDB with the exact
password string you pass on the command line.

Safe to run multiple times — idempotent re-hashing only.
After resetting, log in with `admin@allsale.events` + the password you typed.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Make `core` importable regardless of where you invoke the script from.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from core import db, hash_password, utc_now  # noqa: E402


async def reset(new_password: str) -> int:
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@allsale.events")
    print(f"[reset] target email: {admin_email}")
    print(f"[reset] new password length: {len(new_password)} chars")
    print(f"[reset] new password first 4 chars: {new_password[:4]!r}")
    user = await db.users.find_one({"email": admin_email}, {"_id": 0, "user_id": 1, "role": 1})
    if not user:
        print(f"[reset] ERROR: no user found with email={admin_email}.")
        print("[reset] Listing existing admin/organizer rows so you can pick the right one:")
        async for u in db.users.find({"role": {"$in": ["admin", "organizer"]}}, {"_id": 0, "email": 1, "role": 1}):
            print(f"   • {u.get('email')} ({u.get('role')})")
        return 2
    res = await db.users.update_one(
        {"email": admin_email},
        {"$set": {
            "password_hash": hash_password(new_password),
            "auth_provider": "password",
            "password_reset_at": utc_now().isoformat(),
        }},
    )
    print(f"[reset] matched={res.matched_count} modified={res.modified_count}")
    print(f"[reset] OK — log in with email={admin_email} and the password you just typed.")
    return 0


def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("USAGE: python scripts/reset_admin.py <new_password>")
        print("Example: python scripts/reset_admin.py Allsale2026")
        return 1
    new_password = sys.argv[1]
    return asyncio.run(reset(new_password))


if __name__ == "__main__":
    sys.exit(main())
