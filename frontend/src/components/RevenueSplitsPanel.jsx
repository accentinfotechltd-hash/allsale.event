import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Users, Plus, Trash2, AlertCircle, CheckCircle2, Loader2, Percent } from "lucide-react";

/**
 * Multi-organizer revenue splits panel.
 *
 * Lets the event owner share ticket revenue with one or more co-organizers
 * (e.g. promoter 70 / venue 30). Each recipient must have their own
 * verified Stripe Connect account before the engine will pay them.
 *
 * Mount on the OrganizerEvent drilldown page. Only visible to event owner
 * + admin.
 *
 * Backend:
 *   GET    /api/organizer/events/{id}/revenue-splits
 *   PUT    /api/organizer/events/{id}/revenue-splits  body: {splits: [{user_id,label,percent}]}
 *   DELETE /api/organizer/events/{id}/revenue-splits
 *   GET    /api/organizer/users/lookup?email=foo@bar
 */
export default function RevenueSplitsPanel({ eventId, event, currentUser }) {
  const [rows, setRows] = useState([]); // [{user_id, label, percent, name, email, stripe_payouts_enabled}]
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [lookupEmail, setLookupEmail] = useState("");
  const [adding, setAdding] = useState(false);

  const isOwner = currentUser && event && (currentUser.user_id === event.organizer_id || currentUser.role === "admin");

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/organizer/events/${eventId}/revenue-splits`);
      if (data.configured) setRows(data.splits || []);
      else setRows([]);
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
        const { data } = await api.get(`/organizer/events/${eventId}/revenue-splits`);
        if (cancelled) return;
        if (data.configured) setRows(data.splits || []);
        else setRows([]);
      } catch {
        if (!cancelled) setRows([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [eventId]);

  const total = Math.round(rows.reduce((s, r) => s + Number(r.percent || 0), 0) * 100) / 100;

  const addRecipient = async () => {
    const email = (lookupEmail || "").trim();
    if (!email) return;
    setAdding(true);
    try {
      const { data } = await api.get(`/organizer/users/lookup`, { params: { email } });
      if (rows.find((r) => r.user_id === data.user_id)) {
        toast.message(`${data.name || data.email} is already in the list.`);
        return;
      }
      const nextPercent = Math.max(0, Math.round((100 - total) * 100) / 100);
      setRows([...rows, {
        user_id: data.user_id,
        label: data.name || "Co-organizer",
        percent: nextPercent,
        name: data.name,
        email: data.email,
        stripe_payouts_enabled: data.stripe_payouts_enabled,
      }]);
      setLookupEmail("");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not find that organizer");
    } finally {
      setAdding(false);
    }
  };

  const removeRow = (user_id) => setRows(rows.filter((r) => r.user_id !== user_id));

  const updateField = (user_id, field, value) => {
    setRows(rows.map((r) => r.user_id === user_id ? { ...r, [field]: value } : r));
  };

  const startSplit = async () => {
    // Seed with owner at 100% so the user just needs to invite a co-organizer.
    if (!currentUser) return;
    const owner = {
      user_id: currentUser.user_id,
      label: currentUser.name || "Primary organizer",
      percent: 100,
      name: currentUser.name,
      email: currentUser.email,
      stripe_payouts_enabled: !!currentUser.stripe_payouts_enabled,
    };
    setRows([owner]);
  };

  const save = async () => {
    if (Math.abs(total - 100) > 0.5) {
      toast.error(`Splits must add up to 100% (currently ${total.toFixed(2)}%).`);
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.put(`/organizer/events/${eventId}/revenue-splits`, {
        splits: rows.map((r) => ({
          user_id: r.user_id,
          label: r.label || "recipient",
          percent: Number(r.percent),
        })),
      });
      if (data.warnings?.length) {
        data.warnings.forEach((w) => toast.warning(w));
      } else {
        toast.success("Revenue splits saved");
      }
      setRows(data.splits || rows);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't save splits");
    } finally {
      setSaving(false);
    }
  };

  const clearAll = async () => {
    if (!window.confirm("Clear all revenue splits? After clearing, the event owner receives 100% of each payout.")) return;
    setSaving(true);
    try {
      await api.delete(`/organizer/events/${eventId}/revenue-splits`);
      setRows([]);
      toast.success("Revenue splits cleared");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't clear");
    } finally {
      setSaving(false);
    }
  };

  if (!isOwner) return null;

  return (
    <div
      className="border rounded-2xl p-6 mb-6"
      style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
      data-testid="revenue-splits-panel"
    >
      <div className="flex items-start justify-between mb-1 flex-wrap gap-2">
        <div>
          <div className="serif text-2xl flex items-center gap-2">
            <Users className="w-5 h-5" style={{ color: "var(--accent)" }} />
            Revenue splits
          </div>
          <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>
            Share ticket revenue with one or more co-organizers (e.g. promoter 70% / venue 30%). Each recipient must complete Stripe Connect to receive their share.
          </div>
        </div>
        {rows.length > 0 && (
          <div
            className="text-xs px-2.5 py-1 rounded-full"
            style={{
              background: Math.abs(total - 100) < 0.5 ? "rgba(46,160,67,0.12)" : "rgba(240,138,42,0.12)",
              color: Math.abs(total - 100) < 0.5 ? "rgb(46,160,67)" : "var(--accent)",
            }}
            data-testid="splits-total-pct"
          >
            Total: {total.toFixed(2)}%
          </div>
        )}
      </div>

      {loading ? (
        <div className="text-sm py-6 text-center" style={{ color: "var(--text-dim)" }}>
          <Loader2 className="w-4 h-4 animate-spin inline" /> Loading splits…
        </div>
      ) : rows.length === 0 ? (
        <div className="mt-4 p-4 rounded-xl border text-sm" style={{ borderColor: "var(--border)", background: "var(--bg-elev)", color: "var(--text-muted)" }}>
          <p>No splits configured — you (the event owner) receive 100% of payouts.</p>
          <button
            onClick={startSplit}
            className="btn-primary mt-3 !py-1.5 !px-3 text-xs"
            data-testid="start-splits-btn"
          >
            <Plus className="w-3.5 h-3.5" /> Start a revenue split
          </button>
        </div>
      ) : (
        <>
          <div className="space-y-2 mt-4">
            {rows.map((r) => (
              <div
                key={r.user_id}
                className="grid grid-cols-[1fr_140px_120px_36px] gap-2 items-center p-3 rounded-xl border"
                style={{ borderColor: "var(--border)", background: "var(--bg-elev)" }}
                data-testid={`split-row-${r.user_id}`}
              >
                <div className="min-w-0">
                  <div className="text-sm font-medium truncate">{r.name || r.label || r.email}</div>
                  <div className="text-xs truncate flex items-center gap-1.5" style={{ color: "var(--text-dim)" }}>
                    {r.email}
                    {r.stripe_payouts_enabled ? (
                      <span className="inline-flex items-center gap-0.5" style={{ color: "rgb(46,160,67)" }}>
                        <CheckCircle2 className="w-3 h-3" /> Stripe verified
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-0.5" style={{ color: "var(--accent)" }}>
                        <AlertCircle className="w-3 h-3" /> Connect required
                      </span>
                    )}
                  </div>
                </div>
                <input
                  type="text"
                  value={r.label || ""}
                  placeholder="Label (e.g. Venue)"
                  onChange={(e) => updateField(r.user_id, "label", e.target.value)}
                  className="px-2 py-1 rounded-md text-xs border bg-transparent"
                  style={{ borderColor: "var(--border)" }}
                  data-testid={`split-label-${r.user_id}`}
                />
                <div className="relative">
                  <input
                    type="number"
                    value={r.percent}
                    min={0}
                    max={100}
                    step={0.5}
                    onChange={(e) => updateField(r.user_id, "percent", Number(e.target.value))}
                    className="w-full pl-2 pr-7 py-1 rounded-md text-sm border bg-transparent"
                    style={{ borderColor: "var(--border)" }}
                    data-testid={`split-percent-${r.user_id}`}
                  />
                  <Percent className="w-3.5 h-3.5 absolute right-2 top-1/2 -translate-y-1/2" style={{ color: "var(--text-dim)" }} />
                </div>
                <button
                  onClick={() => removeRow(r.user_id)}
                  className="btn-ghost !p-1.5"
                  title="Remove from split"
                  data-testid={`remove-split-${r.user_id}`}
                >
                  <Trash2 className="w-3.5 h-3.5" style={{ color: "var(--danger)" }} />
                </button>
              </div>
            ))}
          </div>

          {/* Add co-organizer */}
          <div className="flex gap-2 mt-4 items-center">
            <input
              type="email"
              value={lookupEmail}
              placeholder="Add co-organizer by email"
              onChange={(e) => setLookupEmail(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") addRecipient(); }}
              className="flex-1 px-3 py-2 rounded-md text-sm border bg-transparent"
              style={{ borderColor: "var(--border)" }}
              data-testid="splits-lookup-email"
            />
            <button
              onClick={addRecipient}
              disabled={adding || !lookupEmail.trim()}
              className="btn-ghost !py-2"
              data-testid="splits-add-btn"
            >
              {adding ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
              Add
            </button>
          </div>
          <div className="text-[11px] mt-2" style={{ color: "var(--text-dim)" }}>
            Co-organizers must already have an organizer account on Allsale. They&apos;ll need to complete Stripe Connect before they can receive a share.
          </div>

          {/* Actions */}
          <div className="flex gap-2 mt-5 justify-end">
            <button
              onClick={clearAll}
              disabled={saving}
              className="btn-ghost !py-2"
              data-testid="splits-clear-btn"
            >
              <Trash2 className="w-3.5 h-3.5" /> Clear splits
            </button>
            <button
              onClick={save}
              disabled={saving || Math.abs(total - 100) > 0.5}
              className="btn-primary !py-2"
              data-testid="splits-save-btn"
            >
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
              Save splits
            </button>
          </div>
        </>
      )}
    </div>
  );
}
