import { useEffect, useState } from "react";
import { Frown, Loader2, MessageSquare } from "lucide-react";
import api from "@/lib/api";

const REASON_LABELS = {
  too_many: "Too many emails",
  not_relevant: "Not relevant",
  never_signed_up: "Never signed up",
  spam: "Looks like spam",
  other: "Other reason",
};

const REASON_COLORS = {
  too_many: "#F59E0B",
  not_relevant: "#0EA5E9",
  never_signed_up: "#A855F7",
  spam: "#EF4444",
  other: "#94A3B8",
};

/**
 * Inline widget surfacing the aggregate of /admin/newsletter/unsubscribe-reasons.
 * Shows a horizontal bar chart of the top reasons + recent free-form comments.
 * Empty state when no one has unsubscribed (the happy case).
 */
export default function NewsletterUnsubscribeReasons() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const { data: d } = await api.get("/admin/newsletter/unsubscribe-reasons");
        setData(d);
      } catch {
        setData({ counts: {}, comments: [] });
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return (
      <div className="mt-6 p-6 rounded-xl border text-center" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
        <Loader2 className="w-4 h-4 animate-spin inline-block mr-2" /> Loading unsubscribe reasons…
      </div>
    );
  }

  const total = Object.values(data.counts || {}).reduce((a, b) => a + b, 0);

  if (total === 0 && (data.comments || []).length === 0) {
    return (
      <div
        data-testid="unsubscribe-reasons-empty"
        className="mt-6 p-5 rounded-xl border flex items-center gap-3"
        style={{ borderColor: "var(--border)", background: "rgba(34,197,94,0.06)", color: "var(--text)" }}
      >
        <Frown className="w-5 h-5" style={{ color: "#22c55e", transform: "rotate(180deg)" }} />
        <div>
          <div className="text-sm font-medium">No unsubscribes yet — your audience is sticky.</div>
          <div className="text-xs mt-0.5" style={{ color: "var(--text-dim)" }}>When subscribers leave, their reasons will appear here.</div>
        </div>
      </div>
    );
  }

  const sortedReasons = Object.entries(data.counts || {}).sort((a, b) => b[1] - a[1]);
  const maxCount = Math.max(...sortedReasons.map(([, n]) => n), 1);

  return (
    <div
      data-testid="unsubscribe-reasons-widget"
      className="mt-6 rounded-xl border"
      style={{ borderColor: "var(--border)" }}
    >
      <div className="p-4 border-b flex items-center justify-between" style={{ borderColor: "var(--border)" }}>
        <div>
          <div className="text-xs uppercase tracking-widest" style={{ color: "var(--accent)" }}>Newsletter</div>
          <div className="font-serif text-lg" style={{ color: "var(--text)" }}>
            Why people unsubscribe <span style={{ color: "var(--text-dim)", fontWeight: 400 }}>· {total} total</span>
          </div>
        </div>
      </div>

      {/* Bar chart */}
      <div className="p-4 space-y-2.5" data-testid="unsubscribe-reasons-bars">
        {sortedReasons.map(([reason, count]) => {
          const pct = (count / maxCount) * 100;
          const sharePct = ((count / total) * 100).toFixed(0);
          return (
            <div key={reason} className="text-sm" data-testid={`unsubscribe-reason-${reason}`}>
              <div className="flex items-center justify-between mb-1">
                <span style={{ color: "var(--text)" }}>{REASON_LABELS[reason] || reason}</span>
                <span style={{ color: "var(--text-dim)" }}>
                  <span className="font-mono tabular-nums">{count}</span>
                  <span className="ml-1.5 text-xs">({sharePct}%)</span>
                </span>
              </div>
              <div className="h-2 rounded-full overflow-hidden" style={{ background: "var(--border)" }}>
                <div
                  className="h-full transition-all duration-500"
                  style={{ width: `${pct}%`, background: REASON_COLORS[reason] || "var(--accent)" }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Free-form comments */}
      {(data.comments || []).length > 0 && (
        <div className="border-t p-4" style={{ borderColor: "var(--border)" }}>
          <div className="text-xs uppercase tracking-widest mb-2 inline-flex items-center gap-1.5" style={{ color: "var(--text-dim)" }}>
            <MessageSquare className="w-3.5 h-3.5" /> Recent comments
          </div>
          <ul className="space-y-2.5" data-testid="unsubscribe-comments">
            {data.comments.slice(0, 6).map((c, i) => (
              <li key={i} className="text-sm rounded-lg p-3" style={{ background: "var(--bg-card)", color: "var(--text)" }}>
                <div className="text-xs mb-1" style={{ color: "var(--text-dim)" }}>
                  <span className="font-mono">{c.email}</span>
                  {c.unsubscribe_reason && (
                    <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider" style={{
                      background: REASON_COLORS[c.unsubscribe_reason] + "20",
                      color: REASON_COLORS[c.unsubscribe_reason] || "var(--text-dim)",
                    }}>
                      {REASON_LABELS[c.unsubscribe_reason] || c.unsubscribe_reason}
                    </span>
                  )}
                </div>
                <div className="italic leading-relaxed">&ldquo;{c.unsubscribe_comment}&rdquo;</div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
