"""Iteration 7 tests:
- Movies category added (first of 9)
- 2 demo cinema events seeded with seatmap+aisles
- Admin user management endpoints (list, search, role filter, status filter, stats)
- Role change, suspend/unsuspend with self-protection & invalid role
- Suspended user login -> 403; stale JWT -> 403; unsuspend -> works again
- Legacy users without 'active' field treated as active

DEPRECATED: uses stale seed accounts (organizer@allsale.events etc.) that
were removed in the Feb 2026 reset. Admin-user-management is now covered by
tests/test_admin_users_*.py. Kept for archaeology.
"""
import pytest

pytestmark = pytest.mark.skip(
    reason="superseded — stale seed credentials no longer in DB"
)

import os  # noqa: E402
import uuid  # noqa: E402,F401
import requests  # noqa: E402,F401

# Load BASE_URL from frontend env if env var missing (consistent with iter5)
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip()
                    break
    except Exception:
        pass
BASE_URL = (BASE_URL or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

ADMIN = {"email": "admin@allsale.events", "password": "admin123"}
ORG = {"email": "organizer@allsale.events", "password": "organizer123"}
ATT = {"email": "attendee@allsale.events", "password": "attendee123"}


def _login(creds):
    r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    return r.json()["token"], r.json()["user_id"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def admin_auth():
    t, uid = _login(ADMIN)
    return {"token": t, "user_id": uid}


@pytest.fixture(scope="module")
def org_auth():
    t, uid = _login(ORG)
    return {"token": t, "user_id": uid}


@pytest.fixture(scope="module")
def att_auth():
    t, uid = _login(ATT)
    return {"token": t, "user_id": uid}


# ---------- Movies category & seeded events ----------
class TestMoviesCategory:
    def test_categories_includes_movies_first(self):
        r = requests.get(f"{BASE_URL}/api/events/categories", timeout=15)
        assert r.status_code == 200
        cats = r.json()
        assert isinstance(cats, list) and len(cats) == 9, f"Expected 9 categories, got {len(cats)}"
        assert cats[0]["id"] == "movies", f"Expected movies first, got {cats[0]['id']}"

    def test_movies_events_seeded_with_seatmap(self):
        r = requests.get(f"{BASE_URL}/api/events?category=movies", timeout=15)
        assert r.status_code == 200
        evs = r.json()
        assert isinstance(evs, list) and len(evs) == 2, f"Expected 2 movie events, got {len(evs)}"
        titles = [e["title"] for e in evs]
        assert any("Dune" in t for t in titles), f"Dune event missing in {titles}"
        assert any("Ghibli" in t or "Spirited" in t for t in titles), f"Ghibli event missing in {titles}"
        for e in evs:
            assert e.get("has_seatmap") is True, f"{e['title']} missing has_seatmap"
            d = requests.get(f"{BASE_URL}/api/events/{e['event_id']}", timeout=15).json()
            # Aisles can be top-level or nested inside seatmap
            aisles = d.get("aisles") or (d.get("seatmap") or {}).get("aisles") or []
            assert aisles, f"{e['title']} aisles empty"


# ---------- Admin auth gating ----------
class TestAdminAuthGating:
    def test_users_list_requires_admin_role_403_for_attendee(self, att_auth):
        r = requests.get(f"{BASE_URL}/api/admin/users", headers=_h(att_auth["token"]), timeout=15)
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"

    def test_users_list_requires_admin_role_403_for_organizer(self, org_auth):
        r = requests.get(f"{BASE_URL}/api/admin/users", headers=_h(org_auth["token"]), timeout=15)
        assert r.status_code == 403

    def test_users_stats_403_for_non_admin(self, att_auth):
        r = requests.get(f"{BASE_URL}/api/admin/users/stats", headers=_h(att_auth["token"]), timeout=15)
        assert r.status_code == 403

    def test_users_list_no_auth_401(self):
        r = requests.get(f"{BASE_URL}/api/admin/users", timeout=15)
        assert r.status_code in (401, 403)


# ---------- Admin user list / filters / stats ----------
class TestAdminUserList:
    def test_list_users(self, admin_auth):
        r = requests.get(f"{BASE_URL}/api/admin/users", headers=_h(admin_auth["token"]), timeout=15)
        assert r.status_code == 200
        users = r.json()
        assert isinstance(users, list) and len(users) >= 14
        for u in users:
            assert "password_hash" not in u, "password_hash leaked!"
            assert "_id" not in u
            assert "bookings_count" in u and isinstance(u["bookings_count"], int)
            assert "events_count" in u and isinstance(u["events_count"], int)
            assert "active" in u  # normalized

    def test_attendee_bookings_count_positive(self, admin_auth, att_auth):
        r = requests.get(f"{BASE_URL}/api/admin/users", headers=_h(admin_auth["token"]), timeout=15)
        users = r.json()
        att = next((u for u in users if u["user_id"] == att_auth["user_id"]), None)
        assert att is not None
        assert att["bookings_count"] >= 1, f"attendee should have demo bookings, got {att['bookings_count']}"

    def test_search_by_q(self, admin_auth):
        r = requests.get(
            f"{BASE_URL}/api/admin/users?q=organizer",
            headers=_h(admin_auth["token"]), timeout=15,
        )
        assert r.status_code == 200
        users = r.json()
        assert len(users) >= 1
        for u in users:
            hay = (u.get("email", "") + " " + u.get("name", "")).lower()
            assert "organizer" in hay, f"unexpected user in q=organizer: {u['email']}"

    def test_filter_by_role_organizer(self, admin_auth):
        r = requests.get(
            f"{BASE_URL}/api/admin/users?role=organizer",
            headers=_h(admin_auth["token"]), timeout=15,
        )
        assert r.status_code == 200
        users = r.json()
        assert len(users) >= 1
        for u in users:
            assert u["role"] == "organizer"

    def test_filter_active_true_includes_legacy(self, admin_auth):
        r = requests.get(
            f"{BASE_URL}/api/admin/users?active=true",
            headers=_h(admin_auth["token"]), timeout=15,
        )
        assert r.status_code == 200
        users = r.json()
        # admin@allsale.events is legacy (no active field) -> must appear
        assert any(u["email"] == ADMIN["email"] for u in users)

    def test_filter_active_false(self, admin_auth):
        r = requests.get(
            f"{BASE_URL}/api/admin/users?active=false",
            headers=_h(admin_auth["token"]), timeout=15,
        )
        assert r.status_code == 200
        users = r.json()
        for u in users:
            assert u["active"] is False

    def test_user_stats(self, admin_auth):
        r = requests.get(f"{BASE_URL}/api/admin/users/stats", headers=_h(admin_auth["token"]), timeout=15)
        assert r.status_code == 200
        stats = r.json()
        assert "total" in stats and stats["total"] >= 14
        assert "by_role" in stats
        for role in ("attendee", "organizer", "admin"):
            assert role in stats["by_role"]
        assert stats["by_role"]["admin"] >= 1
        assert stats["by_role"]["organizer"] >= 1
        assert "suspended" in stats and stats["suspended"] >= 0


# ---------- Role changes ----------
def _register(name, role="attendee"):
    email = f"test_{uuid.uuid4().hex[:8]}@aura.example.com"
    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"name": name, "email": email, "password": "Pass123!", "role": role},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    j = r.json()
    return j["user_id"], email, j["token"]


class TestRoleChange:
    def test_change_role_valid(self, admin_auth):
        uid, email, _ = _register("TEST role target")
        r = requests.post(
            f"{BASE_URL}/api/admin/users/{uid}/role",
            json={"role": "organizer"}, headers=_h(admin_auth["token"]), timeout=15,
        )
        assert r.status_code == 200
        # Verify via list
        r2 = requests.get(
            f"{BASE_URL}/api/admin/users?q={email}",
            headers=_h(admin_auth["token"]), timeout=15,
        )
        u = next((x for x in r2.json() if x["user_id"] == uid), None)
        assert u and u["role"] == "organizer"

    def test_change_role_invalid_400(self, admin_auth):
        uid, _, _ = _register("TEST bad role")
        r = requests.post(
            f"{BASE_URL}/api/admin/users/{uid}/role",
            json={"role": "superuser"}, headers=_h(admin_auth["token"]), timeout=15,
        )
        assert r.status_code == 400

    def test_change_role_self_demote_400(self, admin_auth):
        r = requests.post(
            f"{BASE_URL}/api/admin/users/{admin_auth['user_id']}/role",
            json={"role": "attendee"}, headers=_h(admin_auth["token"]), timeout=15,
        )
        assert r.status_code == 400

    def test_change_role_unknown_user_404(self, admin_auth):
        r = requests.post(
            f"{BASE_URL}/api/admin/users/user_doesnotexist123/role",
            json={"role": "organizer"}, headers=_h(admin_auth["token"]), timeout=15,
        )
        assert r.status_code == 404


# ---------- Suspend / unsuspend full lifecycle ----------
class TestSuspendLifecycle:
    def test_suspend_blocks_login_and_old_token_then_unsuspend(self, admin_auth):
        # 1) register a fresh attendee
        uid, email, token = _register("TEST suspend lifecycle")
        password = "Pass123!"

        # Verify token works pre-suspend
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=_h(token), timeout=15)
        assert r.status_code == 200

        # 2) admin suspends
        r = requests.post(
            f"{BASE_URL}/api/admin/users/{uid}/suspend",
            headers=_h(admin_auth["token"]), timeout=15,
        )
        assert r.status_code == 200

        # 3) login should now 403
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
        assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text}"
        assert "suspended" in r.json().get("detail", "").lower()

        # 4) old JWT should be rejected on protected endpoint
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=_h(token), timeout=15)
        assert r.status_code == 403, f"stale JWT not rejected, got {r.status_code}"

        # 5) appears in active=false filter
        r = requests.get(
            f"{BASE_URL}/api/admin/users?active=false",
            headers=_h(admin_auth["token"]), timeout=15,
        )
        assert any(u["user_id"] == uid for u in r.json())

        # 6) unsuspend
        r = requests.post(
            f"{BASE_URL}/api/admin/users/{uid}/unsuspend",
            headers=_h(admin_auth["token"]), timeout=15,
        )
        assert r.status_code == 200

        # 7) login works again
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
        assert r.status_code == 200

        # 8) old token also works again (active back to true)
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=_h(token), timeout=15)
        assert r.status_code == 200

    def test_suspend_self_400(self, admin_auth):
        r = requests.post(
            f"{BASE_URL}/api/admin/users/{admin_auth['user_id']}/suspend",
            headers=_h(admin_auth["token"]), timeout=15,
        )
        assert r.status_code == 400

    def test_suspend_unknown_404(self, admin_auth):
        r = requests.post(
            f"{BASE_URL}/api/admin/users/user_doesnotexist123/suspend",
            headers=_h(admin_auth["token"]), timeout=15,
        )
        assert r.status_code == 404


# ---------- Legacy admin still works ----------
class TestLegacyAdminLogin:
    def test_seed_admin_login(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=15)
        assert r.status_code == 200

    def test_seed_organizer_login(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json=ORG, timeout=15)
        assert r.status_code == 200
