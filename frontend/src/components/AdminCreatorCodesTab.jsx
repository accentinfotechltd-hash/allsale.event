import { useEffect, useState, useCallback } from "react";
import { Tag, Plus, Search, Trash2, Loader2, X as XIcon, TrendingUp } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

/**
 * Admin tab to attach a discount promo code to a creator/influencer for a
 * specific event. Two-pane layout:
 *
 *   Left:  pick the event (search by title / category)
 *   Right: list existing creator codes + a "+ Add code" button → modal
 *
 * Each code row shows usage, paid bookings, revenue attributed, and
 * commission credited (if `commission_percent` is set).
 */
export default function AdminCreatorCodesTab() {
  const [events, setEvents] = useState([]);
  const [eventQuery, setEventQuery] = useState("");
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [codes, setCodes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);

  // Load admin event list once.
  useEffect(() => {
    api.get("/admin/events?limit=200")
      .then((r) => setEvents(r.data?.items || r.data || []))
      .catch(() => setEvents([]));
  }, []);

  const refreshCodes = useCallback(async (evId) => {
    if (!evId) return;
    setLoading(true);
    try {
      const r = await api.get(`/admin/events/${evId}/creator-codes`);
      setCodes(r.data?.items || []);
    } catch {
      setCodes([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedEvent?.event_id) refreshCodes(selectedEvent.event_id);
  }, [selectedEvent, refreshCodes]);

  const deactivate = async (codeId) => {
    if (!window.confirm("Deactivate this creator code? (Existing earnings are kept)")) return;
    try {
      await api.delete(`/admin/events/${selectedEvent.event_id}/creator-codes/${codeId}`);
      toast.success("Code deactivated");
      refreshCodes(selectedEvent.event_id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't deactivate");
    }
  };

  const filteredEvents = events.filter((e) =>
    !eventQuery
      ? true
      : (e.title || "").toLowerCase().includes(eventQuery.toLowerCase()) ||
        (e.city || "").toLowerCase().includes(eventQuery.toLowerCase())
  );

  return (
    <div data-testid="admin-creator-codes-tab">
      <div className="flex items-center gap-2 text-xs uppercase tracking-widest mb-2" style={{ color: "var(--accent)" }}>
        <Tag size={13} /> Creator promo codes
      </div>
      <h2 className="font-serif text-2xl mb-1" style={{ color: "var(--text)" }}>
        Attach promo codes to creators
      </h2>
      <p className="text-sm mb-6" style={{ color: "var(--text)" }}>
        Pick an event, attach a promo code to a creator. Buyers get the discount; creators
        earn a commission (if set) on every paid booking that uses their code.
      </p>

      <div className="grid lg:grid-cols-12 gap-6">
        {/* Left: event picker */}
        <div className="lg:col-span-4 rounded-xl border" style={{ borderColor: "var(--border)" }}>
          <div className="p-3 border-b" style={{ borderColor: "var(--border)" }}>
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "var(--text-dim)" }} />
              <input
                type="text"
                value={eventQuery}
                onChange={(e) => setEventQuery(e.target.value)}
                placeholder="Search events…"
                className="w-full pl-8 pr-3 py-2 rounded-md border text-sm"
                style={{ borderColor: "var(--border)", background: "transparent", color: "var(--text)" }}
                data-testid="creator-codes-event-search"
              />
            </div>
          </div>
          <div className="max-h-[600px] overflow-y-auto">
            {filteredEvents.length === 0 && (
              <div className="text-sm p-4 text-center" style={{ color: "var(--text-dim)" }}>No events found</div>
            )}
            {filteredEvents.map((e) => {
              const active = selectedEvent?.event_id === e.event_id;
              return (
                <button
                  key={e.event_id}
                  type="button"
                  onClick={() => setSelectedEvent(e)}
                  className="w-full text-left px-4 py-3 border-b transition"
                  style={{
                    borderColor: "var(--border)",
                    background: active ? "rgba(240,138,42,0.06)" : "transparent",
                  }}
                  data-testid={`creator-codes-event-${e.event_id}`}
                >
                  <div className="text-sm font-medium truncate" style={{ color: "var(--text)" }}>{e.title}</div>
                  <div className="text-xs mt-0.5" style={{ color: "var(--text-dim)" }}>
                    {e.city || "—"} · {e.date ? new Date(e.date).toLocaleDateString() : "—"}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Right: codes for selected event */}
        <div className="lg:col-span-8 rounded-xl border p-4" style={{ borderColor: "var(--border)" }}>
          {!selectedEvent ? (
            <div className="text-sm p-12 text-center" style={{ color: "var(--text-dim)" }}>
              Pick an event on the left to manage its creator codes.
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="font-serif text-lg" style={{ color: "var(--text)" }}>{selectedEvent.title}</h3>
                  <div className="text-xs" style={{ color: "var(--text-dim)" }}>{selectedEvent.event_id}</div>
                </div>
                <button
                  onClick={() => setModalOpen(true)}
                  className="btn-primary text-sm inline-flex items-center gap-1.5"
                  data-testid="creator-codes-add-btn"
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
                      <tr><td colSpan={8} className="text-center py-6" style={{ color: "var(--text-dim)" }}>No creator codes yet</td></tr>
                    )}
                    {codes.map((c) => (
                      <tr key={c.code_id} className="border-t" style={{ borderColor: "var(--border)" }} data-testid={`creator-code-row-${c.code_id}`}>
                        <td className="px-2 py-3 font-mono text-xs" style={{ color: c.active ? "var(--text)" : "var(--text-dim)" }}>
                          {c.code}
                          {!c.active && <span className="ml-1.5 text-[10px] opacity-60">(inactive)</span>}
                        </td>
                        <td className="px-2 py-3" style={{ color: "var(--text)" }}>
                          <div className="text-xs font-medium">{c.creator_name || "—"}</div>
                          <div className="text-[10px]" style={{ color: "var(--text-dim)" }}>{c.creator_email}</div>
                        </td>
                        <td className="px-2 py-3 text-right" style={{ color: "var(--text)" }}>
                          {c.kind === "percent" ? `${c.value}%` : `$${c.value}`}
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
                          {c.active && (
                            <button onClick={() => deactivate(c.code_id)} className="text-xs inline-flex items-center gap-1" style={{ color: "#E74C3C" }} data-testid={`deactivate-code-${c.code_id}`}>
                              <Trash2 size={11} /> Deactivate
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>

      {modalOpen && selectedEvent && (
        <AddCreatorCodeModal
          event={selectedEvent}
          onClose={() => setModalOpen(false)}
          onCreated={() => { setModalOpen(false); refreshCodes(selectedEvent.event_id); }}
        />
      )}
    </div>
  );
}

function AddCreatorCodeModal({ event, onClose, onCreated }) {
  const [form, setForm] = useState({
    code: "", creator_email: "", kind: "percent", value: 15,
    commission_percent: "", max_uses: "", expires_at: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [creatorSearch, setCreatorSearch] = useState("");
  const [creatorSuggestions, setCreatorSuggestions] = useState([]);

  useEffect(() => {
    if (creatorSearch.trim().length < 2) { setCreatorSuggestions([]); return; }
    const t = setTimeout(async () => {
      try {
        const r = await api.get(`/admin/creator-codes/users-search?q=${encodeURIComponent(creatorSearch)}`);
        setCreatorSuggestions(r.data?.items || []);
      } catch {
        setCreatorSuggestions([]);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [creatorSearch]);

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (e) => {
    e.preventDefault();
    if (!form.code.trim()) { toast.error("Code is required"); return; }
    if (!form.creator_email.trim()) { toast.error("Pick a creator"); return; }
    if (!form.value || Number(form.value) <= 0) { toast.error("Discount value must be positive"); return; }
    setSubmitting(true);
    try {
      const payload = {
        code: form.code.trim().toUpperCase(),
        creator_email: form.creator_email,
        kind: form.kind,
        value: Number(form.value),
        commission_percent: form.commission_percent ? Number(form.commission_percent) : null,
        max_uses: form.max_uses ? Number(form.max_uses) : null,
        expires_at: form.expires_at ? new Date(form.expires_at).toISOString() : null,
      };
      await api.post(`/admin/events/${event.event_id}/creator-codes`, payload);
      toast.success("Creator code created");
      onCreated();
    } catch (ex) {
      toast.error(ex?.response?.data?.detail || "Couldn't create code");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.7)", backdropFilter: "blur(4px)" }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      data-testid="add-creator-code-modal"
    >
      <div className="rounded-2xl border w-full max-w-md p-5" style={{ background: "var(--bg, #0f0f12)", borderColor: "var(--border)" }}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-serif text-lg" style={{ color: "var(--text)" }}>New creator code</h3>
          <button onClick={onClose} className="p-1" style={{ color: "var(--text-dim)" }}><XIcon size={16} /></button>
        </div>

        <form onSubmit={submit} className="space-y-3">
          <Field label="Promo code">
            <input
              value={form.code}
              onChange={(e) => update("code", e.target.value.toUpperCase().replace(/[^A-Z0-9_-]/g, ""))}
              placeholder="CHLOE15"
              className="w-full px-3 py-2 rounded-md border text-sm font-mono"
              style={{ borderColor: "var(--border)", background: "transparent", color: "var(--text)" }}
              maxLength={24}
              data-testid="creator-code-input"
            />
          </Field>

          <Field label="Creator (only enrolled creators shown)">
            <input
              value={form.creator_email || creatorSearch}
              onChange={(e) => { setCreatorSearch(e.target.value); update("creator_email", e.target.value); }}
              placeholder="Search by name or email…"
              className="w-full px-3 py-2 rounded-md border text-sm"
              style={{ borderColor: "var(--border)", background: "transparent", color: "var(--text)" }}
              data-testid="creator-email-input"
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
                    data-testid={`creator-suggestion-${u.user_id}`}
                  >
                    <div className="text-xs font-medium">{u.display_name || u.name || u.email}</div>
                    <div className="text-[10px]" style={{ color: "var(--text-dim)" }}>
                      {u.email}
                      {u.follower_count > 0 && (
                        <span> · {u.follower_count.toLocaleString()} followers</span>
                      )}
                      {u.categories && u.categories.length > 0 && (
                        <span> · {u.categories.slice(0, 2).join(", ")}</span>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Discount kind">
              <select
                value={form.kind}
                onChange={(e) => update("kind", e.target.value)}
                className="w-full px-3 py-2 rounded-md border text-sm"
                style={{ borderColor: "var(--border)", background: "transparent", color: "var(--text)" }}
                data-testid="creator-code-kind"
              >
                <option value="percent">% off</option>
                <option value="flat">$ off</option>
              </select>
            </Field>
            <Field label={form.kind === "percent" ? "% off" : "$ off"}>
              <input
                type="number"
                step="0.01"
                value={form.value}
                onChange={(e) => update("value", e.target.value)}
                min={0.01}
                max={form.kind === "percent" ? 100 : undefined}
                className="w-full px-3 py-2 rounded-md border text-sm"
                style={{ borderColor: "var(--border)", background: "transparent", color: "var(--text)" }}
                data-testid="creator-code-value"
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
                data-testid="creator-code-commission"
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
                data-testid="creator-code-max-uses"
              />
            </Field>
            <Field label="Expires at (optional)">
              <input
                type="datetime-local"
                value={form.expires_at}
                onChange={(e) => update("expires_at", e.target.value)}
                className="w-full px-3 py-2 rounded-md border text-sm"
                style={{ borderColor: "var(--border)", background: "transparent", color: "var(--text)" }}
                data-testid="creator-code-expires"
              />
            </Field>
          </div>

          <div className="flex gap-2 pt-2">
            <button type="submit" disabled={submitting} className="btn-primary flex-1 text-sm justify-center" data-testid="creator-code-submit-btn">
              {submitting ? "Creating…" : "Create code"}
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
