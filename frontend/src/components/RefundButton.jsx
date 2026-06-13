import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Receipt, Loader2 } from "lucide-react";

/**
 * "Request refund" button shown next to each paid ticket on Profile.
 *
 * Behavior:
 *  - On mount: fetches eligibility. Hides itself if the booking isn't
 *    eligible (organizer hasn't enabled self-serve, cut-off passed, etc.)
 *    to keep the UI uncluttered. Shows for already-refunded bookings as a
 *    disabled "Refunded" pill.
 *  - On click: confirm dialog → POST refund-request → toast success or
 *    error → reload page to refresh the booking list.
 */
export default function RefundButton({ bookingId, eventCurrency }) {
  const [elig, setElig] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get(`/me/bookings/${bookingId}/refund-eligibility`);
        if (!cancelled) setElig(data);
      } catch {
        if (!cancelled) setElig(null);
      }
    })();
    return () => { cancelled = true; };
  }, [bookingId]);

  if (!elig) return null;

  if (elig.already_refunded) {
    return (
      <span
        className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded-full"
        style={{ background: "var(--bg-elev)", color: "var(--text-dim)" }}
        data-testid={`refunded-pill-${bookingId}`}
      >
        Refunded
      </span>
    );
  }

  if (!elig.eligible) return null;

  const amount = elig.amounts?.total_refund ?? 0;
  const cur = elig.currency || eventCurrency || "NZD";

  const submit = async () => {
    if (!window.confirm(`Refund ${cur} ${amount.toFixed(2)}? Your seats / tickets will be released and the charge reversed on Stripe.`)) return;
    setSubmitting(true);
    try {
      const { data } = await api.post(`/me/bookings/${bookingId}/refund-request`, {});
      toast.success(`Refunded ${cur} ${(data.amount_refunded || 0).toFixed(2)}. It usually arrives in 5–10 business days.`);
      // Reload bookings list
      setTimeout(() => window.location.reload(), 1000);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't process refund — try again or contact support.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <button
      onClick={submit}
      disabled={submitting}
      className="btn-ghost !py-1.5 !px-3 text-xs"
      data-testid={`refund-btn-${bookingId}`}
      title={`Refund window closes ${elig.policy?.hours_before_event}h before the event`}
    >
      {submitting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Receipt className="w-3 h-3" />}
      Refund
    </button>
  );
}
