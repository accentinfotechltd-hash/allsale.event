"""Regression: auth endpoints MUST echo `phone` in their response payload.

Bug: PhoneCaptureGate was firing right after every login because
POST /auth/login (and /register, /google-code, /google-session) returned a
user dict without `phone`. The frontend `setUser(data)` then overwrote the
auth-context user with a phone-less object — even when the DB record had a
phone — and the gate's `!user.phone` check immediately re-prompted.

Fix: include `phone` in every auth response. This test pins that contract.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

API_URL = os.environ.get("EXTERNAL_API_URL") or "http://localhost:8001"


def test_login_response_includes_phone():
    """Admin has a phone in DB — the login response must echo it back."""
    r = requests.post(
        f"{API_URL}/api/auth/login",
        json={"email": "admin@allsale.events", "password": "admin123"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "phone" in body, "login response missing `phone` key — PhoneCaptureGate will re-prompt"
    assert body["phone"], "login response has empty `phone` even though admin has one in DB"
    assert len(str(body["phone"]).strip()) >= 6


def test_register_response_includes_phone():
    """Registration always sets a phone (mandatory) — response must echo it."""
    email = f"phonetest_{uuid.uuid4().hex[:6]}@example.com"
    phone = "+64 21 555 8888"
    r = requests.post(
        f"{API_URL}/api/auth/register",
        json={
            "email": email,
            "password": "testpass123",
            "name": "Phone Test",
            "phone": phone,
            "role": "attendee",
        },
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("phone") == phone, (
        f"register response missing/mismatched phone: got {body.get('phone')!r}"
    )


def test_get_me_includes_phone_after_login():
    """Sanity: GET /auth/me also returns phone."""
    login = requests.post(
        f"{API_URL}/api/auth/login",
        json={"email": "admin@allsale.events", "password": "admin123"},
        timeout=10,
    )
    token = login.json()["token"]
    me = requests.get(
        f"{API_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert me.status_code == 200
    assert me.json().get("phone"), "GET /auth/me must echo phone for gate check"


def test_patch_me_phone_persists_and_returns_value():
    """PATCH /auth/me with a new phone updates the user and echoes it."""
    email = f"phonepatch_{uuid.uuid4().hex[:6]}@example.com"
    reg = requests.post(
        f"{API_URL}/api/auth/register",
        json={
            "email": email,
            "password": "testpass123",
            "name": "Phone Patch",
            "phone": "+64 21 555 7777",
            "role": "attendee",
        },
        timeout=10,
    )
    token = reg.json()["token"]

    new_phone = "+64 27 999 1111"
    patch = requests.patch(
        f"{API_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"phone": new_phone},
        timeout=10,
    )
    assert patch.status_code == 200
    assert patch.json().get("phone") == new_phone

    # And it actually persists for subsequent /auth/me calls.
    me = requests.get(
        f"{API_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert me.json().get("phone") == new_phone
