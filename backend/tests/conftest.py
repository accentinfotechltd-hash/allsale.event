"""Shared pytest fixtures for backend tests.

Motor (async MongoDB driver) caches its connection on the first event loop it
sees. We rely on pytest-asyncio's session-scoped loop (configured via
asyncio_default_test_loop_scope = session in pytest.ini) instead of defining
our own event_loop fixture — the latter conflicts with pytest-asyncio 1.x
when both compete for the loop.
"""
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
