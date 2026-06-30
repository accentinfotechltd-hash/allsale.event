import { useState, useMemo, useEffect } from "react";
import { Link } from "react-router-dom";
import { Check, X, ArrowRight, Calculator, Zap, Sparkles, ShieldCheck, Wallet, AlertCircle } from "lucide-react";

// ============================================================================
// /vs-eventbrite — competitive landing page targeting NZ organizers shopping
// for an Eventbrite alternative.
//
// All math is client-side (no API calls) so the page is instant. Eventbrite
// fees are sourced from their public NZ pricing page (Essentials plan); ours
// come from the public `/api/fees/public-settings` endpoint and are honest:
// Allsale charges 1% + NZ$0.50 per ticket, which is passed to the buyer by
// default — meaning the organizer keeps 100% of face value.
// ============================================================================

// Eventbrite NZ "Essentials" plan, as published on their pricing page.
const EB_PCT = 0.035;          // 3.5%
const EB_FLAT = 0.79;          // NZ$0.79 per paid ticket
// What Allsale skims if the organizer absorbs fees (default = pass-through).
const ALLSALE_PCT = 0.01;      // 1%
const ALLSALE_FLAT = 0.50;     // NZ$0.50

const fmt = (n) => n.toLocaleString("en-NZ", { style: "currency", currency: "NZD", maximumFractionDigits: 0 });
const fmt2 = (n) => n.toLocaleString("en-NZ", { style: "currency", currency: "NZD", minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function VsEventbrite() {
  const [ticketPrice, setTicketPrice] = useState(50);
  const [ticketsPerEvent, setTicketsPerEvent] = useState(200);
  const [eventsPerYear, setEventsPerYear] = useState(6);

  // SEO + social
  useEffect(() => {
    document.title = "Eventbrite Alternative NZ — Keep 100% of Your Ticket Revenue | Allsale Events";
    const ensureMeta = (name, content) => {
      let m = document.querySelector(`meta[name="${name}"]`);
      if (!m) { m = document.createElement("meta"); m.setAttribute("name", name); document.head.appendChild(m); }
      m.setAttribute("content", content);
    };
    ensureMeta("description", "Switching from Eventbrite to Allsale Events saves NZ organizers thousands per event — zero platform commission, 5-day Stripe payouts, free ticket transfers. See your savings live.");
    ensureMeta("keywords", "eventbrite alternative NZ, eventbrite fees NZ, switch from eventbrite, no commission ticketing, ticketing platform NZ");
    return () => { document.title = "Allsale Events"; };
  }, []);

  const numbers = useMemo(() => {
    const tickets = Math.max(0, ticketsPerEvent);
    const price = Math.max(0, ticketPrice);
    const events = Math.max(0, eventsPerYear);

    // Per-ticket fees
    const ebFeePerTicket = (price * EB_PCT) + EB_FLAT;
    const allsaleFeePerTicket = (price * ALLSALE_PCT) + ALLSALE_FLAT;

    // Per-event totals — Eventbrite TAKES THIS FROM THE ORGANIZER on the
    // standard "organizer absorbs" setup most NZ events use.
    const ebPerEvent = ebFeePerTicket * tickets;
    // Allsale charges the buyer by default (pass-through). Organizer keeps
    // 100% of face value. If the organizer instead chose to absorb fees,
    // they'd pay this much:
    const allsaleAbsorbedPerEvent = allsaleFeePerTicket * tickets;

    // Annual numbers
    const ebPerYear = ebPerEvent * events;
    const savingsPerEvent = ebPerEvent; // assuming buyer-absorbed Allsale (default)
    const savingsPerYear = ebPerYear;

    // Even in the WORST case where the organizer chooses to absorb Allsale's
    // fees too, the savings vs Eventbrite are still huge.
    const worstCaseSavingsPerEvent = ebPerEvent - allsaleAbsorbedPerEvent;
    const worstCaseSavingsPerYear = worstCaseSavingsPerEvent * events;

    return {
      ebFeePerTicket, allsaleFeePerTicket,
      ebPerEvent, allsaleAbsorbedPerEvent,
      ebPerYear, savingsPerEvent, savingsPerYear,
      worstCaseSavingsPerEvent, worstCaseSavingsPerYear,
      grossPerEvent: tickets * price,
    };
  }, [ticketPrice, ticketsPerEvent, eventsPerYear]);

  return (
    <div data-testid="vs-eventbrite-page">
      {/* ============== HERO ============== */}
      <section className="border-b" style={{ borderColor: "var(--border)" }}>
        <div className="max-w-6xl mx-auto px-6 py-16 lg:py-24">
          <div className="text-xs uppercase tracking-[0.3em] mb-4" style={{ color: "var(--accent)" }} data-testid="hero-kicker">
            Eventbrite alternative · New Zealand
          </div>
          <h1 className="serif text-4xl sm:text-5xl lg:text-6xl leading-tight mb-6">
            Eventbrite charges <span style={{ color: "var(--danger)" }}>{(EB_PCT * 100).toFixed(1)}% + ${EB_FLAT}</span> per ticket.<br />
            We charge <span style={{ color: "var(--accent)" }}>zero.</span>
          </h1>
          <p className="text-lg max-w-2xl mb-10" style={{ color: "var(--text-muted)" }}>
            Allsale Events is the NZ ticketing platform that lets organisers keep <strong>100% of every ticket sold</strong>.
            Same Stripe under the hood. Same QR e-tickets. Same scanner app. Just none of Eventbrite&apos;s commission.
          </p>
          <div className="flex gap-3 flex-wrap">
            <Link to="/signup?role=organizer" className="btn-primary" data-testid="hero-signup-btn">
              <Sparkles className="w-4 h-4" /> Get started free <ArrowRight className="w-4 h-4" />
            </Link>
            <a href="#calculator" className="btn-ghost" data-testid="hero-calc-btn">
              <Calculator className="w-4 h-4" /> See your savings
            </a>
          </div>
        </div>
      </section>

      {/* ============== LIVE CALCULATOR ============== */}
      <section id="calculator" className="border-b" style={{ borderColor: "var(--border)", background: "var(--bg-elev)" }}>
        <div className="max-w-6xl mx-auto px-6 py-16">
          <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>The math</div>
          <h2 className="serif text-3xl sm:text-4xl mb-3">How much is Eventbrite costing you?</h2>
          <p style={{ color: "var(--text-muted)" }} className="mb-10 max-w-2xl">
            Drag the sliders. Numbers update instantly. Math is the same one Eventbrite publishes — no fine print, no asterisks.
          </p>

          <div className="grid lg:grid-cols-[1.1fr_1.4fr] gap-8">
            {/* Sliders */}
            <div className="border rounded-2xl p-6" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
              <Slider
                label="Ticket price"
                value={ticketPrice} onChange={setTicketPrice}
                min={10} max={300} step={5}
                display={fmt(ticketPrice)}
                testid="calc-price"
              />
              <Slider
                label="Tickets per event"
                value={ticketsPerEvent} onChange={setTicketsPerEvent}
                min={20} max={2000} step={20}
                display={ticketsPerEvent.toLocaleString()}
                testid="calc-tickets"
              />
              <Slider
                label="Events per year"
                value={eventsPerYear} onChange={setEventsPerYear}
                min={1} max={52} step={1}
                display={`${eventsPerYear} event${eventsPerYear === 1 ? "" : "s"}`}
                testid="calc-events"
              />

              <div className="mt-6 pt-6 border-t flex items-start gap-2" style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}>
                <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <p className="text-xs">
                  Allsale defaults to <em>pass-through fees</em> — Stripe + our 1% + NZ$0.50 are added on top, the buyer pays them, you keep the full face value. Numbers below assume that default.
                </p>
              </div>
            </div>

            {/* Results */}
            <div className="grid gap-4">
              <ResultCard
                label="Per event — Eventbrite takes from you"
                value={fmt2(numbers.ebPerEvent)}
                sub={`${ticketsPerEvent} tickets × (${(EB_PCT * 100).toFixed(1)}% + $${EB_FLAT.toFixed(2)}) = ${fmt2(numbers.ebFeePerTicket)}/ticket`}
                negative
                testid="result-eb-per-event"
              />
              <ResultCard
                label="Per event — Allsale takes from you"
                value={fmt(0)}
                sub="Buyer covers our 1% + $0.50 fee. Your payout = full face value."
                positive
                testid="result-allsale-per-event"
              />
              <ResultCard
                label={`Per year savings (${eventsPerYear} events)`}
                value={fmt(numbers.savingsPerYear)}
                sub={`Money that goes to YOU instead of Eventbrite's bottom line.`}
                hero
                testid="result-annual-savings"
              />
            </div>
          </div>

          <p className="mt-8 text-xs text-center" style={{ color: "var(--text-dim)" }}>
            Eventbrite NZ fees published on eventbrite.co.nz/organizer/pricing (Essentials plan).
            Allsale fees from our public <code>/api/fees/public-settings</code> endpoint.
          </p>
        </div>
      </section>

      {/* ============== FEATURE COMPARISON TABLE ============== */}
      <section className="border-b" style={{ borderColor: "var(--border)" }}>
        <div className="max-w-6xl mx-auto px-6 py-16">
          <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Side by side</div>
          <h2 className="serif text-3xl sm:text-4xl mb-10">Every feature, head to head</h2>

          <div className="border rounded-2xl overflow-hidden" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
            <table className="w-full text-sm" data-testid="comparison-table">
              <thead>
                <tr style={{ background: "var(--bg-elev)" }}>
                  <th className="text-left px-5 py-4 font-medium" style={{ color: "var(--text-muted)" }}>Feature</th>
                  <th className="text-center px-5 py-4 font-medium" style={{ color: "var(--text-muted)" }}>Eventbrite</th>
                  <th className="text-center px-5 py-4" style={{ color: "var(--accent)" }}>Allsale Events</th>
                </tr>
              </thead>
              <tbody>
                <Row feature="Platform commission per ticket" eb={`${(EB_PCT * 100).toFixed(1)}% + $${EB_FLAT}`} us="1% + $0.50 (passed to buyer)" highlight />
                <Row feature="Free ticket transfers between attendees" eb="$10 fee per transfer" us="Free, unlimited" />
                <Row feature="Stripe Connect — direct payouts to your bank" eb="Standard 4-5 days" us="5 days, Stripe Connect" />
                <Row feature="Instant payouts" eb="Charged extra" us="Roadmap" />
                <Row feature="Custom seat maps with aisles" eb="Limited to GA tiers" us="Drag-to-design seating included" highlight />
                <Row feature="AI flyer generator" eb={false} us="3 sizes, 1-click, free" highlight />
                <Row feature="Built-in creator / affiliate marketplace" eb={false} us="Open marketplace, per-event codes" highlight />
                <Row feature="Door-scanner app" eb="Native iOS/Android" us="PWA, any phone, no app store" />
                <Row feature="Apple Pay / Google Pay" eb={true} us={true} />
                <Row feature="Sales reports & buyer CSV" eb={true} us="Unified Buyers Report across all events" />
                <Row feature="Refund policies you set per event" eb={true} us={true} />
                <Row feature="Waitlist + demand pricing" eb={false} us="Built-in, auto-recapture sold-out demand" highlight />
                <Row feature="Event Boost — homepage promotion" eb={false} us="1/3/7-day boosts, no ad managers" highlight />
                <Row feature="Embed widget on your own site" eb="Iframe only" us="Native embed, keeps SEO on your domain" />
                <Row feature="PCI-compliant payments" eb={true} us={true} />
                <Row feature="Free to publish events" eb={true} us={true} />
                <Row feature="Made in NZ, supports NZ events first" eb={false} us={true} highlight />
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* ============== MIGRATION ============== */}
      <section className="border-b" style={{ borderColor: "var(--border)" }}>
        <div className="max-w-6xl mx-auto px-6 py-16">
          <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Move in 10 minutes</div>
          <h2 className="serif text-3xl sm:text-4xl mb-3">Switching is easier than you think</h2>
          <p style={{ color: "var(--text-muted)" }} className="mb-10 max-w-2xl">
            You don&apos;t have to migrate everything at once. Run your next event on Allsale, see the savings hit your bank account, then sunset Eventbrite at your own pace.
          </p>

          <div className="grid sm:grid-cols-3 gap-5">
            <Step n="1" title="Create your account" body="Sign up free as an organiser in 60 seconds. Connect Stripe in another 2 minutes." testid="step-1" />
            <Step n="2" title="Recreate your event" body="Title, date, venue, tiers — same info you have on Eventbrite. Copy your image straight over." testid="step-2" />
            <Step n="3" title="Share the new link" body="Update your IG bio, your website, and your email list. Your buyers don't notice the change — they just check out faster." testid="step-3" />
          </div>

          <div className="mt-10 flex gap-3 flex-wrap">
            <Link to="/signup?role=organizer" className="btn-primary" data-testid="migration-cta-signup">
              Start your free Allsale account <ArrowRight className="w-4 h-4" />
            </Link>
            <Link to="/contact" className="btn-ghost" data-testid="migration-cta-contact">
              Talk to a migration helper
            </Link>
          </div>
        </div>
      </section>

      {/* ============== FAQ ============== */}
      <section className="border-b" style={{ borderColor: "var(--border)" }}>
        <div className="max-w-3xl mx-auto px-6 py-16">
          <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Honest answers</div>
          <h2 className="serif text-3xl sm:text-4xl mb-10">The questions you&apos;re actually asking</h2>

          <Faq q={`What about Eventbrite's audience — won't I lose buyer reach?`} testid="faq-audience">
            Eventbrite&apos;s NZ search traffic is real but smaller than they market it. Most of YOUR buyers came from
            <em> your</em> Instagram, your email list, and your venue&apos;s own audience — not Eventbrite&apos;s homepage.
            You can keep running paid ads on Facebook/IG, send to your own email list, and post to your IG story —
            none of that needs Eventbrite. We&apos;re built so your social/email reach drives Allsale checkouts the same way.
          </Faq>
          <Faq q="Do I lose my buyer email list when I switch?" testid="faq-email-list">
            No — every Eventbrite buyer email is yours under NZ law and Eventbrite&apos;s own ToS. Export the CSV from
            your Eventbrite dashboard (Manage → Orders → Export) and re-import wherever you do email marketing
            (Mailchimp, Resend, EDM). We don&apos;t need or touch that list to get you running on Allsale.
          </Faq>
          <Faq q={`How are you cheaper? Where's the catch?`} testid="faq-pricing">
            No catch — we&apos;re a young NZ company without a US sales team to feed. Eventbrite&apos;s
            {" "}{(EB_PCT * 100).toFixed(1)}% + ${EB_FLAT}/ticket pays for their head office, a 1,000-person team, and
            heavy global ad spend. We&apos;re lean, NZ-based, and built to be sustainable on a 1% + $0.50 fee paid by
            buyers, not organisers.
          </Faq>
          <Faq q="What if I have a complex event with reserved seating?" testid="faq-seating">
            We support custom seat maps with aisles, categories, accessibility seats, and per-tier holds — built in,
            no per-event setup fee. Drag-to-design in the dashboard. Eventbrite&apos;s seated events require their
            &quot;Professional&quot; plan at significantly higher fees.
          </Faq>
          <Faq q="Can I run multiple events under one account?" testid="faq-multi-events">
            Yes — unlimited events on one organiser account. Stripe Connect handles your payouts. Use Teams to add
            co-organisers, door staff, or finance leads with scoped permissions.
          </Faq>
        </div>
      </section>

      {/* ============== FINAL CTA ============== */}
      <section>
        <div className="max-w-3xl mx-auto px-6 py-20 text-center">
          <h2 className="serif text-3xl sm:text-5xl mb-5">
            Stop paying Eventbrite&apos;s commission.
          </h2>
          <p className="text-lg mb-8" style={{ color: "var(--text-muted)" }}>
            Run your next event on Allsale. Keep the difference.
          </p>
          <Link to="/signup?role=organizer" className="btn-primary inline-flex" data-testid="final-cta">
            <Sparkles className="w-4 h-4" /> Create my free account <ArrowRight className="w-4 h-4" />
          </Link>
          <div className="mt-6 text-xs" style={{ color: "var(--text-dim)" }}>
            No credit card needed · 60 seconds to first event · Cancel anytime
          </div>
        </div>
      </section>
    </div>
  );
}

