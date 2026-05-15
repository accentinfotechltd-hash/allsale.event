"""Emergent object storage client for AURA Tickets.

Persistent file storage replacing local disk. Files survive container restarts.
"""
import os
import logging
import requests
from typing import Tuple

logger = logging.getLogger("aura.storage")

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
APP_NAME = os.environ.get("APP_NAME", "aura-tickets")
_storage_key: str | None = None


def _key() -> str:
    """Return cached storage key; initialize if missing."""
    global _storage_key
    if _storage_key:
        return _storage_key
    emergent_key = os.environ.get("EMERGENT_LLM_KEY")
    if not emergent_key:
        raise RuntimeError("EMERGENT_LLM_KEY missing from environment")
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": emergent_key}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def init_storage() -> None:
    """Call once at app startup. Logs whether init succeeded."""
    try:
        _key()
        logger.info("Object storage initialized")
    except Exception as e:
        logger.error(f"Object storage init failed: {e}")


def put_object(path: str, data: bytes, content_type: str) -> dict:
    """Upload bytes to storage. Returns {path, size, etag}."""
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": _key(), "Content-Type": content_type},
        data=data,
        timeout=120,
    )
    if resp.status_code == 403:
        # Re-init once and retry
        global _storage_key
        _storage_key = None
        resp = requests.put(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": _key(), "Content-Type": content_type},
            data=data,
            timeout=120,
        )
    resp.raise_for_status()
    return resp.json()


def get_object(path: str) -> Tuple[bytes, str]:
    """Download bytes from storage. Returns (content_bytes, content_type)."""
    resp = requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": _key()},
        timeout=60,
    )
    if resp.status_code == 403:
        global _storage_key
        _storage_key = None
        resp = requests.get(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": _key()},
            timeout=60,
        )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
