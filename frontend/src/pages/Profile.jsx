import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Calendar, MapPin, Download, QrCode } from "lucide-react";

export default function Profile() {
  const { user } = useAuth();
  const [bookings, setBookings] = useState([]);
  const [active, setActive] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/me/bookings");
        setBookings(data);
      } catch { /* noop */ }
    })();
  }, []);

  if (!user) return (
    <div className="text-center py-20">
      <p style={{ color: "var(--text-muted)" }}>Please sign in to view your tickets.</p>
      <Link to="/login" className="btn-primary mt-4 inline-flex">Sign in</Link>
    </div>
  );

  const paid = bookings.filter((b) => b.status === "paid");
  const pending = bookings.filter((b) => b.status !== "paid");

  return (
    <div className="max-w-5xl mx-auto px-6 py-12">
      <div className="mb-10">
        <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Your account</div>
        <h1 className="serif text-5xl">{user.name}</h1>
        <p style={{ color: "var(--text-muted)" }}>{user.email} · <span className="capitalize">{user.role}</span></p>
      </div>

      <h2 className="serif text-2xl mb-4">My tickets</h2>
      {paid.length === 0 ? (
        <p className="mb-10 p-6 border rounded-xl" style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}>
          No tickets yet. <Link to="/events" style={{ color: "var(--accent)" }}>Browse events</Link>
        </p>
      ) : (
        <div className="grid md:grid-cols-2 gap-4 mb-12">
          {paid.map((b) => (
            <div key={b.booking_id} className="border rounded-2xl overflow-hidden flex" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }} data-testid={`ticket-${b.booking_id}`}>
              <div className="w-28 relative">
                <img src={b.event_image} alt="" className="w-full h-full object-cover" />
                <div className="absolute inset-0 bg-gradient-to-r from-transparent to-[color:var(--bg-card)]" />
              </div>
              <div className="flex-1 p-4">
                <div className="serif text-xl leading-tight mb-1">{b.event_title}</div>
                <div className="text-xs mb-3" style={{ color: "var(--text-muted)" }}>
                  <Calendar className="w-3 h-3 inline mr-1" /> {new Date(b.event_date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                  <MapPin className="w-3 h-3 inline ml-3 mr-1" /> {b.event_venue}
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs" style={{ color: "var(--text-dim)" }}>{b.tier_name} · {b.seats?.length || b.quantity}x</span>
                  <button onClick={() => setActive(b)} className="btn-ghost !py-1.5 !px-3 text-xs" data-testid={`show-qr-${b.booking_id}`}>
                    <QrCode className="w-3 h-3" /> Show QR
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {pending.length > 0 && (
        <>
          <h2 className="serif text-2xl mb-4">Pending</h2>
          <div className="space-y-2 mb-12">
            {pending.map((b) => (
              <div key={b.booking_id} className="p-4 border rounded-xl flex justify-between items-center" style={{ borderColor: "var(--border)" }}>
                <div>
                  <div className="font-medium">{b.event_title}</div>
                  <div className="text-xs" style={{ color: "var(--text-dim)" }}>{b.status}</div>
                </div>
                <Link to={`/checkout/${b.booking_id}`} className="btn-primary !py-1.5 !px-4 text-xs">Continue</Link>
              </div>
            ))}
          </div>
        </>
      )}

      {/* QR Modal */}
      {active && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-6" onClick={() => setActive(null)} data-testid="qr-modal">
          <div className="glass max-w-md w-full p-8 rounded-2xl text-center" onClick={(e) => e.stopPropagation()}>
            <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Your ticket</div>
            <h3 className="serif text-3xl mb-1">{active.event_title}</h3>
            <p className="text-sm mb-6" style={{ color: "var(--text-muted)" }}>{new Date(active.event_date).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })} · {active.event_venue}</p>

            {active.qr_code ? (
              <img src={active.qr_code} alt="QR" className="w-64 h-64 mx-auto bg-white p-3 rounded-xl" />
            ) : (
              <div className="w-64 h-64 mx-auto bg-white/5 flex items-center justify-center rounded-xl">Generating...</div>
            )}

            <div className="mt-6 grid grid-cols-2 gap-3 text-sm">
              <div className="text-left"><div style={{ color: "var(--text-dim)" }}>Type</div><div>{active.tier_name}</div></div>
              <div className="text-left"><div style={{ color: "var(--text-dim)" }}>{active.seats?.length ? "Seats" : "Qty"}</div><div>{active.seats?.length ? active.seats.join(", ") : active.quantity}</div></div>
            </div>
            <button onClick={() => setActive(null)} className="btn-ghost mt-6">Close</button>
          </div>
        </div>
      )}
    </div>
  );
}
