import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import EventCard from "@/components/EventCard";
import { SlidersHorizontal } from "lucide-react";

export default function Events() {
  const [params, setParams] = useSearchParams();
  const [events, setEvents] = useState([]);
  const [cats, setCats] = useState([]);
  const [loading, setLoading] = useState(true);

  const q = params.get("q") || "";
  const category = params.get("category") || "";
  const city = params.get("city") || "";

  useEffect(() => {
    (async () => {
      try {
        const c = await api.get("/events/categories");
        setCats(c.data);
      } catch (e) { /* ignore */ }
    })();
  }, []);

  useEffect(() => {
    setLoading(true);
    (async () => {
      try {
        const { data } = await api.get("/events", { params: { q, category, city } });
        setEvents(data);
      } finally { setLoading(false); }
    })();
  }, [q, category, city]);

  const updateParam = (k, v) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v); else next.delete(k);
    setParams(next);
  };

  return (
    <div className="max-w-7xl mx-auto px-6 py-12">
      <div className="mb-10 flex items-end justify-between flex-wrap gap-4">
        <div>
          <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Discover</div>
          <h1 className="serif text-5xl">All events</h1>
        </div>
        <div className="flex items-center gap-2 text-sm" style={{ color: "var(--text-muted)" }}>
          <SlidersHorizontal className="w-4 h-4" /> {events.length} results
        </div>
      </div>

      <div className="grid lg:grid-cols-[260px_1fr] gap-10">
        <aside className="space-y-6 lg:sticky lg:top-24 lg:self-start">
          <div>
            <div className="text-xs uppercase tracking-widest mb-3" style={{ color: "var(--text-dim)" }}>Search</div>
            <input
              defaultValue={q}
              placeholder="Title, venue..."
              onBlur={(e) => updateParam("q", e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") updateParam("q", e.target.value); }}
              data-testid="events-search-input"
            />
          </div>
          <div>
            <div className="text-xs uppercase tracking-widest mb-3" style={{ color: "var(--text-dim)" }}>Category</div>
            <div className="space-y-1">
              <button
                onClick={() => updateParam("category", "")}
                className={`block w-full text-left px-3 py-2 rounded-lg text-sm transition ${!category ? "" : "hover:bg-[color:var(--bg-elev)]"}`}
                style={{
                  background: !category ? "var(--accent-soft)" : "transparent",
                  color: !category ? "var(--accent)" : "var(--text-muted)",
                }}
                data-testid="cat-filter-all"
              >
                All categories
              </button>
              {cats.map((c) => (
                <button
                  key={c.id}
                  onClick={() => updateParam("category", c.id)}
                  className="block w-full text-left px-3 py-2 rounded-lg text-sm transition"
                  style={{
                    background: category === c.id ? "var(--accent-soft)" : "transparent",
                    color: category === c.id ? "var(--accent)" : "var(--text-muted)",
                  }}
                  data-testid={`cat-filter-${c.id}`}
                >
                  {c.name}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-widest mb-3" style={{ color: "var(--text-dim)" }}>City</div>
            <input
              defaultValue={city}
              placeholder="Auckland, Wellington..."
              onBlur={(e) => updateParam("city", e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") updateParam("city", e.target.value); }}
              data-testid="events-city-input"
            />
          </div>
        </aside>

        <div>
          {loading ? (
            <div className="text-center py-20" style={{ color: "var(--text-dim)" }}>Loading...</div>
          ) : events.length === 0 ? (
            <div className="text-center py-20" style={{ color: "var(--text-dim)" }}>No events match these filters.</div>
          ) : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5" data-testid="events-grid">
              {events.map((e, i) => <EventCard key={e.event_id} event={e} index={i} />)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
