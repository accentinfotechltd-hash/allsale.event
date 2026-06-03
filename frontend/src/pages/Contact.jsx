/**
 * Contact page — public form. Hits POST /api/contact.
 *
 * Submits anonymously; backend stores message + emails support inbox and
 * a courtesy auto-reply to the sender.
 */
import { useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Mail, Phone, MapPin, Send, CheckCircle2 } from "lucide-react";
import useSiteSettings from "@/lib/useSiteSettings";

export default function Contact() {
  const settings = useSiteSettings();
  const c = settings.contact || {};
  const [form, setForm] = useState({ name: "", email: "", phone: "", subject: "", message: "" });
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  const update = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/contact", {
        name: form.name.trim(),
        email: form.email.trim(),
        phone: form.phone.trim() || null,
        subject: form.subject.trim(),
        message: form.message.trim(),
      });
      setSent(true);
      toast.success("Message sent — we'll reply within 24 hours");
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Could not send — try again in a moment");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-10 sm:py-16" data-testid="contact-page">
      <div className="text-xs uppercase tracking-[0.3em] mb-3" style={{ color: "var(--accent)" }}>{c.hero_eyebrow || "Contact us"}</div>
      <h1 className="serif text-4xl sm:text-5xl lg:text-6xl leading-[1.02] mb-6 whitespace-pre-line">{c.hero_title || "Let's talk."}</h1>
      <p className="text-base sm:text-lg max-w-2xl mb-10 whitespace-pre-line" style={{ color: "var(--text-muted)" }}>
        {c.hero_subtitle}
      </p>

      <div className="grid lg:grid-cols-[1fr_320px] gap-8 lg:gap-12">
        {/* Form */}
        <div className="rounded-2xl border p-5 sm:p-8" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
          {sent ? (
            <div className="text-center py-10" data-testid="contact-success">
              <div className="w-14 h-14 rounded-full flex items-center justify-center mx-auto mb-4" style={{ background: "rgba(34, 197, 94, 0.1)", color: "var(--success)" }}>
                <CheckCircle2 className="w-7 h-7" />
              </div>
              <h2 className="serif text-2xl mb-2">Message received</h2>
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>We just sent you a confirmation email. A real human will reply within 24 hours.</p>
              <button onClick={() => { setSent(false); setForm({ name: "", email: "", phone: "", subject: "", message: "" }); }} className="btn-ghost mt-6" data-testid="send-another-btn">Send another message</button>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <div className="grid sm:grid-cols-2 gap-4">
                <Field label="Your name *">
                  <input required value={form.name} onChange={update("name")} className="w-full" placeholder="Jane Doe" data-testid="contact-name" />
                </Field>
                <Field label="Email *">
                  <input required type="email" value={form.email} onChange={update("email")} className="w-full" placeholder="you@example.com" data-testid="contact-email" />
                </Field>
              </div>
              <Field label="Phone (optional)">
                <input value={form.phone} onChange={update("phone")} className="w-full" placeholder="+64 21 555 1234" data-testid="contact-phone" />
              </Field>
              <Field label="Subject *">
                <input required value={form.subject} onChange={update("subject")} className="w-full" placeholder="What's it about?" data-testid="contact-subject" />
              </Field>
              <Field label="Message *">
                <textarea required value={form.message} onChange={update("message")} rows={6} className="w-full" placeholder="Tell us anything — issue, idea, partnership…" data-testid="contact-message" />
              </Field>
              <div className="flex justify-end pt-2">
                <button type="submit" disabled={busy} className="btn-primary" data-testid="contact-submit">
                  <Send className="w-4 h-4" /> {busy ? "Sending…" : "Send message"}
                </button>
              </div>
            </form>
          )}
        </div>

        {/* Side info */}
        <div className="space-y-3">
          <InfoCard icon={<Mail className="w-5 h-5" />} label="Email" value={c.email} href={c.email ? `mailto:${c.email}` : undefined} />
          <InfoCard icon={<Phone className="w-5 h-5" />} label="Phone" value={c.phone} href={c.phone ? `tel:${c.phone.replace(/\s+/g, "")}` : undefined} />
          <InfoCard icon={<MapPin className="w-5 h-5" />} label="Based in" value={c.address} />
          {c.organizer_note && (
            <div className="text-xs px-4 py-3 rounded-xl" style={{ background: "var(--bg-elev)", color: "var(--text-muted)" }}>
              {c.organizer_note}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <div className="text-xs uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>{label}</div>
      {children}
    </label>
  );
}

function InfoCard({ icon, label, value, href }) {
  const Inner = (
    <div className="rounded-xl border p-4 flex items-center gap-3" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
      <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: "rgba(234, 88, 12, 0.1)", color: "var(--accent)" }}>{icon}</div>
      <div>
        <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>{label}</div>
        <div className="text-sm font-medium">{value}</div>
      </div>
    </div>
  );
  return href ? <a href={href} className="block hover:opacity-80 transition">{Inner}</a> : Inner;
}
