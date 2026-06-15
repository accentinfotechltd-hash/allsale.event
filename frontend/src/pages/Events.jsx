import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import EventCard from "@/components/EventCard";
import { COUNTRY_BY_CODE, flagForCountry, nameForCountry } from "@/lib/countries";
import { SlidersHorizontal, Calendar, Archive } from "lucide-react";

export default function Events() {
  const [params, setParams] = useSearchParams();
  const [events, setEvents] = useState([]);
  const [cats, setCats] = useState([]);
  const [countries, setCountries] = useState([]);
  const [loading, setLoading] = useState(true);

  const q = params.get("q") || "";
  const category = params.get("category") || "";
  const city = params.get("city") || "";
  const country = params.get("country") || "";
  const past = params.get("past") === "1";

  useEffect(() => {
    (async () => {
      try {
        const [c, cnt] = await Promise.all([
          api.get("/events/categories"),
          api.get("/events/countries").catch(() => ({ data: [] })),
        ]);
        setCats(Array.isArray(c.data) ? c.data : []);
        setCountries(Array.isArray(cnt.data) ? cnt.data : []);
      } catch (e) { /* ignore */ }
    })();
  }, []);

  useEffect(() => {
    setLoading(true);
    (async () => {
      try {
        const { data } = await api.get("/events", { params: { q, category, city, country, past: past ? "true" : "false" } });
        setEvents(Array.isArray(data) ? data : []);
      } finally { setLoading(false); }
    })();
  }, [q, category, city, country, past]);

  const updateParam = (k, v) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v); else next.delete(k);
    setParams(next);
  };

  const setPastTab = (isPast) => {
    const next = new URLSearchParams(params);
    if (isPast) next.set("past", "1"); else next.delete("past");
    setParams(next);
  };

  return (
    <div className="max-w-7xl mx-auto px-6 py-12">
      <div className="mb-8 flex items-end justify-between flex-wrap gap-4">
        <div>
          <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Discover</div>
          <h1 className="serif text-5xl">{past ? "Past events" : "All events"}</h1>
        </div>
        <div className="flex items-center gap-2 text-sm" style={{ color: "var(--text-muted)" }}>
          <SlidersHorizontal className="w-4 h-4" /> {events.length} results
        </div>
      </div>

      {/* Upcoming / Past tabs */}
      <div className="mb-8 inline-flex rounded-full border p-1" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
        <button
          type="button"
          onClick={() => setPastTab(false)}
          className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-sm transition"
          style={{
            background: !past ? "var(--accent)" : "transparent",
            color: !past ? "var(--bg)" : "var(--text-muted)",
          }}
          data-testid="events-tab-upcoming"
        >
          <Calendar className="w-4 h-4" /> Upcoming
        </button>
        <button
          type="button"
          onClick={() => setPastTab(true)}
          className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-sm transition"
          style={{
            background: past ? "var(--accent)" : "transparent",
            color: past ? "var(--bg)" : "var(--text-muted)",
          }}
          data-testid="events-tab-past"
        >
          <Archive className="w-4 h-4" /> Past
        </button>
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
              {(Array.isArray(cats) ? cats : []).map((c) => (
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
            <div className="text-xs uppercase tracking-widest mb-3" style={{ color: "var(--text-dim)" }}>Country</div>
            <div className="space-y-1" data-testid="events-country-filter">
              <button
                onClick={() => updateParam("country", "")}
                className="block w-full text-left px-3 py-2 rounded-lg text-sm transition"
                style={{
                  background: !country ? "var(--accent-soft)" : "transparent",
                  color: !country ? "var(--accent)" : "var(--text-muted)",
                }}
                data-testid="country-filter-all"
              >
                🌐 All countries
              </button>
              {countries.map((row) => {
                const c = COUNTRY_BY_CODE[row.country];
                if (!c) return null;
                return (
                  <button
                    key={row.country}
                    onClick={() => updateParam("country", row.country)}
                    className="block w-full text-left px-3 py-2 rounded-lg text-sm transition"
                    style={{
                      background: country === row.country ? "var(--accent-soft)" : "transparent",
                      color: country === row.country ? "var(--accent)" : "var(--text-muted)",
                    }}
                    data-testid={`country-filter-${row.country}`}
                  >
                    {c.flag} {c.name} <span className="opacity-60">({row.count})</span>
                  </button>
                );
              })}
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
            <div className="text-center py-20" style={{ color: "var(--text-dim)" }} data-testid="events-empty">
              {past ? "No past events yet." : "No events match these filters."}
            </div>
          ) : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5" data-testid="events-grid">
              {(Array.isArray(events) ? events : []).map((e, i) => <EventCard key={e.event_id} event={e} index={i} />)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
