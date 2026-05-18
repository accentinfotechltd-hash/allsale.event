"""WebSocket hub for live seat-map updates.

Replaces the 8-second polling loop on EventDetail. When a seat is held / freed /
booked, the backend broadcasts a delta to every client subscribed to that
event_id over WS. The frontend applies the delta to its local state without a
network round-trip.

Connection: `wss://<host>/api/ws/events/{event_id}`
Server → Client messages:
  { "type": "snapshot", "booked": [...], "held": [...], "tier_status": [...] }
  { "type": "seat", "seat_id": "A-5", "status": "held" | "free" | "booked" }
  { "type": "tier", "tier_status": [...], "sold_out": bool, "surging": bool }
Client → Server: nothing (read-only feed). Heartbeat ping every 25s from server.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core import db, utc_now, compute_tier_effective_price

router = APIRouter(tags=["ws"])
logger = logging.getLogger("aura.ws")


class EventHub:
    """In-memory pub/sub keyed by event_id. Single-process; OK for our deployment."""
    def __init__(self) -> None:
        self.subs: Dict[str, Set[WebSocket]] = defaultdict(set)
        self.lock = asyncio.Lock()

    async def add(self, event_id: str, ws: WebSocket) -> None:
        async with self.lock:
            self.subs[event_id].add(ws)

    async def remove(self, event_id: str, ws: WebSocket) -> None:
        async with self.lock:
            self.subs.get(event_id, set()).discard(ws)
            if not self.subs.get(event_id):
                self.subs.pop(event_id, None)

    async def broadcast(self, event_id: str, message: dict) -> None:
        async with self.lock:
            targets = list(self.subs.get(event_id, set()))
        if not targets:
            return
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        if dead:
            async with self.lock:
                for ws in dead:
                    self.subs.get(event_id, set()).discard(ws)


hub = EventHub()


async def _build_snapshot(event_id: str) -> dict:
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        return {"type": "snapshot", "booked": [], "held": [], "tier_status": [], "sold_out": False, "surging": False}

    now_iso = utc_now().isoformat()
    snapshot: dict = {"type": "snapshot"}
    if event.get("has_seatmap"):
        booked = [r["seat_id"] async for r in db.seat_reservations.find(
            {"event_id": event_id, "status": "booked"}, {"_id": 0, "seat_id": 1},
        )]
        held = [r["seat_id"] async for r in db.seat_reservations.find(
            {"event_id": event_id, "status": "held", "expires_at": {"$gte": now_iso}},
            {"_id": 0, "seat_id": 1},
        )]
        snapshot["booked"] = booked
        snapshot["held"] = held
        rows = event.get("seat_rows", 0)
        cols = event.get("seat_cols", 0)
        aisles = set(event.get("aisles") or [])
        total_non_aisle = max(0, rows * cols - len(aisles))
        locked = len({*booked, *held})
        snapshot["sold_out"] = total_non_aisle > 0 and locked >= total_non_aisle
        snapshot["tier_status"] = []
        snapshot["surging"] = False
    else:
        tier_status = []
        any_remaining = False
        any_surging = False
        for t in event.get("tiers", []):
            sold = 0
            async for b in db.bookings.find(
                {"event_id": event_id, "tier_name": t["name"], "status": {"$in": ["paid", "confirmed", "pending"]}},
                {"_id": 0, "quantity": 1, "hold_expires_at": 1, "status": 1},
            ):
                if b.get("status") == "pending" and (b.get("hold_expires_at") or "") < now_iso:
                    continue
                sold += b.get("quantity", 0)
            remaining = max(0, t.get("capacity", 0) - sold)
            if remaining > 0:
                any_remaining = True
            eff_price, surging = compute_tier_effective_price(event, t, sold)
            if surging:
                any_surging = True
            tier_status.append({"name": t["name"], "sold": sold, "remaining": remaining, "effective_price": eff_price, "surging": surging})
        snapshot["tier_status"] = tier_status
        snapshot["sold_out"] = (not any_remaining) and bool(event.get("tiers"))
        snapshot["surging"] = any_surging
        snapshot["booked"] = []
        snapshot["held"] = []
    return snapshot


@router.websocket("/ws/events/{event_id}")
async def event_socket(ws: WebSocket, event_id: str):
    await ws.accept()
    await hub.add(event_id, ws)
    try:
        await ws.send_json(await _build_snapshot(event_id))
        # Heartbeat keeps proxy connections alive (some platforms drop idle WS at 30-60s).
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=25.0)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"[ws] {event_id} disconnected: {e}")
    finally:
        await hub.remove(event_id, ws)


# ---------------------------------------------------------------------------
# Public broadcast helpers — called from booking / payment / waitlist routers
# ---------------------------------------------------------------------------
async def notify_seats(event_id: str, changes: list[dict]) -> None:
    """Broadcast individual seat changes. `changes` = [{seat_id, status}]."""
    for ch in changes:
        await hub.broadcast(event_id, {"type": "seat", **ch})


async def notify_tier_refresh(event_id: str) -> None:
    """For tier-based events: recompute and broadcast tier_status."""
    snap = await _build_snapshot(event_id)
    if not snap.get("tier_status"):
        return
    await hub.broadcast(event_id, {
        "type": "tier",
        "tier_status": snap["tier_status"],
        "sold_out": snap["sold_out"],
        "surging": snap["surging"],
    })


async def notify_snapshot(event_id: str) -> None:
    """Full snapshot rebroadcast — useful after bulk changes."""
    snap = await _build_snapshot(event_id)
    await hub.broadcast(event_id, snap)
