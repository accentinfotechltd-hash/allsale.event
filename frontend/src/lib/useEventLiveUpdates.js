/**
 * useEventLiveUpdates — subscribes to /api/ws/events/{eventId} and applies
 * deltas to local state. Returns { connected, lastUpdate }.
 *
 * Reconnect strategy: exponential back-off (1s → 2s → 4s → … → 30s cap),
 * resets on successful connection. Falls back gracefully when the browser
 * has no WebSocket support (rare).
 *
 * Callbacks the consumer can wire in (any subset):
 *   onSnapshot(snapshot) — full state on first connect / reconnect
 *   onSeat({seat_id, status})
 *   onTier({tier_status, sold_out, surging})
 */
import { useEffect, useRef, useState } from "react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";

function wsUrl(eventId) {
  if (!BACKEND_URL) return null;
  const base = BACKEND_URL.replace(/^http/, "ws");
  return `${base}/api/ws/events/${eventId}`;
}

export default function useEventLiveUpdates(eventId, handlers = {}) {
  const [connected, setConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);
  const wsRef = useRef(null);
  const attemptRef = useRef(0);
  const stoppedRef = useRef(false);
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    if (!eventId) return;
    stoppedRef.current = false;
    const url = wsUrl(eventId);
    if (!url || typeof window === "undefined" || !("WebSocket" in window)) return;

    let reconnectTimer = null;

    const connect = () => {
      if (stoppedRef.current) return;
      let ws;
      try {
        ws = new WebSocket(url);
      } catch {
        scheduleReconnect();
        return;
      }
      wsRef.current = ws;
      ws.onopen = () => {
        setConnected(true);
        attemptRef.current = 0;
      };
      ws.onmessage = (e) => {
        let msg;
        try { msg = JSON.parse(e.data); } catch { return; }
        if (!msg?.type || msg.type === "ping") return;
        setLastUpdate(Date.now());
        const h = handlersRef.current;
        if (msg.type === "snapshot" && h.onSnapshot) h.onSnapshot(msg);
        else if (msg.type === "seat" && h.onSeat) h.onSeat(msg);
        else if (msg.type === "tier" && h.onTier) h.onTier(msg);
      };
      ws.onerror = () => { /* onclose will fire next */ };
      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        scheduleReconnect();
      };
    };

    const scheduleReconnect = () => {
      if (stoppedRef.current) return;
      attemptRef.current += 1;
      const delay = Math.min(30_000, 1000 * Math.pow(2, attemptRef.current - 1));
      reconnectTimer = setTimeout(connect, delay);
    };

    connect();

    return () => {
      stoppedRef.current = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (wsRef.current) {
        try { wsRef.current.close(); } catch { /* ignore */ }
        wsRef.current = null;
      }
    };
  }, [eventId]);

  return { connected, lastUpdate };
}
