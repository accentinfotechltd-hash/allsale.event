/**
 * Features — public landing-style page documenting every key platform
 * capability, with deep-link anchors so the landing strip chips can jump
 * straight to the right section.
 *
 * Layout choices:
 *  - One long page (no client-side routing per feature) so visitors can
 *    scroll, skim, and bookmark.
 *  - A sticky in-page side-nav on desktop, condensed pill row on mobile.
 *  - Each feature has: hero copy → "How it works" steps → CTA.
 *  - Hash-aware: on mount we scroll to the section matching window.location.hash.
 */
import { useEffect, useMemo } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  Ticket, Calendar, Zap, ScanLine, DollarSign, ShieldCheck,
  Megaphone, Smartphone, ArrowRight, Check, Sparkles, Users,
} from "lucide-react";

const FEATURES = [
  {
    slug: "multi-tier-ticketing",
    icon: Ticket,
    title: "Multi-tier ticketing",
    tagline: "Early Bird, General Admission, VIP — all under one event.",
    body:
      "Run multiple ticket types with their own price, capacity and selling window. Allsale tracks sold + held quantities per tier in real time so you can't oversell.",
    steps: [
      "Create an event from /organizer/new (or open an existing draft).",
      "Toggle OFF the interactive seat map.",
      "Click 'Add tier' for each ticket type (e.g. Early Bird, GA, VIP).",
      "Set the name, price and capacity per tier. Set price 0 to mark a tier as Free.",
      "Save — the public event page now shows tier cards with live availability.",
    ],
    cta: { label: "Create an event", to: "/organizer/new" },
  },
  {
    slug: "custom-seat-maps",
    icon: Calendar,
    title: "Custom seat maps",
    tagline: "Drag-build any venue: rows, aisles, sections, categories, custom labels.",
    body:
      "From a 50-seat black box to a 2,000-seat amphitheatre. Paint aisles, mark VIP / Wheelchair / Premium seats with category colors, set row offsets for indented rows, and even hand-label seats like 'AA1' or 'Box-3' to match your venue's signage.",
    steps: [
      "On /organizer/new toggle ON the Interactive seat map.",
      "Set rows × cols. Upload a floor-plan as a backdrop (optional).",
      "Click a paint mode (Aisle / VIP / Wheelchair / etc.) and tap or drag seats to apply it.",
      "Use 'Label' mode to rename a seat; the rest of the row auto-fills, skipping aisles.",
      "Open the Numbering preview to verify each row, or 'Export row plan (CSV)' for ushers.",
      "Save Layouts as templates and reuse them on every recurring show.",
    ],
    cta: { label: "Open seat designer", to: "/organizer/new" },
  },
  {
    slug: "instant-e-tickets",
    icon: Zap,
    title: "Instant e-tickets",
    tagline: "QR-coded tickets in your inbox within seconds of paying.",
    body:
      "Each ticket is a signed QR code, emailed to the buyer the moment the booking confirms, and also visible in their /profile. Tickets are scannable offline by the door PWA — no third-party app required.",
    steps: [
      "Buyer picks seats / tiers and pays.",
      "Stripe webhook → Allsale generates the QR and emails it via Resend.",
      "Buyer can also open the ticket from /profile any time before the event.",
      "At the door, your staff scan the QR with the Door PWA on their phone.",
    ],
    cta: { label: "View my tickets", to: "/profile" },
  },
  {
    slug: "door-scanner-pwa",
    icon: ScanLine,
    title: "Door-scanner PWA",
    tagline: "Install in 5 seconds, scan offline, zero hardware.",
    body:
      "Any staff phone becomes a scanner. The PWA caches the attendee list so it works even when the venue Wi-Fi is patchy. Each successful scan flips the ticket to 'checked-in' and syncs the moment connectivity returns.",
    steps: [
      "On a staff phone, open /scan and tap 'Install app' when prompted.",
      "Sign in with the staff/organizer account.",
      "Select the event — attendees are downloaded for offline use.",
      "Point the camera at the QR. Green tick = valid. Red cross = already scanned / refunded.",
    ],
    cta: { label: "Try the scanner", to: "/scan" },
  },
  {
    slug: "keep-100",
    icon: DollarSign,
    title: "Keep 100% of the ticket price",
    tagline: "Zero commission on your ticket sales — your face-value goes to you.",
    body:
      "We never skim the ticket price. Your sales settle 1:1 with what you set at checkout.",
    steps: [
      "When pricing your tiers / seats, set the face value you want to receive.",
      "Allsale settles the full face value into your Stripe account.",
      "Payouts land in your bank 5 days after the event.",
    ],
    cta: { label: "Become an organizer", to: "/become-organizer" },
  },
  {
    slug: "stripe-payouts",
    icon: ShieldCheck,
    title: "Stripe Connect payouts",
    tagline: "Money in your bank 5 days after every event.",
    body:
      "Stripe Connect Express handles KYC, bank verification and the actual payout. You see your gross, refunds, fees and net-settled per event right in the Organizer dashboard.",
    steps: [
      "From /organizer click 'Connect Stripe' and complete onboarding.",
      "Your sales now flow into your Stripe account and auto-payout 5 days after the show.",
      "Refunds processed inside Allsale reverse against the same Stripe charge.",
      "Track everything on /organizer/payouts — gross, reversed, net settled.",
    ],
    cta: { label: "Open payouts", to: "/organizer/payouts" },
  },
  {
    slug: "creator-marketplace",
    icon: Megaphone,
    title: "Creator marketplace",
    tagline: "Pay influencers only on sales they actually drive.",
    body:
      "Open your event's affiliate program and any verified creator on Allsale can self-join with one click. Each gets a unique tracked link; you set the commission %. Creators see live earnings, you see the ROI per channel.",
    steps: [
      "On your event page (organizer view), enable 'Open affiliate program'.",
      "Set the default commission % (we start at 5%).",
      "Creators discover your event in the /influencers marketplace and self-join.",
      "When a sale comes in via their link, the commission accrues automatically.",
      "Approved payouts settle monthly via Stripe Express.",
    ],
    cta: { label: "Browse creators", to: "/influencers" },
  },
  {
    slug: "pwa-mobile-first",
    icon: Smartphone,
    title: "PWA + mobile-first",
    tagline: "Installable on any phone — no App Store, no Play Store wait.",
    body:
      "Allsale is a Progressive Web App. Attendees and organizers both get an installable shortcut on their home screen, offline support for tickets, and instant updates without store-review cycles.",
    steps: [
      "Open Allsale in mobile Safari or Chrome.",
      "Tap the share / install icon → 'Add to Home Screen'.",
      "The app launches full-screen with offline ticket access.",
      "Updates ship instantly — no store review delays.",
    ],
    cta: { label: "Browse events", to: "/events" },
  },
  {
    slug: "ai-flyer-maker",
    icon: Sparkles,
    title: "AI Flyer Maker",
    tagline: "Instagram-ready posters in seconds — no designer required.",
    body:
      "Every event gets a Share page that renders three pixel-perfect flyer sizes (square 1:1, story 9:16, landscape 16:9) from your cover photo and details. Hit one button to generate AI-written headlines and CTAs; download all three as a single zip ready for socials.",
    steps: [
      "Open any event you own and click 'Share'.",
      "Pick a template (Minimal / Neon / Bold) and tweak colors if you want.",
      "Tap 'Add AI text overlay' — we generate a headline, tagline and CTA in your voice.",
      "Hit 'Download all (zip)' to get all three social sizes in one click.",
    ],
    cta: { label: "Browse events", to: "/events" },
  },
  {
    slug: "marketing-partners",
    icon: Users,
    title: "Marketing Partner program",
    tagline: "Refer organisers, earn commission — fully automated.",
    body:
      "Bring organisers onto Allsale and earn a percentage of every paid booking they make, forever. Partners get a private portal showing live earnings, attached organisers, and monthly payout statements — all settled via Stripe.",
    steps: [
      "Apply to become a marketing partner (or get granted access by Allsale).",
      "Receive your portal login by email with a temporary password.",
      "Refer organisers — Allsale links them to your account automatically.",
      "Earnings credit on every paid booking; statements email on the 1st, payouts on the 5th.",
    ],
    cta: { label: "Open partner portal", to: "/partner" },
  },
];

