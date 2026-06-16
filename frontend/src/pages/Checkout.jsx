import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { formatApiErrorDetail } from "@/lib/api";
import Countdown from "@/components/Countdown";
import { CreditCard, Lock, ArrowRight } from "lucide-react";
import { toast } from "sonner";
import { formatMoney } from "@/lib/currencies";

export default function Checkout() {
  const { bookingId } = useParams();
  const nav = useNavigate();
  const [booking, setBooking] = useState(null);
  const [paying, setPaying] = useState(false);
  const [expired, setExpired] = useState(false);
  const [stripeMode, setStripeMode] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/bookings/${bookingId}`);
        setBooking(data);
      } catch (e) {
        toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Booking not found");
        nav("/events");
      }
    })();
    // Query backend so we show the truthful Stripe mode (test/live) under the
    // Pay button rather than a hardcoded string. The endpoint is public-safe;
    // it returns just `{configured, mode}` with no secrets.
    (async () => {
      try {
        const { data } = await api.get("/payments/mode");
        setStripeMode(data?.mode || null);
      } catch { /* silent — fall back to nothing instead of a wrong label */ }
    })();
  }, [bookingId, nav]);

  const onPay = async () => {
    if (expired) return;
    setPaying(true);
    try {
      const origin = window.location.origin;
      const { data } = await api.post("/checkout/session", {
        booking_id: bookingId,
        origin_url: origin,
      });
      if (data.direct_paid) {
        // Booking was fully covered (gift card / comp) — skip Stripe.
        window.location.href = `/checkout/success?booking_id=${bookingId}`;
        return;
      }
      window.location.href = data.url;
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Checkout failed");
      setPaying(false);
    }
  };

  if (!booking) return <div className="text-center py-20" style={{ color: "var(--text-dim)" }}>Loading...</div>;

  return (
    <div className="max-w-4xl mx-auto px-6 py-12">
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="text-xs uppercase tracking-[0.3em] mb-1" style={{ color: "var(--accent)" }}>Almost there</div>
          <h1 className="serif text-4xl">Checkout</h1>
        </div>
        <Countdown expiresAt={booking.hold_expires_at} onExpire={() => setExpired(true)} />
      </div>

      <div className="grid md:grid-cols-[1.4fr_1fr] gap-8">
        <div className="border rounded-2xl overflow-hidden" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
          <div className="aspect-[16/9] relative">
            <img src={booking.event_image} alt={booking.event_title} className="w-full h-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-t from-black/80 to-transparent" />
            <div className="absolute bottom-0 inset-x-0 p-5">
              <h2 className="serif text-3xl">{booking.event_title}</h2>
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                {new Date(booking.event_date).toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" })} · {booking.event_venue}
              </p>
            </div>
          </div>
          <div className="p-6 space-y-3 text-sm">
            <Row label="Type" value={booking.tier_name} />
            {booking.seats?.length > 0 ? (
              <Row label="Seats" value={booking.seats.join(", ")} />
            ) : (
              <Row label="Quantity" value={booking.quantity} />
            )}
            <Row label="Booking ID" value={booking.booking_id} mono />
          </div>
        </div>

        <div className="border rounded-2xl p-6 space-y-5" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
          {/* Single "fees" line as agreed — buyer sees ticket subtotal + a
              combined service fee + the grand total. We never expose the
              platform-vs-Stripe split to the buyer. */}
          {booking.service_fee > 0 && (
            <div className="space-y-1.5 text-sm pb-3 border-b" style={{ borderColor: "var(--border)" }} data-testid="checkout-fees-breakdown">
              <div className="flex justify-between" style={{ color: "var(--text-muted)" }}>
                <span>Tickets</span>
                <span data-testid="checkout-ticket-subtotal">{formatMoney(booking.face_value ?? booking.subtotal ?? booking.amount, booking.currency || "NZD")}</span>
              </div>
              <div className="flex justify-between" style={{ color: "var(--text-muted)" }}>
                <span>Service fee</span>
                <span data-testid="checkout-service-fee">{formatMoney(booking.service_fee, booking.currency || "NZD")}</span>
              </div>
            </div>
          )}
          <div>
            <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--text-dim)" }}>Payable now</div>
            <div className="serif text-5xl" style={{ color: "var(--accent)" }} data-testid="checkout-total">{formatMoney(booking.amount, booking.currency || "NZD")}</div>
            <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>{(booking.currency || "NZD")} · all fees included</div>
          </div>

          <button onClick={onPay} disabled={paying || expired} className="btn-primary w-full justify-center" data-testid="pay-stripe-btn">
            <CreditCard className="w-4 h-4" />
            {paying ? "Redirecting..." : expired ? "Hold expired" : "Pay with Stripe"}
            {!paying && !expired && <ArrowRight className="w-4 h-4" />}
          </button>

          <div className="flex items-center gap-2 text-xs" style={{ color: "var(--text-dim)" }} data-testid="stripe-mode-label">
            <Lock className="w-3 h-3" /> Secured by Stripe
            {stripeMode === "live" || stripeMode === "live (restricted)" ? null : stripeMode ? <span> · {stripeMode === "test" ? "Test mode" : stripeMode}</span> : null}
          </div>

          {expired && (
            <div className="text-sm p-3 rounded-lg" style={{ background: "rgba(239,68,68,0.1)", color: "var(--danger)" }}>
              Your hold has expired. Please start a new booking.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, mono }) {
  return (
    <div className="flex justify-between gap-4">
      <span style={{ color: "var(--text-muted)" }}>{label}</span>
      <span className={mono ? "font-mono text-xs" : "text-right"} style={{ color: "var(--text)" }}>{value}</span>
    </div>
  );
}
