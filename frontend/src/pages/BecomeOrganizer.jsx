/**
 * BecomeOrganizer — friendly upgrade page for attendees who want to host events.
 *
 * One-click upgrade. Shows what they get, what commission looks like, then flips
 * role=organizer in the DB and redirects them to /organizer (or ?redirect=...).
 */
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Sparkles, BarChart3, ScanLine, Wallet, ArrowRight, CheckCircle2 } from "lucide-react";

const PERKS = [
  { icon: BarChart3, title: "Real-time analytics", body: "Track sales, attribution, and revenue by tier across every event." },
  { icon: ScanLine, title: "QR check-in scanner", body: "Built-in door scanner with idempotent check-ins and attendance CSV exports." },
  { icon: Wallet, title: "Transparent payouts", body: "8% platform commission + $0.50 per ticket. Net balance visible in real time." },
  { icon: Sparkles, title: "Power tools", body: "Custom seat maps, discount codes, surge pricing, and waitlists out of the box." },
];

export default function BecomeOrganizer() {
  const { user, setUser } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const redirect = params.get("redirect") || "/organizer";
  const [agreed, setAgreed] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  if (!user) {
    nav(`/login?redirect=${encodeURIComponent(`/become-organizer?redirect=${redirect}`)}`);
    return null;
  }

  // Already an organizer/admin? Bounce them to the dashboard directly.
  if (user.role === "organizer" || user.role === "admin") {
    return (
      <div className="max-w-2xl mx-auto px-6 py-24 text-center">
        <CheckCircle2 className="w-12 h-12 mx-auto mb-4" style={{ color: "var(--success)" }} />
        <h1 className="serif text-4xl mb-2">You're already an organizer</h1>
        <p className="mb-8" style={{ color: "var(--text-muted)" }}>Head to your dashboard to create your next event.</p>
        <Link to="/organizer" className="btn-primary" data-testid="goto-dashboard-btn">
          Open dashboard <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    );
  }

  const upgrade = async () => {
    setSubmitting(true);
    try {
      const { data } = await api.post("/auth/become-organizer");
      setUser((u) => ({ ...u, ...data, role: data.role || "organizer" }));
      toast.success("Welcome aboard — you're now an organizer!");
      nav(redirect, { replace: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not upgrade — please try again.");
    } finally { setSubmitting(false); }
  };

  return (
    <div className="max-w-4xl mx-auto px-6 py-16">
      <div className="text-xs uppercase tracking-[0.3em] mb-3" style={{ color: "var(--accent)" }}>For creators</div>
      <h1 className="serif text-5xl mb-4" data-testid="become-organizer-headline">Host events on Allsale Events</h1>
      <p className="text-lg mb-12 max-w-2xl" style={{ color: "var(--text-muted)" }}>
        Switch on the organizer tools. Free to set up — we only charge a small commission when you sell a ticket.
      </p>

      <div className="grid sm:grid-cols-2 gap-5 mb-12">
        {PERKS.map(({ icon: Icon, title, body }) => (
          <div key={title} className="rounded-2xl p-6" style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }} data-testid={`perk-${title.split(' ')[0].toLowerCase()}`}>
            <Icon className="w-5 h-5 mb-3" style={{ color: "var(--accent)" }} />
            <div className="font-medium mb-1.5">{title}</div>
            <div className="text-sm" style={{ color: "var(--text-muted)" }}>{body}</div>
          </div>
        ))}
      </div>

      <div className="rounded-2xl p-6 mb-8" style={{ background: "var(--bg-elev)", border: "1px solid var(--border)" }}>
        <div className="text-xs uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>What changes for you</div>
        <ul className="space-y-2 text-sm" style={{ color: "var(--text-muted)" }}>
          <li>• Your account keeps everything you've booked — no data loss.</li>
          <li>• You get access to <code style={{ color: "var(--text)" }}>/organizer</code>: dashboards, analytics, payouts, discount codes.</li>
          <li>• 8% platform commission + $0.50 per ticket sold. Net payouts processed weekly on request.</li>
          <li>• You can request payouts whenever your balance ≥ $0.</li>
        </ul>
      </div>

      <label className="flex items-start gap-3 mb-6 cursor-pointer">
        <input
          type="checkbox" checked={agreed}
          onChange={(e) => setAgreed(e.target.checked)}
          className="mt-1"
          data-testid="agree-terms-checkbox"
        />
        <span className="text-sm" style={{ color: "var(--text-muted)" }}>
          I understand the commission structure and agree to Allsale Events' <span style={{ color: "var(--accent)" }}>Organizer Terms</span> (no spam, no fraud, valid events only).
        </span>
      </label>

      <div className="flex flex-wrap gap-3">
        <button
          onClick={upgrade}
          disabled={!agreed || submitting}
          className="btn-primary"
          data-testid="confirm-upgrade-btn"
        >
          {submitting ? "Upgrading…" : "Become an organizer"} <ArrowRight className="w-4 h-4" />
        </button>
        <Link to="/" className="btn-ghost" data-testid="cancel-upgrade-btn">
          Not now
        </Link>
      </div>
    </div>
  );
}
