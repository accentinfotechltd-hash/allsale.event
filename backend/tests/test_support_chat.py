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


@pytest.mark.asyncio
async def test_attachment_validation():
    async with httpx.AsyncClient(timeout=15) as client:
        sid = "sup_" + uuid.uuid4().hex[:12]
        # 1x1 transparent PNG, base64-encoded
        png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        ok = await client.post(f"{API}/support/chat/messages", json={
            "session_id": sid,
            "text": "Here's the screenshot",
            "attachment": {
                "filename": "screenshot.png",
                "mime": "image/png",
                "data_url": f"data:image/png;base64,{png_b64}",
            },
        })
        assert ok.status_code == 200, ok.text
        msg = ok.json()
        assert msg["attachment"]["filename"] == "screenshot.png"
        assert msg["attachment"]["mime"] == "image/png"

        # Bad MIME type → 400
        bad = await client.post(f"{API}/support/chat/messages", json={
            "session_id": sid,
            "attachment": {
                "filename": "evil.exe",
                "mime": "application/x-msdownload",
                "data_url": f"data:application/x-msdownload;base64,{png_b64}",
            },
        })
        assert bad.status_code == 400

        # Oversized attachment (fake big base64 string ~1.2 MB) → 413
        huge = "A" * (1_200_000 // 3 * 4)  # ~1.2 MB worth of base64 chars
        too_big = await client.post(f"{API}/support/chat/messages", json={
            "session_id": sid,
            "attachment": {
                "filename": "huge.png",
                "mime": "image/png",
                "data_url": f"data:image/png;base64,{huge}",
            },
        })
        assert too_big.status_code in (413, 422)


@pytest.mark.asyncio
async def test_close_triggers_rating_prompt_and_visitor_rates():
    async with httpx.AsyncClient(timeout=15) as client:
        sid = "sup_" + uuid.uuid4().hex[:12]
        await client.post(f"{API}/support/chat/messages", json={
            "session_id": sid, "text": "I need help",
        })

        admin = await client.post(f"{API}/auth/login", json={
            "email": "admin@allsale.events", "password": "admin123",
        })
        if admin.status_code != 200:
            pytest.skip("No admin seeded")
        auth = {"Authorization": f"Bearer {admin.json()['token']}"}

        # Admin closes — should inject a `rating_prompt` system message
        r = await client.post(f"{API}/admin/support/{sid}/close", headers=auth)
        assert r.status_code == 200

        # Visitor sees the system rating prompt in their thread
        r = await client.get(f"{API}/support/chat/{sid}")
        msgs = r.json()["messages"]
        kinds = [m.get("kind") for m in msgs if m.get("sender") == "system"]
        assert "rating_prompt" in kinds

        # Visitor submits 4 stars
        r = await client.post(f"{API}/support/chat/rate", json={
            "session_id": sid, "stars": 4, "comment": "Quick and helpful!",
        })
        assert r.status_code == 200
        rating = r.json()["rating"]
        assert rating["stars"] == 4
        assert rating["comment"] == "Quick and helpful!"

        # Session document now carries the rating, and a confirmation system
        # message appears in the thread.
        r = await client.get(f"{API}/support/chat/{sid}")
        body = r.json()
        assert body["session"]["rating"]["stars"] == 4
        confirmation = [m for m in body["messages"] if m.get("kind") == "rating_received"]
        assert len(confirmation) == 1

        # Out-of-range stars → 422
        r = await client.post(f"{API}/support/chat/rate", json={
            "session_id": sid, "stars": 6,
        })
        assert r.status_code == 422

        # Unknown session → 404
        r = await client.post(f"{API}/support/chat/rate", json={
            "session_id": "sup_doesnotexistaaaa", "stars": 3,
        })
        assert r.status_code == 404
