import { useEffect, useRef, useState } from "react";
import { MessageCircle, X, Send } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";

/**
 * SupportChat — floating "💬" widget that opens a chat panel.
 *
 *   • Anonymous-friendly: a `session_id` is minted on first open and stored
 *     in localStorage so reloads and route changes keep the conversation.
 *   • Polls every 6 seconds when the panel is open; backs off to nothing
 *     when closed to keep the homepage cheap.
 *   • Sends to `POST /api/support/chat/messages` and receives the full
 *     thread from `GET /api/support/chat/:session_id`.
 *
 * This widget is intentionally NOT rendered on the Scanner kiosk (/scan)
 * and the printable Flyer page (/flyer) so it doesn't interfere with
 * door check-in or PDF export.
 */
const SESSION_KEY = "allsale_support_session";
const POLL_MS = 6000;

function makeSessionId() {
  return "sup_" + Math.random().toString(36).slice(2, 14) + Date.now().toString(36);
}

export default function SupportChat() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [messages, setMessages] = useState([]);
  const [sending, setSending] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const sessionRef = useRef(null);
  const listRef = useRef(null);

  // Lazy-create / fetch the session ID
  const getSessionId = () => {
    if (sessionRef.current) return sessionRef.current;
    let sid = "";
    try { sid = localStorage.getItem(SESSION_KEY) || ""; } catch { /* localStorage may be blocked */ }
    if (!sid) {
      sid = makeSessionId();
      try { localStorage.setItem(SESSION_KEY, sid); } catch { /* ignore */ }
    }
    sessionRef.current = sid;
    return sid;
  };

  // Poll the thread while the panel is open
  useEffect(() => {
    if (!open) return undefined;
    const sid = getSessionId();
    let cancelled = false;
    const fetchOnce = async () => {
      try {
        const { data } = await api.get(`/support/chat/${sid}`);
        if (!cancelled) setMessages(data.messages || []);
      } catch { /* network blip — silent */ }
    };
    fetchOnce();
    const id = setInterval(fetchOnce, POLL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, [open]);

  // Auto-scroll to bottom when new messages land
  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages, open]);

  // Prefill name/email when the visitor signs in
  useEffect(() => {
    if (user) {
      if (user.name && !name) setName(user.name);
      if (user.email && !email) setEmail(user.email);
    }
  }, [user]); // eslint-disable-line

  const send = async (e) => {
    e?.preventDefault();
    const body = text.trim();
    if (!body) return;
    setSending(true);
    // Optimistic update so the message appears instantly.
    const optimistic = {
      message_id: `tmp_${Date.now()}`,
      sender: "visitor",
      text: body,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimistic]);
    setText("");
    try {
      await api.post("/support/chat/messages", {
        session_id: getSessionId(),
        text: body,
        name: name?.trim() || undefined,
        email: email?.trim() || undefined,
      });
    } catch (err) {
      // Roll back the optimistic insert
      setMessages((prev) => prev.filter((m) => m.message_id !== optimistic.message_id));
    } finally {
      setSending(false);
    }
  };

  // Hide the widget on the chrome-less Scanner & Flyer routes
  if (typeof window !== "undefined") {
    const p = window.location.pathname;
    if (p.startsWith("/scan") || p === "/flyer") return null;
  }

  return (
    <>
      {!open && (
        <button
          onClick={() => setOpen(true)}
          data-testid="support-chat-open"
          aria-label="Open live chat"
          className="fixed bottom-5 right-5 z-40 rounded-full shadow-xl flex items-center gap-2 px-4 py-3 transition-transform hover:scale-105"
          style={{ background: "var(--accent)", color: "#0F2A3A" }}
        >
          <MessageCircle size={18} />
          <span className="text-sm font-medium hidden sm:inline">Chat with us</span>
        </button>
      )}

      {open && (
        <div
          className="fixed bottom-5 right-5 z-50 rounded-2xl shadow-2xl flex flex-col overflow-hidden"
          style={{
            width: "min(360px, calc(100vw - 2.5rem))",
            height: "min(540px, calc(100vh - 2.5rem))",
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
          }}
          data-testid="support-chat-panel"
        >
          {/* Header */}
          <div
            className="flex items-center justify-between px-4 py-3"
            style={{ background: "var(--accent)", color: "#0F2A3A" }}
          >
            <div>
              <div className="font-semibold text-sm">Allsale Support</div>
              <div className="text-[10px] opacity-80">Replies in a few minutes</div>
            </div>
            <button
              onClick={() => setOpen(false)}
              data-testid="support-chat-close"
              aria-label="Close"
              className="p-1 rounded hover:bg-black/10"
            >
              <X size={16} />
            </button>
          </div>

          {/* Message list */}
          <div
            ref={listRef}
            className="flex-1 overflow-y-auto p-3 space-y-2"
            style={{ background: "var(--bg-elev)" }}
            data-testid="support-chat-messages"
          >
            {messages.length === 0 && (
              <div className="text-center text-sm py-6" style={{ color: "var(--text-muted)" }}>
                👋 Hi there! Send us a message and we'll get back to you soon.
              </div>
            )}
            {messages.map((m) => (
              <div
                key={m.message_id}
                className={`max-w-[80%] px-3 py-2 rounded-2xl text-sm leading-snug ${m.sender === "admin" ? "" : "ml-auto"}`}
                style={{
                  background: m.sender === "admin" ? "var(--bg-card)" : "var(--accent)",
                  color: m.sender === "admin" ? "var(--text)" : "#0F2A3A",
                  border: m.sender === "admin" ? "1px solid var(--border)" : "none",
                  borderRadius: m.sender === "admin" ? "14px 14px 14px 4px" : "14px 14px 4px 14px",
                }}
                data-testid={`msg-${m.sender}`}
              >
                {m.text}
                {m.sender === "admin" && m.sender_name && (
                  <div className="text-[10px] mt-1 opacity-60">{m.sender_name}</div>
                )}
              </div>
            ))}
          </div>

          {/* Anon contact fields — shown only before the first message */}
          {!user && messages.length === 0 && (
            <div className="px-3 pt-2 border-t" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
              <div className="grid grid-cols-2 gap-2 mb-2">
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Your name (optional)"
                  className="text-xs px-2 py-1.5 rounded border bg-transparent"
                  style={{ borderColor: "var(--border)" }}
                  data-testid="support-chat-name"
                />
                <input
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Email (optional)"
                  className="text-xs px-2 py-1.5 rounded border bg-transparent"
                  style={{ borderColor: "var(--border)" }}
                  data-testid="support-chat-email"
                />
              </div>
            </div>
          )}

          {/* Composer */}
          <form
            onSubmit={send}
            className="flex items-center gap-2 p-3 border-t"
            style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
          >
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Type a message…"
              className="flex-1 px-3 py-2 rounded-full border bg-transparent text-sm"
              style={{ borderColor: "var(--border)" }}
              data-testid="support-chat-input"
              maxLength={2000}
              autoFocus
            />
            <button
              type="submit"
              disabled={!text.trim() || sending}
              data-testid="support-chat-send"
              className="rounded-full p-2 disabled:opacity-40"
              style={{ background: "var(--accent)", color: "#0F2A3A" }}
              aria-label="Send"
            >
              <Send size={16} />
            </button>
          </form>
        </div>
      )}
    </>
  );
}
