/**
 * About page — narrative + values + simple stats.
 *
 * Static content. Lives at /about. Linked from the footer.
 */
import { Link } from "react-router-dom";
import { Sparkles, Ticket, ShieldCheck, Globe2, ArrowRight } from "lucide-react";

const PILLARS = [
  { icon: Ticket, title: "Built for organizers", text: "From a single VIP gala to a 5,000-seat festival — design your own seat layout, run instant QR check-in, and pay out to your bank with one click." },
  { icon: ShieldCheck, title: "No-scalper guarantees", text: "Atomic seat holds, verified organizer accounts, and human-reviewed listings keep your seats safe from bots and resellers." },
  { icon: Globe2, title: "Multi-currency, mobile-first", text: "Sell tickets in 25 currencies, install us as a Progressive Web App, and embed live events on your existing website with one snippet." },
];

export default function About() {
  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-10 sm:py-16" data-testid="about-page">
      <div className="text-xs uppercase tracking-[0.3em] mb-3" style={{ color: "var(--accent)" }}>About us</div>
      <h1 className="serif text-4xl sm:text-5xl lg:text-6xl leading-[1.02] mb-6">
        Live experiences,<br /> sold the human way.
      </h1>
      <p className="text-base sm:text-lg max-w-2xl mb-10" style={{ color: "var(--text-muted)" }}>
        Allsale Events is a tickets &amp; events platform built in Auckland for the next generation of organizers — the local bhajan night, the touring comic, the cinema reopening with a curated lineup. We obsess over two things: <strong>seat-level accuracy</strong> and <strong>organizer payout speed</strong>.
      </p>

      <div className="grid sm:grid-cols-3 gap-4 sm:gap-6 mb-16">
        {PILLARS.map(({ icon: Icon, title, text }) => (
          <div key={title} className="rounded-2xl border p-5" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
            <div className="w-10 h-10 rounded-xl flex items-center justify-center mb-3" style={{ background: "rgba(234, 88, 12, 0.1)", color: "var(--accent)" }}>
              <Icon className="w-5 h-5" />
            </div>
            <div className="font-medium mb-1.5">{title}</div>
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>{text}</p>
          </div>
        ))}
      </div>

      <div className="rounded-2xl border p-6 sm:p-10 mb-16" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
        <h2 className="serif text-3xl mb-3">Why we built it</h2>
        <p className="text-sm sm:text-base mb-3" style={{ color: "var(--text-muted)" }}>
          The first time we tried to run a sold-out community event, the existing platforms were either too expensive, too clunky, or both. Worse — we had no way to <em>actually see</em> which seats were taken in real-time.
        </p>
        <p className="text-sm sm:text-base mb-3" style={{ color: "var(--text-muted)" }}>
          So we built Allsale Events: <strong>10-minute atomic seat holds</strong>, custom layouts with aisle gaps and section colours, AI that reads your venue diagram and builds the seat map automatically, QR-scanner door-check-in on any phone, and Stripe payouts that hit organizers within 24 hours.
        </p>
        <p className="text-sm sm:text-base" style={{ color: "var(--text-muted)" }}>
          We're a small team and we read every contact-form message. If something can be better, tell us.
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <Link to="/events" className="btn-primary" data-testid="about-cta-events">
          Browse events <ArrowRight className="w-4 h-4" />
        </Link>
        <Link to="/contact" className="btn-ghost" data-testid="about-cta-contact">
          <Sparkles className="w-4 h-4" /> Get in touch
        </Link>
      </div>
    </div>
  );
}
