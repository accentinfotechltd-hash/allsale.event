/**
 * About page — narrative + values + simple stats.
 *
 * Static content. Lives at /about. Linked from the footer.
 */
import { Link } from "react-router-dom";
import { Sparkles, Ticket, ShieldCheck, Globe2, ArrowRight } from "lucide-react";
import useSiteSettings from "@/lib/useSiteSettings";

const PILLARS = [
  { icon: Ticket, title: "Built for organizers", text: "From a single VIP gala to a 5,000-seat festival — design your own seat layout, run instant QR check-in, and pay out to your bank with one click." },
  { icon: ShieldCheck, title: "No-scalper guarantees", text: "Atomic seat holds, verified organizer accounts, and human-reviewed listings keep your seats safe from bots and resellers." },
  { icon: Globe2, title: "Multi-currency, mobile-first", text: "Sell tickets in 25 currencies, install us as a Progressive Web App, and embed live events on your existing website with one snippet." },
];

export default function About() {
  const settings = useSiteSettings();
  const about = settings.about || {};
  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-10 sm:py-16" data-testid="about-page">
      <div className="text-xs uppercase tracking-[0.3em] mb-3" style={{ color: "var(--accent)" }}>{about.hero_eyebrow || "About us"}</div>
      <h1 className="serif text-4xl sm:text-5xl lg:text-6xl leading-[1.02] mb-6 whitespace-pre-line">
        {about.hero_title}
      </h1>
      <p className="text-base sm:text-lg max-w-2xl mb-10 whitespace-pre-line" style={{ color: "var(--text-muted)" }}>
        {about.hero_subtitle}
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
        <h2 className="serif text-3xl mb-3">{about.story_title}</h2>
        <p className="text-sm sm:text-base whitespace-pre-line" style={{ color: "var(--text-muted)" }}>
          {about.story_body}
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
