import { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import api, { formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Mail, Lock, ArrowRight } from "lucide-react";
import { toast } from "sonner";

export default function Login() {
  const { setUser } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await api.post("/auth/login", { email, password });
      if (data.token) localStorage.setItem("aura_token", data.token);
      setUser(data);
      const target = loc.state?.from
        || (data.role === "organizer" ? "/organizer"
        : data.role === "admin" ? "/admin"
        : "/");
      nav(target);
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Login failed");
    } finally { setLoading(false); }
  };

  const onGoogle = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/auth/callback";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="min-h-[80vh] grid lg:grid-cols-2">
      <div className="hidden lg:block relative">
        <img src="https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=1400" alt="" className="w-full h-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-r from-[color:var(--bg)] via-black/40 to-transparent" />
        <div className="absolute bottom-10 left-10 right-10">
          <div className="serif text-5xl leading-tight max-w-md">Step into the spotlight.</div>
          <p className="text-sm mt-3 max-w-sm" style={{ color: "var(--text-muted)" }}>Your next favourite night is a few clicks away.</p>
        </div>
      </div>

      <div className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-md">
          <Link to="/" className="serif text-3xl">AURA</Link>
          <h1 className="serif text-4xl mt-8 mb-2">Welcome back</h1>
          <p className="mb-8 text-sm" style={{ color: "var(--text-muted)" }}>Sign in to your tickets and bookings.</p>

          <button onClick={onGoogle} className="btn-ghost w-full justify-center !py-3" data-testid="google-login-btn">
            <img src="https://www.google.com/favicon.ico" alt="" className="w-4 h-4" />
            Continue with Google
          </button>

          <div className="flex items-center gap-3 my-6 text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
            <div className="flex-1 h-px" style={{ background: "var(--border)" }} />
            or
            <div className="flex-1 h-px" style={{ background: "var(--border)" }} />
          </div>

          <form onSubmit={onSubmit} className="space-y-4" data-testid="login-form">
            <div>
              <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>Email</label>
              <div className="relative">
                <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: "var(--text-dim)" }} />
                <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="pl-10" placeholder="you@example.com" data-testid="login-email-input" />
              </div>
            </div>
            <div>
              <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>Password</label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: "var(--text-dim)" }} />
                <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className="pl-10" placeholder="••••••••" data-testid="login-password-input" />
              </div>
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full justify-center" data-testid="login-submit-btn">
              {loading ? "Signing in..." : "Sign in"} <ArrowRight className="w-4 h-4" />
            </button>
          </form>

          <p className="mt-6 text-sm text-center" style={{ color: "var(--text-muted)" }}>
            New here? <Link to="/signup" className="underline" style={{ color: "var(--accent)" }}>Create an account</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
