import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Search, Ticket, ScanLine, Heart, ShieldCheck, ArrowRightLeft,
  PlusCircle, BarChart3, Megaphone, Wallet, Users as UsersIcon, Sparkles,
  Users, DollarSign, MailPlus, KeyRound, RotateCcw,
} from "lucide-react";

/**
 * Static help / how-it-works page accessible from the footer and from the
 * welcome modal's CTA. Three persona tabs (Attendees / Organisers / Partners)
 * — each renders a tall list of cards with concrete next-actions. A reopen
 * button at the bottom fires the `allsale:show-welcome` event that the
 * <WelcomeModal/> listens for, so users can re-watch the tour any time.
 */
export default function Help() {
  const [tab, setTab] = useState("attendees");

  const replay = () => {
    // Clear all role-specific flags so the modal re-shows.
    Object.keys(localStorage)
      .filter((k) => k.startsWith("welcomeSeen_"))
      .forEach((k) => localStorage.removeItem(k));
    window.dispatchEvent(new Event("allsale:show-welcome"));
  };

  return (
    <div className="max-w-5xl mx-auto px-4 py-12" data-testid="help-page">
      {/* Header */}
      <div className="mb-3 flex items-center gap-2 text-xs uppercase tracking-widest" style={{ color: "var(--accent)" }}>
        <Sparkles size={14} /> Help &amp; how it works
      </div>
      <h1 className="font-serif text-4xl sm:text-5xl mb-3" style={{ color: "var(--text)" }}>
        How Allsale Events works
      </h1>
      <p className="text-base max-w-2xl" style={{ color: "var(--text-dim)" }}>
        Whether you're here for a night out, putting on a show, or referring
        organisers — this page walks you through everything you need.
      </p>

      {/* Tabs */}
      <div className="mt-10 border-b flex items-center gap-1 overflow-x-auto" style={{ borderColor: "var(--border)" }} data-testid="help-tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className="px-4 py-2.5 text-sm whitespace-nowrap transition relative"
            style={{
              color: tab === t.id ? "var(--text)" : "var(--text-dim)",
              borderBottom: tab === t.id ? "2px solid var(--accent)" : "2px solid transparent",
              fontWeight: tab === t.id ? 600 : 400,
            }}
            data-testid={`help-tab-${t.id}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Sections */}
      <div className="mt-8 space-y-5">
        {(SECTIONS[tab] || []).map((s, i) => (
          <div
            key={i}
            className="rounded-2xl border p-5 sm:p-6 flex gap-5"
            style={{ borderColor: "var(--border)" }}
            data-testid={`help-card-${tab}-${i}`}
          >
            <div
              className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0"
              style={{ background: "rgba(240,138,42,0.10)", color: "var(--accent)" }}
            >
              <s.icon size={22} />
            </div>
            <div className="min-w-0">
              <h3 className="font-serif text-lg mb-1.5" style={{ color: "var(--text)" }}>{s.title}</h3>
              <p className="text-sm leading-relaxed" style={{ color: "var(--text-dim)" }}>{s.body}</p>
              {s.cta && (
                <Link
                  to={s.cta.href}
                  className="inline-flex items-center gap-1 text-sm mt-3 underline"
                  style={{ color: "var(--accent)" }}
                  data-testid={`help-card-${tab}-${i}-cta`}
                >
                  {s.cta.label} →
                </Link>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Replay tour CTA */}
      <div
        className="mt-12 rounded-2xl border p-6 sm:p-8 text-center"
        style={{ borderColor: "var(--border)", background: "rgba(240,138,42,0.04)" }}
        data-testid="help-replay-tour"
      >
        <h3 className="font-serif text-xl mb-2" style={{ color: "var(--text)" }}>
          Want a quick recap?
        </h3>
        <p className="text-sm mb-4 max-w-md mx-auto" style={{ color: "var(--text-dim)" }}>
          We can show you the welcome tour again — it takes less than a minute and
          adapts to whether you're an attendee, organiser, partner or admin.
        </p>
        <button
          onClick={replay}
          className="btn-primary text-sm inline-flex items-center gap-1.5"
          data-testid="help-replay-btn"
        >
          <RotateCcw size={14} /> Show me the welcome tour
        </button>
      </div>

      {/* Still stuck */}
      <div className="mt-10 text-center text-sm" style={{ color: "var(--text-dim)" }}>
        Still stuck?{" "}
        <Link to="/contact" className="underline" style={{ color: "var(--accent)" }}>
          Talk to us
        </Link>
        .
      </div>
    </div>
  );
}

const TABS = [
  { id: "attendees", label: "For attendees" },
  { id: "organisers", label: "For organisers" },
  { id: "partners", label: "For partners" },
];

const SECTIONS = {
  attendees: [
    {
      icon: Search,
      title: "Discover events you'll love",
      body: "Browse upcoming gigs, theatre, sport, comedy and conferences. Filter by city, date or category. Hit Trending to see what's actually selling — not what we're paid to show you.",
      cta: { href: "/events", label: "Browse all events" },
    },
    {
      icon: Ticket,
      title: "Book in under a minute",
      body: "Pick your tier (or your seat, on seated events), apply a promo code if you have one, and check out with card, Apple Pay or Google Pay. Your e-ticket arrives by email seconds later.",
    },
    {
      icon: ScanLine,
      title: "Walk straight in at the door",
      body: "Show the QR code from your inbox or your Profile → My Tickets. Door staff scan it once and you're in. Save tickets to Apple Wallet for offline-safe entry.",
      cta: { href: "/profile", label: "View my tickets" },
    },
    {
      icon: ArrowRightLeft,
      title: "Plans changed? Transfer your ticket",
      body: "Tap a ticket on your Profile page and 'Transfer'. Enter a friend's email and we'll send them a secure claim link — no fees, no hassle. The original QR is invalidated automatically.",
    },
    {
      icon: ShieldCheck,
      title: "Refunds &amp; ticket protection",
      body: "Most events allow refunds up to 7 days before the date. Some offer Ticket Protection at checkout — covers illness, travel disruption and other surprises with one-click claim.",
    },
    {
      icon: Heart,
      title: "Stay in the loop",
      body: "Favourite an event to track it, follow organisers you love, and turn on email alerts in Profile → Notifications. We'll quietly nudge you only when something matches your taste.",
    },
  ],
  organisers: [
    {
      icon: PlusCircle,
      title: "Create your first event",
      body: "Hit 'Create event' on the organiser dashboard. Add a cover photo, optional 9:16 poster, a description, and one or more ticket tiers with capacity. Save as draft, preview, then publish when you're ready.",
      cta: { href: "/organizer/new", label: "Create event" },
    },
    {
      icon: BarChart3,
      title: "Track every dollar live",
      body: "Your dashboard shows sales, scan-ins, refund rate, demographics and a clear P&L. Filter by event, tier or date range. Export to CSV anytime — your accountant will thank you.",
      cta: { href: "/organizer", label: "Open dashboard" },
    },
    {
      icon: Megaphone,
      title: "Promote without a designer",
      body: "Every event has a Share page that generates Instagram-ready flyers (square / story / landscape), an AI-written headline you can tweak, and one-tap social sharing. Download a zip of all three sizes in one click.",
    },
    {
      icon: ScanLine,
      title: "Scan tickets at the door",
      body: "On show day, log in to /scan from any phone or tablet. Scan QR tickets, see real-time check-in counts, and resolve duplicates instantly. No extra hardware, no printed lists.",
      cta: { href: "/scan", label: "Open door scanner" },
    },
    {
      icon: Wallet,
      title: "Get paid on time",
      body: "Payouts run automatically after each event clears the refund window. Add your bank details once in Payouts and we handle the rest. View statements anytime.",
      cta: { href: "/organizer/payouts", label: "Set up payouts" },
    },
    {
      icon: UsersIcon,
      title: "Build a team",
      body: "Invite scanners, marketing managers and accountants with role-based access. They see only what they need — no risk of accidental changes to your published events.",
    },
  ],
  partners: [
    {
      icon: Users,
      title: "Your partner portal",
      body: "Log in to see your commission rate, organisers attached to you, lifetime earnings and unpaid balance — all on one page.",
      cta: { href: "/partner", label: "Open my portal" },
    },
    {
      icon: DollarSign,
      title: "How you earn commission",
      body: "Every paid booking on an organiser linked to you credits a commission to your ledger automatically. Earnings appear within minutes of the booking clearing — no chasing reports.",
    },
    {
      icon: MailPlus,
      title: "Statements &amp; payouts",
      body: "On the 1st of each month we email you a clean statement of last month's earnings. Funds land in your nominated bank account on the 5th. You don't have to lift a finger.",
    },
    {
      icon: KeyRound,
      title: "Lock down your account",
      body: "Your invitation email had a temporary password. Open your portal and use 'Change password' to set one only you know. We'll never email you a password again.",
      cta: { href: "/partner", label: "Change password" },
    },
  ],
};
