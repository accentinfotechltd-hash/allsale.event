import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import api from "@/lib/api";
import { toast } from "sonner";
import { Loader2, CheckCircle2, X, Gift, Calendar, MapPin } from "lucide-react";
import { useAuth } from "@/lib/auth";

/**
 * Public transfer claim page at /transfer/:transferId.
 *
 * Behavior:
 *   - Reads the transfer via GET /api/transfers/{id} (no auth needed).
 *   - If the user isn't logged in, prompts them to log in with the
 *     transfer's recipient email.
 *   - If logged in with the correct email, shows Accept / Decline buttons.
 *   - If transfer is already accepted/rejected/recalled/expired, shows the
 *     status with no actions.
 */
export default function TransferClaim() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [transfer, setTransfer] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null); // "accepted" | "rejected"

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get(`/transfers/${id}`);
        if (!cancelled) setTransfer(data);
      } catch {
        if (!cancelled) setTransfer(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [id]);

  if (loading) {
    return (
      <div className="max-w-md mx-auto px-4 py-20 text-center">
        <Loader2 className="w-5 h-5 animate-spin mx-auto" style={{ color: "var(--accent)" }} />
      </div>
    );
  }

  if (!transfer) {
    return (
      <div className="max-w-md mx-auto px-4 py-20 text-center">
        <div className="serif text-3xl mb-2">Transfer not found</div>
        <p style={{ color: "var(--text-muted)" }}>The link may have expired or been recalled.</p>
        <Link to="/events" className="btn-primary mt-6 inline-flex">Browse events</Link>
      </div>
    );
  }

  const status = transfer.status;
  const emailMatches = user && (user.email || "").trim().toLowerCase() === (transfer.recipient_email || "").trim().toLowerCase();

  const accept = async () => {
    setBusy(true);
    try {
      await api.post(`/transfers/${id}/accept`);
      setDone("accepted");
      toast.success("Ticket claimed — it's in your profile.");
      setTimeout(() => navigate("/profile"), 1500);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't accept");
    } finally {
      setBusy(false);
    }
  };

  const reject = async () => {
    if (!window.confirm("Decline this ticket? The sender keeps it.")) return;
    setBusy(true);
    try {
      await api.post(`/transfers/${id}/reject`);
      setDone("rejected");
      toast.success("Transfer declined.");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't decline");
    } finally {
      setBusy(false);
    }
  };

  const niceWhen = transfer.event?.date
    ? new Date(transfer.event.date).toLocaleString("en-US", {
        weekday: "short", month: "short", day: "numeric",
        hour: "numeric", minute: "2-digit",
      })
    : "—";

  return (
    <div className="max-w-md mx-auto px-4 py-12" data-testid="transfer-claim-page">
      <div className="border rounded-2xl overflow-hidden" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
        {transfer.event?.image_url && (
          <img src={transfer.event.image_url} alt="" className="w-full h-48 object-cover" />
        )}
        <div className="p-6">
          <div className="text-xs uppercase tracking-[0.3em] mb-2 flex items-center gap-1.5" style={{ color: "var(--accent)" }}>
            <Gift className="w-3.5 h-3.5" /> Ticket transfer
          </div>
          <div className="serif text-3xl mb-1" data-testid="transfer-event-title">{transfer.event?.title || "Event"}</div>
          <div className="text-sm flex items-center gap-3 mb-1" style={{ color: "var(--text-muted)" }}>
            <Calendar className="w-3.5 h-3.5" /> {niceWhen}
          </div>
          <div className="text-sm flex items-center gap-3 mb-4" style={{ color: "var(--text-muted)" }}>
            <MapPin className="w-3.5 h-3.5" /> {transfer.event?.venue}{transfer.event?.city ? `, ${transfer.event.city}` : ""}
          </div>
          <p className="text-sm mb-2" style={{ color: "var(--text)" }}>
            <strong>{transfer.sender_name}</strong> sent you {transfer.booking?.quantity || 1} ticket{(transfer.booking?.quantity || 1) === 1 ? "" : "s"}
            {transfer.booking?.tier_name ? ` (${transfer.booking.tier_name})` : ""}.
          </p>
          {transfer.note && (
            <p className="text-sm italic mt-2 px-3 py-2 rounded-md" style={{ background: "var(--bg-elev)", color: "var(--text-muted)" }}>
              &ldquo;{transfer.note}&rdquo;
            </p>
          )}
          {status !== "pending" && (
            <div className="mt-5 p-3 rounded-md text-sm" style={{ background: "var(--bg-elev)", color: "var(--text-dim)" }} data-testid="transfer-final-state">
              This transfer is {status}.
            </div>
          )}

          {status === "pending" && done === null && (
            <>
              {!user && (
                <div className="mt-5 text-sm" style={{ color: "var(--text-muted)" }}>
                  <p className="mb-3">Sign in to <strong>{transfer.recipient_email}</strong> to accept this ticket.</p>
                  <Link to={`/login?return_to=/transfer/${id}`} className="btn-primary inline-flex" data-testid="transfer-signin-btn">Sign in</Link>
                </div>
              )}
              {user && !emailMatches && (
                <div className="mt-5 p-3 rounded-md text-sm" style={{ background: "rgba(240,138,42,0.12)", color: "var(--accent)" }}>
                  This transfer was sent to <strong>{transfer.recipient_email}</strong>, but you're signed in as <strong>{user.email}</strong>. Sign out and sign back in with the correct email to accept.
                </div>
              )}
              {user && emailMatches && (
                <div className="mt-5 flex gap-2">
                  <button onClick={accept} disabled={busy} className="btn-primary flex-1 justify-center" data-testid="transfer-accept-btn">
                    {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                    Accept ticket
                  </button>
                  <button onClick={reject} disabled={busy} className="btn-ghost" data-testid="transfer-reject-btn">
                    <X className="w-4 h-4" /> Decline
                  </button>
                </div>
              )}
            </>
          )}

          {done === "accepted" && (
            <div className="mt-5 p-3 rounded-md text-sm flex items-center gap-2" style={{ background: "rgba(46,160,67,0.12)", color: "rgb(46,160,67)" }}>
              <CheckCircle2 className="w-4 h-4" /> Ticket claimed. Redirecting to your profile…
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
