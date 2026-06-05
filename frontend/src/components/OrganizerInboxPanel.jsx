import { useEffect, useState } from "react";
import { Mail, MailOpen, Trash2, ExternalLink, X, ChevronDown, ChevronRight } from "lucide-react";
import { toast } from "sonner";

import api from "@/lib/api";

/**
 * Organizer-side message inbox.
 * Reads /api/organizer/messages and lets the organizer mark messages as
 * read/unread or delete them. Used at the top of /organizer dashboard.
 */
export default function OrganizerInboxPanel() {
  const [data, setData] = useState({ messages: [], unread_count: 0 });
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(null); // currently expanded message

  const load = async () => {
    try {
      const { data } = await api.get("/organizer/messages");
      setData(data);
    } catch { /* noop */ } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const markRead = async (m, read) => {
    try {
      await api.post(`/organizer/messages/${m.message_id}/read`, { read });
      load();
    } catch { toast.error("Could not update status"); }
  };

  const del = async (m) => {
    if (!window.confirm(`Delete message from ${m.from_name}? This can't be undone.`)) return;
    try {
      await api.delete(`/organizer/messages/${m.message_id}`);
      toast.success("Message deleted");
      if (active?.message_id === m.message_id) setActive(null);
      load();
    } catch { toast.error("Could not delete"); }
  };

  if (loading) return null;
  // Hide the panel entirely when there are no messages so it doesn't add
  // noise to organizers who haven't received any visitor enquiries yet.
  if (data.messages.length === 0 && !open) return null;

  return (
    <div
      className="border rounded-2xl mb-10"
      style={{ borderColor: data.unread_count ? "var(--accent)" : "var(--border)", background: "var(--bg-card)" }}
      data-testid="organizer-inbox-panel"
    >
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between p-5 text-left"
        data-testid="organizer-inbox-toggle"
      >
        <div className="flex items-center gap-3">
          {data.unread_count ? (
            <Mail className="w-5 h-5" style={{ color: "var(--accent)" }} />
          ) : (
            <MailOpen className="w-5 h-5" style={{ color: "var(--text-dim)" }} />
          )}
          <div>
            <div className="font-medium" style={{ color: "var(--text)" }}>
              Inbox
              {data.unread_count > 0 && (
                <span
                  className="ml-2 px-2 py-0.5 rounded-full text-xs font-semibold"
                  style={{ background: "var(--accent)", color: "#fff" }}
                  data-testid="organizer-inbox-unread-count"
                >
                  {data.unread_count}
                </span>
              )}
            </div>
            <div className="text-xs" style={{ color: "var(--text-dim)" }}>
              {data.messages.length} total · {data.unread_count} unread
            </div>
          </div>
        </div>
        {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
      </button>

      {open && (
        <div className="border-t" style={{ borderColor: "var(--border)" }}>
          {data.messages.length === 0 ? (
            <p className="p-5 text-sm" style={{ color: "var(--text-muted)" }}>
              No messages yet. Visitors can reach you via the "Contact organizer" button on your event pages.
            </p>
          ) : (
            <ul className="divide-y" style={{ borderColor: "var(--border)" }}>
              {data.messages.map((m) => {
                const isActive = active?.message_id === m.message_id;
                return (
                  <li key={m.message_id} style={{ borderTop: "1px solid var(--border)" }} data-testid={`inbox-msg-${m.message_id}`}>
                    <div
                      className="px-5 py-3 flex items-start gap-3 cursor-pointer hover:bg-black/10"
                      onClick={() => {
                        setActive(isActive ? null : m);
                        if (!m.read) markRead(m, true);
                      }}
                    >
                      <span
                        className="mt-1 w-2 h-2 rounded-full flex-shrink-0"
                        style={{ background: m.read ? "transparent" : "var(--accent)", border: m.read ? "1px solid var(--border)" : "none" }}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-baseline justify-between gap-2">
                          <span className="font-medium truncate" style={{ color: "var(--text)" }}>{m.from_name}</span>
                          <span className="text-xs flex-shrink-0" style={{ color: "var(--text-dim)" }}>
                            {new Date(m.created_at).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" })}
                          </span>
                        </div>
                        <div className="text-sm truncate" style={{ color: m.read ? "var(--text-muted)" : "var(--text)" }}>
                          {m.subject}
                        </div>
                        {m.event_title && (
                          <div className="text-xs mt-0.5" style={{ color: "var(--text-dim)" }}>about: {m.event_title}</div>
                        )}
                      </div>
                    </div>
                    {isActive && (
                      <div className="px-5 pb-5 pt-1 ml-5" data-testid={`inbox-msg-body-${m.message_id}`}>
                        <div className="text-sm whitespace-pre-wrap p-4 rounded-lg" style={{ background: "var(--bg)", color: "var(--text)" }}>
                          {m.message}
                        </div>
                        <div className="flex items-center gap-2 mt-3 flex-wrap">
                          <a
                            href={`mailto:${m.from_email}?subject=${encodeURIComponent("Re: " + m.subject)}`}
                            className="btn-primary !text-xs !py-1.5"
                            data-testid={`inbox-reply-${m.message_id}`}
                          >
                            <ExternalLink className="w-3 h-3" /> Reply to {m.from_email}
                          </a>
                          <button
                            type="button"
                            onClick={() => markRead(m, !m.read)}
                            className="btn-ghost !text-xs !py-1.5"
                            data-testid={`inbox-toggle-read-${m.message_id}`}
                          >
                            Mark as {m.read ? "unread" : "read"}
                          </button>
                          <button
                            type="button"
                            onClick={() => del(m)}
                            className="btn-ghost !text-xs !py-1.5"
                            style={{ color: "var(--danger)", borderColor: "var(--danger)" }}
                            data-testid={`inbox-delete-${m.message_id}`}
                          >
                            <Trash2 className="w-3 h-3" /> Delete
                          </button>
                        </div>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
