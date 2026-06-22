import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import api, { formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { trackSignup } from "@/lib/analytics";
import { Mail, Lock, User, ArrowRight, Sparkles } from "lucide-react";
import { toast } from "sonner";
import Logo from "@/components/Logo";

export default function Signup() {
  const { setUser } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const refCode = (params.get("ref") || "").trim().toLowerCase();
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "attendee" });
  const [loading, setLoading] = useState(false);
  const [acceptedTerms, setAcceptedTerms] = useState(false);

  // Persist the referral code in localStorage so it survives the Google OAuth
  // round-trip (Google callback is a separate page).
  useEffect(() => {
    if (refCode && refCode.startsWith("ref_")) {
      try { localStorage.setItem("allsale_ref_code", refCode); } catch { /* noop */ }
    }
  }, [refCode]);

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const stampReferralBestEffort = async () => {
    let stored = "";
    try { stored = localStorage.getItem("allsale_ref_code") || ""; } catch { /* noop */ }
    const code = (refCode || stored).trim().toLowerCase();
    if (!code.startsWith("ref_")) return;
    try {
      await api.post("/auth/register/stamp-referral", { ref_code: code });
      try { localStorage.removeItem("allsale_ref_code"); } catch { /* noop */ }
    } catch { /* silent — non-blocking */ }
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!acceptedTerms) {
      toast.error("Please accept the Terms and Privacy Policy to continue");
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.post("/auth/register", form);
      if (data.token) localStorage.setItem("aura_token", data.token);
      setUser(data);
      await stampReferralBestEffort();
      trackSignup("email", data.role || form.role);
      toast.success("Welcome to Allsale Events!");
      nav("/");
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Signup failed");
    } finally { setLoading(false); }
  };

  const onGoogle = () => {
    if (!acceptedTerms) {
      toast.error("Please accept the Terms and Privacy Policy to continue");
      return;
    }
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/auth/callback";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="min-h-[80vh] grid lg:grid-cols-2">
      <div className="flex items-center justify-center px-6 py-12 order-2 lg:order-1">
        <div className="w-full max-w-md">
          <Link to="/" className="inline-flex"><Logo size={88} /></Link>
          <h1 className="serif text-4xl mt-8 mb-2">Create your account</h1>
          <p className="mb-8 text-sm" style={{ color: "var(--text-muted)" }}>Book tickets, save events, or list your own show.</p>

          {refCode && (
            <div
              className="mb-6 flex items-center gap-2 p-3 rounded-xl"
              style={{ background: "var(--accent-soft)", border: "1px solid var(--accent)" }}
              data-testid="referral-banner"
            >
              <Sparkles size={14} style={{ color: "var(--accent)" }} />
              <div className="text-xs" style={{ color: "var(--accent)" }}>
                Referral active — you're signing up via an organizer's invite link.
              </div>
            </div>
          )}

          <button onClick={onGoogle} className="btn-ghost w-full justify-center !py-3" data-testid="google-signup-btn">
            <img src="https://www.google.com/favicon.ico" alt="" className="w-4 h-4" />
            Continue with Google
          </button>

          <div className="flex items-center gap-3 my-6 text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
            <div className="flex-1 h-px" style={{ background: "var(--border)" }} />
            or
            <div className="flex-1 h-px" style={{ background: "var(--border)" }} />
          </div>

          <form onSubmit={onSubmit} className="space-y-4" data-testid="signup-form">
            <div>
              <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>I want to</label>
              <div className="grid grid-cols-2 gap-2">
                {["attendee", "organizer"].map((r) => (
                  <button key={r} type="button" onClick={() => update("role", r)} className="px-3 py-2 rounded-lg text-sm border transition" style={{
                    borderColor: form.role === r ? "var(--accent)" : "var(--border)",
                    background: form.role === r ? "var(--accent-soft)" : "var(--bg-elev)",
                    color: form.role === r ? "var(--accent)" : "var(--text-muted)",
                  }} data-testid={`role-${r}`}>
                    {r === "attendee" ? "Book tickets" : "Sell tickets"}
                  </button>
                ))}
              </div>
            </div>
            <Field icon={<User className="w-4 h-4" />} placeholder="Full name" value={form.name} onChange={(v) => update("name", v)} testid="signup-name-input" />
            <Field icon={<Mail className="w-4 h-4" />} type="email" placeholder="you@example.com" value={form.email} onChange={(v) => update("email", v)} testid="signup-email-input" />
            <Field icon={<Lock className="w-4 h-4" />} type="password" placeholder="Password (8+ chars)" value={form.password} onChange={(v) => update("password", v)} testid="signup-password-input" />

            <label className="flex items-start gap-2.5 text-xs cursor-pointer pt-1" style={{ color: "var(--text-muted)" }}>
              <input
                type="checkbox"
                checked={acceptedTerms}
                onChange={(e) => setAcceptedTerms(e.target.checked)}
                style={{ width: "16px", height: "16px", flexShrink: 0, marginTop: "2px", accentColor: "var(--accent)" }}
                data-testid="signup-terms-checkbox"
              />
              <span>
                I agree to the{" "}
                <Link to="/terms" target="_blank" className="underline" style={{ color: "var(--accent)" }} data-testid="signup-terms-link">
                  Terms of Service
                </Link>{" "}
                and{" "}
                <Link to="/privacy" target="_blank" className="underline" style={{ color: "var(--accent)" }} data-testid="signup-privacy-link">
                  Privacy Policy
                </Link>
                .
              </span>
            </label>

            <button type="submit" disabled={loading || !acceptedTerms} className="btn-primary w-full justify-center" data-testid="signup-submit-btn">
              {loading ? "Creating..." : "Create account"} <ArrowRight className="w-4 h-4" />
            </button>
          </form>

          <p className="mt-6 text-sm text-center" style={{ color: "var(--text-muted)" }}>
            Already a member? <Link to="/login" className="underline" style={{ color: "var(--accent)" }}>Sign in</Link>
          </p>
        </div>
      </div>

      <div className="hidden lg:block relative order-1 lg:order-2">
        <img src="https://images.unsplash.com/photo-1459749411175-04bf5292ceea?w=1400" alt="" className="w-full h-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-l from-[color:var(--bg)] via-black/40 to-transparent" />
        <div className="absolute bottom-10 left-10 right-10 text-right">
          <div className="serif text-5xl leading-tight max-w-md ml-auto">Tickets without the chaos.</div>
        </div>
      </div>
    </div>
  );
}

function Field({ icon, type = "text", placeholder, value, onChange, testid }) {
  return (
    <div className="relative">
      <span className="absolute left-3.5 top-1/2 -translate-y-1/2" style={{ color: "var(--text-dim)" }}>{icon}</span>
      <input type={type} required placeholder={placeholder} value={value} onChange={(e) => onChange(e.target.value)} className="pl-10" data-testid={testid} />
    </div>
  );
}
