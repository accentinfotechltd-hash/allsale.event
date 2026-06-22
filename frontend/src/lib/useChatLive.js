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
  // Throttle outbound typing events — sending one per keystroke would flood
  // the socket. We send at most one every 1.5s while the user is still typing.
  const lastTypingSentRef = useRef(0);

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
        else if (msg.type === "typing" && h.onTyping) h.onTyping(msg);
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

  // Send a typing event to the server. Throttled to one per 1.5s so the
  // socket isn't flooded on every keystroke. `is_typing=false` is sent
  // immediately (no throttle) so the indicator on the other side
  // disappears as soon as the user stops typing or sends.
  const sendTyping = (isTyping = true) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== 1) return;
    const now = Date.now();
    if (isTyping && now - lastTypingSentRef.current < 1500) return;
    lastTypingSentRef.current = isTyping ? now : 0;
    try { ws.send(JSON.stringify({ type: "typing", is_typing: isTyping })); } catch { /* ignore */ }
  };

  return { connected, lastEvent, sendTyping };
}
