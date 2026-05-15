import { useEffect, useState, useRef } from "react";
import { useSearchParams, Link } from "react-router-dom";
import api from "@/lib/api";
import { CheckCircle2, Ticket, ArrowRight } from "lucide-react";

export default function CheckoutSuccess() {
  const [params] = useSearchParams();
  const sessionId = params.get("session_id");
  const [status, setStatus] = useState("polling");
  const [bookingId, setBookingId] = useState(null);
  const attempts = useRef(0);

  useEffect(() => {
    if (!sessionId) {
      setStatus("error");
      return;
    }
    const poll = async () => {
      try {
        const { data } = await api.get(`/checkout/status/${sessionId}`);
        if (data.payment_status === "paid") {
          setStatus("paid");
          setBookingId(data.booking_id);
          return;
        }
        if (data.status === "expired" || data.payment_status === "expired") {
          setStatus("expired");
          return;
        }
        attempts.current += 1;
        if (attempts.current < 10) setTimeout(poll, 2000);
        else setStatus("timeout");
      } catch {
        setStatus("error");
      }
    };
    poll();
  }, [sessionId]);

  return (
    <div className="max-w-2xl mx-auto px-6 py-20 text-center">
      {status === "polling" && (
        <>
          <div className="serif text-4xl mb-3">Confirming your payment</div>
          <p style={{ color: "var(--text-muted)" }}>Hang tight, this usually takes a few seconds.</p>
          <div className="mt-8 inline-block w-8 h-8 border-2 rounded-full animate-spin" style={{ borderColor: "var(--accent)", borderTopColor: "transparent" }} />
        </>
      )}
      {status === "paid" && (
        <div className="fade-up">
          <div className="inline-flex items-center justify-center w-20 h-20 rounded-full mb-6" style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>
            <CheckCircle2 className="w-10 h-10" />
          </div>
          <h1 className="serif text-5xl mb-3">You're in.</h1>
          <p className="mb-8" style={{ color: "var(--text-muted)" }}>Your tickets are ready. We've sent a confirmation with your QR code.</p>
          <div className="flex justify-center gap-3 flex-wrap">
            <Link to="/profile" className="btn-primary" data-testid="success-tickets-btn">
              <Ticket className="w-4 h-4" /> View my tickets <ArrowRight className="w-4 h-4" />
            </Link>
            {bookingId && <Link to={`/profile`} className="btn-ghost">Booking #{bookingId.slice(-6)}</Link>}
          </div>
        </div>
      )}
      {(status === "error" || status === "timeout") && (
        <>
          <h1 className="serif text-4xl mb-3">Something went sideways</h1>
          <p style={{ color: "var(--text-muted)" }}>If money was deducted, your tickets will appear in your profile within a few minutes.</p>
          <Link to="/profile" className="btn-primary mt-6 inline-flex">View tickets</Link>
        </>
      )}
      {status === "expired" && (
        <>
          <h1 className="serif text-4xl mb-3">Session expired</h1>
          <p style={{ color: "var(--text-muted)" }}>Your hold expired before checkout completed.</p>
          <Link to="/events" className="btn-primary mt-6 inline-flex">Browse events</Link>
        </>
      )}
    </div>
  );
}
