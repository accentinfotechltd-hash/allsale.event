import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Search, Ticket, ScanLine, Heart,
  PlusCircle, BarChart3, Megaphone, Wallet,
  Users, DollarSign, MailPlus, KeyRound,
  X as XIcon, ChevronLeft, ChevronRight, Sparkles,
} from "lucide-react";
import { useAuth } from "@/lib/auth";

/**
 * First-login walkthrough. Shown once per logged-in user, role-aware.
 *
 *   • Trigger: `user` is loaded AND `localStorage[welcomeSeen_<role>]` is unset.
 *   • Persistence: a checkbox lets the user dismiss permanently. Skipping the
 *     modal also marks it as seen so it doesn't reappear on every page load.
 *   • Reopen path: the `/help` page exposes a "Show me the welcome tour again"
 *     link that wipes the flag and re-renders the modal.
 *
 * Slides are tailored per role (attendee / organizer / partner / admin).
 * Keep the copy short — no walls of text.
 */
export default function WelcomeModal() {
  const { user } = useAuth();
  const role = user?.role || (user?.is_organizer ? "organizer" : "attendee");
  const flagKey = `welcomeSeen_${role}`;

  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  const [dontShowAgain, setDontShowAgain] = useState(true);

  useEffect(() => {
    if (!user) return;
    // Tiny defer so the page-load animations finish before the modal lands.
    const seen = localStorage.getItem(flagKey);
    if (!seen) {
      const t = setTimeout(() => setOpen(true), 600);
      return () => clearTimeout(t);
    }
  }, [user, flagKey]);

  // Re-open hook for the /help page button.
  useEffect(() => {
    const handler = () => { setIdx(0); setOpen(true); };
    window.addEventListener("allsale:show-welcome", handler);
    return () => window.removeEventListener("allsale:show-welcome", handler);
  }, []);

  const slides = useMemo(() => SLIDES_BY_ROLE[role] || SLIDES_BY_ROLE.attendee, [role]);

  if (!open || !user) return null;

  const slide = slides[idx];
  const isLast = idx === slides.length - 1;

  const close = () => {
    if (dontShowAgain) localStorage.setItem(flagKey, "1");
    setOpen(false);
  };

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6"
      style={{ background: "rgba(0,0,0,0.72)", backdropFilter: "blur(6px)" }}
      data-testid="welcome-modal"
      onClick={(e) => { if (e.target === e.currentTarget) close(); }}
    >
      <div
        className="relative w-full max-w-xl rounded-2xl border overflow-hidden"
        style={{ background: "var(--bg, #0f0f12)", borderColor: "var(--border)" }}
      >
        <button
          onClick={close}
          className="absolute right-3 top-3 z-10 p-1.5 rounded-full hover:bg-white/10 transition"
          style={{ color: "var(--text-dim)" }}
          aria-label="Close"
          data-testid="welcome-modal-close-btn"
        >
          <XIcon size={18} />
        </button>

        {/* Header strip */}
        <div className="px-6 pt-6 pb-4 border-b" style={{ borderColor: "var(--border)" }}>
          <div className="flex items-center gap-2 text-xs uppercase tracking-widest" style={{ color: "var(--accent)" }}>
            <Sparkles size={13} /> Welcome to Allsale Events
          </div>
          <h2 className="font-serif mt-2" style={{ fontSize: "1.5rem", color: "var(--text)" }}>
            {ROLE_TITLE[role] || ROLE_TITLE.attendee}
          </h2>
        </div>

        {/* Slide body */}
        <div className="px-6 py-8 min-h-[260px]" data-testid={`welcome-slide-${idx}`}>
          <div
            className="w-12 h-12 rounded-xl flex items-center justify-center mb-4"
            style={{ background: "rgba(240,138,42,0.12)", color: "var(--accent)" }}
          >
            <slide.icon size={22} />
          </div>
          <h3 className="font-serif text-lg mb-2" style={{ color: "var(--text)" }}>{slide.title}</h3>
          <p className="text-sm leading-relaxed" style={{ color: "var(--text-dim)" }}>{slide.body}</p>
          {slide.cta && (
            <Link
              to={slide.cta.href}
              onClick={close}
              className="inline-flex items-center gap-1 text-sm mt-4 underline"
              style={{ color: "var(--accent)" }}
              data-testid={`welcome-slide-cta-${idx}`}
            >
              {slide.cta.label} <ChevronRight size={14} />
            </Link>
          )}
        </div>

        {/* Footer: dots, prev/next, dont-show */}
        <div className="px-6 py-4 border-t flex flex-col gap-3" style={{ borderColor: "var(--border)" }}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              {slides.map((_, i) => (
                <button
                  key={i}
                  onClick={() => setIdx(i)}
                  className="w-2 h-2 rounded-full transition"
                  style={{ background: i === idx ? "var(--accent)" : "var(--border)" }}
                  aria-label={`Go to slide ${i + 1}`}
                  data-testid={`welcome-dot-${i}`}
                />
              ))}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setIdx((i) => Math.max(0, i - 1))}
                disabled={idx === 0}
                className="btn-ghost text-xs inline-flex items-center gap-1 disabled:opacity-30"
                data-testid="welcome-prev-btn"
              >
                <ChevronLeft size={14} /> Back
              </button>
              {isLast ? (
                <button
                  onClick={close}
                  className="btn-primary text-xs"
                  data-testid="welcome-done-btn"
                >
                  Got it
                </button>
              ) : (
                <button
                  onClick={() => setIdx((i) => Math.min(slides.length - 1, i + 1))}
                  className="btn-primary text-xs inline-flex items-center gap-1"
                  data-testid="welcome-next-btn"
                >
                  Next <ChevronRight size={14} />
                </button>
              )}
            </div>
          </div>
          <label className="flex items-center gap-2 text-xs cursor-pointer" style={{ color: "var(--text-dim)" }}>
            <input
              type="checkbox"
              checked={dontShowAgain}
              onChange={(e) => setDontShowAgain(e.target.checked)}
              style={{ width: "14px", height: "14px", flexShrink: 0, accentColor: "var(--accent)" }}
              data-testid="welcome-dont-show-checkbox"
            />
            Don&apos;t show this again
          </label>
        </div>
      </div>
    </div>
  );
}

