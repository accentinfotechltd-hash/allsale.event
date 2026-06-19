import { useEffect, useState } from "react";
import { Copy, Check, Sparkles, Users, Gift, Share2 } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

/**
 * OrganizerReferral — show my referral link + stats, and a list of
 * credits I've earned. Shareable everywhere; the REFERRER gets a $50 NZD
 * credit the moment the referred organizer's FIRST event is approved.
 * (The new organizer does not receive a welcome bonus — keeps the
 * program lean and reduces self-referral abuse via burner accounts.)
 */
export default function OrganizerReferral() {
  const [stats, setStats] = useState(null);
  const [credits, setCredits] = useState([]);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [s, c] = await Promise.all([
          api.get("/organizer/referral"),
          api.get("/organizer/credits"),
        ]);
        setStats(s.data);
        setCredits(c.data || []);
      } catch (err) {
        toast.error(err?.response?.data?.detail || "Couldn't load referral stats");
      }
    })();
  }, []);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(stats.share_url);
      setCopied(true);
      toast.success("Link copied");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Couldn't copy");
    }
  };

  const onShare = async () => {
    if (!navigator.share) return onCopy();
    try {
      await navigator.share({
        title: "Sell tickets with Allsale Events",
        text: `Join me on Allsale Events — keep 100% of your ticket revenue. Sign up with my link:`,
        url: stats.share_url,
      });
    } catch { /* user dismissed */ }
  };

  if (!stats) return <div className="text-center py-20" style={{ color: "var(--text-muted)" }}>Loading...</div>;

  return (
    <div className="max-w-3xl mx-auto px-4 py-10">
      <div className="flex items-center gap-2 mb-2">
        <Sparkles size={20} style={{ color: "var(--accent)" }} />
        <h1 className="serif text-3xl">Refer an organizer, earn ${stats.credit_per_referral_nzd}</h1>
      </div>
      <p className="text-sm mb-8" style={{ color: "var(--text-muted)" }}>
        You earn <strong>${stats.credit_per_referral_nzd} NZD</strong> credit the moment the organizer
        you invite launches their first event. Credit is applied to your next payout.
      </p>

      <div className="rounded-2xl border p-5 mb-8" style={{ borderColor: "var(--border-strong)", background: "var(--bg-card)" }} data-testid="referral-card">
        <div className="text-xs uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>Your link</div>
        <div className="flex items-center gap-2 mb-4">
          <input
            value={stats.share_url}
            readOnly
            className="flex-1 font-mono text-xs"
            data-testid="referral-link-input"
            onClick={(e) => e.target.select()}
          />
          <button
            onClick={onCopy}
            className="btn-ghost !px-3 !py-2 text-sm"
            data-testid="copy-link-btn"
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
          </button>
          <button
            onClick={onShare}
            className="btn-primary !px-3 !py-2 text-sm"
            data-testid="share-link-btn"
          >
            <Share2 size={14} />
          </button>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <Stat icon={<Users size={14} />} label="Signups" value={stats.signups} testid="stat-signups" />
          <Stat icon={<Sparkles size={14} />} label="Qualified" value={stats.qualified} testid="stat-qualified" />
          <Stat icon={<Gift size={14} />} label="Credit (NZD)" value={`$${stats.available_credit_nzd.toFixed(2)}`} testid="stat-credit" />
        </div>
      </div>

      <h2 className="serif text-2xl mb-3">Credit ledger</h2>
      {credits.length === 0 ? (
        <div className="text-sm" style={{ color: "var(--text-muted)" }} data-testid="empty-credits">
          No credits yet. Share your link to start earning.
        </div>
      ) : (
        <div className="space-y-2">
          {credits.map((c) => (
            <div
              key={c.credit_id}
              className="flex items-center justify-between p-3 rounded-lg border text-sm"
              style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
              data-testid={`credit-${c.credit_id}`}
            >
              <div>
                <div className="font-medium">${c.amount.toFixed(2)} {c.currency}</div>
                <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                  {c.reason === "referral_signup_bonus" ? "Welcome bonus — your first event launched 🎉" : "Referral reward"}
                  {" · "}
                  {new Date(c.created_at).toLocaleDateString()}
                </div>
              </div>
              <span
                className="text-[10px] uppercase tracking-widest px-2 py-1 rounded-full"
                style={{
                  background: c.status === "available" ? "var(--accent-soft)" : "var(--bg-elev)",
                  color: c.status === "available" ? "var(--accent)" : "var(--text-muted)",
                }}
              >
                {c.status}
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="mt-8 text-xs" style={{ color: "var(--text-muted)" }}>
        Credits are tracked on your account. Reach out to support to apply them against your next payout.
      </div>
    </div>
  );
}

function Stat({ icon, label, value, testid }) {
  return (
    <div className="rounded-xl border p-3 text-center" style={{ borderColor: "var(--border)" }} data-testid={testid}>
      <div className="flex items-center justify-center gap-1 text-xs mb-1" style={{ color: "var(--text-dim)" }}>
        {icon} {label}
      </div>
      <div className="serif text-xl">{value}</div>
    </div>
  );
}
