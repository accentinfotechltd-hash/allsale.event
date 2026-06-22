import { useEffect, useState } from "react";
import { Users, DollarSign, Receipt, ArrowLeft, KeyRound, Eye, EyeOff } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";

/**
 * PartnerPortal — read-only dashboard for a `role=partner` user.
 *
 * Surfaces the same numbers the admin sees in the partner-detail drawer:
 * lifetime earnings, unpaid balance, organizer count, recent ledger.
 *
 * Intentionally read-only — admin still controls payouts. A "Question?"
 * mailto link lets the partner reach out without needing in-app chat.
 */
export default function PartnerPortal() {
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [earnings, setEarnings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  useEffect(() => {
    document.title = "Partner Portal — Allsale Events";
    if (authLoading) return; // wait for the auth context to settle
    if (!user) { navigate("/login?next=/partner"); return; }
    if (user.role !== "partner") {
      setErr("This page is only for marketing lead partners. Ask Allsale admin to grant you partner access.");
      setLoading(false);
      return;
    }
    (async () => {
      try {
        const [{ data: me }, { data: e }] = await Promise.all([
          api.get("/partner/me"),
          api.get("/partner/me/earnings"),
        ]);
        setData(me);
        setEarnings(e || []);
      } catch (ex) {
        setErr(ex?.response?.data?.detail || "Couldn't load your dashboard");
      } finally {
        setLoading(false);
      }
    })();
  }, [user, authLoading, navigate]);

  if (loading) return <div className="max-w-4xl mx-auto px-4 sm:px-6 py-16 text-center" style={{ color: "var(--text-dim)" }}>Loading...</div>;
  if (err) {
    return (
      <div className="max-w-xl mx-auto px-4 sm:px-6 py-20 text-center" data-testid="partner-portal-error">
        <h1 className="font-serif text-2xl mb-3" style={{ color: "var(--text)" }}>Access denied</h1>
        <p className="text-sm mb-6" style={{ color: "var(--text-dim)" }}>{err}</p>
        <Link to="/" className="btn-ghost"><ArrowLeft size={14} /> Back home</Link>
      </div>
    );
  }
  if (!data) return null;

  const fmt = (n) => `NZD ${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-12" data-testid="partner-portal-page">
      <header className="mb-10">
        <div className="text-xs uppercase tracking-[0.32em]" style={{ color: "var(--accent)" }}>Partner portal</div>
        <h1 className="mt-3 font-serif" style={{ fontSize: "clamp(2rem, 4vw, 2.75rem)", lineHeight: 1.1, color: "var(--text)" }}>
          Hi {data.name}, here&apos;s your dashboard.
        </h1>
        <p className="mt-3 text-sm" style={{ color: "var(--text-dim)" }}>
          You earn <strong style={{ color: "var(--text)" }}>{data.commission_pct}%</strong> of platform commission on every paid booking from your referred organizers. Updates in real time.
        </p>
      </header>

      <div className="grid sm:grid-cols-3 gap-3 mb-8">
        <StatCard icon={<Users size={14} />} label="Attached organizers" value={String(data.organizer_count)} testid="partner-stat-organizers" />
        <StatCard icon={<DollarSign size={14} />} label="Lifetime earnings" value={fmt(data.lifetime_earnings)} testid="partner-stat-lifetime" />
        <StatCard icon={<Receipt size={14} />} label="Unpaid balance" value={fmt(data.unpaid_balance)} accent={data.unpaid_balance > 0} testid="partner-stat-unpaid" />
      </div>

      {data.organizers.length > 0 && (
        <section className="mb-8">
          <div className="text-xs uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>Your organizers</div>
          <div className="rounded-xl border" style={{ borderColor: "var(--border)" }}>
            {data.organizers.map((o, i) => (
              <div key={i} className="flex items-center justify-between px-4 py-2 border-b last:border-b-0" style={{ borderColor: "var(--border)" }}>
                <span style={{ color: "var(--text)" }}>{o.name}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <div className="text-xs uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>Earnings ledger</div>
        {earnings.length === 0 ? (
          <div className="rounded-xl border py-10 text-center text-sm" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
            No earnings yet. As soon as your organizers process bookings, you&apos;ll see commission rows here.
          </div>
        ) : (
          <div className="rounded-xl border overflow-hidden" style={{ borderColor: "var(--border)" }}>
            <table className="w-full text-sm">
              <thead style={{ color: "var(--text-dim)" }}>
                <tr className="text-left">
                  <th className="px-4 py-3 font-medium">Date</th>
                  <th className="px-4 py-3 font-medium">Event</th>
                  <th className="px-4 py-3 font-medium text-right">Earning</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {earnings.map((e) => (
                  <tr key={e.earning_id} className="border-t" style={{ borderColor: "var(--border)" }} data-testid={`partner-earning-${e.earning_id}`}>
                    <td className="px-4 py-3" style={{ color: "var(--text-dim)" }}>{fmtDate(e.created_at)}</td>
                    <td className="px-4 py-3" style={{ color: "var(--text)" }}>{e.event_title}</td>
                    <td className="px-4 py-3 text-right" style={{ color: "var(--text)", fontWeight: 500 }}>{e.currency || "NZD"} {e.earning_amount.toFixed(2)}</td>
                    <td className="px-4 py-3">
                      <span className="text-xs px-2 py-0.5 rounded-full" style={{
                        background: e.status === "paid" ? "rgba(46,204,113,0.15)" : "rgba(240,138,42,0.15)",
                        color: e.status === "paid" ? "#2ECC71" : "#F08A2A",
                      }}>{e.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="mt-10 text-center text-sm" style={{ color: "var(--text-dim)" }}>
        Question about your statement?{" "}
        <a href="mailto:partners@allsale.events" style={{ color: "var(--accent)" }} className="underline">
          Email Allsale
        </a>
      </div>

      <ChangePasswordSection />
    </div>
  );
}

function ChangePasswordSection() {
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNext, setShowNext] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const reset = () => {
    setCurrent(""); setNext(""); setConfirm("");
    setShowCurrent(false); setShowNext(false);
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!current || !next) {
      toast.error("Please fill in both passwords");
      return;
    }
    if (next.length < 6) {
      toast.error("New password must be at least 6 characters");
      return;
    }
    if (next !== confirm) {
      toast.error("New password and confirmation don't match");
      return;
    }
    if (next === current) {
      toast.error("New password must be different from current password");
      return;
    }
    setSubmitting(true);
    try {
      await api.put("/auth/change-password", { current_password: current, new_password: next });
      toast.success("Password updated successfully");
      reset();
      setOpen(false);
    } catch (ex) {
      toast.error(ex?.response?.data?.detail || "Couldn't change password");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="mt-12 pt-8 border-t" style={{ borderColor: "var(--border)" }} data-testid="partner-change-password-section">
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>Account security</div>
          <h2 className="font-serif text-lg mt-1" style={{ color: "var(--text)" }}>Change password</h2>
          <p className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>
            Replace the temporary password from your invitation email with one only you know.
          </p>
        </div>
        {!open && (
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="btn-ghost text-sm inline-flex items-center gap-1.5"
            data-testid="partner-change-password-open-btn"
          >
            <KeyRound size={14} /> Change password
          </button>
        )}
      </div>

      {open && (
        <form onSubmit={submit} className="rounded-xl border p-4 sm:p-5 mt-3 max-w-md" style={{ borderColor: "var(--border)" }} data-testid="partner-change-password-form">
          <div className="space-y-3">
            <PwdField
              label="Current password"
              value={current}
              onChange={setCurrent}
              show={showCurrent}
              onToggle={() => setShowCurrent((s) => !s)}
              testid="partner-current-password-input"
              autoComplete="current-password"
            />
            <PwdField
              label="New password"
              value={next}
              onChange={setNext}
              show={showNext}
              onToggle={() => setShowNext((s) => !s)}
              testid="partner-new-password-input"
              autoComplete="new-password"
            />
            <PwdField
              label="Confirm new password"
              value={confirm}
              onChange={setConfirm}
              show={showNext}
              onToggle={() => setShowNext((s) => !s)}
              testid="partner-confirm-password-input"
              autoComplete="new-password"
              hideToggle
            />
          </div>
          <div className="flex items-center gap-2 mt-4">
            <button
              type="submit"
              disabled={submitting}
              className="btn-primary text-sm"
              data-testid="partner-change-password-submit-btn"
            >
              {submitting ? "Updating…" : "Update password"}
            </button>
            <button
              type="button"
              onClick={() => { reset(); setOpen(false); }}
              disabled={submitting}
              className="btn-ghost text-sm"
              data-testid="partner-change-password-cancel-btn"
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

function PwdField({ label, value, onChange, show, onToggle, testid, autoComplete, hideToggle }) {
  return (
    <div>
      <label className="block text-xs mb-1" style={{ color: "var(--text-dim)" }}>{label}</label>
      <div className="relative">
        <input
          type={show ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete}
          className="w-full px-3 py-2 rounded-md border text-sm"
          style={{ borderColor: "var(--border)", background: "transparent", color: "var(--text)" }}
          data-testid={testid}
        />
        {!hideToggle && (
          <button
            type="button"
            onClick={onToggle}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-1"
            style={{ color: "var(--text-dim)" }}
            aria-label={show ? "Hide password" : "Show password"}
          >
            {show ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        )}
      </div>
    </div>
  );
}

function StatCard({ icon, label, value, accent, testid }) {
  return (
    <div className="rounded-xl border p-4" style={{ borderColor: "var(--border)" }} data-testid={testid}>
      <div className="text-[10px] uppercase tracking-widest inline-flex items-center gap-1" style={{ color: "var(--text-dim)" }}>{icon} {label}</div>
      <div className="text-2xl font-medium mt-1" style={{ color: accent ? "#F08A2A" : "var(--text)" }}>{value}</div>
    </div>
  );
}

function fmtDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  } catch { return "—"; }
}
