/**
 * PhoneCaptureGate — one-time blocking modal for users without a phone.
 *
 * Phone is mandatory for every account on Allsale (operational ops, WhatsApp
 * notifications, account recovery). Email/password signup collects it inline,
 * but Google OAuth + pre-existing users may not have one yet — this gate
 * intercepts them on the next page load until they save a valid number.
 *
 * The gate:
 *   • Renders nothing for logged-out visitors and users who already have a phone
 *   • Renders a fixed-overlay modal that can't be dismissed by clicking outside
 *     (no escape, no close button) — phone is mandatory, not optional
 *   • PATCHes `/auth/me` and re-syncs `useAuth().user` on save
 *   • Validates with the same lenient regex the backend uses
 */
import { useState } from "react";
import { Phone, ArrowRight } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const PHONE_RE = /^[+0-9 ()\-]{6,20}$/;

export default function PhoneCaptureGate() {
  const { user, setUser } = useAuth();
  const [phone, setPhone] = useState("");
  const [saving, setSaving] = useState(false);

  if (!user) return null;
  if (user.phone && String(user.phone).trim().length >= 6) return null;

  const onSave = async (e) => {
    e.preventDefault();
    const value = phone.trim();
    if (!PHONE_RE.test(value)) {
      toast.error("Please enter a valid phone number (6–20 chars, digits with optional + and spaces).");
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.patch("/auth/me", { phone: value });
      // PATCH /auth/me returns the refreshed user document at the top level
      // alongside { updated: true }. Spread the fresh fields into the auth
      // context so the rest of the app re-renders without the gate.
      const next = { ...user, ...data, phone: data.phone || value };
      setUser(next);
      toast.success("Phone saved — you're all set.");
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Couldn't save phone");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.85)", backdropFilter: "blur(6px)" }}
      data-testid="phone-capture-gate"
      // Intentional: no onClick handler — the gate is non-dismissible.
    >
      <div
        className="rounded-2xl border w-full max-w-md p-6"
        style={{ background: "var(--bg, #0f0f12)", borderColor: "var(--border)" }}
      >
        <div
          className="w-12 h-12 rounded-full flex items-center justify-center mb-4"
          style={{ background: "var(--accent-soft, rgba(255,79,0,0.12))", color: "var(--accent)" }}
        >
          <Phone size={22} />
        </div>
        <h2 className="font-serif text-2xl mb-1" style={{ color: "var(--text)" }}>
          One last thing
        </h2>
        <p className="text-sm mb-5" style={{ color: "var(--text-muted)" }}>
          Phone number is now required on every Allsale account. We use it for booking
          confirmations, WhatsApp event reminders, and account recovery. Takes 5 seconds.
        </p>

        <form onSubmit={onSave} className="space-y-3">
          <label className="block">
            <span className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
              Mobile number
            </span>
            <div className="relative mt-1">
              <span
                className="absolute left-3.5 top-1/2 -translate-y-1/2"
                style={{ color: "var(--text-dim)" }}
              >
                <Phone className="w-4 h-4" />
              </span>
              <input
                type="tel"
                inputMode="tel"
                autoFocus
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+64 21 555 1234"
                className="pl-10 w-full"
                data-testid="phone-gate-input"
                required
              />
            </div>
          </label>

          <button
            type="submit"
            disabled={saving || phone.trim().length < 6}
            className="btn-primary w-full justify-center"
            data-testid="phone-gate-submit-btn"
          >
            {saving ? "Saving…" : "Save and continue"} <ArrowRight className="w-4 h-4" />
          </button>
        </form>

        <p className="text-[10px] text-center mt-4" style={{ color: "var(--text-dim)" }}>
          We never share your phone with organizers or third parties.
        </p>
      </div>
    </div>
  );
}
