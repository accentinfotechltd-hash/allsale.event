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
  const [liveCount, setLiveCount] = useState(null);
  const [editorPick, setEditorPick] = useState({ event: null, blurb: "", badge_text: "Editor's Pick" });
  const [q, setQ] = useState("");
  const nav = useNavigate();

  useEffect(() => {
    (async () => {
      try {
        const [f, c, s, ep] = await Promise.all([
          api.get("/events/featured"),
          api.get("/events/categories"),
          api.get("/events/stats/public").catch(() => ({ data: { live_events: 0 } })),
          api.get("/site-settings/editor-pick").catch(() => ({ data: { event: null, blurb: "", badge_text: "Editor's Pick" } })),
        ]);
        setFeatured(Array.isArray(f.data) ? f.data : []);
        setCats(Array.isArray(c.data) ? c.data : []);
        setLiveCount(typeof s?.data?.live_events === "number" ? s.data.live_events : 0);
        setEditorPick(ep.data || { event: null, blurb: "", badge_text: "Editor's Pick" });
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

  // Editor's Pick overrides the default "first featured" hero. Falls back when
  // no pick is set or when the picked event was deleted/un-approved.
  const hero = editorPick.event || (Array.isArray(featured) && featured.length > 0 ? featured[0] : null);
  const heroIsEditorPick = !!editorPick.event;
  const heroBlurb = heroIsEditorPick ? editorPick.blurb : "";
  const heroBadge = heroIsEditorPick ? (editorPick.badge_text || "Editor's Pick") : "Featured";

  return (
    <div>
      {/* HERO */}
      <section className="relative overflow-hidden">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 pt-10 sm:pt-16 pb-12 grid lg:grid-cols-12 gap-10 items-end">
          <div className="lg:col-span-7 fade-up">
            <div className="chip mb-6" data-testid="live-event-count">
              <span style={{ background: "var(--accent)", width: 6, height: 6, borderRadius: 99 }} />
              <span>
                {liveCount === null
                  ? "Live · loading…"
                  : liveCount === 0
                    ? "Be the first to host"
                    : `Live · ${liveCount} event${liveCount === 1 ? "" : "s"} on sale`}
              </span>
            </div>
            <h1 className="serif text-5xl sm:text-6xl lg:text-7xl leading-[0.95] mb-6">
              The night is <em style={{ color: "var(--accent)" }}>yours</em>.
              <br /> Tickets are <em>limited</em>.
            </h1>
            <p className="text-base sm:text-lg max-w-xl mb-8" style={{ color: "var(--text-muted)" }}>
              Aotearoa&apos;s ticketing platform where <strong style={{ color: "var(--text)" }}>organizers keep 100%</strong> of the ticket price. Concerts, comedy, sports, theatre, festivals — locked seats, no scalpers, refundable on the organizer&apos;s terms.
            </p>
            <form
              onSubmit={(e) => { e.preventDefault(); nav(`/events?q=${encodeURIComponent(q)}`); }}
              className="flex flex-col sm:flex-row gap-2 max-w-xl"
              data-testid="hero-search-form"
            >
              <div className="relative flex-1 min-w-0">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: "var(--text-dim)" }} />
                <input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Search artists, events, or venues"
                  className="pl-11 !py-4 w-full"
                  data-testid="hero-search-input"
                />
              </div>
              <button type="submit" className="btn-primary justify-center" data-testid="hero-search-submit">
                Search <ArrowRight className="w-4 h-4" />
              </button>
            </form>

            <div className="flex flex-wrap items-center gap-x-6 gap-y-3 mt-10 text-sm" style={{ color: "var(--text-muted)" }}>
              <div className="flex items-center gap-2 whitespace-nowrap"><Zap className="w-4 h-4 flex-shrink-0" style={{ color: "var(--accent)" }} /> Instant e-tickets</div>
              <div className="flex items-center gap-2 whitespace-nowrap"><Award className="w-4 h-4 flex-shrink-0" style={{ color: "var(--accent)" }} /> Paid out in 5 days</div>
              <div className="flex items-center gap-2 whitespace-nowrap"><Calendar className="w-4 h-4 flex-shrink-0" style={{ color: "var(--accent)" }} /> 10-min seat hold</div>
            </div>
          </div>

          {hero && (
            <div className="lg:col-span-5 fade-up fade-up-2">
              <Link
                to={`/events/${hero.event_id}`}
                className="block relative aspect-[3/4] rounded-2xl overflow-hidden border"
                style={{ borderColor: heroIsEditorPick ? "var(--accent)" : "var(--border)" }}
                data-testid={heroIsEditorPick ? "landing-editor-pick" : "landing-hero-featured"}
              >
                <img src={hero.banner_url || hero.image_url} alt={hero.title} className="w-full h-full object-cover" />
                <div className="absolute inset-0 bg-gradient-to-t from-black via-black/40 to-transparent" />
                <div className="absolute inset-x-0 bottom-0 p-6">
                  <span
                    className={`chip mb-3 ${heroIsEditorPick ? "chip-accent" : "chip-accent"}`}
                    data-testid="hero-badge"
                  >
                    {heroBadge}
                  </span>
                  <h3 className="serif text-3xl leading-tight mb-2">{hero.title}</h3>
                  {heroBlurb ? (
                    <p
                      className="text-sm italic leading-snug mb-2 line-clamp-3"
                      style={{ color: "var(--text-muted)" }}
                      data-testid="hero-blurb"
                    >
                      "{heroBlurb}"
                    </p>
                  ) : null}
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
          <Link to="/events" className="hidden md:inline-flex items-center gap-2 text-sm hover:opacity-80" style={{ color: "var(--text-muted)" }}>
            All events <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {(Array.isArray(cats) ? cats : []).map((c, i) => (
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
              {(Array.isArray(recs) ? recs : []).map((r, i) => (
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
          <Link to="/events" className="hidden md:inline-flex items-center gap-2 text-sm hover:opacity-80" style={{ color: "var(--text-muted)" }}>
            See all <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {(Array.isArray(featured) ? featured : []).slice(0, 8).map((e, i) => <EventCard key={e.event_id} event={e} index={i} />)}
        </div>
      </section>

      {/* WHY ORGANIZERS — comparison strip */}
      <section className="max-w-7xl mx-auto px-6 pb-16" data-testid="why-organizers">
        <div className="text-xs uppercase tracking-[0.3em] mb-2 text-center" style={{ color: "var(--accent)" }}>Why promoters move to Allsale</div>
        <h2 className="serif text-4xl text-center mb-10">Keep more. Sell faster. Stress less.</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { kpi: "100%", label: "of face value kept", sub: "Buyers pay the service fee — you keep every cent of the ticket price." },
            { kpi: "5 days", label: "payout after event", sub: "Most platforms hold 30+. We release straight to your bank in five." },
            { kpi: "70 / 30", label: "auto revenue splits", sub: "Co-promoting? Split a single event between multiple Stripe accounts automatically." },
            { kpi: "0 ¢", label: "to list", sub: "Free event listing, free seat map builder, free QR scanning. You pay zero up-front." },
          ].map((item, i) => (
            <div
              key={item.kpi}
              className="rounded-xl border p-5 fade-up"
              style={{ borderColor: "var(--border)", animationDelay: `${i * 0.05}s`, background: "var(--bg-card)" }}
            >
              <div className="serif text-4xl mb-1" style={{ color: "var(--accent)" }}>{item.kpi}</div>
              <div className="text-sm font-semibold mb-2" style={{ color: "var(--text)" }}>{item.label}</div>
              <div className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>{item.sub}</div>
            </div>
          ))}
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
                Drag-build your seat map, set tier prices, hand out affiliate codes to influencers, and watch sales hit your dashboard live. On-the-door QR scanning, refunds on your terms, and payouts in 5 days — no spreadsheets, no scalper drama, no platform tax.
              </p>
              <Link to="/signup" className="btn-primary" data-testid="cta-signup-organizer">
                Become an organizer <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
            <div className="grid grid-cols-2 gap-4">
              {["Live sales tracking", "Affiliate codes", "Custom seat maps", "Auto QR check-in"].map((s, i) => (
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
