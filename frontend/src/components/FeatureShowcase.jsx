import { Link } from "react-router-dom";
import {
  Ticket, QrCode, ScanLine, ShieldCheck, Zap, DollarSign, Megaphone,
  Sparkles, BarChart3, Heart, Smartphone, ArrowRight, Users,
} from "lucide-react";

/**
 * FeatureShowcase
 * A premium "everything Allsale does" section for the landing page.
 * Layout: one large hero feature on the left (photo + headline) + a tight
 * grid of icon cards on the right. On mobile, stacks vertically.
 *
 * Photos are sourced from Unsplash (free for commercial use, hot-link
 * direct CDN URLs so we don't ship megabytes of bundle weight).
 */

const HERO_PHOTOS = [
  // Order matters — first photo is the big spotlight card on the left.
  {
    src: "https://images.unsplash.com/photo-1470229722913-7c0e2dbbafd3?auto=format&fit=crop&w=1200&q=80",
    alt: "Concert crowd with hands raised",
    icon: Ticket,
    eyebrow: "Sell tickets",
    title: "From open to sold-out in days",
    body: "Multi-tier ticketing, custom seat maps with aisles, dynamic pricing, FOMO timers, discount codes, and a checkout that converts on mobile in under 30 seconds.",
    cta: { to: "/become-organizer", label: "List your event" },
  },
];

const FEATURE_CARDS = [
  {
    icon: ScanLine,
    photo: "https://images.unsplash.com/photo-1551818255-e6e10975bc17?auto=format&fit=crop&w=600&q=80",
    title: "Door-scanner PWA",
    body: "Install in 5 seconds. Scan QR e-tickets offline. Zero hardware required.",
    tone: "orange",
  },
  {
    icon: DollarSign,
    photo: "https://images.unsplash.com/photo-1554224155-6726b3ff858f?auto=format&fit=crop&w=600&q=80",
    title: "Stripe Connect payouts",
    body: "Money in your account 5 days after each event. Zero commission — you keep 100% of the ticket price.",
    tone: "teal",
  },
  {
    icon: Sparkles,
    photo: "https://images.unsplash.com/photo-1611162616305-c69b3fa7fbe0?auto=format&fit=crop&w=600&q=80",
    title: "AI Flyer Maker",
    body: "Auto-generate Instagram-ready posters in three sizes with AI-written headlines. Download all formats as one zip.",
    tone: "black",
    isNew: true,
  },
  {
    icon: Megaphone,
    photo: "https://images.unsplash.com/photo-1554224155-6726b3ff858f?auto=format&fit=crop&w=600&q=80",
    title: "Creator marketplace",
    body: "Open your event to influencers. Pay only on sales they drive. Self-serve, no contracts.",
    tone: "orange",
  },
];

const PILL_FEATURES = [
  { icon: QrCode, label: "QR e-tickets" },
  { icon: Ticket, label: "Seat maps + aisles" },
  { icon: BarChart3, label: "Live analytics" },
  { icon: Heart, label: "Follow organisers" },
  { icon: ShieldCheck, label: "Self-serve refunds" },
  { icon: Zap, label: "Auto FIRST-50 promo" },
  { icon: Smartphone, label: "PWA install" },
  { icon: Users, label: "Partner program" },
];

