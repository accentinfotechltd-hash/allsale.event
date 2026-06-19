import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Ticket, ScanLine, QrCode, ShieldCheck, Zap, Smartphone, BarChart3,
  Megaphone, Sparkles, Layers, Globe, DollarSign, Heart, Users, Download, Printer,
} from "lucide-react";

/**
 * A printable one-pager that doubles as a sharable web flyer.
 *
 *   • At `/flyer`, the design fills the viewport and reads beautifully on phones.
 *   • Hitting Ctrl/Cmd+P renders a clean PDF (print-only CSS removes nav/footer
 *     and forces a single A4 page with a teal→orange gradient backdrop).
 *   • Each "for X" section is a self-contained card so it can be screenshotted
 *     individually for Instagram/WhatsApp without losing context.
 */
export default function Flyer() {
  const [downloading, setDownloading] = useState(false);

  const handlePrint = () => {
    window.print();
  };

  const handleDownload = async () => {
    setDownloading(true);
    try {
      // The browser's "print to PDF" is the most reliable cross-browser export.
      // We trigger it here and let the user pick "Save as PDF" in the dialog.
      window.print();
    } finally {
      // Small delay so the user sees the spinner pulse, then reset
      setTimeout(() => setDownloading(false), 800);
    }
  };

  return (
    <div className="flyer-root" data-testid="flyer-page">
      {/* Floating actions — hidden in print */}
      <div className="flyer-actions print:hidden">
        <button
          onClick={handlePrint}
          data-testid="flyer-print"
          className="px-4 py-2 rounded-full text-sm font-medium inline-flex items-center gap-2 shadow-lg"
          style={{ background: "#FFFFFF", color: "#0F2A3A" }}
        >
          <Printer size={14} /> Print
        </button>
        <button
          onClick={handleDownload}
          disabled={downloading}
          data-testid="flyer-download"
          className="px-4 py-2 rounded-full text-sm font-medium inline-flex items-center gap-2 shadow-lg disabled:opacity-60"
          style={{ background: "var(--accent)", color: "#000" }}
        >
          <Download size={14} /> {downloading ? "Preparing…" : "Save as PDF"}
        </button>
      </div>

      <section className="flyer-page" id="flyer-print-area" data-testid="flyer-printable">
        {/* Header */}
        <header className="flyer-header">
          <div className="flyer-eyebrow">EVENT TICKETING · NEW ZEALAND</div>
          <h1 className="flyer-title">Allsale Events</h1>
          <p className="flyer-tagline">
            Sell tickets. Scan at the door. Pay creators. <br />
            <strong>No platform tax. No app store.</strong>
          </p>
        </header>

        {/* Three audience tracks */}
        <div className="flyer-grid">
          <Audience
            tone="orange"
            icon={<Megaphone size={20} />}
            heading="For Organisers"
            tagline="List your event in 90 seconds."
            bullets={[
              { icon: <Ticket size={14} />, text: "Multi-tier ticketing + custom seat maps with aisles" },
              { icon: <DollarSign size={14} />, text: "Stripe Connect payouts 5 days after each event" },
              { icon: <BarChart3 size={14} />, text: "Live dashboard, refund policies, dynamic pricing" },
              { icon: <Layers size={14} />, text: "Discount codes, affiliate links, revenue splits" },
              { icon: <Globe size={14} />, text: "Embeddable widget for your own website" },
            ]}
          />

          <Audience
            tone="teal"
            icon={<Heart size={20} />}
            heading="For Fans"
            tagline="The cleanest checkout in NZ."
            bullets={[
              { icon: <Zap size={14} />, text: "30-second checkout, mobile-first, no signup needed" },
              { icon: <QrCode size={14} />, text: "QR e-tickets delivered instantly to your inbox" },
              { icon: <Smartphone size={14} />, text: "Apple/Google Wallet pass coming soon" },
              { icon: <ShieldCheck size={14} />, text: "Self-serve refunds + ticket transfers" },
              { icon: <Users size={14} />, text: "Follow organisers, get weekly digests" },
            ]}
          />

          <Audience
            tone="black"
            icon={<Sparkles size={20} />}
            heading="For Creators"
            tagline="Earn promoting events you love."
            bullets={[
              { icon: <DollarSign size={14} />, text: "5% default commission on every ticket you sell" },
              { icon: <Megaphone size={14} />, text: "Self-join open campaigns in one click" },
              { icon: <BarChart3 size={14} />, text: "Live dashboard of clicks, conversions, earnings" },
              { icon: <ShieldCheck size={14} />, text: "Monthly Stripe payouts ($50 minimum)" },
              { icon: <Globe size={14} />, text: "Public profile in the Creator Marketplace" },
            ]}
          />
        </div>

        {/* Bonus features ribbon */}
        <div className="flyer-ribbon">
          <div className="flyer-ribbon-title">All this. None of the bloat.</div>
          <div className="flyer-ribbon-grid">
            <Pill icon={<ScanLine size={12} />} label="Door-scanner PWA" />
            <Pill icon={<QrCode size={12} />} label="QR e-tickets" />
            <Pill icon={<Ticket size={12} />} label="Seat maps + aisles" />
            <Pill icon={<DollarSign size={12} />} label="Stripe Connect" />
            <Pill icon={<Layers size={12} />} label="Revenue splits" />
            <Pill icon={<Megaphone size={12} />} label="Affiliate marketplace" />
            <Pill icon={<Heart size={12} />} label="Follow organisers" />
            <Pill icon={<Smartphone size={12} />} label="PWA install" />
            <Pill icon={<Globe size={12} />} label="Embed widget" />
            <Pill icon={<ShieldCheck size={12} />} label="Self-serve refunds" />
            <Pill icon={<BarChart3 size={12} />} label="Live analytics" />
            <Pill icon={<Sparkles size={12} />} label="Auto FIRST50 promo" />
          </div>
        </div>

        {/* Footer / CTA */}
        <footer className="flyer-footer">
          <div className="flyer-cta-left">
            <div className="flyer-cta-eyebrow">GET STARTED</div>
            <div className="flyer-cta-url">www.allsale.events</div>
            <div className="flyer-cta-sub">Free to list. Buyers cover the service fee.</div>
          </div>
          <div className="flyer-cta-right">
            <div className="flyer-qr">
              <img
                src="https://api.qrserver.com/v1/create-qr-code/?size=180x180&margin=0&color=0F2A3A&bgcolor=ffffff&data=https%3A%2F%2Fwww.allsale.events"
                alt="QR code to allsale.events"
                width={120}
                height={120}
                data-testid="flyer-qr"
              />
              <div className="flyer-qr-caption">Scan to visit</div>
            </div>
          </div>
        </footer>
      </section>

      {/* Hidden share helper (only on web view) */}
      <div className="flyer-meta print:hidden" data-testid="flyer-meta">
        <Link to="/" className="flyer-back">← Back to Allsale Events</Link>
        <p>Use Ctrl/Cmd + P to save this flyer as a PDF, or take a screenshot to share on Instagram, WhatsApp, or print on A4.</p>
      </div>

      {/* All flyer-specific styles live here, scoped to .flyer-root so they
          never bleed into the rest of the app */}
      <style>{flyerCss}</style>
    </div>
  );
}

