import { useEffect, useState } from "react";
import { Plus, Package, Trash2 } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatMoney } from "@/lib/currencies";

/**
 * BundleManager — organizer page to create + list season-pass bundles.
 * Picks 2+ of their own events, sets a price and (optional) capacity.
 */
export default function BundleManager() {
  const { user } = useAuth();
  const [events, setEvents] = useState([]);
  const [bundles, setBundles] = useState([]);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    title: "",
    description: "",
    price: 100,
    capacity: "",
    event_ids: [],
  });

  const load = async () => {
    try {
      const [evRes, bnRes] = await Promise.all([
        api.get("/organizer/events"),
        api.get("/organizer/bundles"),
      ]);
      setEvents(evRes.data || []);
      setBundles(bnRes.data || []);
    } catch { /* silent */ }
  };

  useEffect(() => { load(); }, []);

  const toggleEvent = (id) => {
    setForm((f) => ({
      ...f,
      event_ids: f.event_ids.includes(id)
        ? f.event_ids.filter((e) => e !== id)
        : [...f.event_ids, id],
    }));
  };

  const onCreate = async (e) => {
    e.preventDefault();
    if (form.event_ids.length < 2) { toast.error("Pick at least 2 events"); return; }
    if (!form.title.trim()) { toast.error("Title required"); return; }
    setCreating(true);
    try {
      await api.post("/organizer/bundles", {
        title: form.title.trim(),
        description: form.description.trim(),
        event_ids: form.event_ids,
        price: Number(form.price),
        capacity: form.capacity ? Number(form.capacity) : null,
      });
      toast.success("Bundle created");
      setForm({ title: "", description: "", price: 100, capacity: "", event_ids: [] });
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not create");
    } finally {
      setCreating(false);
    }
  };

  const toggleStatus = async (b) => {
    try {
      const next = b.status === "active" ? "inactive" : "active";
      await api.patch(`/organizer/bundles/${b.bundle_id}`, { status: next });
      toast.success(`Bundle ${next}`);
      load();
    } catch {
      toast.error("Could not update");
    }
  };

  if (!user || (user.role !== "organizer" && user.role !== "admin")) {
    return <div className="text-center py-20" style={{ color: "var(--text-muted)" }}>Organizer access required.</div>;
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-10">
      <div className="flex items-center gap-2 mb-2">
        <Package size={20} style={{ color: "var(--accent)" }} />
        <h1 className="serif text-3xl">Season passes & bundles</h1>
      </div>
      <p className="text-sm mb-8" style={{ color: "var(--text-muted)" }}>
        Pick 2+ of your events, set a price, and let fans buy them all at once.
      </p>

      <form onSubmit={onCreate} className="rounded-2xl border p-5 mb-10" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }} data-testid="bundle-create-form">
        <div className="grid sm:grid-cols-2 gap-3 mb-4">
          <input
            placeholder="Bundle title (e.g. Summer Festival Pass)"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            data-testid="bundle-title-input"
          />
          <input
            type="number"
            step="0.01"
            min="1"
            placeholder="Price (NZD)"
            value={form.price}
            onChange={(e) => setForm({ ...form, price: e.target.value })}
            data-testid="bundle-price-input"
          />
        </div>
        <input
          placeholder="Short description"
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
          className="mb-4 w-full"
          data-testid="bundle-description-input"
        />
        <input
          type="number"
          min="1"
          placeholder="Capacity (optional — leave blank for unlimited)"
          value={form.capacity}
          onChange={(e) => setForm({ ...form, capacity: e.target.value })}
          className="mb-4 w-full"
          data-testid="bundle-capacity-input"
        />

        <div className="mb-4">
          <div className="text-xs uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>
            Include events ({form.event_ids.length} selected — min 2)
          </div>
          <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
            {events.length === 0 && (
              <div className="text-sm" style={{ color: "var(--text-muted)" }}>You don&apos;t have any events yet.</div>
            )}
            {events.map((e) => (
              <label
                key={e.event_id}
                className="flex items-center gap-3 p-2 rounded-lg border cursor-pointer"
                style={{ borderColor: form.event_ids.includes(e.event_id) ? "var(--accent)" : "var(--border)" }}
                data-testid={`bundle-pick-${e.event_id}`}
              >
                <input
                  type="checkbox"
                  checked={form.event_ids.includes(e.event_id)}
                  onChange={() => toggleEvent(e.event_id)}
                />
                <img src={e.image_url} alt="" className="w-10 h-10 rounded object-cover" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm truncate">{e.title}</div>
                  <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {e.venue}, {e.city} · {e.currency}
                  </div>
                </div>
              </label>
            ))}
          </div>
        </div>

        <button
          type="submit"
          disabled={creating || form.event_ids.length < 2}
          className="btn-primary"
          data-testid="create-bundle-btn"
        >
          <Plus size={14} /> {creating ? "Creating..." : "Create bundle"}
        </button>
      </form>

      <h2 className="serif text-2xl mb-3">Your bundles</h2>
      {bundles.length === 0 ? (
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>No bundles yet.</div>
      ) : (
        <div className="space-y-3">
          {bundles.map((b) => (
            <div
              key={b.bundle_id}
              className="flex flex-col sm:flex-row gap-3 sm:items-center justify-between p-4 rounded-xl border"
              style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
              data-testid={`bundle-row-${b.bundle_id}`}
            >
              <div className="flex-1 min-w-0">
                <div className="font-medium">{b.title}</div>
                <div className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                  {b.event_ids?.length} events · {b.sold_count || 0} sold
                  {b.capacity ? ` of ${b.capacity}` : ""}
                  {" · "}
                  <a href={`/bundles/${b.bundle_id}`} className="underline" target="_blank" rel="noreferrer" data-testid={`view-bundle-${b.bundle_id}`}>
                    Public link
                  </a>
                </div>
              </div>
              <div className="text-right">
                <div className="serif text-2xl" style={{ color: "var(--accent)" }}>
                  {formatMoney(b.price, b.currency)}
                </div>
              </div>
              <button
                onClick={() => toggleStatus(b)}
                className="btn-ghost text-xs"
                data-testid={`toggle-status-${b.bundle_id}`}
              >
                {b.status === "active" ? "Pause" : "Activate"}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
