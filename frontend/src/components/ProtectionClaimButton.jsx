/**
 * ProtectionClaimButton — small Profile-page CTA that lets an attendee file
 * a Ticket Protection refund claim on a paid, protected booking.
 *
 * Flow:
 *   1. Read the user's existing claims for this booking on mount.
 *   2. If a pending/approved claim already exists, show its status badge
 *      (button is disabled).
 *   3. Otherwise show "Request refund" — click opens a small reason modal
 *      → POSTs to /api/ticket-protection/claims → flips to "Pending review".
 *
 * Why an inline modal instead of a separate page? Claims are quick — the
 * reason text + optional evidence URL is the only thing we need from the
 * buyer. Keeping it next to the booking row makes the flow obvious.
 */
import { useEffect, useState } from "react";
import { ShieldCheck, AlertTriangle } from "lucide-react";
import api, { formatApiErrorDetail } from "@/lib/api";
import { toast } from "sonner";

const STATUS_COPY = {
  pending: { label: "Claim under review", bg: "rgba(255,165,0,0.15)", color: "#ff9100" },
  approved: { label: "Refund approved", bg: "rgba(46,204,113,0.15)", color: "#2ECC71" },
  denied: { label: "Claim denied", bg: "rgba(231,76,60,0.15)", color: "#E74C3C" },
};

export default function ProtectionClaimButton({ booking }) {
  const [existingClaim, setExistingClaim] = useState(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [evidenceUrl, setEvidenceUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .get("/ticket-protection/claims/mine")
      .then(({ data }) => {
        if (cancelled) return;
        const mine = (data || []).find((c) => c.booking_id === booking.booking_id);
        setExistingClaim(mine || null);
      })
      .catch(() => {})
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [booking.booking_id]);

  if (loading) return null;

  if (existingClaim) {
    const c = STATUS_COPY[existingClaim.status] || STATUS_COPY.pending;
    return (
      <span
        className="px-2 py-1 rounded-full text-[10px] uppercase tracking-widest inline-flex items-center gap-1"
        style={{ background: c.bg, color: c.color }}
        title={existingClaim.reason}
        data-testid={`claim-status-${booking.booking_id}`}
      >
        <ShieldCheck className="w-3 h-3" /> {c.label}
      </span>
    );
  }

  const submit = async () => {
    const r = reason.trim();
    if (r.length < 10) {
      toast.error("Tell us a little more (at least 10 characters)");
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await api.post("/ticket-protection/claims", {
        booking_id: booking.booking_id,
        reason: r,
        evidence_url: evidenceUrl.trim() || null,
      });
      setExistingClaim(data);
      toast.success("Claim filed — we'll email you within 48 hours");
      setOpen(false);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Couldn't submit claim");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="btn-ghost !py-1.5 !px-3 text-xs"
        title="Refundable via Ticket Protection"
        data-testid={`file-claim-${booking.booking_id}`}
      >
        <ShieldCheck className="w-3 h-3" /> Request refund
      </button>
      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: "rgba(0,0,0,0.7)" }}
          onClick={() => !submitting && setOpen(false)}
          data-testid="protection-claim-modal"
        >
          <div
            className="w-full max-w-md rounded-2xl p-6"
            style={{ background: "var(--bg-card)", border: "1px solid var(--border)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2 mb-1">
              <ShieldCheck className="w-5 h-5" style={{ color: "var(--accent)" }} />
              <h3 className="serif text-xl">Ticket Protection claim</h3>
            </div>
            <p className="text-xs mb-4" style={{ color: "var(--text-muted)" }}>
              Tell us why you can't attend. We approve most valid claims within 48 hours and refund via Stripe.
            </p>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={5}
              maxLength={2000}
              placeholder="E.g. I came down with the flu and have a doctor's note dated 14 March…"
              className="w-full rounded-lg p-3 text-sm mb-3"
              style={{ background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)" }}
              data-testid="claim-reason-input"
            />
            <input
              value={evidenceUrl}
              onChange={(e) => setEvidenceUrl(e.target.value)}
              maxLength={500}
              placeholder="Optional: link to doctor's note, screenshot, etc."
              className="w-full rounded-lg p-3 text-sm mb-4"
              style={{ background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text)" }}
              data-testid="claim-evidence-input"
            />
            <div className="rounded-lg p-3 mb-4 text-xs flex items-start gap-2" style={{ background: "rgba(255,165,0,0.08)", border: "1px solid rgba(255,165,0,0.3)" }}>
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" style={{ color: "#ff9100" }} />
              <span style={{ color: "var(--text-muted)" }}>
                False claims may result in account suspension. The Ticket Protection upgrade fee itself is non-refundable per our terms.
              </span>
            </div>
            <div className="flex gap-2">
              <button
                onClick={submit}
                disabled={submitting}
                className="btn-primary flex-1 justify-center"
                data-testid="submit-claim-btn"
              >
                {submitting ? "Submitting…" : "Submit claim"}
              </button>
              <button
                onClick={() => setOpen(false)}
                disabled={submitting}
                className="btn-ghost flex-1"
                data-testid="cancel-claim-btn"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
