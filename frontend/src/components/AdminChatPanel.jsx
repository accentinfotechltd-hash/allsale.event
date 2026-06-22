/**
 * AdminChatPanel — organizer's side of the admin↔organizer thread.
 *
 * Renders an inline chat panel on the organizer dashboard. Subscribes to the
 * WebSocket hub (`useChatLive`) so admin replies appear instantly without a
 * page refresh; a 60s safety-net poll keeps the unread badge accurate if the
 * socket ever drops. Sending is Enter-to-send / Shift+Enter for newline,
 * matching the admin side.
 */
import { useEffect, useRef, useState } from "react";
import { Send, Headphones } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import useChatLive from "@/lib/useChatLive";

export default function AdminChatPanel() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [unread, setUnread] = useState(0);
  const [busy, setBusy] = useState(false);
  // "Admin is typing…" indicator — set by an inbound `typing` WS event, cleared
  // either by a follow-up `is_typing:false` event OR a 3s safety timeout in case
  // the other side disconnects mid-type.
  const [adminTyping, setAdminTyping] = useState(false);
  const typingTimerRef = useRef(null);
  const openRef = useRef(false);
  const endRef = useRef(null);
  // Track whether we've already seen a message (de-dupes between optimistic insert
  // and WS broadcast that comes back to the sender).
  const seenIds = useRef(new Set());
  openRef.current = open;

  const loadUnread = async () => {
    try {
      const { data } = await api.get("/organizer/admin-thread/unread");
      setUnread(data?.unread || 0);
    } catch { /* noop */ }
  };

  const loadThread = async () => {
    try {
      const { data } = await api.get("/organizer/admin-thread");
      const msgs = data?.messages || [];
      setMessages(msgs);
      seenIds.current = new Set(msgs.map((m) => m.message_id));
      setUnread(0); // backend auto-marked as read on fetch
    } catch { /* noop */ }
  };

  // Real-time updates — append admin messages live, refresh unread badge.
  const { sendTyping } = useChatLive(user?.user_id, {
    onMessage: (msg) => {
      if (!msg?.message_id || seenIds.current.has(msg.message_id)) return;
      seenIds.current.add(msg.message_id);
      setMessages((prev) => [...prev, msg]);
      if (msg.sender_role === "admin" && !openRef.current) {
        setUnread((c) => c + 1);
      }
      // A real message arriving means the other side is no longer "typing".
      setAdminTyping(false);
    },
    onTyping: (evt) => {
      if (evt?.by !== "admin") return;
      setAdminTyping(!!evt.is_typing);
      if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
      if (evt.is_typing) {
        // Auto-clear after 3s in case the admin closes the tab without sending
        // an explicit `is_typing:false`.
        typingTimerRef.current = setTimeout(() => setAdminTyping(false), 3000);
      }
    },
  });

  useEffect(() => {
    loadUnread();
    const t = setInterval(loadUnread, 60000);  // safety net poll (every 60s) in case WS drops
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (open) loadThread();
  }, [open]);

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, open]);

  const send = async () => {
    const body = draft.trim();
    if (!body) return;
    setBusy(true);
    try {
      await api.post("/organizer/admin-thread", { body });
      setDraft("");
      // We stopped typing the moment we send — tell the other side.
      try { sendTyping(false); } catch { /* ignore */ }
      loadThread();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to send");
    } finally { setBusy(false); }
  };

  return (
    <div
      className="border rounded-2xl p-5"
      style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}
      data-testid="organizer-admin-chat"
    >
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 text-left"
        data-testid="organizer-admin-chat-toggle"
      >
        <div
          className="w-10 h-10 rounded-full flex items-center justify-center"
          style={{ background: "rgba(255,79,0,0.12)", color: "var(--accent)" }}
        >
          <Headphones className="w-5 h-5" />
        </div>
        <div className="flex-1">
          <div className="font-medium" style={{ color: "var(--text)" }}>Chat with Allsale support</div>
          <div className="text-xs" style={{ color: "var(--text-dim)" }}>
            Direct line to the admin team — questions, issues, feature requests.
          </div>
        </div>
        {unread > 0 && (
          <span
            className="px-2 py-0.5 rounded-full text-xs font-bold"
            style={{ background: "var(--accent)", color: "#0F0F0F", minWidth: 22, textAlign: "center" }}
            data-testid="organizer-admin-chat-unread"
          >
            {unread}
          </span>
        )}
      </button>

      {open && (
        <div className="mt-4">
          <div
            className="border rounded-xl p-3 space-y-2 max-h-[420px] overflow-y-auto"
            style={{ borderColor: "var(--border)", background: "var(--bg)" }}
            data-testid="organizer-admin-chat-messages"
          >
            {messages.length === 0 && (
              <div className="text-sm text-center py-8" style={{ color: "var(--text-dim)" }}>
                No messages yet — say hi to the team.
              </div>
            )}
            {messages.map((m) => {
              const mine = m.sender_role === "organizer";
              return (
                <div key={m.message_id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                  <div
                    className="max-w-[75%] px-3 py-2 rounded-2xl text-sm"
                    style={{
                      background: mine ? "var(--accent)" : "var(--bg-card)",
                      color: mine ? "#0F0F0F" : "var(--text)",
                      whiteSpace: "pre-wrap",
                    }}
                    data-testid={`organizer-admin-chat-msg-${m.message_id}`}
                  >
                    {m.body}
                    <div className="text-[10px] opacity-70 mt-1">
                      {mine ? "You" : (m.sender_name || "Allsale support")} · {new Date(m.created_at).toLocaleString()}
                    </div>
                  </div>
                </div>
              );
            })}
            <div ref={endRef} />
          </div>

          {adminTyping && (
            <div
              className="text-xs mt-2 inline-flex items-center gap-1"
              style={{ color: "var(--text-dim)" }}
              data-testid="organizer-admin-chat-typing"
            >
              Allsale support is typing<span className="dots-pulse">…</span>
            </div>
          )}

          <div className="flex gap-2 mt-3">
            <textarea
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                // Only signal typing while there's actual content to send.
                try { sendTyping(e.target.value.trim().length > 0); } catch { /* ignore */ }
              }}
              onBlur={() => { try { sendTyping(false); } catch { /* ignore */ } }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
              }}
              placeholder="Type a message — Enter to send"
              className="flex-1 text-sm"
              rows={2}
              data-testid="organizer-admin-chat-input"
            />
            <button
              onClick={send}
              disabled={busy || !draft.trim()}
              className="btn-primary !py-2 !px-4 text-sm self-end inline-flex items-center gap-1"
              data-testid="organizer-admin-chat-send"
            >
              <Send className="w-4 h-4" /> Send
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
