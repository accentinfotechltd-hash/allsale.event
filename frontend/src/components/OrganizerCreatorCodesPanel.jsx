/**
 * OrganizerCreatorCodesPanel — embed in OrganizerEvent.jsx.
 *
 * Lets the event's organizer manage their own creator promo codes:
 *   • View each creator's code, discount %, commission %, usage, revenue, credited
 *   • Add / Edit / Deactivate codes
 *   • Search & pick from enrolled creators
 *
 * Talks to the organizer-scoped mirror endpoints (auth checks ownership):
 *   POST   /api/organizer/events/{event_id}/creator-codes
 *   GET    /api/organizer/events/{event_id}/creator-codes
 *   PATCH  /api/organizer/events/{event_id}/creator-codes/{code_id}
 *   DELETE /api/organizer/events/{event_id}/creator-codes/{code_id}
 *   GET    /api/organizer/creator-codes/users-search?q=
 */
import { useEffect, useState, useCallback } from "react";
import { Tag, Plus, Trash2, Loader2, X as XIcon, TrendingUp, Pencil } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

const BASE = "/organizer";

export default function OrganizerCreatorCodesPanel({ eventId, eventTitle }) {
  const [codes, setCodes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingCode, setEditingCode] = useState(null);

  const refresh = useCallback(async () => {
    if (!eventId) return;
    setLoading(true);
    try {
      const r = await api.get(`${BASE}/events/${eventId}/creator-codes`);
      setCodes(r.data?.items || []);
    } catch (err) {
      // 403 = not your event (shouldn't reach here normally); silent log.
      if (err?.response?.status === 403) {
        setCodes([]);
      } else {
        setCodes([]);
      }
    } finally {
      setLoading(false);
    }
  }, [eventId]);

  useEffect(() => { refresh(); }, [refresh]);

  const deactivate = async (codeId) => {
    if (!window.confirm("Deactivate this creator code? (Existing earnings stay)")) return;
    try {
      await api.delete(`${BASE}/events/${eventId}/creator-codes/${codeId}`);
      toast.success("Code deactivated");
      refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't deactivate");
    }
  };

  return (
    <div className="mb-8 rounded-2xl border p-5" style={{ background: "var(--surface)", borderColor: "var(--border)" }} data-testid="organizer-creator-codes-panel">
      <div className="flex items-start justify-between flex-wrap gap-3 mb-4">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-widest" style={{ color: "var(--accent)" }}>
            <Tag size={13} /> Creator promo codes
          </div>
          <h3 className="font-serif text-lg mt-1" style={{ color: "var(--text)" }}>Codes for your creators</h3>
          <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
            Attach codes to enrolled creators for this event. Buyers get a discount, the creator
            earns a commission on each paid booking that uses the code.
          </p>
        </div>
        <button
          onClick={() => { setEditingCode(null); setModalOpen(true); }}
          className="btn-primary text-sm inline-flex items-center gap-1.5"
          data-testid="org-creator-codes-add-btn"
        >
          <Plus size={14} /> Add creator code
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
              <th className="text-left px-2 py-2">Code</th>
              <th className="text-left px-2 py-2">Creator</th>
              <th className="text-right px-2 py-2">Discount</th>
              <th className="text-right px-2 py-2">Commission</th>
              <th className="text-right px-2 py-2">Uses</th>
              <th className="text-right px-2 py-2">Revenue</th>
              <th className="text-right px-2 py-2">Credited</th>
              <th className="text-right px-2 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={8} className="text-center py-4"><Loader2 className="inline animate-spin" size={16} /></td></tr>
            )}
            {!loading && codes.length === 0 && (
              <tr>
                <td colSpan={8} className="text-center py-6" style={{ color: "var(--text-dim)" }} data-testid="org-creator-codes-empty">
                  No creator codes yet for this event. Click <span className="font-medium" style={{ color: "var(--accent)" }}>Add creator code</span> to attach one to an enrolled creator.
                </td>
              </tr>
            )}
            {codes.map((c) => (
              <tr key={c.code_id} className="border-t" style={{ borderColor: "var(--border)" }} data-testid={`org-creator-code-row-${c.code_id}`}>
                <td className="px-2 py-3 font-mono text-xs" style={{ color: c.active ? "var(--text)" : "var(--text-dim)" }}>
                  {c.code}
                  {!c.active && <span className="ml-1.5 text-[10px] opacity-60">(inactive)</span>}
                </td>
                <td className="px-2 py-3" style={{ color: "var(--text)" }}>
                  <div className="text-xs font-medium">{c.creator_name || "—"}</div>
                  <div className="text-[10px]" style={{ color: "var(--text-dim)" }}>{c.creator_email}</div>
                </td>
                <td className="px-2 py-3 text-right" style={{ color: "var(--text)" }}>
                  {Number(c.value) > 0
                    ? (c.kind === "percent" ? `${c.value}%` : `$${c.value}`)
                    : "—"}
                </td>
                <td className="px-2 py-3 text-right" style={{ color: "var(--text)" }}>
                  {c.commission_percent != null ? `${c.commission_percent}%` : "—"}
                </td>
                <td className="px-2 py-3 text-right" style={{ color: "var(--text)" }}>
                  {c.uses_count}{c.max_uses ? `/${c.max_uses}` : ""}
                </td>
                <td className="px-2 py-3 text-right" style={{ color: "var(--text)" }}>${c.revenue.toFixed(2)}</td>
                <td className="px-2 py-3 text-right" style={{ color: "var(--text)" }}>
                  ${c.commission_credited.toFixed(2)}
                  {c.commission_unpaid > 0 && (
                    <div className="text-[10px]" style={{ color: "var(--accent)" }}>${c.commission_unpaid.toFixed(2)} unpaid</div>
                  )}
                </td>
                <td className="px-2 py-3 text-right">
                  <div className="inline-flex items-center gap-2">
                    <button
                      onClick={() => { setEditingCode(c); setModalOpen(true); }}
                      className="text-xs inline-flex items-center gap-1"
                      style={{ color: "var(--accent)" }}
                      data-testid={`org-edit-code-${c.code_id}`}
                    >
                      <Pencil size={11} /> Edit
                    </button>
                    {c.active && (
                      <button onClick={() => deactivate(c.code_id)} className="text-xs inline-flex items-center gap-1" style={{ color: "#E74C3C" }} data-testid={`org-deactivate-code-${c.code_id}`}>
                        <Trash2 size={11} /> Deactivate
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modalOpen && (
        <OrganizerAddCreatorCodeModal
          eventId={eventId}
          eventTitle={eventTitle}
          code={editingCode}
          onClose={() => { setModalOpen(false); setEditingCode(null); }}
          onSaved={() => { setModalOpen(false); setEditingCode(null); refresh(); }}
        />
      )}
    </div>
  );
}

function OrganizerAddCreatorCodeModal({ eventId, eventTitle, code, onClose, onSaved }) {
  const isEdit = !!code;
  const [form, setForm] = useState(() => isEdit ? {
    code: code.code, creator_email: code.creator_email,
    kind: code.kind || "percent", value: code.value ?? "",
    commission_percent: code.commission_percent ?? "",
    max_uses: code.max_uses ?? "",
    expires_at: code.expires_at ? code.expires_at.slice(0, 16) : "",
  } : {
    code: "", creator_email: "", kind: "percent", value: "",
    commission_percent: "", max_uses: "", expires_at: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [creatorSearch, setCreatorSearch] = useState("");
  const [creatorSuggestions, setCreatorSuggestions] = useState([]);

  useEffect(() => {
    if (isEdit) return;
    if (creatorSearch.trim().length < 2) { setCreatorSuggestions([]); return; }
    const t = setTimeout(async () => {
      try {
        const r = await api.get(`${BASE}/creator-codes/users-search?q=${encodeURIComponent(creatorSearch)}`);
        setCreatorSuggestions(r.data?.items || []);
      } catch {
        setCreatorSuggestions([]);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [creatorSearch, isEdit]);

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    if (!isEdit && !form.code.trim()) { toast.error("Code is required"); return; }
    if (!isEdit && !form.creator_email.trim()) { toast.error("Pick a creator"); return; }
    const numValue = form.value === "" || form.value === null ? 0 : Number(form.value);
    if (Number.isNaN(numValue) || numValue < 0) { toast.error("Discount value must be 0 or more"); return; }
    const numCommission = form.commission_percent === "" || form.commission_percent === null ? 0 : Number(form.commission_percent);
    if (numValue === 0 && numCommission === 0) {
      toast.error("Set a discount, a commission %, or both — otherwise the code has no effect.");
      return;
    }
    setSubmitting(true);
    try {
      if (isEdit) {
        const payload = {
          kind: form.kind,
          value: numValue,
          commission_percent: numCommission,
          max_uses: form.max_uses ? Number(form.max_uses) : null,
          expires_at: form.expires_at ? new Date(form.expires_at).toISOString() : null,
        };
        await api.patch(`${BASE}/events/${eventId}/creator-codes/${code.code_id}`, payload);
        toast.success("Creator code updated");
      } else {
        const payload = {
          code: form.code.trim().toUpperCase(),
          creator_email: form.creator_email,
          kind: form.kind,
          value: numValue,
          commission_percent: numCommission > 0 ? numCommission : null,
          max_uses: form.max_uses ? Number(form.max_uses) : null,
          expires_at: form.expires_at ? new Date(form.expires_at).toISOString() : null,
        };
        await api.post(`${BASE}/events/${eventId}/creator-codes`, payload);
        toast.success("Creator code created");
      }
      onSaved();
    } catch (ex) {
      toast.error(ex?.response?.data?.detail || "Couldn't save code");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.7)", backdropFilter: "blur(4px)" }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      data-testid="org-add-creator-code-modal"
    >
      <div className="rounded-2xl border w-full max-w-md p-5" style={{ background: "var(--bg, #0f0f12)", borderColor: "var(--border)" }}>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="font-serif text-lg" style={{ color: "var(--text)" }}>
              {isEdit ? `Edit ${code.code}` : "New creator code"}
            </h3>
            {eventTitle && <div className="text-[11px] mt-0.5" style={{ color: "var(--text-dim)" }}>{eventTitle}</div>}
          </div>
          <button onClick={onClose} className="p-1" style={{ color: "var(--text-dim)" }}><XIcon size={16} /></button>
        </div>

        <form onSubmit={submit} className="space-y-3">
          {!isEdit && (
            <Field label="Promo code">
              <input
                value={form.code}
                onChange={(e) => update("code", e.target.value.toUpperCase().replace(/[^A-Z0-9_-]/g, ""))}
                placeholder="CHLOE15"
                className="w-full px-3 py-2 rounded-md border text-sm font-mono"
                style={{ borderColor: "var(--border)", background: "transparent", color: "var(--text)" }}
                maxLength={24}
                data-testid="org-creator-code-input"
              />
            </Field>
          )}

          {isEdit ? (
            <Field label="Creator (immutable)">
              <div className="px-3 py-2 rounded-md border text-sm" style={{ borderColor: "var(--border)", color: "var(--text-dim)", background: "rgba(255,255,255,0.02)" }}>
                {code.creator_name || code.creator_email} <span className="text-[10px]">· {code.creator_email}</span>
              </div>
            </Field>
          ) : (
            <Field label="Creator (only enrolled creators shown)">
              <input
                value={form.creator_email || creatorSearch}
                onChange={(e) => { setCreatorSearch(e.target.value); update("creator_email", e.target.value); }}
                placeholder="Search by name or email…"
                className="w-full px-3 py-2 rounded-md border text-sm"
                style={{ borderColor: "var(--border)", background: "transparent", color: "var(--text)" }}
                data-testid="org-creator-email-input"
              />
              {creatorSearch.trim().length >= 2 && creatorSuggestions.length === 0 && (
                <p className="text-[10px] mt-1" style={{ color: "var(--text-dim)" }}>
                  No enrolled creator matches. They must first enable creator mode via /influencer/onboarding.
                </p>
              )}
              {creatorSuggestions.length > 0 && (
                <div className="mt-1 rounded-md border max-h-44 overflow-y-auto" style={{ borderColor: "var(--border)", background: "var(--bg, #0f0f12)" }}>
                  {creatorSuggestions.map((u) => (
                    <button
                      key={u.user_id}
                      type="button"
                      onClick={() => { update("creator_email", u.email); setCreatorSearch(""); setCreatorSuggestions([]); }}
                      className="block w-full text-left px-3 py-2 text-sm hover:bg-white/5"
                      style={{ color: "var(--text)" }}
                      data-testid={`org-creator-suggestion-${u.user_id}`}
                    >
                      <div className="text-xs font-medium">{u.display_name || u.name || u.email}</div>
                      <div className="text-[10px]" style={{ color: "var(--text-dim)" }}>
                        {u.email}
                        {u.follower_count > 0 && <span> · {u.follower_count.toLocaleString()} followers</span>}
                        {u.categories && u.categories.length > 0 && <span> · {u.categories.slice(0, 2).join(", ")}</span>}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </Field>
          )}

          <div className="grid grid-cols-2 gap-3">
            <Field label="Discount kind">
              <select
                value={form.kind}
                onChange={(e) => update("kind", e.target.value)}
                className="w-full px-3 py-2 rounded-md border text-sm"
                style={{ borderColor: "var(--border)", background: "transparent", color: "var(--text)" }}
                data-testid="org-creator-code-kind"
              >
                <option value="percent">% off</option>
                <option value="flat">$ off</option>
              </select>
            </Field>
            <Field label={`${form.kind === "percent" ? "% off" : "$ off"} (optional)`} help="Leave blank for a commission-only code.">
              <input
                type="number"
                step="0.01"
                value={form.value}
                onChange={(e) => update("value", e.target.value)}
                min={0}
                max={form.kind === "percent" ? 100 : undefined}
                placeholder="0 = no discount"
                className="w-full px-3 py-2 rounded-md border text-sm"
                style={{ borderColor: "var(--border)", background: "transparent", color: "var(--text)" }}
                data-testid="org-creator-code-value"
              />
            </Field>
          </div>

          <Field
            label="Creator commission %"
            help="Optional — % the creator earns on each paid booking using this code. Leave blank for discount-only."
          >
            <div className="relative">
              <TrendingUp size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "var(--text-dim)" }} />
              <input
                type="number"
                step="0.1"
                value={form.commission_percent}
                onChange={(e) => update("commission_percent", e.target.value)}
                placeholder="e.g. 5"
                min={0}
                max={100}
                className="w-full pl-8 pr-3 py-2 rounded-md border text-sm"
                style={{ borderColor: "var(--border)", background: "transparent", color: "var(--text)" }}
                data-testid="org-creator-code-commission"
              />
            </div>
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Max uses (optional)">
              <input
                type="number"
                value={form.max_uses}
                onChange={(e) => update("max_uses", e.target.value)}
                placeholder="unlimited"
                min={1}
                className="w-full px-3 py-2 rounded-md border text-sm"
                style={{ borderColor: "var(--border)", background: "transparent", color: "var(--text)" }}
                data-testid="org-creator-code-max-uses"
              />
            </Field>
            <Field label="Expires at (optional)">
              <input
                type="datetime-local"
                value={form.expires_at}
                onChange={(e) => update("expires_at", e.target.value)}
                className="w-full px-3 py-2 rounded-md border text-sm"
                style={{ borderColor: "var(--border)", background: "transparent", color: "var(--text)" }}
                data-testid="org-creator-code-expires"
              />
            </Field>
          </div>

          <div className="flex gap-2 pt-2">
            <button type="submit" disabled={submitting} className="btn-primary flex-1 text-sm justify-center" data-testid="org-creator-code-submit-btn">
              {submitting ? "Saving…" : isEdit ? "Save changes" : "Create code"}
            </button>
            <button type="button" onClick={onClose} className="btn-ghost text-sm">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({ label, help, children }) {
  return (
    <div>
      <label className="block text-xs mb-1" style={{ color: "var(--text-dim)" }}>{label}</label>
      {children}
      {help && <p className="text-[10px] mt-1" style={{ color: "var(--text-dim)" }}>{help}</p>}
    </div>
  );
}
