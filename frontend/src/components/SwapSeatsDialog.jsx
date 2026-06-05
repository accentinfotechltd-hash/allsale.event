import { useEffect, useState } from "react";
import { toast } from "sonner";
import { X, ArrowRight } from "lucide-react";

import api, { formatApiErrorDetail } from "@/lib/api";

/**
 * Admin/organizer dialog to swap a paid booking's seats within the same event.
 *
 * Validations are enforced server-side, but we also pre-validate locally to
 * give the operator immediate feedback (wrong count, duplicate, etc.).
 *
 * Props:
 *   booking      – { booking_id, seats: [...], user_email, user_name, event_id }
 *   eventId      – event id (defensive; falls back to booking.event_id)
 *   eventSeats   – array of seatmap seat objects: { id, tier, ... }
 *   bookedSeats  – set of seat ids currently booked by anyone (read-only)
 *   heldSeats    – set of seat ids currently held by anyone (read-only)
 *   onClose      – callback to dismiss
 *   onSwapped    – callback(newSeats) after a successful swap
 */
export default function SwapSeatsDialog({
  booking,
  eventId,
  eventSeats = [],
  bookedSeats = [],
  heldSeats = [],
  onClose,
  onSwapped,
}) {
  const oldSeats = booking?.seats || [];
  const [input, setInput] = useState(oldSeats.join(", "));
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose?.();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const parseSeats = () => {
    return input
      .split(/[\s,;\n]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
  };

  // Local validation — surface mistakes before the API call.
  const seatById = new Map((eventSeats || []).map((s) => [s.id, s]));
  const bookedSet = new Set(bookedSeats || []);
  const heldSet = new Set(heldSeats || []);
  const oldSet = new Set(oldSeats);
  const requested = parseSeats();
  const dupes = requested.filter((s, i) => requested.indexOf(s) !== i);
  const unknown = requested.filter((s) => !seatById.has(s));
  const taken = requested.filter((s) => !oldSet.has(s) && (bookedSet.has(s) || heldSet.has(s)));
  const wrongTier = (() => {
    const oldTiers = new Set(oldSeats.map((s) => seatById.get(s)?.tier).filter(Boolean));
    const newTiers = new Set(requested.map((s) => seatById.get(s)?.tier).filter(Boolean));
    if (oldTiers.size === 0 || newTiers.size === 0) return false;
    if (newTiers.size > 1) return true;
    const oldOnly = [...oldTiers].sort().join(",");
    const newOnly = [...newTiers].sort().join(",");
    return oldOnly !== newOnly;
  })();
  const valid =
    requested.length === oldSeats.length &&
    dupes.length === 0 &&
    unknown.length === 0 &&
    taken.length === 0 &&
    !wrongTier;

  const doSwap = async () => {
    if (!valid) {
      toast.error("Fix validation errors before swapping");
      return;
    }
    if (requested.join(",") === oldSeats.join(",")) {
      toast("No change — seats are identical");
      onClose?.();
      return;
    }
    setBusy(true);
    try {
      const { data } = await api.post(`/organizer/bookings/${booking.booking_id}/swap-seats`, {
        new_seats: requested,
        reason: reason.trim() || undefined,
      });
      toast.success(`Seats swapped → ${data.new_seats.join(", ")}`);
      onSwapped?.(data.new_seats);
      onClose?.();
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Swap failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.7)" }}
      onClick={onClose}
      data-testid="swap-seats-dialog"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg border rounded-2xl p-8 max-h-[90vh] overflow-y-auto"
        style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}
      >
        <div className="flex items-start justify-between mb-5">
          <div>
            <div className="text-xs uppercase tracking-[0.3em] mb-1" style={{ color: "var(--accent)" }}>
              Swap seats
            </div>
            <h2 className="serif text-2xl">{booking?.user_name || booking?.user_email || "Booking"}</h2>
            <p className="text-xs mt-1 font-mono" style={{ color: "var(--text-dim)" }}>
              {booking?.booking_id}
            </p>
          </div>
          <button type="button" onClick={onClose} className="p-2 -mr-2" data-testid="swap-seats-close">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="mb-5 p-4 rounded-xl flex items-center gap-3" style={{ background: "var(--bg)", border: "1px solid var(--border)" }}>
          <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>Current</div>
          <div className="font-mono font-semibold flex-1" style={{ color: "var(--text)" }}>
            {oldSeats.join(", ")}
          </div>
          <ArrowRight className="w-4 h-4" style={{ color: "var(--accent)" }} />
          <div className="text-xs uppercase tracking-widest" style={{ color: "var(--accent)" }}>
            {requested.length} new
          </div>
        </div>

        <label className="block mb-4">
          <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>
            New seats (same count, same tier)
          </div>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="e.g. B-5, B-6"
            className="w-full font-mono"
            data-testid="swap-seats-input"
          />
          <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>
            Comma-separated. Currently {oldSeats.length} seat{oldSeats.length === 1 ? "" : "s"} — must enter exactly the same count.
          </div>
        </label>

        {/* Validation feedback */}
        {requested.length > 0 && (
          <div className="mb-4 space-y-1 text-xs" data-testid="swap-seats-validation">
            {requested.length !== oldSeats.length && (
              <div style={{ color: "var(--danger)" }}>
                ✗ Enter exactly {oldSeats.length} seat{oldSeats.length === 1 ? "" : "s"} (you have {requested.length})
              </div>
            )}
            {dupes.length > 0 && (
              <div style={{ color: "var(--danger)" }}>✗ Duplicate seat(s): {dupes.join(", ")}</div>
            )}
            {unknown.length > 0 && (
              <div style={{ color: "var(--danger)" }}>✗ Unknown seat(s): {unknown.join(", ")}</div>
            )}
            {taken.length > 0 && (
              <div style={{ color: "var(--danger)" }}>✗ Already taken: {taken.join(", ")}</div>
            )}
            {wrongTier && (
              <div style={{ color: "var(--danger)" }}>✗ New seats must be in the same tier as the original.</div>
            )}
            {valid && (
              <div style={{ color: "var(--success)" }}>✓ Looks good — ready to swap.</div>
            )}
          </div>
        )}

        <label className="block mb-6">
          <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>Reason (optional)</div>
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Customer request, accessibility, etc."
            className="w-full"
            data-testid="swap-seats-reason"
          />
          <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>
            Shown to the customer in the seat-swap confirmation email.
          </div>
        </label>

        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="btn-ghost" data-testid="swap-seats-cancel">
            Cancel
          </button>
          <button type="button" onClick={doSwap} disabled={busy || !valid} className="btn-primary" data-testid="swap-seats-confirm">
            {busy ? "Swapping…" : "Confirm swap"}
          </button>
        </div>
      </div>
    </div>
  );
}
