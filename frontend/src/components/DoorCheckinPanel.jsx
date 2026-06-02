import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api, { formatApiErrorDetail } from "@/lib/api";
import { toast } from "sonner";
import { ScanLine, X, Share2, Copy, Trash2, Plus, Loader2, ExternalLink } from "lucide-react";

/**
 * DoorCheckinPanel — the organizer dashboard's "go straight to the scanner"
 * entry point. Two flows in one tile:
 *   1) "Scan now"  — picks an upcoming event and opens the authenticated
 *      scanner page (organizer or admin).
 *   2) "Share link with door staff" — mints a scoped scanner token and copies
 *      a public /scan/:eventId?t=... URL to clipboard. No login required for
 *      the recipient; revocable any time.
 */
export default function DoorCheckinPanel({ events }) {
  const navigate = useNavigate();
  const upcoming = (events || []).filter((e) => e.status !== "rejected");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [shareEvent, setShareEvent] = useState(null);

  return (
    <>
      <div
        className="border rounded-2xl p-6 mb-10 flex flex-col sm:flex-row sm:items-center gap-4"
        style={{
          borderColor: "var(--accent)",
          background: "linear-gradient(135deg, rgba(13,148,136,0.06), rgba(240,138,42,0.04))",
        }}
        data-testid="door-checkin-panel"
      >
        <div
          className="w-14 h-14 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: "var(--accent)", color: "#fff" }}
        >
          <ScanLine className="w-7 h-7" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-xs uppercase tracking-[0.3em] mb-1" style={{ color: "var(--accent)" }}>Door check-in</div>
          <div className="serif text-2xl leading-tight">Open the QR scanner</div>
          <div className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
            Scan tickets at the door from any phone — or share a scoped link with volunteers (no login needed).
          </div>
        </div>
        <div className="flex flex-col sm:flex-row gap-2 flex-shrink-0">
          <button
            type="button"
            onClick={() => setPickerOpen(true)}
            className="btn-primary"
            data-testid="open-scanner-btn"
          >
            <ScanLine className="w-4 h-4" /> Scan now
          </button>
          <button
            type="button"
            onClick={() => { if (upcoming.length === 1) setShareEvent(upcoming[0]); else setPickerOpen("share"); }}
            className="btn-ghost"
            data-testid="share-scanner-btn"
            disabled={upcoming.length === 0}
          >
            <Share2 className="w-4 h-4" /> Share link
          </button>
        </div>
      </div>

      {pickerOpen && (
        <EventPicker
          events={upcoming}
          mode={pickerOpen === "share" ? "share" : "open"}
          onClose={() => setPickerOpen(false)}
          onPick={(ev) => {
            if (pickerOpen === "share") {
              setShareEvent(ev);
            } else {
              navigate(`/organizer/events/${ev.event_id}/checkin`);
            }
            setPickerOpen(false);
          }}
        />
      )}

      {shareEvent && (
        <ShareScannerModal event={shareEvent} onClose={() => setShareEvent(null)} />
      )}
    </>
  );
}

