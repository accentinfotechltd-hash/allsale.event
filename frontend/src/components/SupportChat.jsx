import { useEffect, useRef, useState } from "react";
import { MessageCircle, X, Send, Paperclip, Star } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import MessageReactions from "@/components/MessageReactions";

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
  const [adminTyping, setAdminTyping] = useState(false);
  const [sending, setSending] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [attachment, setAttachment] = useState(null); // {filename, mime, data_url}
  const sessionRef = useRef(null);
  const listRef = useRef(null);
  const fileInputRef = useRef(null);
  const lastTypingPing = useRef(0);

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
        if (!cancelled) {
          setMessages(data.messages || []);
          setAdminTyping(!!data.session?.admin_is_typing);
        }
      } catch { /* network blip — silent */ }
    };
    fetchOnce();
    // Poll every 4s (down from 6s) so the typing indicator feels responsive.
    const id = setInterval(fetchOnce, 4000);
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

  // Notify the server that the visitor is typing — throttled to once per 2s.
  const pingTyping = () => {
    const now = Date.now();
    if (now - lastTypingPing.current < 2000) return;
    lastTypingPing.current = now;
    api.post("/support/chat/typing", { session_id: getSessionId() }).catch(() => { /* silent */ });
  };

  const send = async (e) => {
    e?.preventDefault();
    const body = text.trim();
    if (!body && !attachment) return;
    setSending(true);
    // Optimistic update so the message appears instantly.
    const optimistic = {
      message_id: `tmp_${Date.now()}`,
      sender: "visitor",
      text: body,
      attachment,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimistic]);
    setText("");
    const sentAttachment = attachment;
    setAttachment(null);
    try {
      await api.post("/support/chat/messages", {
        session_id: getSessionId(),
        text: body || undefined,
        attachment: sentAttachment || undefined,
        name: name?.trim() || undefined,
        email: email?.trim() || undefined,
      });
    } catch (err) {
      setMessages((prev) => prev.filter((m) => m.message_id !== optimistic.message_id));
      toast.error(err?.response?.data?.detail || "Couldn't send");
    } finally {
      setSending(false);
    }
  };

  // Convert a picked file → base64 data URL → state. Validates size and type
  // client-side so we get a friendly error before hitting the backend.
  const onFilePick = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = ""; // allow re-picking the same file
    if (!file) return;
    if (file.size > 800 * 1024) {
      toast.error("File too large — max 800 KB. Compress or screenshot a smaller area.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setAttachment({
        filename: file.name.slice(0, 200),
        mime: file.type || "application/octet-stream",
        data_url: reader.result,
      });
    };
    reader.onerror = () => toast.error("Couldn't read file");
    reader.readAsDataURL(file);
  };

  const rate = async (stars) => {
    try {
      await api.post("/support/chat/rate", { session_id: getSessionId(), stars });
      toast.success("Thanks for your feedback!");
    } catch {
      toast.error("Couldn't submit rating");
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
            {messages.map((m) => {
              // System messages (rating prompt, rating confirmation) render
              // as inline cards in the middle of the thread — not bubbles.
              if (m.sender === "system") {
                if (m.kind === "rating_prompt") {
                  return <RatingPrompt key={m.message_id} text={m.text} onRate={rate} />;
                }
                return (
                  <div key={m.message_id} className="text-center text-xs italic py-1" style={{ color: "var(--text-muted)" }} data-testid={`sys-${m.kind}`}>
                    {m.text}
                  </div>
                );
              }
              return (
                <div key={m.message_id} className={`group flex ${m.sender === "admin" ? "" : "justify-end"}`}>
                  <div className="flex flex-col" style={{ maxWidth: "80%" }}>
                    <div
                      className="px-3 py-2 rounded-2xl text-sm leading-snug"
                      style={{
                        background: m.sender === "admin" ? "var(--bg-card)" : "var(--accent)",
                        color: m.sender === "admin" ? "var(--text)" : "#0F2A3A",
                        border: m.sender === "admin" ? "1px solid var(--border)" : "none",
                        borderRadius: m.sender === "admin" ? "14px 14px 14px 4px" : "14px 14px 4px 14px",
                      }}
                      data-testid={`msg-${m.sender}`}
                    >
                      {m.attachment && <Attachment att={m.attachment} />}
                      {m.text}
                      {m.sender === "admin" && m.sender_name && (
                        <div className="text-[10px] mt-1 opacity-60">{m.sender_name}</div>
                      )}
                    </div>
                    <div className={`mt-1 ${m.sender === "admin" ? "self-start" : "self-end"}`}>
                      <MessageReactions
                        message={{ ...m, session_id: m.session_id || sessionRef.current }}
                        onReact={(reactions) => {
                          setMessages((prev) => prev.map((p) => p.message_id === m.message_id ? { ...p, reactions } : p));
                        }}
                        align={m.sender === "admin" ? "left" : "right"}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
            {adminTyping && (
              <div
                className="max-w-[80%] px-3 py-2 text-sm italic"
                style={{
                  background: "var(--bg-card)",
                  color: "var(--text-muted)",
                  border: "1px solid var(--border)",
                  borderRadius: "14px 14px 14px 4px",
                }}
                data-testid="admin-typing-indicator"
              >
                Allsale is typing<span className="dots-pulse">…</span>
              </div>
            )}
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
            className="flex flex-col gap-2 p-3 border-t"
            style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
          >
            {attachment && (
              <div className="flex items-center gap-2 text-xs px-2 py-1 rounded-lg border" style={{ borderColor: "var(--border)" }} data-testid="attachment-preview">
                {attachment.mime.startsWith("image/") ? (
                  <img src={attachment.data_url} alt="" className="w-8 h-8 object-cover rounded" />
                ) : (
                  <Paperclip size={14} />
                )}
                <span className="flex-1 truncate">{attachment.filename}</span>
                <button type="button" onClick={() => setAttachment(null)} className="opacity-60 hover:opacity-100" aria-label="Remove attachment" data-testid="attachment-remove">
                  <X size={14} />
                </button>
              </div>
            )}
            <div className="flex items-center gap-2">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*,application/pdf"
                onChange={onFilePick}
                className="hidden"
                data-testid="support-chat-file-input"
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="p-2 rounded-full hover:opacity-80"
                style={{ color: "var(--text-muted)" }}
                aria-label="Attach a file"
                data-testid="support-chat-attach"
                title="Attach image or PDF (max 800 KB)"
              >
                <Paperclip size={16} />
              </button>
              <input
                value={text}
                onChange={(e) => { setText(e.target.value); pingTyping(); }}
                placeholder="Type a message…"
                className="flex-1 px-3 py-2 rounded-full border bg-transparent text-sm"
                style={{ borderColor: "var(--border)" }}
                data-testid="support-chat-input"
                maxLength={2000}
                autoFocus
              />
              <button
                type="submit"
                disabled={(!text.trim() && !attachment) || sending}
                data-testid="support-chat-send"
                className="rounded-full p-2 disabled:opacity-40"
                style={{ background: "var(--accent)", color: "#0F2A3A" }}
                aria-label="Send"
              >
                <Send size={16} />
              </button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}

/**
 * Attachment — renders an image inline (clickable to open full-size) or a
 * small download card for PDFs. Used in both visitor + admin views.
 */
function Attachment({ att }) {
  if (!att) return null;
  if (att.mime?.startsWith("image/")) {
    return (
      <a href={att.data_url} target="_blank" rel="noopener noreferrer" className="block mb-1.5" data-testid="msg-attachment">
        <img
          src={att.data_url}
          alt={att.filename || "attachment"}
          className="rounded-lg max-w-[240px] max-h-[240px] object-contain"
        />
      </a>
    );
  }
  return (
    <a
      href={att.data_url}
      download={att.filename || "file.pdf"}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-2 px-2 py-1.5 rounded-lg border text-xs mb-1.5 hover:opacity-80"
      style={{ borderColor: "rgba(0,0,0,0.15)", background: "rgba(255,255,255,0.5)" }}
      data-testid="msg-attachment"
    >
      📎 {att.filename || "attachment"}
    </a>
  );
}


/**
 * RatingPrompt — 5-star widget rendered inline in the chat thread when the
 * admin closes the conversation. Submitting fires `POST /support/chat/rate`
 * and the system reply ("You rated this chat 4/5 — thanks!") appears next poll.
 */
function RatingPrompt({ text, onRate }) {
  const [hover, setHover] = useState(0);
  const [submitted, setSubmitted] = useState(false);

  if (submitted) {
    return (
      <div className="text-center text-xs italic py-2" style={{ color: "var(--text-muted)" }}>
        Thanks for the feedback! 🌟
      </div>
    );
  }

  return (
    <div
      className="mx-auto rounded-xl px-3 py-3 text-center text-sm"
      style={{ background: "var(--bg-card)", border: "1px solid var(--border)", maxWidth: 260 }}
      data-testid="rating-prompt"
    >
      <div className="font-medium mb-2">{text}</div>
      <div className="flex justify-center gap-1">
        {[1, 2, 3, 4, 5].map((star) => (
          <button
            key={star}
            type="button"
            onMouseEnter={() => setHover(star)}
            onMouseLeave={() => setHover(0)}
            onClick={() => { onRate?.(star); setSubmitted(true); }}
            aria-label={`Rate ${star} of 5`}
            data-testid={`rate-${star}`}
            className="transition-transform hover:scale-110"
          >
            <Star
              size={22}
              fill={(hover || 0) >= star ? "#F08A2A" : "transparent"}
              stroke={(hover || 0) >= star ? "#F08A2A" : "var(--text-muted)"}
            />
          </button>
        ))}
      </div>
    </div>
  );
}

