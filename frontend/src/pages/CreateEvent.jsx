import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatApiErrorDetail } from "@/lib/api";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import ImageUploader from "@/components/ImageUploader";
import SeatDesigner from "@/components/SeatDesigner";
import DateTimePicker from "@/components/DateTimePicker";

const CATEGORIES = [
  { id: "music", name: "Music" },
  { id: "comedy", name: "Comedy" },
  { id: "sports", name: "Sports" },
  { id: "theater", name: "Theater" },
  { id: "tech", name: "Tech" },
  { id: "workshops", name: "Workshops" },
  { id: "festivals", name: "Festivals" },
  { id: "arts", name: "Arts" },
];

export default function CreateEvent() {
  const nav = useNavigate();
  const [form, setForm] = useState({
    title: "",
    description: "",
    category: "music",
    venue: "",
    city: "",
    date: "",
    image_url: "",
    banner_url: "",
    has_seatmap: false,
    seat_rows: 6,
    seat_cols: 10,
    seat_price: 50.0,
    aisles: [],
    seat_map_image_url: "",
  });
  const [tiers, setTiers] = useState([{ name: "General", price: 50.0, capacity: 200 }]);
  const [submitting, setSubmitting] = useState(false);

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!form.image_url) { toast.error("Please upload a cover photo"); return; }
    setSubmitting(true);
    try {
      const payload = {
        ...form,
        date: new Date(form.date).toISOString(),
        tiers: form.has_seatmap ? [] : tiers,
      };
      const { data } = await api.post("/events", payload);
      toast.success("Event submitted! Pending approval.");
      nav(`/events/${data.event_id}`);
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Failed");
    } finally { setSubmitting(false); }
  };

  return (
    <div className="max-w-3xl mx-auto px-6 py-12">
      <div className="mb-8">
        <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>New event</div>
        <h1 className="serif text-5xl">Set the stage</h1>
      </div>
      <form onSubmit={onSubmit} className="space-y-6" data-testid="create-event-form">
        <Field label="Cover photo">
          <ImageUploader
            value={form.image_url}
            onUploaded={(url) => { update("image_url", url); if (!form.banner_url) update("banner_url", url); }}
            label="Drop cover photo or click to upload"
            aspect="16/9"
            testid="cover-uploader"
          />
        </Field>
        <Field label="Title">
          <input required value={form.title} onChange={(e) => update("title", e.target.value)} data-testid="event-title-input" />
        </Field>
        <Field label="Description">
          <textarea required rows={4} value={form.description} onChange={(e) => update("description", e.target.value)} data-testid="event-desc-input" />
        </Field>
        <div className="grid md:grid-cols-2 gap-4">
          <Field label="Category">
            <select value={form.category} onChange={(e) => update("category", e.target.value)} data-testid="event-category-select">
              {CATEGORIES.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Date & time">
            <DateTimePicker value={form.date} onChange={(v) => update("date", v)} testid="event-datetime" />
          </Field>
          <Field label="Venue">
            <input required value={form.venue} onChange={(e) => update("venue", e.target.value)} />
          </Field>
          <Field label="City">
            <input required value={form.city} onChange={(e) => update("city", e.target.value)} />
          </Field>
        </div>

        <div className="border rounded-xl p-5 space-y-4" style={{ borderColor: "var(--border)" }}>
          <label className="flex items-center justify-between cursor-pointer">
            <div>
              <div className="font-medium">Interactive seat map</div>
              <div className="text-xs" style={{ color: "var(--text-dim)" }}>Use this for cinemas, theaters and assigned-seating venues.</div>
            </div>
            <input type="checkbox" className="!w-5 !h-5" checked={form.has_seatmap} onChange={(e) => update("has_seatmap", e.target.checked)} data-testid="seatmap-toggle" />
          </label>

          {form.has_seatmap && (
            <>
              <div className="grid grid-cols-3 gap-3">
                <Field label="Rows"><input type="number" min={2} max={26} value={form.seat_rows} onChange={(e) => update("seat_rows", parseInt(e.target.value) || 2)} /></Field>
                <Field label="Cols"><input type="number" min={4} max={26} value={form.seat_cols} onChange={(e) => update("seat_cols", parseInt(e.target.value) || 4)} /></Field>
                <Field label="Price / seat"><input type="number" step="0.01" value={form.seat_price} onChange={(e) => update("seat_price", parseFloat(e.target.value) || 0)} /></Field>
              </div>

              <Field label="Venue floor-plan (optional)">
                <ImageUploader
                  value={form.seat_map_image_url}
                  onUploaded={(url) => update("seat_map_image_url", url)}
                  label="Upload a backdrop showing your venue layout"
                  aspect="16/7"
                  testid="seatmap-uploader"
                />
              </Field>

              <Field label="Draw the seat arrangement">
                <SeatDesigner
                  rows={form.seat_rows}
                  cols={form.seat_cols}
                  aisles={form.aisles}
                  onChange={(a) => update("aisles", a)}
                  backdropUrl={form.seat_map_image_url}
                />
              </Field>
            </>
          )}
        </div>

        {!form.has_seatmap && (
          <div>
            <div className="flex items-center justify-between mb-3">
              <label className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>Ticket tiers</label>
              <button type="button" onClick={() => setTiers((t) => [...t, { name: "VIP", price: 100, capacity: 50 }])} className="text-xs flex items-center gap-1" style={{ color: "var(--accent)" }} data-testid="add-tier-btn">
                <Plus className="w-3 h-3" /> Add tier
              </button>
            </div>
            <div className="space-y-3">
              {tiers.map((t, i) => (
                <div key={i} className="grid grid-cols-[1fr_120px_120px_auto] gap-2">
                  <input placeholder="Name" value={t.name} onChange={(e) => { const n = [...tiers]; n[i].name = e.target.value; setTiers(n); }} />
                  <input type="number" step="0.01" placeholder="Price" value={t.price} onChange={(e) => { const n = [...tiers]; n[i].price = parseFloat(e.target.value); setTiers(n); }} />
                  <input type="number" placeholder="Capacity" value={t.capacity} onChange={(e) => { const n = [...tiers]; n[i].capacity = parseInt(e.target.value); setTiers(n); }} />
                  <button type="button" onClick={() => setTiers((arr) => arr.filter((_, x) => x !== i))} className="px-3 rounded-lg border" style={{ borderColor: "var(--border-strong)" }}><Trash2 className="w-4 h-4" /></button>
                </div>
              ))}
            </div>
          </div>
        )}

        <button type="submit" disabled={submitting} className="btn-primary" data-testid="submit-event-btn">
          {submitting ? "Submitting..." : "Submit for approval"}
        </button>
      </form>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>{label}</label>
      {children}
    </div>
  );
}
