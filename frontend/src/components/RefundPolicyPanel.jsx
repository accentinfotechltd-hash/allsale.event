import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { ShieldCheck, Loader2, Info } from "lucide-react";

/**
 * Refund-window policy editor. Mounted in OrganizerEvent.
 *
 * Stored on the event as `refund_policy = {enabled, hours_before_event,
 * refund_pct, include_fees}`. When enabled, attendees can self-refund up to
 * `hours_before_event` hours before the event start.
 */
export default function RefundPolicyPanel({ eventId, event }) {
  const initial = event?.refund_policy || { enabled: false, hours_before_event: 48, refund_pct: 100, include_fees: false };
  const [policy, setPolicy] = useState({
    enabled: !!initial.enabled,
    hours_before_event: Number(initial.hours_before_event ?? 48),
    refund_pct: Number(initial.refund_pct ?? 100),
    include_fees: !!initial.include_fees,
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!event?.refund_policy) return;
    const p = event.refund_policy;
    setPolicy({
      enabled: !!p.enabled,
      hours_before_event: Number(p.hours_before_event ?? 48),
      refund_pct: Number(p.refund_pct ?? 100),
      include_fees: !!p.include_fees,
    });
  }, [event?.event_id]);

  const save = async () => {
    setSaving(true);
    try {
      await api.patch(`/events/${eventId}`, { refund_policy: policy });
      toast.success("Refund policy saved");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't save policy");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="border rounded-2xl p-6 mb-6"
      style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
      data-testid="refund-policy-panel"
    >
      <div className="serif text-2xl flex items-center gap-2">
        <ShieldCheck className="w-5 h-5" style={{ color: "var(--accent)" }} />
        Refund policy
      </div>
      <div className="text-xs mt-1 mb-4" style={{ color: "var(--text-dim)" }}>
        Publish a clear refund window so attendees can self-serve cancellations. Refunds release seats/tier capacity back on sale automatically.
      </div>

      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={policy.enabled}
          onChange={(e) => setPolicy({ ...policy, enabled: e.target.checked })}
          data-testid="refund-policy-enabled"
        />
        <span className="text-sm">Enable self-serve refunds</span>
      </label>

      {policy.enabled && (
        <div className="mt-4 grid sm:grid-cols-2 gap-4">
          <div>
            <div className="text-xs mb-1" style={{ color: "var(--text-dim)" }}>Cut-off (hours before event)</div>
            <input
              type="number"
              min={0}
              max={8760}
              value={policy.hours_before_event}
              onChange={(e) => setPolicy({ ...policy, hours_before_event: Math.max(0, Number(e.target.value)) })}
              className="w-full px-3 py-2 rounded-md border bg-transparent"
              style={{ borderColor: "var(--border)" }}
              data-testid="refund-policy-hours"
            />
          </div>
          <div>
            <div className="text-xs mb-1" style={{ color: "var(--text-dim)" }}>Refund % of ticket face value</div>
            <input
              type="number"
              min={0}
              max={100}
              value={policy.refund_pct}
              onChange={(e) => setPolicy({ ...policy, refund_pct: Math.max(0, Math.min(100, Number(e.target.value))) })}
              className="w-full px-3 py-2 rounded-md border bg-transparent"
              style={{ borderColor: "var(--border)" }}
              data-testid="refund-policy-pct"
            />
          </div>
          <label className="flex items-center gap-2 cursor-pointer sm:col-span-2 mt-1">
            <input
              type="checkbox"
              checked={policy.include_fees}
              onChange={(e) => setPolicy({ ...policy, include_fees: e.target.checked })}
              data-testid="refund-policy-fees"
            />
            <span className="text-sm">Also refund service fees</span>
          </label>
          <div className="sm:col-span-2 text-[11px] flex items-start gap-1.5" style={{ color: "var(--text-dim)" }}>
            <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
            <span>
              Preview: &quot;Full {policy.refund_pct}% refund up to {policy.hours_before_event}h before the event{policy.include_fees ? ", including service fees" : ""}.&quot;
              Refunds after the cut-off must be handled manually.
            </span>
          </div>
        </div>
      )}

      <div className="flex justify-end mt-5">
        <button
          onClick={save}
          disabled={saving}
          className="btn-primary !py-2"
          data-testid="refund-policy-save-btn"
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
          Save policy
        </button>
      </div>
    </div>
  );
}
