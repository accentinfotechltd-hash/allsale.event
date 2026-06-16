"""End-to-end test for the live support chat router."""
import os
import uuid
import pytest
import httpx

API = os.environ.get("TEST_API_URL", "http://localhost:8001/api")


@pytest.mark.asyncio
async def test_anon_chat_to_admin_reply():
    async with httpx.AsyncClient(timeout=15) as client:
        # 1. Anon visitor sends a message → session is auto-created
        sid = "sup_" + uuid.uuid4().hex[:12]
        r = await client.post(f"{API}/support/chat/messages", json={
            "session_id": sid,
            "text": "Hi, I need help with a refund",
            "name": "Test Visitor",
            "email": "v@example.com",
        })
        assert r.status_code == 200, r.text
        msg = r.json()
        assert msg["sender"] == "visitor"
        assert msg["text"] == "Hi, I need help with a refund"

        # 2. Anon visitor pulls thread
        r = await client.get(f"{API}/support/chat/{sid}")
        assert r.status_code == 200
        body = r.json()
        assert len(body["messages"]) == 1
        assert body["session"]["visitor_name"] == "Test Visitor"
        assert body["session"]["visitor_email"] == "v@example.com"
        assert body["session"]["unread_admin_count"] == 1

        # 3. Admin logs in
        admin = await client.post(f"{API}/auth/login", json={
            "email": "admin@allsale.events", "password": "admin123",
        })
        if admin.status_code != 200:
            pytest.skip("No admin seeded")
        a_auth = {"Authorization": f"Bearer {admin.json()['token']}"}

        # 4. Admin lists sessions — ours should be there with a preview
        r = await client.get(f"{API}/admin/support/sessions", headers=a_auth)
        assert r.status_code == 200
        sessions = r.json()
        ours = next((s for s in sessions if s["session_id"] == sid), None)
        assert ours is not None
        assert "refund" in (ours.get("last_message_preview") or "")
        assert ours["unread_admin_count"] == 1

        # 5. Admin opens the session → unread should reset to 0
        r = await client.get(f"{API}/admin/support/sessions/{sid}", headers=a_auth)
        assert r.status_code == 200
        opened = r.json()
        assert opened["session"]["unread_admin_count"] == 0

        # 6. Admin replies
        r = await client.post(f"{API}/admin/support/reply", json={
            "session_id": sid,
            "text": "Sure! What's your booking ID?",
        }, headers=a_auth)
        assert r.status_code == 200
        reply = r.json()
        assert reply["sender"] == "admin"

        # 7. Visitor polls and sees both messages
        r = await client.get(f"{API}/support/chat/{sid}")
        body = r.json()
        assert len(body["messages"]) == 2
        assert body["messages"][1]["sender"] == "admin"

        # 8. Admin closes the chat
        r = await client.post(f"{API}/admin/support/{sid}/close", headers=a_auth)
        assert r.status_code == 200
        r = await client.get(f"{API}/support/chat/{sid}")
        assert r.json()["session"]["status"] == "closed"

        # 9. Non-admin can't list sessions
        r = await client.get(f"{API}/admin/support/sessions")
        assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_typing_indicators():
    async with httpx.AsyncClient(timeout=15) as client:
        sid = "sup_" + uuid.uuid4().hex[:12]
        # Visitor sends an opening message (so the session row exists)
        await client.post(f"{API}/support/chat/messages", json={
            "session_id": sid, "text": "hi",
        })

        # Visitor "is typing"
        r = await client.post(f"{API}/support/chat/typing", json={"session_id": sid})
        assert r.status_code == 200

        # Admin polls and sees visitor_is_typing=true
        admin = await client.post(f"{API}/auth/login", json={
            "email": "admin@allsale.events", "password": "admin123",
        })
        if admin.status_code != 200:
            pytest.skip("No admin seeded")
        a_auth = {"Authorization": f"Bearer {admin.json()['token']}"}
        r = await client.get(f"{API}/admin/support/sessions/{sid}", headers=a_auth)
        assert r.json()["session"]["visitor_is_typing"] is True

        # Admin "is typing"
        r = await client.post(f"{API}/admin/support/typing", json={"session_id": sid}, headers=a_auth)
        assert r.status_code == 200

        # Visitor polls and sees admin_is_typing=true
        r = await client.get(f"{API}/support/chat/{sid}")
        assert r.json()["session"]["admin_is_typing"] is True

        # Non-admin can't POST admin typing
        r = await client.post(f"{API}/admin/support/typing", json={"session_id": sid})
        assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_emoji_reactions_toggle():
    async with httpx.AsyncClient(timeout=15) as client:
        sid = "sup_" + uuid.uuid4().hex[:12]
        # Visitor posts a message
        m = await client.post(f"{API}/support/chat/messages", json={
            "session_id": sid, "text": "Help please",
        })
        msg = m.json()
        mid = msg["message_id"]

        # Add a 👍 reaction as the anon visitor
        r = await client.post(f"{API}/support/chat/reactions", json={
            "session_id": sid, "message_id": mid, "emoji": "👍",
        })
        assert r.status_code == 200, r.text
        assert "👍" in r.json()["reactions"]
        assert len(r.json()["reactions"]["👍"]) == 1

        # Toggling the same emoji removes it
        r = await client.post(f"{API}/support/chat/reactions", json={
            "session_id": sid, "message_id": mid, "emoji": "👍",
        })
        assert "👍" not in r.json()["reactions"]

        # Unknown emoji is rejected
        r = await client.post(f"{API}/support/chat/reactions", json={
            "session_id": sid, "message_id": mid, "emoji": "🤖",
        })
        assert r.status_code == 400

        # Wrong session_id is rejected (security)
        r = await client.post(f"{API}/support/chat/reactions", json={
            "session_id": "sup_otherrandom123", "message_id": mid, "emoji": "🎉",
        })
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_canned_replies_settings():
    async with httpx.AsyncClient(timeout=15) as client:
        admin = await client.post(f"{API}/auth/login", json={
            "email": "admin@allsale.events", "password": "admin123",
        })
        if admin.status_code != 200:
            pytest.skip("No admin seeded")
        auth = {"Authorization": f"Bearer {admin.json()['token']}"}

        # PATCH canned replies + slack URL
        r = await client.patch(f"{API}/admin/site-settings", json={
            "support_chat": {
                "canned_replies": ["Hello!", "  ", "How can I help?", ""],
                "slack_webhook_url": "https://hooks.slack.com/services/T123/B456/abc",
            },
        }, headers=auth)
        assert r.status_code == 200, r.text
        sc = r.json()["support_chat"]
        # Whitespace-only entries are dropped
        assert sc["canned_replies"] == ["Hello!", "How can I help?"]
        assert sc["slack_webhook_url"] == "https://hooks.slack.com/services/T123/B456/abc"

        # Public GET surfaces them (the support chat tab loads from here)
        r = await client.get(f"{API}/site-settings")
        sc = r.json()["support_chat"]
        assert "Hello!" in sc["canned_replies"]
