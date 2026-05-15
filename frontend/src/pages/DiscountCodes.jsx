import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";
import { Plus, Trash2, Tag, Copy, ArrowLeft } from "lucide-react";

export default function DiscountCodes() {
  const { user } = useAuth();
  const [codes, setCodes] = useState([]);
  const [events, setEvents] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ code: "", kind: "percent", value: 10, event_id: "", max_uses: "", expires_at: "" });
  const [submitting, setSubmitting] = useState(false);

  const load = async () => {
    try {
      const [c, e] = await Promise.all([api.get("/organizer/discount-codes"), api.get("/organizer/events")]);
      setCodes(c.data);
      setEvents(e.data);
    } catch { /* noop */ }
  };
  useEffect(() => { load(); }, []);

  const create = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const payload = {
        code: form.code,
        kind: form.kind,
        value: parseFloat(form.value),
        event_id: form.event_id || null,
        max_uses: form.max_uses ? parseInt(form.max_uses) : null,
        expires_at: form.expires_at ? new Date(form.expires_at).toISOString() : null,
      };
      await api.post("/organizer/discount-codes", payload);
      toast.success(`Code ${form.code.toUpperCase()} created`);
      setShowForm(false);
      setForm({ code: "", kind: "percent", value: 10, event_id: "", max_uses: "", expires_at: "" });
      load();
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Create failed");
    } finally { setSubmitting(false); }
  };

  const remove = async (code_id, code) => {
    if (!window.confirm(`Deactivate ${code}? Existing bookings keep their discount; the code stops working for new ones.`)) return;
    try {
      await api.delete(`/organizer/discount-codes/${code_id}`);
      toast.success("Deactivated");
      load();
    } catch { toast.error("Failed"); }
  };

  const copy = (c) => {
    navigator.clipboard.writeText(c);
    toast("Copied " + c);
  };

  if (!user || (user.role !== "organizer" && user.role !== "admin")) {
    return <div className="text-center py-20" style={{ color: "var(--text-muted)" }}>Organizer access required.</div>;
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-12">
      <Link to="/organizer" className="inline-flex items-center gap-2 text-sm mb-6" style={{ color: "var(--text-muted)" }}>
        <ArrowLeft className="w-4 h-4" /> Back to dashboard
      </Link>

      <div className="flex items-end justify-between mb-10 flex-wrap gap-4">
        <div>
          <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Promotions</div>
          <h1 className="serif text-5xl">Discount codes</h1>
          <p className="mt-2 max-w-xl" style={{ color: "var(--text-muted)" }}>Create promo codes for marketing campaigns. Every booking using a code is tracked on the per-event analytics page.</p>
        </div>
        <button onClick={() => setShowForm((s) => !s)} className="btn-primary" data-testid="new-code-btn">
          <Plus className="w-4 h-4" /> New code
        </button>
      </div>

      {showForm && (
        <form onSubmit={create} className="border rounded-2xl p-6 mb-8 space-y-4" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }} data-testid="new-code-form">
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>Code</label>
              <input required value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} placeholder="EARLY20" data-testid="code-input" />
            </div>
            <div>
              <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>Discount type</label>
              <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })} data-testid="kind-select">
                <option value="percent">Percentage off (%)</option>
                <option value="flat">Flat $ off</option>
              </select>
            </div>
            <div>
              <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>{form.kind === "percent" ? "Percent off" : "Dollars off"}</label>
              <input required type="number" step="0.01" min="0.01" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} data-testid="value-input" />
            </div>
            <div>
              <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>Max uses (optional)</label>
              <input type="number" min="1" value={form.max_uses} onChange={(e) => setForm({ ...form, max_uses: e.target.value })} placeholder="Unlimited" data-testid="max-uses-input" />
            </div>
            <div className="md:col-span-2">
              <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>Apply to</label>
              <select value={form.event_id} onChange={(e) => setForm({ ...form, event_id: e.target.value })} data-testid="event-scope-select">
                <option value="">All my events</option>
                {events.map((e) => <option key={e.event_id} value={e.event_id}>{e.title}</option>)}
              </select>
            </div>
            <div className="md:col-span-2">
              <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>Expires at (optional)</label>
              <input type="datetime-local" value={form.expires_at} onChange={(e) => setForm({ ...form, expires_at: e.target.value })} data-testid="expires-input" />
            </div>
          </div>
          <div className="flex gap-2">
            <button type="submit" disabled={submitting} className="btn-primary" data-testid="create-code-submit">{submitting ? "Creating..." : "Create code"}</button>
            <button type="button" onClick={() => setShowForm(false)} className="btn-ghost">Cancel</button>
          </div>
        </form>
      )}

      {codes.length === 0 ? (
        <p className="p-10 border rounded-xl text-center" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
          No codes yet. Create your first one to start tracking promo attribution.
        </p>
      ) : (
        <div className="space-y-3">
          {codes.map((c) => {
            const scopeLabel = c.event_id ? (events.find((e) => e.event_id === c.event_id)?.title || "Single event") : "All events";
            const discountLabel = c.kind === "percent" ? `${c.value}% off` : `$${c.value} off`;
            const usesLabel = c.max_uses != null ? `${c.uses_count} / ${c.max_uses}` : `${c.uses_count} uses`;
            return (
              <div key={c.code_id} className="border rounded-2xl p-5 grid md:grid-cols-[auto_1fr_auto_auto] gap-4 items-center" style={{ borderColor: "var(--border)", background: "var(--bg-card)", opacity: c.active ? 1 : 0.55 }} data-testid={`code-${c.code}`}>
                <div className="flex items-center gap-2">
                  <Tag className="w-4 h-4" style={{ color: "var(--accent)" }} />
                  <button onClick={() => copy(c.code)} className="font-mono text-lg hover:text-[color:var(--accent)] flex items-center gap-1.5">
                    {c.code} <Copy className="w-3 h-3 opacity-50" />
                  </button>
                  {!c.active && <span className="chip" style={{ fontSize: "0.65rem" }}>Inactive</span>}
                </div>
                <div className="text-sm" style={{ color: "var(--text-muted)" }}>
                  <span style={{ color: "var(--accent)" }}>{discountLabel}</span> · {scopeLabel} · {usesLabel}
                  {c.attributed_revenue > 0 && (
                    <span> · <strong style={{ color: "var(--text)" }}>${c.attributed_revenue.toLocaleString()}</strong> attributed revenue ({c.attributed_tickets} tickets, ${c.total_discount_given} given)</span>
                  )}
                </div>
                <button onClick={() => copy(c.code)} className="btn-ghost !py-1.5 !px-3 text-xs" data-testid={`copy-${c.code}`}>
                  <Copy className="w-3 h-3" /> Copy
                </button>
                {c.active && (
                  <button onClick={() => remove(c.code_id, c.code)} className="btn-ghost !py-1.5 !px-3 text-xs" data-testid={`deactivate-${c.code}`}>
                    <Trash2 className="w-3 h-3" /> Deactivate
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
