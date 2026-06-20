/**
 * useChatLive — subscribes to /api/ws/admin-organizer-chat/{organizerId}
 * and emits live `message` / `read` events back to the caller. Mirrors the
 * pattern in `useEventLiveUpdates.js` (exponential reconnect, JSON heartbeat
 * filtering, no-op when WS unsupported).
 *
 * Auth: passes the JWT from localStorage via `?token=` because the browser
 * WebSocket API can't set Authorization headers. The backend validates and
 * either admits or closes with 4401/4403.
 *
 * Returns { connected, lastEvent }. Consumers wire handlers via the second arg.
 */
import { useEffect, useRef, useState } from "react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";

function getToken() {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("aura_token") || null;
}

function wsUrl(organizerId, token) {
  if (!BACKEND_URL || !organizerId || !token) return null;
  const base = BACKEND_URL.replace(/^http/, "ws");
  return `${base}/api/ws/admin-organizer-chat/${encodeURIComponent(organizerId)}?token=${encodeURIComponent(token)}`;
}

export default function useChatLive(organizerId, handlers = {}) {
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState(null);
  const wsRef = useRef(null);
  const attemptRef = useRef(0);
  const stoppedRef = useRef(false);
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    if (!organizerId) return;
    stoppedRef.current = false;
    const token = getToken();
    const url = wsUrl(organizerId, token);
    if (!url || typeof window === "undefined" || !("WebSocket" in window)) return;

    let reconnectTimer = null;

    const connect = () => {
      if (stoppedRef.current) return;
      let ws;
      try { ws = new WebSocket(url); } catch { scheduleReconnect(); return; }
      wsRef.current = ws;
      ws.onopen = () => {
        setConnected(true);
        attemptRef.current = 0;
      };
      ws.onmessage = (e) => {
        let msg;
        try { msg = JSON.parse(e.data); } catch { return; }
        if (!msg?.type || msg.type === "ping" || msg.type === "hello") return;
        setLastEvent({ at: Date.now(), msg });
        const h = handlersRef.current;
        if (msg.type === "message" && h.onMessage) h.onMessage(msg.message);
        else if (msg.type === "read" && h.onRead) h.onRead(msg.by);
      };
      ws.onerror = () => { /* close fires next */ };
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
  }, [organizerId]);

  return { connected, lastEvent };
}