export default function FeatureShowcase() {
  const hero = HERO_PHOTOS[0];

  return (
    <section
      className="max-w-7xl mx-auto px-6 pb-20 pt-8"
      data-testid="feature-showcase"
    >
      <div className="text-center mb-12">
        <div className="text-xs uppercase tracking-[0.3em] mb-3 inline-flex items-center gap-2" style={{ color: "var(--accent)" }}>
          <Sparkles className="w-3 h-3" /> Everything you need
        </div>
        <h2 className="serif text-4xl sm:text-5xl mb-3">One platform. Every moving part.</h2>
        <p className="text-base max-w-2xl mx-auto" style={{ color: "var(--text-muted)" }}>
          From the first poster to the last person through the gate — Allsale handles every step so you don&apos;t have to glue 5 tools together.
        </p>
      </div>

      {/* Hero feature + 2 secondary cards */}
      <div className="grid lg:grid-cols-12 gap-5 mb-5">
        {/* Big hero card */}
        <div
          className="lg:col-span-7 relative overflow-hidden rounded-3xl group"
          style={{ minHeight: 460 }}
          data-testid="feature-hero"
        >
          <img
            src={hero.src}
            alt={hero.alt}
            className="absolute inset-0 w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
            loading="lazy"
          />
          <div className="absolute inset-0" style={{
            background: "linear-gradient(180deg, rgba(15,42,58,0) 30%, rgba(15,42,58,0.85) 80%, rgba(15,42,58,0.95) 100%)",
          }} />
          <div className="relative h-full flex flex-col justify-end p-7 sm:p-9 text-white" style={{ minHeight: 460 }}>
            <div className="inline-flex items-center gap-2 mb-4 px-3 py-1 rounded-full text-xs w-fit" style={{ background: "rgba(255,255,255,0.18)", backdropFilter: "blur(8px)" }}>
              <hero.icon className="w-3 h-3" /> {hero.eyebrow}
            </div>
            <h3 className="serif text-3xl sm:text-4xl mb-3 leading-tight">{hero.title}</h3>
            <p className="text-sm sm:text-base opacity-90 max-w-md mb-5">{hero.body}</p>
            <Link
              to={hero.cta.to}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full text-sm font-medium w-fit transition-transform hover:translate-x-0.5"
              style={{ background: "var(--accent)", color: "#0F2A3A" }}
              data-testid="feature-hero-cta"
            >
              {hero.cta.label} <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>

        {/* Top-right 2 cards stacked */}
        <div className="lg:col-span-5 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 gap-5">
          {FEATURE_CARDS.slice(0, 2).map((f, i) => (
            <FeatureCard key={i} {...f} testid={`feature-card-${i}`} />
          ))}
        </div>
      </div>

      {/* Bottom row — 2 wider cards */}
      <div className="grid sm:grid-cols-2 gap-5 mb-12">
        {FEATURE_CARDS.slice(2).map((f, i) => (
          <FeatureCard key={i + 2} {...f} wide testid={`feature-card-${i + 2}`} />
        ))}
      </div>

      {/* Pill ribbon — "and so much more" */}
      <div
        className="rounded-3xl p-7 sm:p-9 relative overflow-hidden"
        style={{
          background: "linear-gradient(135deg, var(--bg-card) 0%, var(--bg-elev) 100%)",
          border: "1px solid var(--border)",
        }}
        data-testid="feature-pills"
      >
        <div className="absolute -top-12 -right-12 w-60 h-60 rounded-full" style={{ background: "var(--accent-soft)", filter: "blur(40px)" }} />
        <div className="relative">
          <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>And so much more</div>
          <h3 className="serif text-2xl sm:text-3xl mb-6">Powered by a long list of small details.</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {PILL_FEATURES.map((p) => (
              <div
                key={p.label}
                className="flex items-center gap-3 px-4 py-3 rounded-xl transition-all hover:translate-x-0.5"
                style={{
                  background: "var(--bg-card)",
                  border: "1px solid var(--border)",
                }}
              >
                <div
                  className="w-9 h-9 rounded-lg grid place-items-center flex-shrink-0"
                  style={{ background: "var(--accent-soft)", color: "var(--accent)" }}
                >
                  <p.icon className="w-4 h-4" />
                </div>
                <div className="text-sm font-medium" style={{ color: "var(--text)" }}>{p.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function FeatureCard({ icon: Icon, photo, title, body, tone = "orange", wide = false, testid, isNew }) {
  const accentMap = {
    orange: { ring: "rgba(240,138,42,0.4)", iconBg: "var(--accent)", iconFg: "#0F2A3A" },
    teal: { ring: "rgba(27,122,158,0.4)", iconBg: "var(--primary)", iconFg: "#FFFFFF" },
    black: { ring: "rgba(15,42,58,0.4)", iconBg: "#0F2A3A", iconFg: "var(--accent)" },
  };
  const a = accentMap[tone] || accentMap.orange;
  return (
    <div
      className="relative overflow-hidden rounded-3xl group transition-all"
      style={{ background: "var(--bg-card)", border: "1px solid var(--border)", minHeight: wide ? 240 : 215 }}
      data-testid={testid}
    >
      {isNew && (
        <span
          className="absolute top-4 right-4 z-10 text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full"
          style={{ background: "var(--accent)", color: "#fff" }}
        >
          New
        </span>
      )}
      <div className="absolute inset-y-0 right-0 w-2/5 overflow-hidden">
        <img
          src={photo}
          alt=""
          aria-hidden
          loading="lazy"
          className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110"
          style={{ filter: "saturate(0.95)" }}
        />
        <div className="absolute inset-0" style={{
          background: "linear-gradient(90deg, var(--bg-card) 0%, rgba(255,255,255,0.1) 70%, transparent 100%)",
        }} />
      </div>
      <div className="relative p-6 sm:p-7 max-w-[60%] h-full flex flex-col justify-between">
        <div>
          <div
            className="w-12 h-12 rounded-xl grid place-items-center mb-4"
            style={{ background: a.iconBg, color: a.iconFg, boxShadow: `0 6px 18px ${a.ring}` }}
          >
            <Icon className="w-5 h-5" />
          </div>
          <h3 className="serif text-xl sm:text-2xl mb-2 leading-tight">{title}</h3>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>{body}</p>
        </div>
      </div>
    </div>
  );
}
