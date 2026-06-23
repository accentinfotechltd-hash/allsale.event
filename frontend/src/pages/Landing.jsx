import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import EventCard from "@/components/EventCard";
import FeatureShowcase from "@/components/FeatureShowcase";
import TrendingCarousel from "@/components/TrendingCarousel";
import { useAuth } from "@/lib/auth";
import { ArrowRight, Search, Calendar, Zap, Award, Sparkles, Ticket, ScanLine, DollarSign, ShieldCheck, Smartphone, Megaphone, Users } from "lucide-react";

export default function Landing() {
  const { user } = useAuth();
  const [featured, setFeatured] = useState([]);
  const [cats, setCats] = useState([]);
  const [recs, setRecs] = useState([]);
  const [recsLoading, setRecsLoading] = useState(false);
  const [liveCount, setLiveCount] = useState(null);
  const [editorPick, setEditorPick] = useState({ picks: [], event: null, blurb: "", badge_text: "Editor's Pick" });
  // Carousel index for multi-pick hero rotation.
  const [heroIdx, setHeroIdx] = useState(0);
  const [q, setQ] = useState("");
  const nav = useNavigate();

  useEffect(() => {
    (async () => {
      try {
        const [f, c, s, ep] = await Promise.all([
          api.get("/events/featured"),
          api.get("/events/categories"),
          api.get("/events/stats/public").catch(() => ({ data: { live_events: 0 } })),
          api.get("/site-settings/editor-pick").catch(() => ({ data: { picks: [], event: null, blurb: "", badge_text: "Editor's Pick" } })),
        ]);
        setFeatured(Array.isArray(f.data) ? f.data : []);
        setCats(Array.isArray(c.data) ? c.data : []);
        setLiveCount(typeof s?.data?.live_events === "number" ? s.data.live_events : 0);
        setEditorPick(ep.data || { picks: [], event: null, blurb: "", badge_text: "Editor's Pick" });
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

  // Build the rotation list:
  //   - If admin pinned 1+ editor picks → rotate through those.
  //   - Otherwise fall back to the first featured event so the hero is never empty.
  const heroPicks = Array.isArray(editorPick.picks) && editorPick.picks.length > 0
    ? editorPick.picks
    : (Array.isArray(featured) && featured.length > 0
        ? [{ event: featured[0], blurb: "" }]
        : []);
  const heroIsEditorPick = Array.isArray(editorPick.picks) && editorPick.picks.length > 0;
  const heroBadge = heroIsEditorPick ? (editorPick.badge_text || "Editor's Pick") : "Featured";
  const safeIdx = heroPicks.length > 0 ? heroIdx % heroPicks.length : 0;
  const currentPick = heroPicks[safeIdx] || null;
  const hero = currentPick?.event || null;
  const heroBlurb = currentPick?.blurb || "";

  // Auto-rotate every 6 seconds when there are 2+ picks. Stops if the user
  // manually clicks a dot (we don't track that explicitly — rotation just
  // resumes on the next interval, which is fine for a hero spotlight).
  useEffect(() => {
    if (heroPicks.length < 2) return undefined;
    const id = setInterval(() => setHeroIdx((i) => (i + 1) % heroPicks.length), 6000);
    return () => clearInterval(id);
  }, [heroPicks.length]);

  return (
    <div>
      {/* TOP FEATURE STRIP — first thing every visitor sees: a one-glance summary
          of what Allsale does. Marquee on mobile, static row on desktop. */}
      <FeatureStrip />

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
            <p className="text-base sm:text-lg max-w-xl mb-8" style={{ color: "var(--text)" }}>
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

            <div className="flex flex-wrap items-center gap-x-6 gap-y-3 mt-10 text-sm" style={{ color: "var(--text)" }}>
              <div className="flex items-center gap-2 whitespace-nowrap"><Zap className="w-4 h-4 flex-shrink-0" style={{ color: "var(--accent)" }} /> Instant e-tickets</div>
              <div className="flex items-center gap-2 whitespace-nowrap"><Award className="w-4 h-4 flex-shrink-0" style={{ color: "var(--accent)" }} /> Paid out in 5 days</div>
              <div className="flex items-center gap-2 whitespace-nowrap"><Calendar className="w-4 h-4 flex-shrink-0" style={{ color: "var(--accent)" }} /> 10-min seat hold</div>
            </div>
          </div>

          {hero && (
            <div className="lg:col-span-5 fade-up fade-up-2">
              <Link
                to={`/events/${hero.event_id}`}
                className="group block relative aspect-[3/4] rounded-2xl overflow-hidden border shadow-xl"
                style={{
                  borderColor: heroIsEditorPick ? "var(--accent)" : "var(--border)",
                  boxShadow: "0 20px 60px -20px rgba(0,0,0,0.6)",
                }}
                data-testid={heroIsEditorPick ? "landing-editor-pick" : "landing-hero-featured"}
              >
                <img
                  src={hero.banner_url || hero.image_url}
                  alt={hero.title}
                  className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-[1.04]"
                />
                {/* Two-layer scrim: a tall soft gradient + a solid panel on the
                    bottom 40% guarantees the title is readable no matter how
                    light the underlying image is. */}
                <div
                  className="absolute inset-0 pointer-events-none"
                  style={{
                    background:
                      "linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,0) 35%, rgba(0,0,0,0.55) 65%, rgba(0,0,0,0.88) 100%)",
                  }}
                />
                <div className="absolute inset-x-0 bottom-0 p-6">
                  <span
                    className={`chip mb-3 ${heroIsEditorPick ? "chip-accent" : "chip-accent"}`}
                    data-testid="hero-badge"
                  >
                    {heroBadge}
                  </span>
                  <h3
                    className="serif text-3xl leading-tight mb-2"
                    style={{
                      color: "#FFFFFF",
                      textShadow: "0 2px 12px rgba(0,0,0,0.65)",
                      fontWeight: 600,
                    }}
                  >
                    {hero.title}
                  </h3>
                  {heroBlurb ? (
                    <p
                      className="text-sm italic leading-snug mb-2 line-clamp-3"
                      style={{ color: "rgba(255,255,255,0.85)", textShadow: "0 1px 6px rgba(0,0,0,0.5)" }}
                      data-testid="hero-blurb"
                    >
                      "{heroBlurb}"
                    </p>
                  ) : null}
                  <p
                    className="text-sm"
                    style={{ color: "rgba(255,255,255,0.8)", textShadow: "0 1px 6px rgba(0,0,0,0.5)" }}
                  >
                    {hero.venue} · {hero.city}
                  </p>
                </div>
              </Link>

              {/* Carousel controls — only visible when 2+ picks are pinned */}
              {heroPicks.length > 1 && (
                <div className="flex items-center justify-between mt-3 px-1" data-testid="hero-carousel-controls">
                  <button
                    type="button"
                    onClick={() => setHeroIdx((i) => (i - 1 + heroPicks.length) % heroPicks.length)}
                    className="text-sm hover:opacity-80 inline-flex items-center gap-1"
                    style={{ color: "var(--text)" }}
                    data-testid="hero-prev"
                    aria-label="Previous pick"
                  >
                    ← Prev
                  </button>
                  <div className="flex items-center gap-1.5" data-testid="hero-dots">
                    {heroPicks.map((_, i) => (
                      <button
                        key={i}
                        type="button"
                        onClick={() => setHeroIdx(i)}
                        className="transition-all"
                        style={{
                          width: i === safeIdx ? 22 : 6,
                          height: 6,
                          borderRadius: 99,
                          background: i === safeIdx ? "var(--accent)" : "var(--border-strong)",
                        }}
                        aria-label={`Show pick ${i + 1}`}
                        data-testid={`hero-dot-${i}`}
                      />
                    ))}
                  </div>
                  <button
                    type="button"
                    onClick={() => setHeroIdx((i) => (i + 1) % heroPicks.length)}
                    className="text-sm hover:opacity-80 inline-flex items-center gap-1"
                    style={{ color: "var(--text)" }}
                    data-testid="hero-next"
                    aria-label="Next pick"
                  >
                    Next →
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </section>

      {/* PREMIUM FEATURE SHOWCASE — moved to top so visitors see Allsale's full power immediately */}
      <FeatureShowcase />

      {/* TRENDING THIS WEEK — only renders when there's at least one boosted event */}
      <TrendingCarousel />

      {/* CATEGORIES */}
      <section className="max-w-7xl mx-auto px-6 py-16">
        <div className="flex items-end justify-between mb-8">
          <div>
            <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Browse by mood</div>
            <h2 className="serif text-4xl">Pick your scene</h2>
          </div>
          <Link to="/events" className="hidden md:inline-flex items-center gap-2 text-sm hover:opacity-80" style={{ color: "var(--text)" }}>
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
              <p className="text-sm mt-1" style={{ color: "var(--text)" }}>
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
                  <div className="mt-2 px-1 text-xs italic leading-snug" style={{ color: "var(--text)" }}>
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
          <Link to="/events" className="hidden md:inline-flex items-center gap-2 text-sm hover:opacity-80" style={{ color: "var(--text)" }}>
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
        <h2 className="serif text-4xl text-center mb-3">Price the show. Keep the show.</h2>
        <p className="text-sm text-center max-w-xl mx-auto mb-10" style={{ color: "var(--text)" }}>
          Built in Aotearoa for promoters tired of giving away 15-20% to platforms that don&apos;t lift a finger past launch day.
        </p>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { kpi: "100%", label: "of face value, yours", sub: "Set your price. Keep every dollar. No platform cut — ever." },
            { kpi: "5 days", label: "payout after event", sub: "Industry-fastest. Straight to your bank — while other platforms still hold the cash." },
            { kpi: "70 / 30", label: "auto revenue splits", sub: "Co-promoting? Split a single event across multiple Stripe accounts — automatically." },
            { kpi: "0 ¢", label: "to list", sub: "Free event listing, free seat-map builder, free QR scanning. Sell first, pay never." },
          ].map((item, i) => (
            <div
              key={item.kpi}
              className="rounded-xl border p-5 fade-up"
              style={{ borderColor: "var(--border)", animationDelay: `${i * 0.05}s`, background: "var(--bg-card)" }}
            >
              <div className="serif text-4xl mb-1" style={{ color: "var(--accent)" }}>{item.kpi}</div>
              <div className="text-sm font-semibold mb-2" style={{ color: "var(--text)" }}>{item.label}</div>
              <div className="text-xs leading-relaxed" style={{ color: "var(--text)" }}>{item.sub}</div>
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
              <h3 className="serif text-4xl lg:text-5xl leading-tight mb-4">Sell out your next show. <em style={{ color: "var(--accent)" }}>Keep&nbsp;every dollar.</em></h3>
              <p className="mb-6 max-w-md" style={{ color: "var(--text)" }}>
                Drag-build your seat map. Set tier prices. Hand affiliate codes to local influencers. Watch sales hit your dashboard live. On-the-door QR scanning, refunds on your terms, payouts in 5 days. No spreadsheets, no scalper drama, <strong style={{ color: "var(--text)" }}>no platform tax</strong>.
              </p>
              <Link to="/signup" className="btn-primary" data-testid="cta-signup-organizer">
                Become an organizer <ArrowRight className="w-4 h-4" />
              </Link>
            </div>
            <div className="grid grid-cols-2 gap-4">
              {["Live sales tracking", "Affiliate codes", "Custom seat maps", "Auto QR check-in"].map((s, i) => (
                <div key={s} className="glass rounded-xl p-5 fade-up" style={{ animationDelay: `${i * 0.05}s` }}>
                  <div className="serif text-2xl mb-1">0{i + 1}</div>
                  <div className="text-sm" style={{ color: "var(--text)" }}>{s}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

/**
 * FeatureStrip — slim, eye-level ribbon at the very top of the landing page
 * so every visitor sees Allsale's core capabilities within half a second.
 * On wide screens it lays out in a single row; on phones it horizontally
 * scrolls (touch + keyboard friendly) so we don't sacrifice copy density.
 */
const TOP_FEATURES = [
  { slug: "multi-tier-ticketing", icon: Ticket, label: "Multi-tier ticketing", sub: "Early Bird, GA, VIP" },
  { slug: "custom-seat-maps", icon: Calendar, label: "Custom seat maps", sub: "Aisles, categories, holds" },
  { slug: "instant-e-tickets", icon: Zap, label: "Instant e-tickets", sub: "QR delivered in seconds" },
  { slug: "ai-flyer-maker", icon: Sparkles, label: "AI Flyer Maker", sub: "Posters in seconds", isNew: true },
  { slug: "door-scanner-pwa", icon: ScanLine, label: "Door-scanner PWA", sub: "Works offline at the gate" },
  { slug: "keep-100", icon: DollarSign, label: "Keep 100%", sub: "Zero commission on ticket sales" },
  { slug: "stripe-payouts", icon: ShieldCheck, label: "Stripe payouts", sub: "5 days after the show" },
  { slug: "marketing-partners", icon: Users, label: "Partner program", sub: "Refer and earn", isNew: true },
  { slug: "creator-marketplace", icon: Megaphone, label: "Creator marketplace", sub: "Pay only on sales" },
  { slug: "pwa-mobile-first", icon: Smartphone, label: "PWA + mobile-first", sub: "Install, no app store" },
];

function FeatureStrip() {
  return (
    <section
      className="border-b"
      style={{ borderColor: "var(--border)", background: "var(--bg-elev)" }}
      data-testid="landing-feature-strip"
      aria-label="Platform features"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3">
        <div
          className="flex items-center gap-2.5 overflow-x-auto sm:overflow-visible sm:flex-wrap sm:justify-center scrollbar-hide"
          style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
        >
          <span
            className="text-[10px] uppercase tracking-[0.25em] font-medium shrink-0 hidden sm:inline-block"
            style={{ color: "var(--accent)" }}
          >
            What you get
          </span>
          <span className="hidden sm:inline-block w-px h-3" style={{ background: "var(--border-strong)" }} />
          {TOP_FEATURES.map(({ icon: Icon, label, sub, slug, isNew }) => (
            <Link
              key={label}
              to={`/features#${slug}`}
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full shrink-0 border transition hover:-translate-y-px hover:shadow-sm"
              style={{
                background: "var(--bg-card)",
                borderColor: "var(--border)",
                color: "var(--text)",
              }}
              data-testid={`feature-chip-${slug}`}
              title={`${sub} — click to learn how`}
            >
              <Icon className="w-3.5 h-3.5" style={{ color: "var(--accent)" }} />
              <span className="text-xs font-medium whitespace-nowrap">{label}</span>
              {isNew && (
                <span
                  className="text-[9px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-full"
                  style={{ background: "var(--accent)", color: "#fff" }}
                  data-testid={`feature-chip-${slug}-new-badge`}
                >
                  New
                </span>
              )}
              <span className="text-[10px] whitespace-nowrap hidden md:inline" style={{ color: "var(--text)" }}>· {sub}</span>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}