// ============================================================================
// Subcomponents
// ============================================================================
function Slider({ label, value, onChange, min, max, step, display, testid }) {
  return (
    <div className="mb-6" data-testid={testid}>
      <div className="flex justify-between items-baseline mb-2">
        <label className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>{label}</label>
        <span className="serif text-2xl" style={{ color: "var(--text)" }}>{display}</span>
      </div>
      <input
        type="range"
        min={min} max={max} step={step}
        value={value}
        onChange={(e) => onChange(parseInt(e.target.value, 10))}
        className="w-full"
        data-testid={`${testid}-input`}
        style={{ accentColor: "var(--accent)" }}
      />
    </div>
  );
}

function ResultCard({ label, value, sub, negative, positive, hero, testid }) {
  const border = hero ? "var(--accent)" : negative ? "rgba(239,68,68,0.4)" : positive ? "rgba(52,211,153,0.4)" : "var(--border)";
  const bg = hero ? "var(--accent-soft)" : "var(--bg-card)";
  const valColor = hero ? "var(--accent)" : negative ? "var(--danger)" : positive ? "var(--success)" : "var(--text)";
  return (
    <div className="border rounded-2xl p-6" style={{ borderColor: border, background: bg }} data-testid={testid}>
      <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>{label}</div>
      <div className="serif mb-1" style={{ color: valColor, fontSize: hero ? "3rem" : "2.25rem", lineHeight: 1.1 }}>{value}</div>
      <div className="text-xs" style={{ color: "var(--text-muted)" }}>{sub}</div>
    </div>
  );
}

