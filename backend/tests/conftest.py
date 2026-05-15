"""Shared pytest fixtures for backend tests.

Motor (async MongoDB driver) caches its connection on the first event loop it
sees. Without a session-scoped event loop, each async test gets a fresh loop
and motor blows up on the second test with "Event loop is closed".
"""
import asyncio
from pathlib import Path

import pytest
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
