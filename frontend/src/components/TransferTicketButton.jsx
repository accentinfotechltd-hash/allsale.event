import { useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Send, Loader2, X } from "lucide-react";

/**
 * "Send to friend" button placed next to a paid ticket on Profile.
 * Opens an inline dialog → POSTs /me/bookings/{id}/transfer → toast.
 *
 * After a transfer is initiated, the original owner keeps the ticket
 * (recallable) until the recipient accepts. The recipient gets an email
 * with a claim link.
 */
export default function TransferTicketButton({ bookingId, eventTitle }) {
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!email || !email.includes("@")) {
      toast.error("Enter a valid email");
      return;
    }
    setBusy(true);
    try {
      await api.post(`/me/bookings/${bookingId}/transfer`, {
        recipient_email: email.trim(),
        note: note.trim() || undefined,
      });
      toast.success(`Transfer sent to ${email}. They have 7 days to accept.`);
      setOpen(false);
      setEmail("");
      setNote("");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't send transfer");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="btn-ghost !py-1.5 !px-3 text-xs"
        data-testid={`transfer-btn-${bookingId}`}
      >
        <Send className="w-3 h-3" /> Send
      </button>

      {open && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center p-4" style={{ background: "rgba(0,0,0,0.6)" }} onClick={() => setOpen(false)}>
          <div
            className="w-full max-w-md rounded-2xl p-6 border"
            style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}
            onClick={(e) => e.stopPropagation()}
            data-testid="transfer-dialog"
          >
            <div className="flex justify-between items-start mb-4">
              <div>
                <div className="serif text-xl">Transfer ticket</div>
                <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>{eventTitle}</div>
              </div>
              <button onClick={() => setOpen(false)} className="p-1" data-testid="transfer-close-btn">
                <X className="w-4 h-4" style={{ color: "var(--text-dim)" }} />
              </button>
            </div>

            <label className="text-xs" style={{ color: "var(--text-dim)" }}>Recipient email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="friend@example.com"
              className="w-full mb-3"
              data-testid="transfer-email-input"
              autoFocus
            />
            <label className="text-xs" style={{ color: "var(--text-dim)" }}>Note (optional)</label>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              placeholder="Hey! Couldn't make it — enjoy the show."
              className="w-full mb-3"
              data-testid="transfer-note-input"
            />
            <p className="text-[11px] mb-4" style={{ color: "var(--text-dim)" }}>
              You can recall this transfer anytime before the recipient accepts. Once accepted, your ticket and QR code are reassigned to them.
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setOpen(false)} className="btn-ghost !py-2" data-testid="transfer-cancel-btn">Cancel</button>
              <button onClick={submit} disabled={busy} className="btn-primary !py-2" data-testid="transfer-submit-btn">
                {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                Send transfer
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
