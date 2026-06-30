import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Gift, Sparkles, Mail, ArrowRight, Copy, Check, Search, Send, Calendar } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";

/**
 * GiftCards — buy or view Allsale Events gift cards.
 *
 * Top half: pick amount + recipient → Stripe Checkout.
 * Bottom half: any cards I purchased OR received (matched on email).
 */
const PRESET_AMOUNTS = [25, 50, 100, 200];

export default function GiftCards() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [amount, setAmount] = useState(50);
  const [recipientEmail, setRecipientEmail] = useState("");
  const [recipientName, setRecipientName] = useState("");
  const [note, setNote] = useState("");
  // Optional scheduled delivery: empty = email recipient immediately on
  // payment success; YYYY-MM-DD = hold until that date (birthday/Christmas).
  const [deliverAt, setDeliverAt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [myCards, setMyCards] = useState([]);
  const [copied, setCopied] = useState(null);
  const [resendingId, setResendingId] = useState(null);

  const reloadCards = () => {
    if (!user) return;
    api.get("/me/gift-cards").then(({ data }) => setMyCards(data || [])).catch(() => {});
  };

  useEffect(() => {
    if (!user) return;
    reloadCards();
  }, [user]);

  const onPurchase = async () => {
    if (!user) {
      toast("Please sign in to purchase a gift card");
      nav("/login");
      return;
    }
    if (!recipientEmail.trim()) { toast.error("Add a recipient email"); return; }
    if (amount < 10 || amount > 1000) { toast.error("Amount must be NZD $10–$1000"); return; }
    setSubmitting(true);
    try {
      const { data } = await api.post("/gift-cards/purchase", {
        amount: Number(amount),
        recipient_email: recipientEmail.trim(),
        recipient_name: recipientName.trim() || undefined,
        personal_note: note.trim() || undefined,
        currency: "NZD",
        origin_url: window.location.origin,
        deliver_at: deliverAt || undefined,
      });
      if (data.url) {
        window.location.href = data.url;
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't start checkout");
    } finally {
      setSubmitting(false);
    }
  };

  const copyCode = async (code) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(code);
      toast.success("Code copied");
      setTimeout(() => setCopied(null), 2000);
    } catch {
      toast.error("Couldn't copy");
    }
  };

  return (
    <div className="max-w-3xl mx-auto px-4 py-12">
      <div className="mb-8">
        <div className="inline-flex items-center gap-2 text-xs uppercase tracking-widest mb-3" style={{ color: "var(--accent)" }}>
          <Sparkles size={14} /> Gift cards
        </div>
        <h1 className="serif text-4xl sm:text-5xl mb-2">Give the gift of <span style={{ color: "var(--accent)" }}>live moments</span>.</h1>
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          They pick the event. You pick the amount. Delivered by email instantly after payment.
        </p>
      </div>

      <div className="rounded-2xl border p-6 mb-12" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }} data-testid="gift-card-purchase-form">
        <div className="mb-5">
          <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>Amount (NZD)</label>
          <div className="flex flex-wrap gap-2 mb-3">
            {PRESET_AMOUNTS.map((a) => (
              <button
                key={a}
                onClick={() => setAmount(a)}
                className={`px-4 py-2 rounded-lg border text-sm ${amount === a ? "border-2" : ""}`}
                style={{ borderColor: amount === a ? "var(--accent)" : "var(--border)", color: amount === a ? "var(--accent)" : "var(--text)" }}
                data-testid={`amount-preset-${a}`}
              >
                ${a}
              </button>
            ))}
          </div>
          <input
            type="number"
            min="10"
            max="1000"
            step="5"
            value={amount}
            onChange={(e) => setAmount(parseFloat(e.target.value) || 0)}
            placeholder="Custom amount"
            data-testid="amount-input"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-5">
          <div>
            <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>Recipient name</label>
            <input
              value={recipientName}
              onChange={(e) => setRecipientName(e.target.value)}
              placeholder="Optional"
              data-testid="recipient-name-input"
            />
          </div>
          <div>
            <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>Recipient email</label>
            <input
              type="email"
              value={recipientEmail}
              onChange={(e) => setRecipientEmail(e.target.value)}
              placeholder="them@email.com"
              data-testid="recipient-email-input"
            />
          </div>
        </div>

        <div className="mb-5">
          <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>Personal note (optional)</label>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Happy birthday! Pick any show you like."
            rows={3}
            maxLength={400}
            data-testid="personal-note-input"
            className="w-full px-3 py-2 rounded-lg border bg-transparent text-sm"
            style={{ borderColor: "var(--border)" }}
          />
        </div>

        <div className="mb-5">
          <label className="text-xs uppercase tracking-widest mb-2 flex items-center gap-2" style={{ color: "var(--text-dim)" }}>
            <Calendar size={12} /> Deliver on a specific date (optional)
          </label>
          <input
            type="date"
            value={deliverAt}
            onChange={(e) => setDeliverAt(e.target.value)}
            min={new Date(Date.now() + 86400000).toISOString().slice(0, 10)}
            max={new Date(Date.now() + 365 * 86400000).toISOString().slice(0, 10)}
            className="w-full px-3 py-2 rounded-lg border bg-transparent text-sm"
            style={{ borderColor: "var(--border)" }}
            data-testid="deliver-at-input"
          />
          <p className="text-[11px] mt-1.5" style={{ color: "var(--text-muted)" }}>
            {deliverAt
              ? `Recipient gets the email on ${new Date(deliverAt).toLocaleDateString()} — surprise stays under wraps.`
              : "Leave blank to deliver instantly after payment. Set a date for birthdays, Christmas, anniversaries…"}
          </p>
        </div>

        <button
          onClick={onPurchase}
          disabled={submitting || !recipientEmail.trim() || amount < 10}
          className="btn-primary w-full justify-center"
          data-testid="purchase-gift-card-btn"
        >
          <Gift size={16} />
          {submitting ? "Redirecting to payment..." : `Buy NZD $${amount} gift card`}
          <ArrowRight size={16} />
        </button>
      </div>

      <BalanceLookup />

      {user && myCards.length > 0 && (
        <div data-testid="my-gift-cards">
          <h2 className="serif text-2xl mb-4">Your gift cards</h2>
          <div className="space-y-3">
            {myCards.map((c) => (
              <div
                key={c.card_id}
                className="rounded-xl border p-4 flex items-center justify-between gap-3"
                style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
                data-testid={`gc-row-${c.card_id}`}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono text-sm">{c.code}</span>
                    <button onClick={() => copyCode(c.code)} className="opacity-60 hover:opacity-100" data-testid={`copy-${c.card_id}`} aria-label="Copy code">
                      {copied === c.code ? <Check size={12} /> : <Copy size={12} />}
                    </button>
                  </div>
                  <div className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {c.purchased_by === user.user_id ? `Sent to ${c.recipient_email}` : `From ${c.purchaser_name || "a friend"}`}
                    {c.personal_note ? ` • "${c.personal_note.slice(0, 60)}"` : ""}
                  </div>
                  {c.purchased_by === user.user_id && c.deliver_at && !c.delivered_at && (
                    <div className="text-[11px] mt-1 inline-flex items-center gap-1 px-2 py-0.5 rounded-full" style={{ background: "rgba(255,165,0,0.12)", color: "var(--accent)" }}>
                      <Calendar size={10} /> Scheduled for {new Date(c.deliver_at).toLocaleDateString()}
                    </div>
                  )}
                  {c.purchased_by === user.user_id && c.status === "active" && c.delivered_at && (
                    <button
                      onClick={async () => {
                        setResendingId(c.card_id);
                        try {
                          await api.post(`/me/gift-cards/${c.card_id}/resend`);
                          toast.success(`Email resent to ${c.recipient_email}`);
                          reloadCards();
                        } catch (err) {
                          toast.error(err?.response?.data?.detail || "Couldn't resend");
                        } finally {
                          setResendingId(null);
                        }
                      }}
                      disabled={resendingId === c.card_id || Number(c.resend_count || 0) >= 3}
                      className="text-[11px] inline-flex items-center gap-1 mt-1 underline opacity-70 hover:opacity-100 disabled:opacity-40 disabled:no-underline"
                      title={Number(c.resend_count || 0) >= 3 ? "Resend limit reached (3 max)" : "Re-send the recipient email"}
                      data-testid={`resend-${c.card_id}`}
                    >
                      <Send size={10} />
                      {resendingId === c.card_id ? "Sending…" : `Resend email${c.resend_count ? ` (${c.resend_count}/3 used)` : ""}`}
                    </button>
                  )}
                </div>
                <div className="text-right">
                  <div className="serif text-2xl" style={{ color: c.status === "depleted" ? "var(--text-muted)" : "var(--accent)" }}>
                    ${c.balance?.toFixed(2)}
                  </div>
                  <div className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                    {c.status === "depleted" ? "Used up" : c.status === "pending" ? "Pending" : `of $${c.amount?.toFixed(2)}`}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-12 text-center text-xs" style={{ color: "var(--text-muted)" }}>
        <Mail size={14} className="inline mr-1" />
        Gift cards arrive by email seconds after payment. No expiry. Apply at checkout on any event.
      </div>
    </div>
  );
}


function BalanceLookup() {
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [err, setErr] = useState("");

  const check = async (e) => {
    if (e) e.preventDefault();
    const c = code.trim().toUpperCase().replace(/\s+/g, "");
    if (!c) { setErr("Enter a gift card code"); return; }
    setLoading(true);
    setErr("");
    setResult(null);
    try {
      const { data } = await api.get(`/gift-cards/${encodeURIComponent(c)}/balance`);
      setResult(data);
    } catch (e) {
      setErr(e?.response?.data?.detail || "Couldn't find that gift card");
    } finally {
      setLoading(false);
    }
  };

  const reset = () => { setCode(""); setResult(null); setErr(""); };

  return (
    <div className="rounded-2xl border p-6 mb-12" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }} data-testid="gift-card-balance-lookup">
      <div className="flex items-center gap-2 mb-2">
        <Search size={16} style={{ color: "var(--accent)" }} />
        <h2 className="serif text-2xl">Check a gift card balance</h2>
      </div>
      <p className="text-sm mb-4" style={{ color: "var(--text-muted)" }}>
        Got a code? Drop it in to see what&apos;s left on your card. No login needed.
      </p>
      <form onSubmit={check} className="flex flex-col sm:flex-row gap-2">
        <input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="GC-XXXX-XXXX-XXXX"
          className="flex-1 px-3 py-2 rounded-lg border bg-transparent text-sm font-mono tracking-wider"
          style={{ borderColor: "var(--border)", color: "var(--text)" }}
          data-testid="gift-card-code-input"
          autoComplete="off"
          spellCheck={false}
        />
        <button
          type="submit"
          disabled={loading || !code.trim()}
          className="btn-primary"
          data-testid="check-balance-btn"
        >
          {loading ? "Checking…" : "Check balance"}
        </button>
      </form>

      {err && (
        <div
          className="mt-4 text-sm px-3 py-2 rounded-lg"
          style={{ background: "rgba(239,68,68,0.08)", color: "var(--danger)" }}
          data-testid="gift-card-lookup-error"
        >
          {err}
        </div>
      )}

      {result && (
        <div
          className="mt-4 rounded-xl border p-4 flex items-center justify-between gap-3"
          style={{ borderColor: "var(--border)", background: "var(--bg-elev)" }}
          data-testid="gift-card-lookup-result"
        >
          <div className="flex-1 min-w-0">
            <div className="font-mono text-sm" style={{ color: "var(--text)" }}>{result.code}</div>
            <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
              {result.status === "depleted"
                ? "This card has been fully used."
                : `Worth ${result.currency || "NZD"} $${result.amount?.toFixed(2)} when issued.`}
            </div>
          </div>
          <div className="text-right">
            <div
              className="serif text-3xl"
              style={{ color: result.status === "depleted" ? "var(--text-muted)" : "var(--accent)" }}
              data-testid="gift-card-balance-amount"
            >
              ${result.balance?.toFixed(2)}
            </div>
            <div className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
              {result.status === "depleted" ? "Used up" : "Available"}
            </div>
          </div>
          <button onClick={reset} className="ml-2 text-xs underline" style={{ color: "var(--text-muted)" }} data-testid="gift-card-lookup-clear">
            Clear
          </button>
        </div>
      )}
    </div>
  );
}
