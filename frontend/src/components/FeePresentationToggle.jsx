/**
 * FeePresentationToggle — used inside CreateEvent.jsx to let organizers pick
 * between "fees on top" (default) and "fees included in ticket price".
 *
 * Renders a 2-card radio choice + a live preview using the same client-side
 * fee math (`estimateBuyerFees`) the rest of the app uses, so the organizer
 * sees exactly what the buyer will be charged and exactly what they'll
 * receive per ticket.
 */
import { useMemo } from "react";
import { estimateBuyerFees, useFeeSettings } from "@/lib/fees";
import { formatMoney } from "@/lib/currencies";

export default function FeePresentationToggle({ value, onChange, samplePrice, currency }) {
  const fees = useFeeSettings();
  const sample = Number(samplePrice) > 0 ? Number(samplePrice) : 50;

  const exclusive = useMemo(
    () => estimateBuyerFees(sample, { ...fees, absorbFees: false }),
    [fees, sample],
  );
  const inclusive = useMemo(
    () => estimateBuyerFees(sample, { ...fees, absorbFees: true }),
    [fees, sample],
  );

  return (
    <div data-testid="fee-presentation-section">
      <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>
        How is the platform fee shown?
      </label>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <ModeCard
          selected={!value}
          onClick={() => onChange(false)}
          title="Fees on top (default)"
          subtitle="Buyer sees the platform fee as a separate line"
          testid="fee-mode-exclusive"
        >
          <PreviewRow label={`Ticket price (${formatMoney(sample, currency)})`} value={formatMoney(sample, currency)} />
          <PreviewRow label="+ service fee" value={`+ ${formatMoney(exclusive.fees, currency)}`} muted />
          <PreviewRow label="Buyer pays" value={formatMoney(exclusive.total, currency)} highlight />
          <PreviewRow label="You receive" value={formatMoney(exclusive.organizerNet, currency)} accent />
        </ModeCard>

        <ModeCard
          selected={!!value}
          onClick={() => onChange(true)}
          title="Fees included in price"
          subtitle="Buyer sees one clean number; you absorb the fee"
          testid="fee-mode-inclusive"
        >
          <PreviewRow label="Ticket price" value={formatMoney(sample, currency)} />
          <PreviewRow label="+ service fee" value="(included)" muted />
          <PreviewRow label="Buyer pays" value={formatMoney(sample, currency)} highlight />
          <PreviewRow
            label="You receive"
            value={formatMoney(inclusive.organizerNet, currency)}
            accent
          />
        </ModeCard>
      </div>
      <p className="text-[11px] mt-2 leading-relaxed" style={{ color: "var(--text-dim)" }}>
        Numbers are based on a sample ticket at <strong>{formatMoney(sample, currency)}</strong>. Switch this any
        time before going live — it only affects new bookings.
      </p>
    </div>
  );
}

function ModeCard({ selected, onClick, title, subtitle, testid, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testid}
      className="text-left rounded-xl border p-4 transition"
      style={{
        background: selected ? "var(--accent-soft, rgba(255,79,0,0.08))" : "var(--surface)",
        borderColor: selected ? "var(--accent)" : "var(--border)",
        borderWidth: selected ? 2 : 1,
      }}
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="text-sm font-medium" style={{ color: "var(--text)" }}>{title}</div>
          <div className="text-[11px] mt-0.5" style={{ color: "var(--text-dim)" }}>{subtitle}</div>
        </div>
        <div
          className="w-4 h-4 rounded-full flex-shrink-0 mt-1"
          style={{
            background: selected ? "var(--accent)" : "transparent",
            border: "2px solid " + (selected ? "var(--accent)" : "var(--border-strong)"),
          }}
        />
      </div>
      <div className="space-y-1">{children}</div>
    </button>
  );
}

function PreviewRow({ label, value, muted, highlight, accent }) {
  return (
    <div className="flex justify-between items-baseline text-xs">
      <span style={{ color: muted ? "var(--text-dim)" : "var(--text-muted)" }}>{label}</span>
      <span
        className={highlight ? "font-semibold" : ""}
        style={{
          color: accent ? "var(--accent)" : highlight ? "var(--text)" : muted ? "var(--text-dim)" : "var(--text)",
        }}
      >
        {value}
      </span>
    </div>
  );
}
