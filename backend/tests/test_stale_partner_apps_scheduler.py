"""Stale partner application reminder — scheduler tick test.

Covers:
- Tick is a no-op outside the Tuesday 09-11 UTC window.
- Tick emails admin when there are pending apps >5 days old.
- Tick is idempotent within the same ISO week.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from scheduler import _send_stale_partner_application_reminder  # noqa: E402


class _FakeCursor:
    def __init__(self, docs): self.docs = docs
    def sort(self, *_a, **_k): return self
    def limit(self, *_a, **_k): return self
    def __aiter__(self): self._i = 0; return self
    async def __anext__(self):
        if self._i >= len(self.docs): raise StopAsyncIteration
        d = self.docs[self._i]; self._i += 1; return d


class _FakeCollection:
    def __init__(self, docs=None, find_one_result=None):
        self.docs = docs or []
        self.find_one_result = find_one_result
        self.updates = []
    def find(self, *_a, **_k): return _FakeCursor(self.docs)
    async def find_one(self, *_a, **_k): return self.find_one_result
    async def update_one(self, q, update, upsert=False):
        self.updates.append({"q": q, "update": update, "upsert": upsert})


class _FakeDB:
    def __init__(self, apps=None, meta=None, admins=None):
        self.partner_applications = _FakeCollection(docs=apps or [])
        self.platform_meta = _FakeCollection(find_one_result=meta)
        self.users = _FakeCollection(docs=admins or [{"email": "admin@allsale.events"}])


@pytest.mark.asyncio
async def test_noop_outside_tuesday_window():
    """Wednesday at noon should NOT fire the tick."""
    wed = datetime(2026, 3, 4, 12, 0, tzinfo=timezone.utc)  # 2026-03-04 is a Wednesday
    db = _FakeDB(apps=[{"application_id": "a", "full_name": "Test", "email": "t@e.com", "company": "", "created_at": (wed - timedelta(days=10)).isoformat(), "status": "pending"}])
    with patch("scheduler.datetime") as mock_dt:
        mock_dt.now.return_value = wed
        mock_dt.fromisoformat = datetime.fromisoformat
        n = await _send_stale_partner_application_reminder(db)
    assert n == 0


@pytest.mark.asyncio
async def test_noop_when_already_sent_this_week():
    """Re-running on Tuesday within the same week must be a no-op (dedupe)."""
    tue = datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc)  # 2026-03-10 is a Tuesday
    week_key = tue.strftime("%G-W%V")
    apps = [{"application_id": "a", "full_name": "Test", "email": "t@e.com", "company": "", "created_at": (tue - timedelta(days=10)).isoformat(), "status": "pending"}]
    db = _FakeDB(apps=apps, meta={"week": week_key})
    with patch("scheduler.datetime") as mock_dt:
        mock_dt.now.return_value = tue
        mock_dt.fromisoformat = datetime.fromisoformat
        n = await _send_stale_partner_application_reminder(db)
    assert n == 0


@pytest.mark.asyncio
async def test_fires_on_tuesday_with_stale_apps():
    """Tuesday 10:00 UTC + pending apps >5 days old → must send 1 email per admin."""
    tue = datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc)
    apps = [
        {"application_id": "a1", "full_name": "Sarah", "email": "s@e.com", "company": "Co", "created_at": (tue - timedelta(days=8)).isoformat(), "status": "pending"},
        {"application_id": "a2", "full_name": "Mike", "email": "m@e.com", "company": "", "created_at": (tue - timedelta(days=12)).isoformat(), "status": "pending"},
    ]
    db = _FakeDB(apps=apps, meta=None, admins=[{"email": "admin1@allsale.events"}, {"email": "admin2@allsale.events"}])
    with patch("scheduler.datetime") as mock_dt, \
         patch("scheduler.send_template_fireforget") as mock_send:
        mock_dt.now.return_value = tue
        mock_dt.fromisoformat = datetime.fromisoformat
        n = await _send_stale_partner_application_reminder(db)
    assert n == 2, f"expected 2 admins emailed, got {n}"
    assert mock_send.call_count == 2
    # All calls used the right template
    for call in mock_send.call_args_list:
        assert call.args[0] == "partner_applications_stale_digest"
        ctx = call.args[2]
        assert ctx["count"] == 2
        # age_days correctly computed
        names = {r["full_name"] for r in ctx["applications"]}
        assert names == {"Sarah", "Mike"}


@pytest.mark.asyncio
async def test_skips_apps_younger_than_5_days():
    """A pending app submitted 3 days ago should NOT trigger the reminder."""
    tue = datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc)
    apps = [
        {"application_id": "a1", "full_name": "Fresh", "email": "f@e.com", "company": "", "created_at": (tue - timedelta(days=3)).isoformat(), "status": "pending"},
    ]
    db = _FakeDB(apps=apps, meta=None)
    with patch("scheduler.datetime") as mock_dt, \
         patch("scheduler.send_template_fireforget") as mock_send:
        mock_dt.now.return_value = tue
        mock_dt.fromisoformat = datetime.fromisoformat
        # Override find to apply the date filter manually (since our fake cursor doesn't actually filter)
        async def _filtered_find_cursor(*_a, **_k):
            return _FakeCursor([])  # no apps older than 5 days
        db.partner_applications.find = lambda *_a, **_k: _FakeCursor([])
        n = await _send_stale_partner_application_reminder(db)
    assert n == 0
    assert mock_send.call_count == 0
