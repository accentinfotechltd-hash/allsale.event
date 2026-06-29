/**
 * BecomePartner — public application form for the Allsale Marketing Partner program.
 *
 * No login required. Submission persists to `partner_applications` and fires
 * an admin notification email + an applicant acknowledgement.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import axios from "axios";
import { Sparkles, ArrowRight, CheckCircle2, TrendingUp, Users, Mail, DollarSign } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const CHANNEL_OPTIONS = [
  { id: "instagram", label: "Instagram" },
  { id: "tiktok", label: "TikTok" },
  { id: "youtube", label: "YouTube" },
  { id: "whatsapp", label: "WhatsApp / Telegram" },
  { id: "email", label: "Email list" },
  { id: "blog", label: "Blog / Website" },
  { id: "podcast", label: "Podcast" },
  { id: "events", label: "Events / Meetups" },
  { id: "other", label: "Other" },
];

const PERKS = [
  { icon: DollarSign, title: "10-25% recurring", body: "Cut of every booking from your audience — forever." },
  { icon: TrendingUp, title: "Monthly statements", body: "Auto-emailed payout reports + a self-serve dashboard." },
  { icon: Users, title: "Your own portal", body: "Track every organizer / event you brought in." },
];

export default function BecomePartner() {
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    phone: "",
    company: "",
    channels: [],
    audience_size: "",
    why_partner: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(null); // { application_id }

  const toggleChannel = (id) => {
    setForm((f) => ({
      ...f,
      channels: f.channels.includes(id) ? f.channels.filter((c) => c !== id) : [...f.channels, id],
    }));
  };

  const submit = async (e) => {
    e.preventDefault();
    if (form.why_partner.trim().length < 10) {
      toast.error("Please tell us a bit more about why you'd like to partner (10+ characters).");
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await axios.post(`${API}/partners/apply`, form);
      setSuccess({ application_id: data.application_id });
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't submit — please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (success) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-24 text-center" data-testid="partner-apply-success">
        <CheckCircle2 className="w-14 h-14 mx-auto mb-5" style={{ color: "var(--success)" }} />
        <div className="text-[11px] uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Application received</div>
        <h1 className="serif text-4xl mb-3">Thanks — we&apos;ve got it.</h1>
        <p className="mb-6" style={{ color: "var(--text-muted)" }}>
          Our team will review and reach out within <b style={{ color: "var(--text)" }}>2-3 business days</b>. Keep an eye on your inbox — and check spam just in case.
        </p>
        <div className="text-xs mb-8 rounded-lg p-3 inline-block" style={{ background: "var(--bg-card)", color: "var(--text-muted)" }}>
          Reference: <code data-testid="partner-apply-ref">{success.application_id}</code>
        </div>
        <div>
          <Link to="/" className="btn-secondary" data-testid="partner-apply-back-home">Back to home</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-12" data-testid="become-partner-page">
      {/* Hero */}
      <div className="mb-10">
        <div className="inline-flex items-center gap-1 text-[11px] uppercase tracking-[0.25em] mb-3" style={{ color: "var(--accent)" }}>
          <Sparkles className="w-3.5 h-3.5" /> Marketing partner program
        </div>
        <h1 className="serif text-4xl md:text-5xl mb-3">Earn from every event you send our way.</h1>
        <p className="text-lg leading-relaxed" style={{ color: "var(--text-muted)" }}>
          Allsale partners get a recurring cut of platform commission on bookings their audience drives.
          Apply once — get a dashboard, monthly payouts, and direct contact with our team.
        </p>
      </div>

      {/* Perks */}
      <div className="grid sm:grid-cols-3 gap-3 mb-10">
        {PERKS.map(({ icon: Icon, title, body }) => (
          <div
            key={title}
            className="rounded-xl border p-4"
            style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
          >
            <Icon className="w-5 h-5 mb-2" style={{ color: "var(--accent)" }} />
            <div className="font-medium mb-0.5" style={{ color: "var(--text)" }}>{title}</div>
            <div className="text-sm" style={{ color: "var(--text-muted)" }}>{body}</div>
          </div>
        ))}
      </div>

      {/* Form */}
      <form onSubmit={submit} className="space-y-5 rounded-2xl border p-6" style={{ borderColor: "var(--border)" }}>
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="full_name" className="block text-xs uppercase tracking-wider mb-1.5" style={{ color: "var(--text-muted)" }}>
              Full name <span style={{ color: "var(--accent)" }}>*</span>
            </label>
            <input
              id="full_name"
              type="text"
              required
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              data-testid="partner-apply-name"
              className="w-full"
            />
          </div>
          <div>
            <label htmlFor="email" className="block text-xs uppercase tracking-wider mb-1.5" style={{ color: "var(--text-muted)" }}>
              Email <span style={{ color: "var(--accent)" }}>*</span>
            </label>
            <input
              id="email"
              type="email"
              required
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              data-testid="partner-apply-email"
              className="w-full"
            />
          </div>
        </div>

        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="phone" className="block text-xs uppercase tracking-wider mb-1.5" style={{ color: "var(--text-muted)" }}>Phone / WhatsApp</label>
            <input
              id="phone"
              type="tel"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
              data-testid="partner-apply-phone"
              className="w-full"
              placeholder="+64 21 xxx xxxx"
            />
          </div>
          <div>
            <label htmlFor="company" className="block text-xs uppercase tracking-wider mb-1.5" style={{ color: "var(--text-muted)" }}>Brand / Company</label>
            <input
              id="company"
              type="text"
              value={form.company}
              onChange={(e) => setForm({ ...form, company: e.target.value })}
              data-testid="partner-apply-company"
              className="w-full"
              placeholder="Optional"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs uppercase tracking-wider mb-2" style={{ color: "var(--text-muted)" }}>Where do you reach your audience?</label>
          <div className="flex flex-wrap gap-2" data-testid="partner-apply-channels">
            {CHANNEL_OPTIONS.map((opt) => {
              const active = form.channels.includes(opt.id);
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => toggleChannel(opt.id)}
                  data-testid={`partner-apply-channel-${opt.id}`}
                  className="px-3 py-1.5 rounded-full text-sm border transition"
                  style={{
                    borderColor: active ? "var(--accent)" : "var(--border)",
                    background: active ? "var(--accent-soft)" : "transparent",
                    color: active ? "var(--accent)" : "var(--text)",
                  }}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <label htmlFor="audience_size" className="block text-xs uppercase tracking-wider mb-1.5" style={{ color: "var(--text-muted)" }}>How big is your audience?</label>
          <input
            id="audience_size"
            type="text"
            value={form.audience_size}
            onChange={(e) => setForm({ ...form, audience_size: e.target.value })}
            data-testid="partner-apply-audience"
            className="w-full"
            placeholder="e.g. 12,000 IG followers + 3,000 email list"
          />
        </div>

        <div>
          <label htmlFor="why_partner" className="block text-xs uppercase tracking-wider mb-1.5" style={{ color: "var(--text-muted)" }}>
            Why partner with Allsale? <span style={{ color: "var(--accent)" }}>*</span>
          </label>
          <textarea
            id="why_partner"
            required
            value={form.why_partner}
            onChange={(e) => setForm({ ...form, why_partner: e.target.value.slice(0, 1500) })}
            data-testid="partner-apply-why"
            className="w-full min-h-[120px]"
            placeholder="Tell us about the events your audience cares about, why you think they'd book through Allsale, and what makes you a great partner."
          />
          <div className="text-[11px] mt-1" style={{ color: "var(--text-muted)" }}>{form.why_partner.length} / 1500</div>
        </div>

        <div className="flex items-center gap-3 pt-3 border-t" style={{ borderColor: "var(--border)" }}>
          <button
            type="submit"
            disabled={submitting}
            data-testid="partner-apply-submit"
            className="btn-primary inline-flex items-center gap-2"
          >
            {submitting ? "Submitting…" : "Submit application"} <ArrowRight className="w-4 h-4" />
          </button>
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            <Mail className="w-3.5 h-3.5 inline-block mr-1" />
            We&apos;ll reply within 2-3 days
          </span>
        </div>
      </form>
    </div>
  );
}
