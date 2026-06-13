import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Link2, Plus, Copy, Check, Trash2, Loader2 } from "lucide-react";

/**
 * AffiliatesPanel — organizer-only.
 *
 * Lets organizers create + manage affiliate / referral codes that:
 *   - Drop a 30-day cookie on click via /api/affiliate/track
 *   - Attribute conversions to the partner
 *   - Track commission owed
 *
 * Mounted on OrganizerEvent (event-scoped) and on a global /organizer/affiliates
 * page (no event_id = applies to all this organizer's events).
 */
export default function AffiliatesPanel({ eventId = null }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [draft, setDraft] = useState({
    code: "",
    partner_name: "",
    partner_email: "",
    commission_pct: 10,
    notes: "",
  });
  const [creating, setCreating] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/organizer/affiliates");
      const filtered = eventId
        ? data.filter((d) => d.event_id === eventId)
        : data;
      setRows(filtered);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get("/organizer/affiliates");
        if (cancelled) return;
        const filtered = eventId ? data.filter((d) => d.event_id === eventId) : data;
        setRows(filtered);
      } catch {
        if (!cancelled) setRows([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [eventId]);

  const create = async () => {
    if (!draft.code.trim() || !draft.partner_name.trim()) {
      toast.error("Code and partner name are required");
      return;
    }
    setCreating(true);
    try {
      await api.post("/organizer/affiliates", {
        ...draft,
        event_id: eventId,
        partner_email: draft.partner_email || null,
        commission_pct: Number(draft.commission_pct) || 0,
      });
      toast.success("Affiliate code created");
      setShowForm(false);
      setDraft({ code: "", partner_name: "", partner_email: "", commission_pct: 10, notes: "" });
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't create");
    } finally {
      setCreating(false);
    }
  };

  const remove = async (affiliate_id) => {
    if (!window.confirm("Deactivate this affiliate code?")) return;
    try {
      await api.delete(`/organizer/affiliates/${affiliate_id}`);
      toast.success("Deactivated");
      await load();
    } catch { toast.error("Failed"); }
  };

  return (
    <div
      className="border rounded-2xl p-6 mb-6"
      style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
      data-testid="affiliates-panel"
    >
      <div className="flex items-start justify-between mb-1 flex-wrap gap-2">
        <div>
          <div className="serif text-2xl flex items-center gap-2">
            <Link2 className="w-5 h-5" style={{ color: "var(--accent)" }} />
            Affiliate codes
          </div>
          <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>
            Track clicks and bookings driven by promoters, influencers, or partners. Each code drops a 30-day cookie so commission is attributed to the right person even if the buyer comes back later.
          </div>
        </div>
        <button
          onClick={() => setShowForm((s) => !s)}
          className="btn-primary !py-1.5 !px-3 text-xs"
          data-testid="affiliate-add-toggle"
        >
          <Plus className="w-3.5 h-3.5" />
          {showForm ? "Close" : "New affiliate"}
        </button>
      </div>

      {showForm && (
        <div className="mt-4 grid sm:grid-cols-2 gap-3 p-4 rounded-xl border" style={{ borderColor: "var(--border)", background: "var(--bg-elev)" }}>
          <div>
            <label className="text-xs" style={{ color: "var(--text-dim)" }}>Code</label>
            <input
              value={draft.code}
              onChange={(e) => setDraft({ ...draft, code: e.target.value.toUpperCase() })}
              placeholder="PROMO50"
              className="w-full"
              data-testid="affiliate-code-input"
            />
          </div>
          <div>
            <label className="text-xs" style={{ color: "var(--text-dim)" }}>Partner name</label>
            <input
              value={draft.partner_name}
              onChange={(e) => setDraft({ ...draft, partner_name: e.target.value })}
              placeholder="Influencer A / Promoter Co"
              className="w-full"
              data-testid="affiliate-partner-input"
            />
          </div>
          <div>
            <label className="text-xs" style={{ color: "var(--text-dim)" }}>Partner email (optional)</label>
            <input
              type="email"
              value={draft.partner_email}
              onChange={(e) => setDraft({ ...draft, partner_email: e.target.value })}
              placeholder="partner@example.com"
              className="w-full"
              data-testid="affiliate-email-input"
            />
          </div>
          <div>
            <label className="text-xs" style={{ color: "var(--text-dim)" }}>Commission %</label>
            <input
              type="number"
              min={0}
              max={100}
              value={draft.commission_pct}
              onChange={(e) => setDraft({ ...draft, commission_pct: e.target.value })}
              className="w-full"
              data-testid="affiliate-pct-input"
            />
          </div>
          <div className="sm:col-span-2">
            <label className="text-xs" style={{ color: "var(--text-dim)" }}>Notes (optional)</label>
            <input
              value={draft.notes}
              onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
              placeholder="Where this code is being used"
              className="w-full"
              data-testid="affiliate-notes-input"
            />
          </div>
          <div className="sm:col-span-2 flex justify-end">
            <button
              onClick={create}
              disabled={creating}
              className="btn-primary !py-2"
              data-testid="affiliate-save-btn"
            >
              {creating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
              Create
            </button>
          </div>
        </div>
      )}

      <div className="mt-4 space-y-2">
        {loading && <div className="text-xs" style={{ color: "var(--text-dim)" }}>Loading…</div>}
        {!loading && rows.length === 0 && (
          <div className="text-xs text-center py-6" style={{ color: "var(--text-dim)" }}>
            No affiliate codes yet. Create one to share with a partner — they&apos;ll get a trackable link they can paste anywhere.
          </div>
        )}
        {rows.map((a) => (
          <AffiliateRow key={a.affiliate_id} affiliate={a} onDelete={() => remove(a.affiliate_id)} />
        ))}
      </div>
    </div>
  );
}

function AffiliateRow({ affiliate, onDelete }) {
  const [copied, setCopied] = useState(false);
  const origin = typeof window !== "undefined" ? window.location.origin : "https://www.allsale.events";
  const eventParam = affiliate.event_id ? `&event_id=${affiliate.event_id}` : "";
  const trackUrl = `${origin}/api/affiliate/track?code=${encodeURIComponent(affiliate.code)}${eventParam}`;

  const copy = async () => {
    try { await navigator.clipboard.writeText(trackUrl); setCopied(true); setTimeout(() => setCopied(false), 1200); } catch { /* empty */ }
  };

  return (
    <div
      className="border rounded-xl p-3 flex flex-wrap items-center gap-3"
      style={{ borderColor: "var(--border)", background: "var(--bg-elev)" }}
      data-testid={`affiliate-row-${affiliate.affiliate_id}`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-sm font-semibold">{affiliate.code}</span>
          <span className="text-xs" style={{ color: "var(--text-dim)" }}>{affiliate.partner_name}</span>
          {!affiliate.active && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: "rgba(198,40,40,0.12)", color: "rgb(198,40,40)" }}>Deactivated</span>
          )}
        </div>
        <div className="flex items-center gap-3 mt-1 text-xs flex-wrap" style={{ color: "var(--text-dim)" }}>
          <span><strong>{affiliate.clicks || 0}</strong> clicks</span>
          <span><strong>{affiliate.conversions || 0}</strong> sales</span>
          <span><strong>{(affiliate.tickets_sold || 0)}</strong> tickets</span>
          <span><strong>{affiliate.commission_pct}%</strong> commission</span>
          {affiliate.commission_owed > 0 && (
            <span style={{ color: "rgb(46,160,67)" }}>
              <strong>${(affiliate.commission_owed || 0).toFixed(2)}</strong> owed
            </span>
          )}
        </div>
      </div>
      <button onClick={copy} className="btn-ghost !py-1 !px-2 text-xs" data-testid={`affiliate-copy-${affiliate.affiliate_id}`} title={trackUrl}>
        {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
        Copy link
      </button>
      {affiliate.active && (
        <button onClick={onDelete} className="btn-ghost !p-1.5" title="Deactivate" data-testid={`affiliate-delete-${affiliate.affiliate_id}`}>
          <Trash2 className="w-3.5 h-3.5" style={{ color: "var(--danger)" }} />
        </button>
      )}
    </div>
  );
}