function Audience({ tone, icon, heading, tagline, bullets }) {
  return (
    <div className={`flyer-card flyer-card--${tone}`}>
      <div className="flyer-card-head">
        <div className="flyer-card-icon">{icon}</div>
        <div>
          <div className="flyer-card-heading">{heading}</div>
          <div className="flyer-card-tagline">{tagline}</div>
        </div>
      </div>
      <ul className="flyer-card-list">
        {bullets.map((b, i) => (
          <li key={i}>
            <span className="flyer-bullet-icon">{b.icon}</span>
            <span>{b.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Pill({ icon, label }) {
  return (
    <span className="flyer-pill">
      {icon}
      {label}
    </span>
  );
}

const flyerCss = `
.flyer-root {
  min-height: 100vh;
  background: linear-gradient(135deg, #0F2A3A 0%, #1B7A9E 55%, #F08A2A 100%);
  padding: 32px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  font-family: 'General Sans', system-ui, sans-serif;
  color: #0F2A3A;
}
.flyer-actions {
  position: fixed;
  top: 16px;
  right: 16px;
  display: flex;
  gap: 8px;
  z-index: 10;
}
.flyer-page {
  width: 100%;
  max-width: 820px;
  background: #FFFFFF;
  border-radius: 18px;
  padding: 36px 32px;
  box-shadow: 0 24px 60px rgba(15, 42, 58, 0.25);
  position: relative;
  overflow: hidden;
}
.flyer-page::before {
  content: "";
  position: absolute;
  top: -120px;
  right: -120px;
  width: 280px;
  height: 280px;
  background: radial-gradient(circle, rgba(240,138,42,0.18) 0%, transparent 70%);
  border-radius: 50%;
}
.flyer-page::after {
  content: "";
  position: absolute;
  bottom: -160px;
  left: -100px;
  width: 320px;
  height: 320px;
  background: radial-gradient(circle, rgba(27,122,158,0.16) 0%, transparent 70%);
  border-radius: 50%;
}
.flyer-header { text-align: center; margin-bottom: 28px; position: relative; }
.flyer-eyebrow { font-size: 11px; letter-spacing: 0.18em; color: #F08A2A; font-weight: 600; margin-bottom: 8px; }
.flyer-title { font-family: 'Instrument Serif', serif; font-size: 60px; font-weight: 400; line-height: 1; margin: 0 0 12px; color: #0F2A3A; }
.flyer-tagline { font-size: 17px; line-height: 1.4; color: #4A5A6B; margin: 0; }
.flyer-tagline strong { color: #0F2A3A; }
.flyer-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin: 28px 0 24px;
  position: relative;
}
.flyer-card {
  border-radius: 14px;
  padding: 18px 16px;
  border: 1.5px solid rgba(0,0,0,0.06);
  display: flex;
  flex-direction: column;
}
.flyer-card--orange { background: linear-gradient(145deg, #FFF6EC 0%, #FFE4C7 100%); border-color: rgba(240,138,42,0.4); }
.flyer-card--teal { background: linear-gradient(145deg, #EAF6FB 0%, #C9E5EF 100%); border-color: rgba(27,122,158,0.4); }
.flyer-card--black { background: #0F2A3A; color: #FFFFFF; border-color: rgba(255,255,255,0.15); }
.flyer-card--black .flyer-card-heading { color: #FFFFFF; }
.flyer-card--black .flyer-card-tagline { color: rgba(255,255,255,0.7); }
.flyer-card--black .flyer-card-list li { color: rgba(255,255,255,0.85); }
.flyer-card--black .flyer-bullet-icon { color: #F08A2A; }
.flyer-card-head { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 12px; }
.flyer-card-icon {
  width: 36px; height: 36px; border-radius: 10px;
  background: #0F2A3A;
  color: #FFFFFF;
  display: grid; place-items: center;
  flex-shrink: 0;
}
.flyer-card--orange .flyer-card-icon { background: #F08A2A; }
.flyer-card--teal .flyer-card-icon { background: #1B7A9E; }
.flyer-card--black .flyer-card-icon { background: #F08A2A; color: #0F2A3A; }
.flyer-card-heading { font-family: 'Instrument Serif', serif; font-size: 22px; line-height: 1.05; }
.flyer-card-tagline { font-size: 12px; opacity: 0.75; margin-top: 2px; }
.flyer-card-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }
.flyer-card-list li { display: flex; gap: 8px; align-items: flex-start; font-size: 13px; line-height: 1.4; }
.flyer-bullet-icon { color: #F08A2A; flex-shrink: 0; margin-top: 2px; }

.flyer-ribbon {
  background: #F1F4F8;
  border-radius: 14px;
  padding: 18px 16px;
  margin-bottom: 24px;
  position: relative;
}
.flyer-ribbon-title {
  font-family: 'Instrument Serif', serif;
  font-size: 22px;
  text-align: center;
  margin-bottom: 12px;
  color: #0F2A3A;
}
.flyer-ribbon-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
}
.flyer-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  background: #FFFFFF;
  border: 1px solid rgba(0,0,0,0.08);
  font-size: 11.5px;
  font-weight: 500;
  color: #0F2A3A;
}
.flyer-pill svg { color: #F08A2A; }

.flyer-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-top: 20px;
  border-top: 2px dashed rgba(15,42,58,0.15);
  position: relative;
}
.flyer-cta-eyebrow { font-size: 10px; letter-spacing: 0.18em; color: #F08A2A; font-weight: 600; margin-bottom: 4px; }
.flyer-cta-url { font-family: 'Instrument Serif', serif; font-size: 32px; color: #0F2A3A; line-height: 1; margin-bottom: 4px; }
.flyer-cta-sub { font-size: 12px; color: #4A5A6B; }
.flyer-qr { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.flyer-qr img { border: 4px solid #FFFFFF; border-radius: 6px; }
.flyer-qr-caption { font-size: 10px; color: #4A5A6B; }

.flyer-meta {
  max-width: 820px;
  width: 100%;
  text-align: center;
  margin-top: 24px;
  color: rgba(255,255,255,0.85);
  font-size: 13px;
}
.flyer-back { color: #FFFFFF; text-decoration: underline; display: inline-block; margin-bottom: 8px; }

/* Mobile */
@media (max-width: 720px) {
  .flyer-grid { grid-template-columns: 1fr; }
  .flyer-ribbon-grid { grid-template-columns: repeat(2, 1fr); }
  .flyer-title { font-size: 44px; }
  .flyer-page { padding: 24px 20px; }
  .flyer-footer { flex-direction: column; text-align: center; }
  .flyer-actions { top: auto; bottom: 16px; right: 50%; transform: translateX(50%); }
}

/* Print rules — single A4 page, no scroll, no chrome */
@media print {
  @page { size: A4; margin: 8mm; }
  body { background: #FFFFFF; }
  .flyer-root {
    background: #FFFFFF !important;
    padding: 0;
    min-height: auto;
  }
  .flyer-page {
    box-shadow: none;
    border-radius: 0;
    padding: 8mm;
    max-width: none;
    width: 100%;
  }
  .flyer-actions, .flyer-meta { display: none !important; }
  .flyer-card { break-inside: avoid; }
  .flyer-title { font-size: 48px; }
  .flyer-grid { gap: 8px; }
  .flyer-ribbon-grid { gap: 4px; }
  .flyer-page::before, .flyer-page::after { display: none; }
}
`;