function EventPicker({ events, mode, onClose, onPick }) {
  return (
    <div className="fixed inset-0 z-[8000] flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,0.4)" }} onClick={onClose}>
      <div className="rounded-2xl border w-full max-w-md max-h-[80vh] overflow-auto" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between p-5 border-b" style={{ borderColor: "var(--border)" }}>
          <div>
            <div className="text-xs uppercase tracking-widest" style={{ color: "var(--accent)" }}>
              {mode === "share" ? "Share scanner with team" : "Choose an event"}
            </div>
            <div className="serif text-xl mt-1">{mode === "share" ? "Pick the event" : "Open scanner"}</div>
          </div>
          <button onClick={onClose} className="p-2 rounded-full hover:opacity-70" data-testid="event-picker-close"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-2">
          {events.length === 0 ? (
            <div className="text-center py-8" style={{ color: "var(--text-dim)" }}>No events yet. Create one first.</div>
          ) : events.map((e) => (
            <button
              key={e.event_id}
              type="button"
              onClick={() => onPick(e)}
              className="w-full text-left p-3 rounded-xl hover:bg-[color:var(--bg-elev)] transition flex items-center gap-3"
              data-testid={`event-picker-row-${e.event_id}`}
            >
              {e.image_url && (
                <img src={e.image_url.startsWith("http") ? e.image_url : `${process.env.REACT_APP_BACKEND_URL}${e.image_url}`} alt="" className="w-12 h-12 rounded-lg object-cover flex-shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <div className="font-medium truncate">{e.title}</div>
                <div className="text-xs" style={{ color: "var(--text-dim)" }}>
                  {e.venue} · {new Date(e.date).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                </div>
              </div>
              <span className="chip text-xs">{e.status}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function ShareScannerModal({ event, onClose }) {
  const [tokens, setTokens] = useState([]);
  const [label, setLabel] = useState("");
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);
  const origin = typeof window !== "undefined" ? window.location.origin : "";

  const load = async () => {
    try {
      setLoading(true);
      const { data } = await api.get(`/organizer/events/${event.event_id}/scanner-tokens`);
      setTokens(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Could not load scanner links");
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []); // eslint-disable-line

  const create = async () => {
    setCreating(true);
    try {
      const { data } = await api.post(`/organizer/events/${event.event_id}/scanner-tokens`, { label: label || undefined });
      setTokens((t) => [data, ...t]);
      setLabel("");
      copyLink(data.token);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Could not create scanner link");
    } finally { setCreating(false); }
  };

  const revoke = async (token_id) => {
    if (!window.confirm("Revoke this scanner link? It will stop working immediately.")) return;
    try {
      await api.delete(`/organizer/events/${event.event_id}/scanner-tokens/${token_id}`);
      setTokens((t) => t.map((x) => x.token_id === token_id ? { ...x, revoked: true } : x));
      toast.success("Link revoked");
    } catch (e) {
      toast.error("Revoke failed");
    }
  };

  const linkFor = (token) => `${origin}/scan/${event.event_id}?t=${encodeURIComponent(token)}`;

  const copyLink = (token) => {
    try {
      navigator.clipboard.writeText(linkFor(token));
      toast.success("Scanner link copied — paste it into WhatsApp / SMS / Email");
    } catch {
      toast(linkFor(token));
    }
  };

  return (
    <div className="fixed inset-0 z-[8000] flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,0.4)" }} onClick={onClose} data-testid="share-scanner-modal">
      <div className="rounded-2xl border w-full max-w-xl max-h-[85vh] overflow-auto" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between p-5 border-b" style={{ borderColor: "var(--border)" }}>
          <div>
            <div className="text-xs uppercase tracking-widest" style={{ color: "var(--accent)" }}>Door staff scanner</div>
            <div className="serif text-xl mt-1">{event.title}</div>
            <div className="text-xs" style={{ color: "var(--text-dim)" }}>Share a link — no account needed on the other side.</div>
          </div>
          <button onClick={onClose} className="p-2 rounded-full hover:opacity-70" data-testid="share-scanner-close"><X className="w-4 h-4" /></button>
        </div>

        <div className="p-5 border-b" style={{ borderColor: "var(--border)" }}>
          <div className="text-xs uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>Create new link</div>
          <div className="flex gap-2">
            <input
              type="text"
              placeholder='Label e.g. "Door 1" or "Sam (Volunteer)"'
              value={label}
              maxLength={80}
              onChange={(e) => setLabel(e.target.value)}
              className="flex-1 px-3 py-2 rounded-lg border outline-none text-sm"
              style={{ borderColor: "var(--border)", background: "var(--bg)", color: "var(--text)" }}
              data-testid="scanner-token-label-input"
            />
            <button type="button" onClick={create} disabled={creating} className="btn-primary" data-testid="create-scanner-token-btn">
              {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Create
            </button>
          </div>
          <div className="text-xs mt-2" style={{ color: "var(--text-dim)" }}>
            Each link is scoped to <strong>{event.title}</strong> only and can be revoked any time.
          </div>
        </div>

        <div className="p-5">
          {loading ? (
            <div className="text-center py-8" style={{ color: "var(--text-dim)" }}>Loading...</div>
          ) : tokens.length === 0 ? (
            <div className="text-center py-8 text-sm" style={{ color: "var(--text-dim)" }}>No scanner links yet. Create one above.</div>
          ) : (
            <div className="space-y-2">
              {tokens.map((t) => (
                <div
                  key={t.token_id}
                  className={`p-3 rounded-xl border flex items-center gap-3 ${t.revoked ? "opacity-50" : ""}`}
                  style={{ borderColor: "var(--border)", background: "var(--bg-elev)" }}
                  data-testid={`scanner-token-row-${t.token_id}`}
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">{t.label || "Door scanner"}</div>
                    <div className="text-[11px] truncate" style={{ color: "var(--text-dim)" }}>
                      Created {new Date(t.created_at).toLocaleDateString()} {t.revoked && "· Revoked"}
                    </div>
                  </div>
                  {!t.revoked && (
                    <>
                      <button onClick={() => copyLink(t.token)} className="btn-ghost text-xs py-1.5 px-2" data-testid={`copy-token-${t.token_id}`} title="Copy link">
                        <Copy className="w-3.5 h-3.5" /> Copy
                      </button>
                      <a href={linkFor(t.token)} target="_blank" rel="noreferrer" className="btn-ghost text-xs py-1.5 px-2" title="Open in new tab">
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                      <button onClick={() => revoke(t.token_id)} className="btn-ghost text-xs py-1.5 px-2" data-testid={`revoke-token-${t.token_id}`} title="Revoke">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
