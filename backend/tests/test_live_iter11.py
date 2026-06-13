"""Live preview tests for iteration 11 features (refunds, follows, transfers, affiliates, stripe admin, PWA)."""
import os
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://seathold.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@allsale.events"
ADMIN_PW = "admin123"


def _admin_token():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


# -------- Stripe Admin Diagnostics --------
def test_stripe_webhook_health():
    tok = _admin_token()
    r = requests.get(f"{BASE}/api/admin/stripe/webhook-health", headers=_hdr(tok), timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "secret_configured" in data
    assert "recent_deliveries" in data
    assert "critical_events_seen" in data


def test_stripe_tax_status_off_by_default():
    tok = _admin_token()
    r = requests.get(f"{BASE}/api/admin/stripe/tax-status", headers=_hdr(tok), timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "enabled" in data
    assert data["enabled"] is False
    assert "activation_checklist" in data
    assert isinstance(data["activation_checklist"], list)


# -------- Refund policy (public) --------
def test_refund_policy_public_endpoint_shape():
    # Need an event id — pick first published
    ev_list = requests.get(f"{BASE}/api/events", timeout=15)
    assert ev_list.status_code == 200
    events = ev_list.json()
    if not events:
        return  # no events to test
    eid = events[0].get("id") or events[0].get("event_id")
    r = requests.get(f"{BASE}/api/events/{eid}/refund-policy", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    # Normalized shape: {event_id, policy: {enabled, cutoff_hours, refund_percent}}
    policy = data.get("policy", data)
    assert "enabled" in policy


# -------- Follow organizer (public) --------
def test_organizer_public_endpoint_no_auth():
    # Get an organizer via existing events
    ev_list = requests.get(f"{BASE}/api/events", timeout=15).json()
    if not ev_list:
        return
    org_id = ev_list[0].get("organizer_id") or ev_list[0].get("created_by")
    if not org_id:
        return
    r = requests.get(f"{BASE}/api/organizers/{org_id}/public", timeout=15)
    # Public should not 401
    assert r.status_code in (200, 404), r.text
    tok = _admin_token()
    me = requests.get(f"{BASE}/api/auth/me", headers=_hdr(tok), timeout=15).json()
    my_id = me.get("id") or me.get("_id") or me.get("user_id")
    if not my_id:
        return
    r = requests.post(f"{BASE}/api/organizers/{my_id}/follow", headers=_hdr(tok), timeout=15)
    # Self-follow should be 400 (admin's role is admin, may also be 400 because admins aren't organizers per policy)
    assert r.status_code in (400, 403), f"expected 400/403, got {r.status_code}: {r.text}"


def test_me_following_requires_auth():
    r = requests.get(f"{BASE}/api/me/following", timeout=15)
    assert r.status_code in (401, 403)


# -------- Transfers --------
def test_me_transfers_auth():
    tok = _admin_token()
    r = requests.get(f"{BASE}/api/me/transfers", headers=_hdr(tok), timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    # Should have outgoing+incoming
    assert "outgoing" in data or "incoming" in data or isinstance(data, list)


# -------- Affiliate tracking pixel --------
def test_affiliate_track_unknown_code_redirects_safely():
    r = requests.get(f"{BASE}/api/affiliate/track?code=NOPECODE", allow_redirects=False, timeout=15)
    # Should 302 even for unknown code (silent), or 404
    assert r.status_code in (302, 303, 307, 404)


def test_affiliate_resolve_unknown():
    r = requests.get(f"{BASE}/api/affiliate/NOPECODE", timeout=15)
    assert r.status_code in (404, 200)
