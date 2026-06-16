import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { CheckCircle2, Gift, ArrowRight } from "lucide-react";

/**
 * GiftCardSuccess — landing page after Stripe checkout returns.
 * We don't show the code here (it's emailed to the recipient).
 * Just confirm + offer a polite next-step CTA.
 */
export default function GiftCardSuccess() {
  const [params] = useSearchParams();
  const sessionId = params.get("session_id");
  const [polling, setPolling] = useState(true);

  // Stripe webhook usually fires within seconds, so just show a friendly
  // confirmation. No need to poll the API in MVP.
  useEffect(() => {
    const t = setTimeout(() => setPolling(false), 2500);
    return () => clearTimeout(t);
  }, []);

  return (
    <div className="max-w-xl mx-auto px-4 py-24 text-center">
      <div className="mb-6 inline-flex items-center justify-center w-16 h-16 rounded-full" style={{ background: "var(--accent-soft)" }}>
        <CheckCircle2 size={32} style={{ color: "var(--accent)" }} />
      </div>
      <h1 className="serif text-4xl mb-3">Gift card on its way 🎁</h1>
      <p className="text-sm mb-8" style={{ color: "var(--text-muted)" }} data-testid="gc-success-msg">
        Payment received. The recipient will get an email with the code within a minute.
        You&apos;ll also see it under <strong>Profile → Gift cards</strong>.
      </p>
      {sessionId && (
        <div className="text-[10px] mb-8 font-mono opacity-50" data-testid="session-id">{sessionId.slice(0, 32)}...</div>
      )}
      <div className="flex gap-3 justify-center">
        <Link to="/events" className="btn-primary" data-testid="back-to-events">
          Browse events <ArrowRight size={14} />
        </Link>
        <Link to="/gift-cards" className="btn-ghost" data-testid="buy-another">
          <Gift size={14} /> Buy another
        </Link>
      </div>
      {polling && (
        <div className="mt-6 text-xs" style={{ color: "var(--text-muted)" }}>
          Activating card...
        </div>
      )}
    </div>
  );
}
