import { useEffect, useState } from "react";
import { Megaphone, ToggleLeft, ToggleRight } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

/**
 * InfluencerProgramPanel
 * Sits on the OrganizerEvent page. Lets the organizer flip
 * `affiliate_program_open` on the event so any creator can self-join
 * (with the default commission %), and tweak that default %.
 */
export default function InfluencerProgramPanel({ event }) {
  const [open, setOpen] = useState(false);
  const [pct, setPct] = useState(10);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!event) return;
    setOpen(!!event.affiliate_program_open);
    setPct(Number(event.affiliate_default_commission_pct ?? 10));
  }, [event]);

  if (!event) return null;

  const save = async (nextOpen = open, nextPct = pct) => {
    setSaving(true);
    try {
      await api.patch(`/events/${event.event_id}`, {
        affiliate_program_open: nextOpen,
        affiliate_default_commission_pct: Number(nextPct),
      });
      setOpen(nextOpen);
      setPct(Number(nextPct));
      toast.success(nextOpen ? "Influencer program is now OPEN" : "Influencer program closed");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-2xl border p-5 sm:p-6 mb-8" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }} data-testid="influencer-program-panel">
      <div className="flex items-start gap-4 flex-wrap mb-3">
        <Megaphone size={20} style={{ color: "var(--accent)" }} />
        <div className="flex-1 min-w-[200px]">
          <div className="font-medium">Influencer marketplace</div>
          <p className="text-sm opacity-70 mt-1 max-w-prose">
            When open, any verified creator can self-join your event and start sharing a trackable link.
            You only pay commission on sales they actually drive.
          </p>
        </div>
        <button
          type="button"
          onClick={() => save(!open, pct)}
          disabled={saving}
          data-testid="program-toggle"
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border text-sm font-medium disabled:opacity-50"
          style={{
            borderColor: open ? "var(--accent)" : "var(--border)",
            background: open ? "rgba(255,79,0,0.1)" : "transparent",
            color: open ? "var(--accent)" : "var(--text)",
          }}
        >
          {open ? <ToggleRight size={18} /> : <ToggleLeft size={18} />}
          {open ? "Open" : "Closed"}
        </button>
      </div>

      {open && (
        <div className="mt-2 flex items-center gap-3 flex-wrap" data-testid="commission-row">
          <label className="text-sm opacity-80">Default commission per ticket:</label>
          <input
            type="number"
            min="0"
            max="50"
            step="0.5"
            value={pct}
            onChange={(e) => setPct(e.target.value)}
            onBlur={() => save(open, pct)}
            data-testid="commission-input"
            className="w-24 rounded-lg border px-3 py-2 text-sm bg-transparent"
            style={{ borderColor: "var(--border)" }}
          />
          <span className="text-sm opacity-70">%</span>
        </div>
      )}
    </div>
  );
}
