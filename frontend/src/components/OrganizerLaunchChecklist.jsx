import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Circle, ArrowRight } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";

/**
 * Pre-launch readiness checklist shown on the organizer dashboard.
 *
 * Surfaces the 5 most common "stuck draft" reasons so newcomers can see
 * exactly what stands between them and their first ticket sale:
 *
 *   1. Stripe Connect — bank + ID verified (required for paid events)
 *   2. Phone number on the profile
 *   3. Profile photo / avatar
 *   4. Refund policy chosen on at least one event
 *   5. At least one event published (status approved/published)
 *
 * Auto-hides once all 5 are ticked so the dashboard stays clean for
 * established organizers. Each row is a clickable shortcut to the page
 * that fixes it.
 */
export default function OrganizerLaunchChecklist({ events }) {
  const { user } = useAuth();
  const [stripe, setStripe] = useState(null);
  // events is passed by the parent — we use it for refund-policy + published checks.

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get("/stripe/connect/status");
        if (!cancelled) setStripe(data);
      } catch {
        if (!cancelled) setStripe({ stripe_payouts_enabled: false });
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const items = [
    {
      key: "stripe",
      label: "Connect Stripe for payouts",
      hint: "Bank + ID verification. 3-minute setup. Required for paid events.",
      to: "/organizer",
      done: !!stripe?.stripe_payouts_enabled,
    },
    {
      key: "phone",
      label: "Add a phone number",
      hint: "For ticket-buyer SMS, support escalation, and dispute resolution.",
      to: "/profile",
      done: !!(user?.phone && String(user.phone).trim().length >= 6),
    },
    {
      key: "avatar",
      label: "Upload a profile photo",
      hint: "Builds trust — your face appears on every event card you publish.",
      to: "/profile",
      done: !!(user?.picture && String(user.picture).startsWith("http")),
    },
    {
      key: "refund_policy",
      label: "Choose a refund policy",
      hint: "On at least one event. Sets the right expectations with buyers up front.",
      to: "/organizer",
      done: (Array.isArray(events) ? events : []).some(
        (e) => e?.refund_policy && Object.keys(e.refund_policy).length > 0,
      ),
    },
    {
      key: "first_event",
      label: "Publish your first event",
      hint: "Once Stripe is connected and pricing is set, hit save to go live.",
      to: "/organizer/new",
      done: (Array.isArray(events) ? events : []).some(
        (e) => e?.status === "approved" || e?.status === "published",
      ),
    },
  ];

  const doneCount = items.filter((i) => i.done).length;
  const total = items.length;
  const pct = Math.round((doneCount / total) * 100);

  // Hide the widget entirely once every step is done — the dashboard
  // doesn't need a "you're all set" badge taking up real estate.
  if (doneCount === total) return null;

  return (
    <div
      className="border rounded-2xl p-6 mb-8"
      style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
      data-testid="organizer-launch-checklist"
    >
      <div className="flex items-end justify-between mb-4 gap-4 flex-wrap">
        <div>
          <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--accent)" }}>
            Pre-launch checklist
          </div>
          <div className="serif text-2xl">
            {doneCount === 0
              ? "Get ready to sell your first ticket"
              : doneCount === total - 1
                ? "One step from going live"
                : "Almost there"}
          </div>
        </div>
        <div className="text-sm" style={{ color: "var(--text-dim)" }}>
          <span className="font-semibold" style={{ color: "var(--text)" }} data-testid="launch-checklist-progress">
            {doneCount}/{total}
          </span>
          {" "}complete · {pct}%
        </div>
      </div>

      {/* Progress bar */}
      <div className="h-1.5 rounded-full overflow-hidden mb-5" style={{ background: "var(--border)" }}>
        <div
          className="h-full transition-all duration-500"
          style={{ width: `${pct}%`, background: "var(--accent)" }}
          aria-hidden
          data-testid="launch-checklist-bar"
        />
      </div>

      <ul className="space-y-2" role="list">
        {items.map((it) => (
          <li key={it.key}>
            <Link
              to={it.to}
              className={`flex items-start gap-3 p-3 rounded-xl transition group ${it.done ? "opacity-60" : "hover:bg-black/5"}`}
              data-testid={`launch-checklist-item-${it.key}`}
              data-done={it.done ? "1" : "0"}
            >
              <span className="mt-0.5 shrink-0" aria-hidden>
                {it.done ? (
                  <CheckCircle2 className="w-5 h-5" style={{ color: "var(--accent)" }} />
                ) : (
                  <Circle className="w-5 h-5" style={{ color: "var(--text-dim)" }} />
                )}
              </span>
              <span className="flex-1 min-w-0">
                <span
                  className={`block text-sm font-medium ${it.done ? "line-through" : ""}`}
                  style={{ color: "var(--text)" }}
                >
                  {it.label}
                </span>
                {!it.done && (
                  <span className="block text-xs mt-0.5" style={{ color: "var(--text-dim)" }}>
                    {it.hint}
                  </span>
                )}
              </span>
              {!it.done && (
                <ArrowRight
                  className="w-4 h-4 shrink-0 mt-1 opacity-50 group-hover:opacity-100 transition"
                  style={{ color: "var(--text)" }}
                  aria-hidden
                />
              )}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