export default function Features() {
  const { hash } = useLocation();

  // Scroll to the requested anchor on mount and whenever the hash changes.
  useEffect(() => {
    if (!hash) {
      window.scrollTo({ top: 0, behavior: "auto" });
      return;
    }
    const id = hash.replace("#", "");
    const t = setTimeout(() => {
      const el = document.getElementById(id);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 60);
    return () => clearTimeout(t);
  }, [hash]);

  const nav = useMemo(
    () => FEATURES.map((f) => ({ slug: f.slug, title: f.title, Icon: f.icon })),
    []
  );

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-10 sm:py-16" data-testid="features-page">
      <div className="mb-10">
        <div className="text-xs uppercase tracking-[0.3em] mb-3" style={{ color: "var(--accent)" }}>
          What Allsale does
        </div>
        <h1 className="serif text-4xl sm:text-5xl lg:text-6xl leading-[1.05] mb-3">
          Everything you need to <em style={{ color: "var(--accent)" }}>sell out</em>.
        </h1>
        <p className="text-base max-w-2xl" style={{ color: "var(--text)" }}>
          Ten core capabilities that cover the entire journey — from listing
          your first event to scanning the last ticket at the door. Click any
          feature below to jump to a quick tutorial.
        </p>
      </div>

      {/* Top chip nav — same look as the landing strip, but each pill anchors */}
      <nav
        className="flex flex-wrap gap-2 mb-12 pb-4 border-b"
        style={{ borderColor: "var(--border)" }}
        aria-label="Feature index"
        data-testid="features-nav"
      >
        {nav.map(({ slug, title, Icon }) => (
          <a
            key={slug}
            href={`#${slug}`}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-medium hover:opacity-80 transition"
            style={{ background: "var(--bg-card)", borderColor: "var(--border)", color: "var(--text)" }}
            data-testid={`features-nav-${slug}`}
          >
            <Icon className="w-3.5 h-3.5" style={{ color: "var(--accent)" }} />
            {title}
          </a>
        ))}
      </nav>

      <div className="space-y-16">
        {FEATURES.map(({ slug, icon: Icon, title, tagline, body, steps, cta }, idx) => (
          <section
            key={slug}
            id={slug}
            className="scroll-mt-24"
            data-testid={`features-section-${slug}`}
          >
            <div className="grid lg:grid-cols-[1fr_1.2fr] gap-8 lg:gap-12 items-start">
              <div>
                <div className="inline-flex items-center gap-2 mb-3 text-xs uppercase tracking-widest" style={{ color: "var(--accent)" }}>
                  <span className="w-6 h-6 rounded-full grid place-items-center" style={{ background: "var(--accent-soft)" }}>
                    <Icon className="w-3.5 h-3.5" />
                  </span>
                  Feature {String(idx + 1).padStart(2, "0")}
                </div>
                <h2 className="serif text-3xl sm:text-4xl mb-3">{title}</h2>
                <p className="text-base mb-4" style={{ color: "var(--text)" }}>{tagline}</p>
                <p className="text-sm leading-relaxed" style={{ color: "var(--text)" }}>{body}</p>
                {cta && (
                  <Link
                    to={cta.to}
                    className="btn-primary mt-6 inline-flex items-center gap-2"
                    data-testid={`features-cta-${slug}`}
                  >
                    {cta.label} <ArrowRight className="w-4 h-4" />
                  </Link>
                )}
              </div>

              <div
                className="rounded-2xl p-6 border"
                style={{ background: "var(--bg-elev)", borderColor: "var(--border)" }}
              >
                <div className="text-xs uppercase tracking-widest mb-4" style={{ color: "var(--text-dim)" }}>
                  How to use it
                </div>
                <ol className="space-y-3">
                  {steps.map((s, i) => (
                    <li key={i} className="flex items-start gap-3 text-sm">
                      <span
                        className="shrink-0 w-6 h-6 rounded-full grid place-items-center text-[11px] font-medium mt-0.5"
                        style={{ background: "var(--accent)", color: "#000" }}
                      >
                        {i + 1}
                      </span>
                      <span style={{ color: "var(--text)" }}>{s}</span>
                    </li>
                  ))}
                </ol>
                <div className="mt-5 pt-4 border-t flex items-center gap-2 text-xs" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
                  <Check className="w-3 h-3" style={{ color: "var(--accent)" }} />
                  No setup fees, no contracts, no platform tax on tickets.
                </div>
              </div>
            </div>
          </section>
        ))}
      </div>

      <div
        className="mt-20 rounded-2xl p-8 sm:p-12 text-center border"
        style={{ background: "var(--bg-elev)", borderColor: "var(--border)" }}
      >
        <h3 className="serif text-3xl sm:text-4xl mb-3">Ready to run your show?</h3>
        <p className="text-sm mb-6 max-w-xl mx-auto" style={{ color: "var(--text)" }}>
          Sign up takes 60 seconds. List your event in under five minutes.
          Allsale handles tickets, payments and the front door.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <Link to="/signup" className="btn-primary" data-testid="features-bottom-cta-signup">
            Get started — free <ArrowRight className="w-4 h-4" />
          </Link>
          <Link to="/events" className="btn-ghost" data-testid="features-bottom-cta-browse">
            Browse live events
          </Link>
        </div>
      </div>
    </div>
  );
}
