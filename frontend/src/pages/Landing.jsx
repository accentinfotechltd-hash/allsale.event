import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import EventCard from "@/components/EventCard";
import { useAuth } from "@/lib/auth";
import { ArrowRight, Search, Calendar, Zap, Award, Sparkles } from "lucide-react";

export default function Landing() {
  const { user } = useAuth();
  const [featured, setFeatured] = useState([]);
  const [cats, setCats] = useState([]);
  const [recs, setRecs] = useState([]);
  const [recsLoading, setRecsLoading] = useState(false);
  const [q, setQ] = useState("");
  const nav = useNavigate();

  useEffect(() => {
    (async () => {
      try {
        const [f, c] = await Promise.all([
          api.get("/events/featured"),
          api.get("/events/categories"),
        ]);
        setFeatured(f.data);
        setCats(c.data);
      } catch (e) { console.error(e); }
    })();
  }, []);

  useEffect(() => {
    if (!user) return;
    setRecsLoading(true);
    api.get("/me/recommendations")
      .then(({ data }) => setRecs(data.items || []))
      .catch(() => setRecs([]))
      .finally(() => setRecsLoading(false));
  }, [user?.user_id]);

  const hero = featured[0];

  return (
    <div>
      {/* HERO */}
      <section className="relative overflow-hidden">
        <div className="max-w-7xl mx-auto px-6 pt-16 pb-12 grid lg:grid-cols-12 gap-10 items-end">
          <div className="lg:col-span-7 fade-up">
            <div className="chip mb-6">
              <span style={{ background: "var(--accent)", width: 6, height: 6, borderRadius: 99 }} />
              <span>Live · 124 events on sale</span>
            </div>
            <h1 className="serif text-5xl sm:text-6xl lg:text-7xl leading-[0.95] mb-6">
              The night is <em style={{ color: "var(--accent)" }}>yours</em>.
              <br /> Tickets are <em>limited</em>.
            </h1>
            <p className="text-lg max-w-xl mb-8" style={{ color: "var(--text-muted)" }}>
              Discover concerts, comedy, sports, theater and festivals — and lock your seat with a 10-minute hold while you check out. No surprises, no scalpers.
            </p>
            <form
              onSubmit={(e) => { e.preventDefault(); nav(`/events?q=${encodeURIComponent(q)}`); }}
              className="flex gap-2 max-w-xl"
              data-testid="hero-search-form"
            >
              <div className="relative flex-1">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: "var(--text-dim)" }} />
                <input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Search artists, events, or venues"
                  className="pl-11 !py-4"
                  data-testid="hero-search-input"
                />
              </div>
              <button type="submit" className="btn-primary" data-testid="hero-search-submit">
                Search <ArrowRight className="w-4 h-4" />
              </button>
            </form>

            <div className="flex items-center gap-8 mt-10 text-sm" style={{ color: "var(--text-muted)" }}>
              <div className="flex items-center gap-2"><Zap className="w-4 h-4" style={{ color: "var(--accent)" }} /> Instant e-tickets</div>
              <div className="flex items-center gap-2"><Award className="w-4 h-4" style={{ color: "var(--accent)" }} /> Verified organizers</div>
              <div className="flex items-center gap-2"><Calendar className="w-4 h-4" style={{ color: "var(--accent)" }} /> 10-min seat hold</div>
            </div>
          </div>

          {hero && (
            <div className="lg:col-span-5 fade-up fade-up-2">
              <Link to={`/events/${hero.event_id}`} className="block relative aspect-[3/4] rounded-2xl overflow-hidden border" style={{ borderColor: "var(--border)" }}>
                <img src={hero.banner_url || hero.image_url} alt={hero.title} className="w-full h-full object-cover" />
                <div className="absolute inset-0 bg-gradient-to-t from-black via-black/40 to-transparent" />
                <div className="absolute inset-x-0 bottom-0 p-6">
                  <span className="chip chip-accent mb-3">Featured</span>
                  <h3 className="serif text-3xl leading-tight mb-2">{hero.title}</h3>
                  <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                    {hero.venue} · {hero.city}
                  </p>
                </div>
              </Link>
            </div>
          )}
        </div>

        {/* Ticker */}
        <div className="border-y overflow-hidden whitespace-nowrap py-4" style={{ borderColor: "var(--border)" }}>
          <div className="marquee-track inline-flex gap-12 text-sm uppercase tracking-[0.25em]" style={{ color: "var(--text-dim)" }}>
            {Array(2).fill(0).map((_, k) => (
              <div key={k} className="inline-flex gap-12">
                <span>Auckland</span><span>·</span><span>Wellington</span><span>·</span><span>Christchurch</span><span>·</span>
                <span>Queenstown</span><span>·</span><span>Hamilton</span><span>·</span><span>Tauranga</span><span>·</span>
                <span>Dunedin</span><span>·</span><span>Napier</span><span>·</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CATEGORIES */}
      <section className="max-w-7xl mx-auto px-6 py-16">
        <div className="flex items-end justify-between mb-8">
          <div>
            <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Browse by mood</div>
            <h2 className="serif text-4xl">Pick your scene</h2>
          </div>
          <Link to="/events" className="hidden md:inline-flex items-center gap-2 text-sm hover:text-white" style={{ color: "var(--text-muted)" }}>
            All events <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {cats.map((c, i) => (
            <Link
              to={`/events?category=${c.id}`}
              key={c.id}
              className="relative aspect-[4/3] rounded-xl overflow-hidden group border fade-up"
              style={{ borderColor: "var(--border)", animationDelay: `${i * 0.04}s` }}
              data-testid={`category-${c.id}`}
            >
              <img src={c.image} alt={c.name} className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110" />
              <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/30 to-transparent" />
              <div className="absolute inset-x-0 bottom-0 p-4">
                <div className="serif text-2xl group-hover:text-[color:var(--accent)] transition-colors">{c.name}</div>
              </div>
            </Link>
          ))}
        </div>
      </section>

      {/* AI RECOMMENDATIONS (logged in only) */}
      {user && (recs.length > 0 || recsLoading) && (
        <section className="max-w-7xl mx-auto px-6 pb-16" data-testid="ai-recs-section">
          <div className="flex items-end justify-between mb-8">
            <div>
              <div className="text-xs uppercase tracking-[0.3em] mb-2 inline-flex items-center gap-2" style={{ color: "var(--accent)" }}>
                <Sparkles className="w-3 h-3" /> Picked for you
              </div>
              <h2 className="serif text-4xl">Recommendations</h2>
              <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
                Personalized by your booking history.
              </p>
            </div>
          </div>
          {recsLoading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="rounded-2xl aspect-[4/5] animate-pulse" style={{ background: "var(--bg-card)" }} />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
              {recs.map((r, i) => (
                <div key={r.event.event_id} className="relative" data-testid={`rec-${r.event.event_id}`}>
                  <EventCard event={r.event} index={i} />
                  <div className="mt-2 px-1 text-xs italic leading-snug" style={{ color: "var(--text-muted)" }}>
                    "{r.reason}"
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* FEATURED EVENTS */}
      <section className="max-w-7xl mx-auto px-6 pb-16">
        <div className="flex items-end justify-between mb-8">
          <div>
            <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Curated this week</div>
            <h2 className="serif text-4xl">Hand-picked headliners</h2>
          </div>
          <Link to="/events" className="hidden md:inline-flex items-center gap-2 text-sm hover:text-white" style={{ color: "var(--text-muted)" }}>
            See all <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {featured.slice(0, 8).map((e, i) => <EventCard key={e.event_id} event={e} index={i} />)}
        </div>
      </section>

      {/* CTA */}
      <section className="max-w-7xl mx-auto px-6 pb-16">
        <div className="rounded-3xl border p-10 lg:p-16 relative overflow-hidden" style={{ borderColor: "var(--border)", background: "linear-gradient(135deg, rgba(255,79,0,0.08), transparent 60%)" }}>
          <div className="grid md:grid-cols-2 gap-8 items-center">
            <div>
              <div className="text-xs uppercase tracking-[0.3em] mb-3" style={{ color: "var(--accent)" }}>For organizers</div>
              <h3 className="serif text-4xl lg:text-5xl leading-tight mb-4">Sell out your next show in <em style={{ color: "var(--accent)" }}>minutes</em>.</h3>
              <p className="mb-6 max-w-md" style={{ color: "var(--text-muted)" }}>
                Set up your event, pick a seating layout, and start selling. Real-time analytics, on-the-door check-in, and zero scalper anxiety.
              </p>
              <Link to="/signup" className="btn-primary" data-testid="cta-signup-organizer">
                Become an organizer <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
            <div className="grid grid-cols-2 gap-4">
              {["Live sales tracking", "Tiered pricing", "Seat maps", "QR check-in"].map((s, i) => (
                <div key={s} className="glass rounded-xl p-5 fade-up" style={{ animationDelay: `${i * 0.05}s` }}>
                  <div className="serif text-2xl mb-1">0{i + 1}</div>
                  <div className="text-sm" style={{ color: "var(--text-muted)" }}>{s}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
