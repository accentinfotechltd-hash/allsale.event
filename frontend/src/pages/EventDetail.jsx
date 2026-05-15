import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import SeatMap from "@/components/SeatMap";
import { Calendar, MapPin, User, ArrowRight, Plus, Minus, Tag, X, Bell, BellOff, Clock, ExternalLink } from "lucide-react";
import { toast } from "sonner";

export default function EventDetail() {
  const { eventId } = useParams();
  const { user } = useAuth();
  const nav = useNavigate();
  const [event, setEvent] = useState(null);
  const [selectedSeats, setSelectedSeats] = useState([]);
  const [tier, setTier] = useState(null);
  const [qty, setQty] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [codeInput, setCodeInput] = useState("");
  const [appliedCode, setAppliedCode] = useState(null); // {code, discount_amount, final_amount, kind, value}
  const [validatingCode, setValidatingCode] = useState(false);
  const [myWaitlist, setMyWaitlist] = useState(null); // null=unknown, []=not on, [{...}]=on
  const [joiningWl, setJoiningWl] = useState(false);

  const loadWaitlist = async () => {
    if (!user) { setMyWaitlist([]); return; }
    try {
      const { data } = await api.get(`/events/${eventId}/waitlist/me`);
      setMyWaitlist(data);
    } catch { setMyWaitlist([]); }
  };

  const load = async () => {
    try {
      const { data } = await api.get(`/events/${eventId}`);
      setEvent(data);
      if (!data.has_seatmap && data.tiers?.length) setTier(data.tiers[0].name);
    } catch (e) {
      toast.error("Event not found");
      nav("/events");
    }
  };

  useEffect(() => { load(); }, [eventId]);
  useEffect(() => { loadWaitlist(); /* eslint-disable-next-line */ }, [eventId, user?.user_id]);

  const joinWaitlist = async () => {
    if (!user) { nav("/login"); return; }
    setJoiningWl(true);
    try {
      await api.post(`/events/${eventId}/waitlist/join`, { tier_preference: tier || null, quantity: qty });
      toast.success("You're on the waitlist — we'll email you the moment a spot opens.");
      await loadWaitlist();
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Could not join waitlist");
    } finally { setJoiningWl(false); }
  };

  const leaveWaitlist = async () => {
    try {
      await api.delete(`/events/${eventId}/waitlist/me`);
      toast.success("Left the waitlist");
      await loadWaitlist();
    } catch { toast.error("Could not leave"); }
  };

  useEffect(() => {
    // Poll seat status every 8s for live updates
    if (!event?.has_seatmap) return;
    const i = setInterval(load, 8000);
    return () => clearInterval(i);
  }, [event?.has_seatmap, eventId]);

  // Clear applied code if the order changes (must be before any early return to obey rules of hooks)
  useEffect(() => {
    if (appliedCode) setAppliedCode(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tier, qty, selectedSeats.length]);

  if (!event) return <div className="text-center py-20" style={{ color: "var(--text-dim)" }}>Loading event...</div>;

  const date = new Date(event.date);
  const tierObj = event.tiers?.find((t) => t.name === tier);
  const subtotal = event.has_seatmap
    ? selectedSeats.length * event.seat_price
    : (tierObj?.price || 0) * qty;
  const total = appliedCode ? Math.max(0, subtotal - appliedCode.discount_amount) : subtotal;

  const applyCode = async () => {
    if (!codeInput.trim()) return;
    if (subtotal <= 0) { toast.error("Pick tickets/seats first"); return; }
    setValidatingCode(true);
    try {
      const { data } = await api.post("/discount-codes/validate", {
        code: codeInput.trim(),
        event_id: event.event_id,
        tier_name: event.has_seatmap ? null : tier,
        quantity: qty,
        seat_count: selectedSeats.length,
        subtotal,
      });
      setAppliedCode(data);
      toast.success(`Code applied: -$${data.discount_amount}`);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Invalid code");
    } finally { setValidatingCode(false); }
  };

  const onToggleSeat = (id) => {
    setSelectedSeats((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  };

  const onBook = async () => {
    if (!user) {
      toast("Please sign in to book", { description: "Redirecting to login..." });
      nav("/login");
      return;
    }
    if (event.has_seatmap && selectedSeats.length === 0) {
      toast.error("Pick at least one seat");
      return;
    }
    setSubmitting(true);
    try {
      const payload = event.has_seatmap
        ? { event_id: event.event_id, seats: selectedSeats }
        : { event_id: event.event_id, tier_name: tier, quantity: qty };
      if (appliedCode) payload.code = appliedCode.code;
      const { data } = await api.post("/bookings/hold", payload);
      nav(`/checkout/${data.booking_id}`);
    } catch (e) {
      toast.error(formatApiErrorDetail(e?.response?.data?.detail) || "Could not hold seats");
    } finally { setSubmitting(false); }
  };

  return (
    <div>
      {/* Banner */}
      <div className="relative h-[420px] overflow-hidden">
        <img src={event.banner_url || event.image_url} alt={event.title} className="w-full h-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-t from-[color:var(--bg)] via-black/60 to-transparent" />
        <div className="absolute inset-x-0 bottom-0 max-w-7xl mx-auto px-6 pb-10">
          <span className="chip chip-accent mb-4">{event.category}</span>
          <h1 className="serif text-5xl lg:text-7xl leading-[0.95] max-w-3xl" data-testid="event-title">{event.title}</h1>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-12 grid lg:grid-cols-[1fr_400px] gap-12">
        {/* Main */}
        <div>
          <div className="flex flex-wrap gap-5 mb-8 text-sm" style={{ color: "var(--text-muted)" }}>
            <div className="flex items-center gap-2"><Calendar className="w-4 h-4" style={{ color: "var(--accent)" }} /> {date.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" })}, {date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</div>
            <div className="flex items-center gap-2"><MapPin className="w-4 h-4" style={{ color: "var(--accent)" }} /> {event.venue}, {event.city}</div>
            <div className="flex items-center gap-2"><User className="w-4 h-4" style={{ color: "var(--accent)" }} /> {event.organizer_name}</div>
          </div>

          <p className="text-lg leading-relaxed max-w-3xl mb-12" style={{ color: "var(--text-muted)" }}>{event.description}</p>

          {event.has_seatmap && (
            <div className="border rounded-2xl p-6 lg:p-8" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
              <div className="mb-6">
                <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Pick your seats</div>
                <h2 className="serif text-3xl">Interactive seat map</h2>
                <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>${event.seat_price.toFixed(2)} per seat. Updates live every few seconds.</p>
              </div>
              <SeatMap
                rows={event.seat_rows}
                cols={event.seat_cols}
                booked={event.booked_seats || []}
                held={event.held_seats || []}
                selected={selectedSeats}
                aisles={event.aisles || []}
                backdropUrl={event.seat_map_image_url}
                onToggle={onToggleSeat}
              />
            </div>
          )}
        </div>

        {/* Booking sidebar */}
        <aside className="lg:sticky lg:top-24 lg:self-start">
          <div className="border rounded-2xl p-6" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
            <div className="text-xs uppercase tracking-[0.3em] mb-3" style={{ color: "var(--accent)" }}>Book your tickets</div>

            {!event.has_seatmap ? (
              <>
                <div className="space-y-3 mb-5">
                  {(event.tiers || []).map((t) => (
                    <button
                      type="button"
                      key={t.name}
                      onClick={() => setTier(t.name)}
                      className={`w-full text-left p-4 rounded-xl border transition`}
                      style={{
                        borderColor: tier === t.name ? "var(--accent)" : "var(--border)",
                        background: tier === t.name ? "var(--accent-soft)" : "var(--bg-elev)",
                      }}
                      data-testid={`tier-${t.name}`}
                    >
                      <div className="flex justify-between items-center">
                        <div>
                          <div className="serif text-xl">{t.name}</div>
                          <div className="text-xs" style={{ color: "var(--text-dim)" }}>{t.capacity} seats total</div>
                        </div>
                        <div className="serif text-2xl" style={{ color: "var(--accent)" }}>${t.price}</div>
                      </div>
                    </button>
                  ))}
                </div>

                <div className="flex items-center justify-between mb-4 px-1">
                  <span className="text-sm" style={{ color: "var(--text-muted)" }}>Quantity</span>
                  <div className="flex items-center gap-3">
                    <button onClick={() => setQty(Math.max(1, qty - 1))} className="w-8 h-8 rounded-full border" style={{ borderColor: "var(--border-strong)" }} data-testid="qty-minus"><Minus className="w-4 h-4 mx-auto" /></button>
                    <span className="serif text-xl w-8 text-center" data-testid="qty-value">{qty}</span>
                    <button onClick={() => setQty(Math.min(10, qty + 1))} className="w-8 h-8 rounded-full border" style={{ borderColor: "var(--border-strong)" }} data-testid="qty-plus"><Plus className="w-4 h-4 mx-auto" /></button>
                  </div>
                </div>
              </>
            ) : (
              <div className="mb-5">
                <div className="text-sm mb-2" style={{ color: "var(--text-muted)" }}>Selected seats</div>
                {selectedSeats.length === 0 ? (
                  <p className="text-sm" style={{ color: "var(--text-dim)" }}>Tap seats on the map to select</p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {selectedSeats.map((s) => <span key={s} className="chip chip-accent" data-testid={`selected-${s}`}>{s}</span>)}
                  </div>
                )}
              </div>
            )}

            <div className="border-t pt-4 space-y-2" style={{ borderColor: "var(--border)" }}>
              {/* Promo code input */}
              {appliedCode ? (
                <div className="flex items-center justify-between p-2.5 rounded-lg" style={{ background: "var(--accent-soft)", border: "1px solid var(--accent)" }} data-testid="applied-code">
                  <div className="flex items-center gap-2">
                    <Tag className="w-4 h-4" style={{ color: "var(--accent)" }} />
                    <span className="font-mono text-sm" style={{ color: "var(--accent)" }}>{appliedCode.code}</span>
                    <span className="text-xs" style={{ color: "var(--text-muted)" }}>−${appliedCode.discount_amount}</span>
                  </div>
                  <button onClick={() => { setAppliedCode(null); setCodeInput(""); }} className="text-xs flex items-center gap-1" style={{ color: "var(--text-muted)" }} data-testid="remove-code-btn">
                    <X className="w-3 h-3" /> Remove
                  </button>
                </div>
              ) : (
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <Tag className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: "var(--text-dim)" }} />
                    <input
                      value={codeInput}
                      onChange={(e) => setCodeInput(e.target.value.toUpperCase())}
                      placeholder="Promo code"
                      className="!pl-9 !py-2 text-sm"
                      data-testid="promo-code-input"
                      onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); applyCode(); } }}
                    />
                  </div>
                  <button
                    type="button"
                    onClick={applyCode}
                    disabled={!codeInput.trim() || validatingCode || subtotal <= 0}
                    className="btn-ghost !py-2 !px-4 text-sm"
                    data-testid="apply-code-btn"
                  >{validatingCode ? "..." : "Apply"}</button>
                </div>
              )}

              {appliedCode && subtotal > 0 && (
                <div className="flex justify-between text-sm pt-2" style={{ color: "var(--text-dim)" }}>
                  <span>Subtotal</span>
                  <span className="line-through">${subtotal.toFixed(2)}</span>
                </div>
              )}
              <div className="flex items-baseline justify-between pt-1">
                <span className="text-sm uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>Total</span>
                <span className="serif text-4xl" style={{ color: "var(--accent)" }} data-testid="total-price">${total.toFixed(2)}</span>
              </div>
            </div>

            <button onClick={onBook} disabled={submitting || total <= 0 || event.sold_out} className="btn-primary w-full justify-center mt-5" data-testid="book-now-btn">
              {submitting ? "Holding seats..." : event.sold_out ? "Sold out" : "Book now"} <ArrowRight className="w-4 h-4" />
            </button>
            <p className="text-xs mt-3 text-center" style={{ color: "var(--text-dim)" }}>You'll have 10 minutes to complete payment.</p>

            {/* Waitlist section (tier-based, sold-out events) */}
            {!event.has_seatmap && (event.sold_out || (myWaitlist && myWaitlist.length > 0)) && (
              <div className="mt-5 pt-5 border-t" style={{ borderColor: "var(--border)" }} data-testid="waitlist-section">
                {myWaitlist && myWaitlist.find((e) => e.status === "offered") ? (
                  (() => {
                    const offer = myWaitlist.find((e) => e.status === "offered");
                    return (
                      <div className="rounded-xl p-4" style={{ background: "rgba(52,211,153,0.08)", border: "1px solid var(--success)" }} data-testid="waitlist-offer-ready">
                        <div className="flex items-center gap-2 mb-2">
                          <Bell className="w-4 h-4" style={{ color: "var(--success)" }} />
                          <div className="font-medium" style={{ color: "var(--success)" }}>A spot just opened!</div>
                        </div>
                        <p className="text-xs mb-3" style={{ color: "var(--text-muted)" }}>
                          Your 15-min hold is ticking. Claim now before it rolls to the next person.
                        </p>
                        <button
                          onClick={() => nav(`/checkout/${offer.booking_id}`)}
                          className="btn-primary w-full justify-center"
                          data-testid="claim-waitlist-btn"
                        >
                          <ExternalLink className="w-4 h-4" /> Claim my spot
                        </button>
                      </div>
                    );
                  })()
                ) : myWaitlist && myWaitlist.find((e) => e.status === "waiting") ? (
                  (() => {
                    const w = myWaitlist.find((e) => e.status === "waiting");
                    return (
                      <div className="rounded-xl p-4" style={{ background: "var(--accent-soft)", border: "1px solid var(--accent)" }} data-testid="waitlist-waiting">
                        <div className="flex items-center gap-2 mb-1">
                          <Clock className="w-4 h-4" style={{ color: "var(--accent)" }} />
                          <div className="font-medium">You're on the waitlist</div>
                        </div>
                        <div className="text-sm mb-3" style={{ color: "var(--text-muted)" }}>
                          Position #{w.position} — we'll email you the moment a spot opens.
                        </div>
                        <button onClick={leaveWaitlist} className="btn-ghost text-xs" data-testid="leave-waitlist-btn">
                          <BellOff className="w-3 h-3" /> Leave waitlist
                        </button>
                      </div>
                    );
                  })()
                ) : (
                  <button
                    onClick={joinWaitlist}
                    disabled={joiningWl}
                    className="btn-ghost w-full justify-center"
                    data-testid="join-waitlist-btn"
                  >
                    <Bell className="w-4 h-4" /> {joiningWl ? "Joining…" : "Notify me when a spot opens"}
                  </button>
                )}
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
