"""FAQ chatbot (b3) — endpoint behavior.

We only smoke-test the persistence layer (visitor question + bot answer
are saved as messages, escalation toggles session status). The LLM call
is mocked out so the test runs offline.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

from core import db  # noqa: E402
from routers import support_chat as sc  # noqa: E402


def _make_session_id():
    return f"sup_{uuid.uuid4().hex[:14]}"


def test_faq_ask_persists_visitor_and_bot_messages():
    async def run():
        sid = _make_session_id()
        # Patch the LLM call to return a known answer (no <ESCALATE>).
        fake_chat = AsyncMock()
        fake_chat.send_message = AsyncMock(return_value="Check Profile → My Tickets for the QR.")
        fake_chat.with_model = lambda *a, **k: fake_chat
        with patch.object(sc, "LlmChat", return_value=fake_chat), \
             patch.object(sc.os.environ, "get", side_effect=lambda k, d=None: "fake-key" if k == "EMERGENT_LLM_KEY" else d):
            res = await sc.faq_ask(
                sc.FaqAskIn(session_id=sid, question="How do I find my ticket?"),
                request=None,
            )
        assert res["can_help"] is True
        assert "Profile" in res["answer"]
        # Both visitor + bot messages persisted
        msgs = []
        async for m in db.support_messages.find({"session_id": sid}, {"_id": 0}).sort("created_at", 1):
            msgs.append(m)
        assert [m["sender"] for m in msgs] == ["visitor", "bot"]
        # Session row exists with status=bot
        sess = await db.support_chats.find_one({"session_id": sid}, {"_id": 0})
        assert sess and sess["status"] == "bot"

        # Cleanup
        await db.support_messages.delete_many({"session_id": sid})
        await db.support_chats.delete_one({"session_id": sid})

    asyncio.get_event_loop().run_until_complete(run())


def test_faq_ask_escalates_when_token_present():
    async def run():
        sid = _make_session_id()
        fake_chat = AsyncMock()
        fake_chat.send_message = AsyncMock(
            return_value="I can't process refunds directly. <ESCALATE>"
        )
        fake_chat.with_model = lambda *a, **k: fake_chat
        with patch.object(sc, "LlmChat", return_value=fake_chat), \
             patch.object(sc.os.environ, "get", side_effect=lambda k, d=None: "fake-key" if k == "EMERGENT_LLM_KEY" else d):
            res = await sc.faq_ask(
                sc.FaqAskIn(session_id=sid, question="Refund my order RX-12345"),
                request=None,
            )
        assert res["can_help"] is False
        assert "<ESCALATE>" not in res["answer"]

        # Cleanup
        await db.support_messages.delete_many({"session_id": sid})
        await db.support_chats.delete_one({"session_id": sid})

    asyncio.get_event_loop().run_until_complete(run())


def test_faq_escalate_flips_session_status_to_open():
    async def run():
        sid = _make_session_id()
        # Seed a session in bot mode (as faq_ask would have done)
        from core import utc_now
        await db.support_chats.insert_one({
            "session_id": sid,
            "status": "bot",
            "visitor_name": "Anon",
            "created_at": utc_now().isoformat(),
            "last_visitor_msg_at": utc_now().isoformat(),
            "unread_admin": 0,
        })
        res = await sc.faq_escalate(
            sc.FaqAskIn(session_id=sid, question="Please help — refund?")
        )
        assert res["status"] == "open"
        sess = await db.support_chats.find_one({"session_id": sid}, {"_id": 0})
        assert sess["status"] == "open"
        handoff = await db.support_messages.find_one(
            {"session_id": sid, "kind": "bot_handoff"}, {"_id": 0}
        )
        assert handoff is not None

        # Cleanup
        await db.support_messages.delete_many({"session_id": sid})
        await db.support_chats.delete_one({"session_id": sid})

    asyncio.get_event_loop().run_until_complete(run())
