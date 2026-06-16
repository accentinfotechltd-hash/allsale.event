import { useEffect, useState } from "react";
import { Gift, ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { formatMoney } from "@/lib/currencies";

/**
 * GiftCardRedemptionsPanel — shown on the organizer dashboard.
 * Surfaces gift cards used to pay for bookings on this organizer's events.
 * Hidden when there are zero redemptions (no empty-state noise).
 */
export default function GiftCardRedemptionsPanel() {
  const [data, setData] = useState(null);

  useEffect(() => {
    api.get("/organizer/gift-card-redemptions")
      .then(({ data }) => setData(data))
      .catch(() => setData(null));
  }, []);

  if (!data || (data.totals?.count || 0) === 0) return null;

  return (
    <div
      className="border rounded-2xl p-6 mb-10"
      style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
      data-testid="gift-card-redemptions-panel"
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Gift size={18} style={{ color: "var(--accent)" }} />
          <div>
            <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>Gift card redemptions</div>
            <div className="serif text-2xl">
              <span data-testid="gc-redemption-count">{data.totals.count}</span> use{data.totals.count === 1 ? "" : "s"} ·{" "}
              <span style={{ color: "var(--accent)" }} data-testid="gc-redemption-total">
                {formatMoney(data.totals.amount, "NZD")}
              </span>
            </div>
          </div>
        </div>
        <Link to="/gift-cards" className="btn-ghost text-xs" data-testid="learn-more-gift-cards">
          Sell gift cards <ArrowRight size={12} />
        </Link>
      </div>
      <div className="space-y-2">
        {data.recent.map((b) => (
          <div
            key={b.booking_id}
            className="flex items-center justify-between gap-3 p-3 rounded-lg border text-sm"
            style={{ borderColor: "var(--border)" }}
            data-testid={`gc-redemption-${b.booking_id}`}
          >
            <div className="flex-1 min-w-0">
              <div className="truncate">{b.event_title}</div>
              <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                {b.user_name || b.user_email} ·{" "}
                <span className="font-mono">{b.gift_card_code}</span>
              </div>
            </div>
            <div className="text-right">
              <div className="serif text-lg" style={{ color: "var(--accent)" }}>
                {formatMoney(b.gift_card_amount, b.currency)}
              </div>
              <div className="text-[10px]" style={{ color: "var(--text-muted)" }}>
                {b.created_at ? new Date(b.created_at).toLocaleDateString() : ""}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
