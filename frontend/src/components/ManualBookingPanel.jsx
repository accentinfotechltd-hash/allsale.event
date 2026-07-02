import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Banknote, CreditCard, Clock, Check, X, Plus, RotateCw } from "lucide-react";

/**
 * ManualBookingPanel — box-office / cash / offline-card sales.
 *
 * Admins and event organizers use this to create bookings on the spot
 * (someone standing at the door paying cash, over-the-phone card, comp
 * ticket for press, etc.) without going through Stripe. Two modes:
 *   - **Paid now**: booking lands as `paid` + e-ticket PDF emailed instantly
 *   - **24h hold**: seats blocked, buyer emailed "come pay to confirm"; the
 *     panel below lists pending holds with Confirm / Cancel actions.
 */
export default function ManualBookingPanel({ eventId, event }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [summary, setSummary] = useState({});
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/organizer/events/${eventId}/manual-bookings`);
      setItems(data.items || []);
      setSummary(data.summary || {});
    } catch (e) {
      // Silent — this panel is optional. Errors surface in the modal instead.
    } finally { setLoading(false); }
  }, [eventId]);

  useEffect(() => { load(); }, [load]);

  // When someone lands with #manual-booking (e.g. from the "Sell cash/card"
  // shortcut on the organizer dashboard), scroll the panel into view + flash
  // its border so the box-office feature is impossible to miss.
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.location.hash !== "#manual-booking") return;
    const el = document.getElementById("manual-booking");
    if (!el) return;
    const t = setTimeout(() => {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
      el.classList.add("ring-2", "ring-offset-2");
      setTimeout(() => el.classList.remove("ring-2", "ring-offset-2"), 2500);
    }, 200);
    return () => clearTimeout(t);
  }, []);

  const holds = items.filter((b) => b.status === "manual_hold");
  const paidCount = summary.paid || 0;
  const holdCount = summary.manual_hold || 0;

  return (
    <div id="manual-booking" className="mb-8" data-testid="manual-booking-panel">
      <div className="border rounded-2xl p-5" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>
              Box office · manual bookings
            </div>
            <div className="serif text-xl" style={{ color: "var(--text)" }}>
              Sell tickets in person (cash or card)
            </div>
            <div className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              {paidCount} paid manually · {holdCount} unpaid hold{holdCount === 1 ? "" : "s"}
            </div>
          </div>
          <button
            onClick={() => setOpen(true)}
            className="btn-primary"
            data-testid="open-manual-booking-modal"
          >
            <Plus className="w-4 h-4" /> New manual booking
          </button>
        </div>

        {holds.length > 0 && (
          <div className="mt-5 pt-5 border-t" style={{ borderColor: "var(--border)" }}>
            <div className="text-xs uppercase tracking-widest mb-3" style={{ color: "var(--text-dim)" }}>
              Pending holds — buyer needs to pay
            </div>
            <div className="space-y-2">
              {holds.map((h) => (
                <HoldRow key={h.booking_id} booking={h} onChanged={load} />
              ))}
            </div>
          </div>
        )}
      </div>

      {open && (
        <ManualBookingModal
          eventId={eventId}
          event={event}
          onClose={() => setOpen(false)}
          onCreated={() => { setOpen(false); load(); }}
        />
      )}
    </div>
  );
}


function HoldRow({ booking, onChanged }) {
  const [busy, setBusy] = useState(false);
  const expiresIn = booking.hold_expires_at
    ? Math.max(0, Math.round((new Date(booking.hold_expires_at) - Date.now()) / 3600000))
    : null;

  const confirm = async () => {
    if (!window.confirm(`Mark this booking as PAID?\n\nBuyer: ${booking.user_name} <${booking.user_email}>\nAmount: ${booking.currency} $${(booking.amount || 0).toFixed(2)}\n\nThe buyer will receive their e-ticket immediately.`)) return;
    setBusy(true);
    try {
      await api.post(`/organizer/manual-bookings/${booking.booking_id}/confirm`, {});
      toast.success("Marked paid — buyer emailed their ticket");
      onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't confirm");
    } finally { setBusy(false); }
  };

  const cancel = async () => {
    if (!window.confirm(`Cancel this hold?\n\nBuyer: ${booking.user_name}\nSeats will be released and the buyer gets nothing.`)) return;
    setBusy(true);
    try {
      await api.post(`/organizer/manual-bookings/${booking.booking_id}/cancel`, {});
      toast.success("Hold cancelled — seats released");
      onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't cancel");
    } finally { setBusy(false); }
  };

  return (
    <div
      className="flex flex-wrap items-center gap-3 px-3 py-2 border rounded-xl"
      style={{ borderColor: "var(--border)" }}
      data-testid={`hold-row-${booking.booking_id}`}
    >
      <div className="flex-1 min-w-[240px]">
        <div className="text-sm font-semibold" style={{ color: "var(--text)" }}>
          {booking.user_name} <span className="opacity-60 font-normal">· {booking.user_email}</span>
        </div>
        <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
          {booking.seats?.length ? `Seats: ${booking.seats.join(", ")}` : `${booking.tier_name} × ${booking.quantity}`}
          {" · "}
          {booking.currency} ${(booking.amount || 0).toFixed(2)}
          {" · "}
          {booking.payment_method === "cash" ? "Cash" : "Card (offline)"}
        </div>
      </div>
      <div className="text-xs inline-flex items-center gap-1" style={{ color: expiresIn <= 4 ? "var(--danger)" : "var(--text-muted)" }}>
        <Clock className="w-3 h-3" />
        {expiresIn != null ? `${expiresIn}h left` : "no expiry"}
      </div>
      <button onClick={confirm} disabled={busy} className="btn-primary !py-1 !px-3 text-xs" data-testid={`hold-confirm-${booking.booking_id}`}>
        <Check className="w-3 h-3" /> Mark paid
      </button>
      <button onClick={cancel} disabled={busy} className="btn-ghost !py-1 !px-3 text-xs" style={{ color: "var(--danger)" }} data-testid={`hold-cancel-${booking.booking_id}`}>
        <X className="w-3 h-3" /> Cancel
      </button>
    </div>
  );
}


function ManualBookingModal({ eventId, event: initialEvent, onClose, onCreated }) {
  // Fetch a FRESH event snapshot from the server inside the modal —
  // the `event` prop passed down from OrganizerEvent can be stale (or
  // occasionally missing tiers if the parent hydration hasn't finished).
  // We fall back to whatever the parent had while the request is in flight.
  const [event, setEvent] = useState(initialEvent);
  const [loadingEvent, setLoadingEvent] = useState(!initialEvent?.tiers);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get(`/events/${eventId}`);
        if (!cancelled) setEvent(data);
      } catch { /* keep the initial event on failure */ }
      finally { if (!cancelled) setLoadingEvent(false); }
    })();
    return () => { cancelled = true; };
  }, [eventId]);

  const isSeatmap = !!event?.has_seatmap;
  const tiers = event?.tiers || [];
  const currency = event?.currency || "NZD";

  const [buyerName, setBuyerName] = useState("");
  const [buyerEmail, setBuyerEmail] = useState("");
  const [buyerPhone, setBuyerPhone] = useState("");
  const [paymentMethod, setPaymentMethod] = useState("cash");
  const [mode, setMode] = useState("paid"); // paid | hold
  const [tierName, setTierName] = useState("");
  const [quantity, setQuantity] = useState(1);
  const [seatsInput, setSeatsInput] = useState("");
  const [amountOverride, setAmountOverride] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);

  // Auto-select the first tier as soon as event data arrives so the operator
  // never has to face an empty picker. If the organizer only defined one
  // tier this becomes zero-click. Only fires on the initial load — a later
  // manual clear stays cleared.
  useEffect(() => {
    if (!tierName && tiers.length > 0) {
      setTierName(tiers[0].name);
    }
  }, [tiers, tierName]);

  const selectedTier = tiers.find((t) => t.name === tierName);
  const projectedFaceValue = isSeatmap
    ? null
    : (selectedTier ? Number(selectedTier.price || 0) * (Number(quantity) || 1) : null);

  const submit = async () => {
    if (!buyerName.trim() || !buyerEmail.trim()) {
      toast.error("Buyer name and email are required");
      return;
    }
    const payload = {
      buyer_name: buyerName.trim(),
      buyer_email: buyerEmail.trim(),
      buyer_phone: buyerPhone.trim() || undefined,
      payment_method: paymentMethod,
      mode,
      notes: notes.trim() || undefined,
    };
    if (isSeatmap) {
      const seats = seatsInput
        .split(/[,\s]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      if (!seats.length) { toast.error("Enter at least one seat ID (e.g. A-1, A-2)"); return; }
      payload.seats = seats;
    } else {
      if (tiers.length === 0) {
        toast.error("This event has no ticket tiers — add one on the event's Edit page first.");
        return;
      }
      if (!tierName) { toast.error("Pick a ticket type"); return; }
      payload.tier_name = tierName;
      payload.quantity = Math.max(1, Number(quantity) || 1);
    }
    if (amountOverride.trim()) {
      const n = Number(amountOverride);
      if (!Number.isFinite(n) || n < 0) { toast.error("Amount override must be a number ≥ 0"); return; }
      payload.amount_paid = n;
    }

    setBusy(true);
    try {
      const { data } = await api.post(`/organizer/events/${eventId}/manual-booking`, payload);
      if (data.status === "paid") {
        toast.success(`Booking created — ticket emailed to ${buyerEmail}`);
      } else {
        toast.success(`24-hour hold created — reminder emailed to ${buyerEmail}`);
      }
      onCreated();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't create booking");
    } finally { setBusy(false); }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.6)" }}
      onClick={onClose}
      data-testid="manual-booking-modal"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-xl border rounded-2xl p-6 max-h-[90vh] overflow-y-auto"
        style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}
      >
        <div className="flex items-center justify-between mb-5">
          <div>
            <h3 className="serif text-2xl">New manual booking</h3>
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              For door sales, phone bookings and comps. Skips Stripe.
            </p>
          </div>
          <button onClick={onClose} className="opacity-60 hover:opacity-100" data-testid="close-manual-modal">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Mode + payment method — two toggles at the top */}
        <div className="grid sm:grid-cols-2 gap-3 mb-5">
          <div>
            <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>
              Booking type
            </label>
            <div className="grid grid-cols-2 gap-2">
              <ToggleCard
                active={mode === "paid"}
                onClick={() => setMode("paid")}
                title="Paid now"
                sub="Buyer is paying you now"
                icon={<Check className="w-4 h-4" />}
                testid="mode-paid"
              />
              <ToggleCard
                active={mode === "hold"}
                onClick={() => setMode("hold")}
                title="24h hold"
                sub="Buyer pays later"
                icon={<Clock className="w-4 h-4" />}
                testid="mode-hold"
              />
            </div>
          </div>
          <div>
            <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>
              Payment method
            </label>
            <div className="grid grid-cols-2 gap-2">
              <ToggleCard
                active={paymentMethod === "cash"}
                onClick={() => setPaymentMethod("cash")}
                title="Cash"
                sub="Physical cash"
                icon={<Banknote className="w-4 h-4" />}
                testid="pm-cash"
              />
              <ToggleCard
                active={paymentMethod === "card_offline"}
                onClick={() => setPaymentMethod("card_offline")}
                title="Card"
                sub="POS / phone"
                icon={<CreditCard className="w-4 h-4" />}
                testid="pm-card"
              />
            </div>
          </div>
        </div>

        {/* Buyer details */}
        <div className="grid sm:grid-cols-2 gap-3 mb-4">
          <div>
            <label className="text-xs uppercase tracking-widest mb-1 block" style={{ color: "var(--text-dim)" }}>Buyer name *</label>
            <input value={buyerName} onChange={(e) => setBuyerName(e.target.value)} data-testid="manual-buyer-name" />
          </div>
          <div>
            <label className="text-xs uppercase tracking-widest mb-1 block" style={{ color: "var(--text-dim)" }}>Buyer email *</label>
            <input type="email" value={buyerEmail} onChange={(e) => setBuyerEmail(e.target.value)} data-testid="manual-buyer-email" />
          </div>
          <div className="sm:col-span-2">
            <label className="text-xs uppercase tracking-widest mb-1 block" style={{ color: "var(--text-dim)" }}>Buyer phone (optional)</label>
            <input value={buyerPhone} onChange={(e) => setBuyerPhone(e.target.value)} data-testid="manual-buyer-phone" />
          </div>
        </div>

        {/* Tickets — tier picker OR seat list */}
        {isSeatmap ? (
          <div className="mb-4">
            <label className="text-xs uppercase tracking-widest mb-1 block" style={{ color: "var(--text-dim)" }}>Seat IDs *</label>
            <input
              value={seatsInput}
              onChange={(e) => setSeatsInput(e.target.value)}
              placeholder="A-1, A-2, B-3"
              data-testid="manual-seats-input"
            />
            <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>Comma or space-separated. Must be available seats.</div>
          </div>
        ) : tiers.length === 0 ? (
          <div
            className="mb-4 p-3 border rounded-xl text-sm"
            style={{ borderColor: "var(--border)", color: "var(--text-muted)", background: "rgba(217,119,6,0.06)" }}
            data-testid="manual-no-tiers-warning"
          >
            {loadingEvent
              ? "Loading ticket types…"
              : "This event has no ticket tiers set up yet. Open the event's Edit page and add at least one tier before selling tickets manually."}
          </div>
        ) : (
          <div className="mb-4">
            <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>
              Ticket type <span style={{ color: "var(--danger)" }}>*</span>
            </label>
            {/* Show the tiers the ORGANIZER created as clickable cards. One
                click = tier selected; the current pick is highlighted with
                the accent border/tint. Radios provide the a11y semantics. */}
            <div
              className="grid gap-2"
              role="radiogroup"
              aria-label="Ticket tier"
              data-testid="manual-tier-list"
            >
              {tiers.map((t) => {
                const active = tierName === t.name;
                const price = Number(t.price || 0);
                return (
                  <button
                    key={t.name}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    onClick={() => setTierName(t.name)}
                    className="w-full text-left p-3 border rounded-xl transition flex items-center justify-between gap-3"
                    style={{
                      borderColor: active ? "var(--accent)" : "var(--border)",
                      background: active ? "var(--accent-soft)" : "var(--bg)",
                    }}
                    data-testid={`manual-tier-${t.name}`}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <div
                        className="shrink-0 w-4 h-4 rounded-full border flex items-center justify-center"
                        style={{
                          borderColor: active ? "var(--accent)" : "var(--border)",
                          background: active ? "var(--accent)" : "transparent",
                        }}
                      >
                        {active && <Check className="w-2.5 h-2.5" style={{ color: "#fff" }} />}
                      </div>
                      <div className="min-w-0">
                        <div className="text-sm font-semibold truncate" style={{ color: "var(--text)" }}>{t.name}</div>
                        {t.capacity != null && (
                          <div className="text-[11px]" style={{ color: "var(--text-dim)" }}>Capacity {t.capacity}</div>
                        )}
                      </div>
                    </div>
                    <div className="text-sm font-mono whitespace-nowrap" style={{ color: active ? "var(--accent)" : "var(--text)" }}>
                      {price === 0 ? "Free" : `${currency} $${price.toFixed(2)}`}
                    </div>
                  </button>
                );
              })}
            </div>
            <div className="mt-3">
              <label className="text-xs uppercase tracking-widest mb-1 block" style={{ color: "var(--text-dim)" }}>Quantity</label>
              <input
                type="number"
                min="1"
                max="50"
                value={quantity}
                onChange={(e) => setQuantity(Math.max(1, Number(e.target.value) || 1))}
                data-testid="manual-quantity"
              />
              {projectedFaceValue != null && (
                <div className="text-xs mt-1.5" style={{ color: "var(--text-muted)" }}>
                  Face value: <b style={{ color: "var(--text)" }}>{currency} ${projectedFaceValue.toFixed(2)}</b>
                  {" — leave 'amount taken' blank to charge this, or override below for comps / discounts."}
                </div>
              )}
            </div>
          </div>
        )}

        <div className="mb-4">
          <label className="text-xs uppercase tracking-widest mb-1 block" style={{ color: "var(--text-dim)" }}>
            Amount taken (optional — leave blank for face value)
          </label>
          <input
            type="number"
            min="0"
            step="0.01"
            value={amountOverride}
            onChange={(e) => setAmountOverride(e.target.value)}
            placeholder="e.g. 0 for a comp, or a discounted amount"
            data-testid="manual-amount-override"
          />
        </div>

        <div className="mb-5">
          <label className="text-xs uppercase tracking-widest mb-1 block" style={{ color: "var(--text-dim)" }}>Internal notes (optional)</label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            placeholder="e.g. VIP comp for press, phoned in at 3pm, etc."
            data-testid="manual-notes"
          />
        </div>

        <div className="flex justify-end gap-3">
          <button onClick={onClose} className="btn-ghost" data-testid="manual-cancel">Cancel</button>
          <button onClick={submit} disabled={busy} className="btn-primary" data-testid="manual-submit">
            {busy ? "Creating…" : (mode === "paid" ? "Create paid booking" : "Create 24h hold")}
          </button>
        </div>
      </div>
    </div>
  );
}


function ToggleCard({ active, onClick, title, sub, icon, testid }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="p-3 border rounded-xl text-left transition"
      style={{
        borderColor: active ? "var(--accent)" : "var(--border)",
        background: active ? "var(--accent-soft)" : "var(--bg)",
      }}
      data-testid={testid}
    >
      <div className="flex items-center gap-2 text-sm font-semibold" style={{ color: active ? "var(--accent)" : "var(--text)" }}>
        {icon} {title}
      </div>
      <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{sub}</div>
    </button>
  );
}