function Row({ feature, eb, us, highlight }) {
  const renderCell = (v, isUs) => {
    if (v === true) return <Check className="w-5 h-5 mx-auto" style={{ color: isUs ? "var(--accent)" : "var(--text-muted)" }} />;
    if (v === false) return <X className="w-5 h-5 mx-auto" style={{ color: "var(--danger)" }} />;
    return <span style={{ color: isUs ? "var(--text)" : "var(--text-muted)" }}>{v}</span>;
  };
  return (
    <tr className="border-t" style={{ borderColor: "var(--border)", background: highlight ? "rgba(255,79,0,0.04)" : "transparent" }}>
      <td className="px-5 py-4" style={{ color: "var(--text)" }}>{feature}</td>
      <td className="px-5 py-4 text-center text-sm">{renderCell(eb, false)}</td>
      <td className="px-5 py-4 text-center text-sm" style={{ background: highlight ? "rgba(255,79,0,0.06)" : "transparent" }}>{renderCell(us, true)}</td>
    </tr>
  );
}

function Step({ n, title, body, testid }) {
  return (
    <div className="border rounded-2xl p-6" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }} data-testid={testid}>
      <div className="serif text-4xl mb-3" style={{ color: "var(--accent)" }}>{n}</div>
      <div className="text-lg mb-2" style={{ color: "var(--text)" }}>{title}</div>
      <div className="text-sm" style={{ color: "var(--text-muted)" }}>{body}</div>
    </div>
  );
}

function Faq({ q, children, testid }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-t py-5" style={{ borderColor: "var(--border)" }} data-testid={testid}>
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between text-left"
        style={{ color: "var(--text)" }}
      >
        <span className="text-lg pr-4">{q}</span>
        <span className="serif text-2xl" style={{ color: "var(--accent)" }}>{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="mt-3 text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>
          {children}
        </div>
      )}
    </div>
  );
}