const ROLE_TITLE = {
  attendee: "Find your next night out",
  organizer: "Get your event online in minutes",
  partner: "Refer events, earn commission",
  admin: "Run the platform",
};

const SLIDES_BY_ROLE = {
  attendee: [
    {
      icon: Search,
      title: "1. Discover events",
      body: "Browse upcoming gigs, theatre, sports and conferences. Filter by city, date or category — or hit Trending to see what's selling fast.",
      cta: { href: "/events", label: "Browse events" },
    },
    {
      icon: Ticket,
      title: "2. Book in under a minute",
      body: "Pick your tier or seat, apply a promo code if you have one, and pay with card or Apple/Google Pay. Your e-ticket lands in your inbox instantly.",
    },
    {
      icon: ScanLine,
      title: "3. Walk straight in",
      body: "At the door, show the QR code from your email or your Profile page. Door staff scan and you're in — no printing required.",
      cta: { href: "/profile", label: "View my tickets" },
    },
    {
      icon: Heart,
      title: "4. Never miss out",
      body: "Save favourites, follow organisers, and turn on email alerts. We'll quietly nudge you when something matches your taste.",
    },
  ],
  organizer: [
    {
      icon: PlusCircle,
      title: "1. Create your event",
      body: "Click 'Create event' in your dashboard. Add the cover photo, optional 9:16 poster, ticket tiers and capacity. You can save as draft and publish later.",
      cta: { href: "/organizer/new", label: "Create event" },
    },
    {
      icon: BarChart3,
      title: "2. Track sales live",
      body: "Your organiser dashboard shows live sales, scan-ins, demographics and a P&L. Filter by event, tier or date range — export to CSV anytime.",
      cta: { href: "/organizer", label: "Open dashboard" },
    },
    {
      icon: Megaphone,
      title: "3. Promote in one click",
      body: "Open any event's Share page to download Instagram-ready flyers (square / story / landscape), generate AI headlines, and share to socials directly.",
    },
    {
      icon: ScanLine,
      title: "4. Scan at the door",
      body: "On show day, log in to the door scanner app from any phone. Scan QR tickets, see real-time check-in counts, and resolve duplicates instantly.",
      cta: { href: "/scan", label: "Open scanner" },
    },
    {
      icon: Wallet,
      title: "5. Get paid",
      body: "Payouts run automatically after each event clears refund windows. Add your bank details in Payouts and we'll handle the rest.",
      cta: { href: "/organizer/payouts", label: "Set up payouts" },
    },
  ],
  partner: [
    {
      icon: Users,
      title: "1. Your partner home",
      body: "This is your private portal — see your commission rate, organisers you've brought on board, and your unpaid balance at a glance.",
      cta: { href: "/partner", label: "Open my portal" },
    },
    {
      icon: DollarSign,
      title: "2. How you earn",
      body: "Every paid booking on an organiser linked to you credits a commission to your ledger. Earnings appear within minutes of the booking clearing.",
    },
    {
      icon: MailPlus,
      title: "3. Monthly statements",
      body: "On the 1st of each month we email you a statement of last month's earnings. Payouts land in your nominated account on the 5th.",
    },
    {
      icon: KeyRound,
      title: "4. Lock down your account",
      body: "Your invitation email had a temporary password. Pop into your portal and use 'Change password' to set one only you know.",
      cta: { href: "/partner", label: "Change password" },
    },
  ],
  admin: [
    {
      icon: BarChart3,
      title: "1. Admin command centre",
      body: "Live P&L, pending event approvals, ticket protection metrics and chat-with-organisers — all on the admin dashboard hero strip.",
      cta: { href: "/admin", label: "Open admin" },
    },
    {
      icon: Users,
      title: "2. Manage partners",
      body: "Spin up marketing partners, set their commission %, attach organisers and trigger monthly statements/payouts from the Partners tab.",
    },
    {
      icon: Megaphone,
      title: "3. Edit the public site",
      body: "Blog posts, featured events and platform-wide announcements live under the Content tabs. Everything is DB-driven — changes are live instantly.",
    },
  ],
};
