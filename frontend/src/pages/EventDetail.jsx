import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import api, { formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import SeatMap from "@/components/SeatMap";
import DemandSparkline from "@/components/DemandSparkline";
import useEventLiveUpdates from "@/lib/useEventLiveUpdates";
import { ContactOrganizerButton } from "@/components/ContactOrganizerDialog";
import FollowOrganizerButton from "@/components/FollowOrganizerButton";
import AffiliateBanner from "@/components/AffiliateBanner";
import { Calendar, MapPin, User, ArrowRight, Plus, Minus, Tag, X, Bell, BellOff, Clock, ExternalLink, Wifi } from "lucide-react";
import { toast } from "sonner";
import { formatMoney } from "@/lib/currencies";

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
  const [demand, setDemand] = useState([]);

  // Fire a single anonymous-friendly view ping (debounced to once per minute per browser tab)
  useEffect(() => {
    if (!eventId) return;
    const key = `aura:view:${eventId}`;
    try {
      const last = sessionStorage.getItem(key);
      if (last && Date.now() - parseInt(last, 10) < 60_000) return;
      sessionStorage.setItem(key, String(Date.now()));
    } catch { /* SSR / private mode */ }
    api.post(`/events/${eventId}/view`).catch(() => {});
  }, [eventId]);

  // Pull 7-day demand sparkline (refresh every 2 min)
  useEffect(() => {
    if (!eventId) return;
    let cancelled = false;
    const fetchDemand = () => {
      api.get(`/events/${eventId}/demand`)
        .then(({ data }) => { if (!cancelled) setDemand(data.items || []); })
        .catch(() => {});
    };
    fetchDemand();
    const id = setInterval(fetchDemand, 120_000);
    return () => { cancelled = true; clearInterval(id); };
  }, [eventId]);

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
      const payload = event.has_seatmap
        ? { quantity: Math.max(1, selectedSeats.length || 1) }
        : { tier_preference: tier || null, quantity: qty };
      await api.post(`/events/${eventId}/waitlist/join`, payload);
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
    // Background safety net: refresh full event every 60s in case WS misses a delta.
    if (!event) return;
    const i = setInterval(load, 60000);
    return () => clearInterval(i);
  }, [event?.event_id, eventId]);

  // Live WebSocket: applies deltas in real time (no 8s lag).
  const { connected: liveConnected } = useEventLiveUpdates(eventId, {
    onSnapshot: (snap) => {
      setEvent((prev) => prev ? {
        ...prev,
        booked_seats: snap.booked || prev.booked_seats,
        held_seats: snap.held || prev.held_seats,
        sold_out: typeof snap.sold_out === "boolean" ? snap.sold_out : prev.sold_out,
        tier_status: snap.tier_status?.length ? snap.tier_status : prev.tier_status,
        surging: typeof snap.surging === "boolean" ? snap.surging : prev.surging,
        tiers: snap.tier_status?.length && Array.isArray(prev.tiers)
          ? prev.tiers.map((t) => {
              const ts = snap.tier_status.find((s) => s.name === t.name);
              return ts ? { ...t, effective_price: ts.effective_price, surging: ts.surging } : t;
            })
          : prev.tiers,
      } : prev);
    },
    onSeat: ({ seat_id, status }) => {
      setEvent((prev) => {
        if (!prev) return prev;
        const booked = new Set(prev.booked_seats || []);
        const held = new Set(prev.held_seats || []);
        if (status === "booked") { booked.add(seat_id); held.delete(seat_id); }
        else if (status === "held") { held.add(seat_id); booked.delete(seat_id); }
        else if (status === "free") { booked.delete(seat_id); held.delete(seat_id); }
        return { ...prev, booked_seats: Array.from(booked), held_seats: Array.from(held) };
      });
      // Toast if someone else grabbed a seat we had selected (rare but possible)
      setSelectedSeats((sel) => {
        if (status !== "free" && sel.includes(seat_id) && !selectedSeats.includes(seat_id)) return sel;
        return sel;
      });
    },
    onTier: ({ tier_status, sold_out, surging }) => {
      setEvent((prev) => prev ? {
        ...prev,
        sold_out, surging,
        tier_status,
        tiers: Array.isArray(prev.tiers)
          ? prev.tiers.map((t) => {
              const ts = (tier_status || []).find((s) => s.name === t.name);
              return ts ? { ...t, effective_price: ts.effective_price, surging: ts.surging } : t;
            })
          : prev.tiers,
      } : prev);
    },
  });

  // Clear applied code if the order changes (must be before any early return to obey rules of hooks)
  useEffect(() => {
    if (appliedCode) setAppliedCode(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tier, qty, selectedSeats.length]);

  if (!event) return <div className="text-center py-20" style={{ color: "var(--text-dim)" }}>Loading event...</div>;

  const date = new Date(event.date);
  const tierObj = event.tiers?.find((t) => t.name === tier);
  const tierEffectivePrice = tierObj?.effective_price ?? tierObj?.price ?? 0;
  const seatPriceFor = (seatId) => {
    const sections = event.seatmap_sections || [];
    if (!sections.length) return event.seat_price;
    try {
      const rowIdx = seatId.charCodeAt(0) - "A".charCodeAt(0);
      const sorted = [...sections].sort((a, b) => (a.after_row || 0) - (b.after_row || 0));
      const boundaries = [-1, ...sorted.map((s) => s.after_row || 0), 1e6];
      for (let i = 1; i < boundaries.length; i++) {
        if (boundaries[i - 1] < rowIdx && rowIdx <= boundaries[i]) {
          if (i === 1) return event.seat_price; // front zone
          const sec = sorted[i - 2];
          return sec?.price ?? event.seat_price;
        }
      }
    } catch { /* fall through */ }
    return event.seat_price;
  };
  const subtotal = event.has_seatmap
    ? selectedSeats.reduce((sum, s) => sum + (seatPriceFor(s) || 0), 0)
    : tierEffectivePrice * qty;
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
      <div className="relative h-[260px] sm:h-[360px] lg:h-[420px] overflow-hidden">
        <img src={event.banner_url || event.image_url} alt={event.title} className="w-full h-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-t from-[color:var(--bg)] via-black/60 to-transparent" />
        <div className="absolute inset-x-0 bottom-0 max-w-7xl mx-auto px-4 sm:px-6 pb-6 sm:pb-10">
          <div className="flex flex-wrap items-center gap-2 mb-3 sm:mb-4">
            <span className="chip chip-accent">{event.category}</span>
            {event.is_past && (
              <span
                data-testid="event-past-badge"
                className="inline-flex items-center px-3 py-1 rounded-full text-[11px] uppercase tracking-widest font-medium"
                style={{ background: "rgba(255,255,255,0.9)", color: "#222" }}
              >
                Past event
              </span>
            )}
          </div>
          <h1 className="serif text-4xl sm:text-5xl lg:text-7xl leading-[0.95] max-w-3xl" data-testid="event-title">{event.title}</h1>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 sm:py-12 grid lg:grid-cols-[1fr_400px] gap-8 lg:gap-12">
        {/* Main */}
        <div>
          <AffiliateBanner />
          <div className="flex flex-wrap gap-3 sm:gap-5 mb-6 sm:mb-8 text-sm" style={{ color: "var(--text-muted)" }}>
            <div className="flex items-center gap-2"><Calendar className="w-4 h-4 flex-shrink-0" style={{ color: "var(--accent)" }} /> {date.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" })}, {date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</div>
            <div className="flex items-center gap-2"><MapPin className="w-4 h-4 flex-shrink-0" style={{ color: "var(--accent)" }} /> {event.venue}, {event.city}</div>
            <div className="flex items-center gap-2">
              <User className="w-4 h-4 flex-shrink-0" style={{ color: "var(--accent)" }} />
              {event.organizer_id ? (
                <Link
                  to={`/organizers/${event.organizer_id}`}
                  className="hover:underline"
                  style={{ color: "var(--text)" }}
                  data-testid="event-detail-organizer-link"
                >
                  {event.organizer_name}
                </Link>
              ) : (
                <span>{event.organizer_name}</span>
              )}
              {event.organizer_id && (
                <ContactOrganizerButton
                  organizerId={event.organizer_id}
                  organizerName={event.organizer_name}
                  eventId={event.event_id}
                  eventTitle={event.title}
                  user={user}
                  className="ml-2 text-xs underline"
                  label="Contact"
                  testid="event-detail-contact-organizer-btn"
                />
              )}
              {event.organizer_id && (
                <FollowOrganizerButton
                  organizerId={event.organizer_id}
                  organizerName={event.organizer_name}
                  size="sm"
                />
              )}
            </div>
          </div>

          <p className="text-base sm:text-lg leading-relaxed max-w-3xl mb-10 sm:mb-12" style={{ color: "var(--text-muted)" }}>{event.description}</p>

          {event.has_seatmap && (
            <div className="border rounded-2xl p-4 sm:p-6 lg:p-8" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
              <div className="mb-5 sm:mb-6">
                <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Pick your seats</div>
                <h2 className="serif text-2xl sm:text-3xl">Interactive seat map</h2>
                <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>{formatMoney(event.seat_price, event.currency)} per seat. Updates live every few seconds.</p>
              </div>
              <SeatMap
                rows={event.seat_rows}
                cols={event.seat_cols}
                booked={event.booked_seats || []}
                held={event.held_seats || []}
                selected={selectedSeats}
                aisles={event.aisles || []}
                sections={event.seatmap_sections || []}
                curved={!!event.seatmap_curved}
                numberingRtl={!!event.seatmap_numbering_rtl}
                backdropUrl={event.seat_map_image_url}
                backdropOpacity={event.seatmap_backdrop_opacity ?? 0.4}
                backdropOffsetY={event.seatmap_backdrop_offset_y ?? 0}
                backdropOffsetX={event.seatmap_backdrop_offset_x ?? 0}
                backdropScale={event.seatmap_backdrop_scale ?? 1}
                onToggle={onToggleSeat}
              />
            </div>
          )}
        </div>

        {/* Booking sidebar */}
        <aside className="lg:sticky lg:top-24 lg:self-start">
          <div className="border rounded-2xl p-6" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
            <div className="flex items-center justify-between mb-3">
              <div className="text-xs uppercase tracking-[0.3em]" style={{ color: "var(--accent)" }}>Book your tickets</div>
              {liveConnected && (
                <span
                  className="inline-flex items-center gap-1 text-[10px] uppercase tracking-widest"
                  style={{ color: "var(--success)" }}
                  data-testid="live-indicator"
                  title="Live seat updates"
                >
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: "var(--success)", boxShadow: "0 0 8px var(--success)" }} />
                  Live
                </span>
              )}
            </div>
            {demand.length > 0 && (
              <div className="mb-4 pb-4 border-b" style={{ borderColor: "var(--border)" }}>
                <DemandSparkline items={demand} />
              </div>
            )}

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
                        <div className="text-right">
                          {t.surging && t.effective_price > t.price ? (
                            <>
                              <div className="text-[10px] uppercase tracking-widest" style={{ color: "var(--danger)" }}>High demand</div>
                              <div className="serif text-2xl" style={{ color: "var(--accent)" }}>{formatMoney(t.effective_price, event.currency, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}</div>
                              <div className="text-xs line-through" style={{ color: "var(--text-dim)" }}>{formatMoney(t.price, event.currency, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}</div>
                            </>
                          ) : (
                            <div className="serif text-2xl" style={{ color: "var(--accent)" }}>{formatMoney(t.price, event.currency, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}</div>
                          )}
                        </div>
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
                  <span className="line-through">{formatMoney(subtotal, event.currency)}</span>
                </div>
              )}
              <div className="flex items-baseline justify-between pt-1">
                <span className="text-sm uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>Total</span>
                <span className="serif text-4xl" style={{ color: "var(--accent)" }} data-testid="total-price">{formatMoney(total, event.currency)}</span>
              </div>
            </div>

            <button onClick={onBook} disabled={submitting || total <= 0 || event.sold_out || event.is_past} className="btn-primary w-full justify-center mt-5" data-testid="book-now-btn">
              {submitting ? "Holding seats..." : event.is_past ? "Event ended" : event.sold_out ? "Sold out" : "Book now"} <ArrowRight className="w-4 h-4" />
            </button>
            {event.is_past ? (
              <p className="text-xs mt-3 text-center" style={{ color: "var(--text-dim)" }} data-testid="event-ended-note">This event has finished. Browse upcoming events instead.</p>
            ) : (
              <p className="text-xs mt-3 text-center" style={{ color: "var(--text-dim)" }}>You'll have 10 minutes to complete payment.</p>
            )}

            {/* Waitlist section (sold-out events) */}
            {!event.is_past && (event.sold_out || (myWaitlist && myWaitlist.length > 0)) && (
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
                        {offer.offered_seats && offer.offered_seats.length > 0 && (
                          <div className="text-xs mb-2 flex flex-wrap gap-1.5">
                            {offer.offered_seats.map((s) => (
                              <span key={s} className="chip chip-accent" style={{ fontSize: "0.65rem" }}>{s}</span>
                            ))}
                          </div>
                        )}
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
