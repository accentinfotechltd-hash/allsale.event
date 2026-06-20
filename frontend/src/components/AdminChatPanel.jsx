/**
 * AdminChatPanel — organizer's side of the admin↔organizer thread.
 *
 * Renders an inline chat panel on the organizer dashboard. Polls the unread
 * endpoint every 30s so a red dot shows up when admin replies. Sending is
 * Enter-to-send / Shift+Enter newline, matching the admin side.
 */
import { useEffect, useRef, useState } from "react";
import { Send, Headphones } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

export default function AdminChatPanel() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [unread, setUnread] = useState(0);
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);

  const loadUnread = async () => {
    try {
      const { data } = await api.get("/organizer/admin-thread/unread");
      setUnread(data?.unread || 0);
    } catch { /* noop */ }
  };

  const loadThread = async () => {
    try {
      const { data } = await api.get("/organizer/admin-thread");
      setMessages(data?.messages || []);
      setUnread(0); // backend auto-marked as read on fetch
    } catch { /* noop */ }
  };

  useEffect(() => {
    loadUnread();
    const t = setInterval(loadUnread, 30000);
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

          <div className="flex gap-2 mt-3">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
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
