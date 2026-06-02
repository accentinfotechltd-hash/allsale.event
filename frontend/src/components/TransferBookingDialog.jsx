/**
 * TransferBookingDialog — reassign a paid booking to another attendee.
 *
 * Replaces a refund when the original holder can't make it but someone else
 * can take their seat. Sends a fresh QR ticket to the new email and a notice
 * to the previous holder.
 */
import { useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { X, Send } from "lucide-react";

export default function TransferBookingDialog({ booking, onClose, onTransferred }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  if (!booking) return null;

  const submit = async (e) => {
    e.preventDefault();
    if (!email.trim()) return toast.error("Recipient email is required");
    setBusy(true);
    try {
      const { data } = await api.post(`/organizer/bookings/${booking.booking_id}/transfer`, {
        email: email.trim(),
        name: name.trim() || null,
        reason: reason.trim() || null,
      });
      toast.success(`Transferred to ${data.new_email}`);
      onTransferred?.(data);
      onClose?.();
    } catch (err) {
      const d = err?.response?.data?.detail;
      const msg = typeof d === "string" ? d : "Transfer failed";
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={onClose} data-testid="transfer-dialog">
      <div
        className="w-full max-w-md rounded-2xl border shadow-2xl"
        style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-5 border-b" style={{ borderColor: "var(--border)" }}>
          <div>
            <div className="text-xs uppercase tracking-[0.3em]" style={{ color: "var(--accent)" }}>Transfer booking</div>
            <div className="serif text-xl mt-1">Re-assign to another attendee</div>
          </div>
          <button onClick={onClose} className="p-1" data-testid="transfer-close-btn">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={submit} className="p-5 space-y-4">
          <div className="text-sm p-3 rounded-lg" style={{ background: "var(--bg-elev)" }}>
            <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>Current holder</div>
            <div className="font-medium">{booking.user_name}</div>
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>{booking.user_email}</div>
            <div className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              {booking.seats?.length ? booking.seats.join(", ") : booking.tier_name} · {booking.quantity} ticket{booking.quantity === 1 ? "" : "s"}
            </div>
          </div>

          <div>
            <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>New recipient email *</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="new.attendee@example.com"
              className="w-full"
              data-testid="transfer-email-input"
              required
            />
            <p className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>
              If they have an account, the booking appears in their My Tickets. Otherwise they get the ticket by email.
            </p>
          </div>

          <div>
            <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>Recipient name (optional)</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Jane Doe"
              className="w-full"
              data-testid="transfer-name-input"
            />
          </div>

          <div>
            <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>Reason (internal note, optional)</label>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Original guest can't attend"
              className="w-full"
              data-testid="transfer-reason-input"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="btn-ghost !py-2 !px-4 text-sm" data-testid="transfer-cancel-btn">Cancel</button>
            <button type="submit" disabled={busy} className="btn-primary" data-testid="transfer-submit-btn">
              <Send className="w-4 h-4" /> {busy ? "Transferring…" : "Transfer & email ticket"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
