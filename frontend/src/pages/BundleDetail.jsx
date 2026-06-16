import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Calendar, MapPin, Package, ArrowRight, Sparkles } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatMoney } from "@/lib/currencies";

/**
 * BundleDetail — public season-pass landing.
 * One click → Stripe checkout. On webhook success the backend mints one
 * booking per included event under the buyer's account.
 */
export default function BundleDetail() {
  const { bundleId } = useParams();
  const { user } = useAuth();
  const [bundle, setBundle] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get(`/bundles/${bundleId}`);
        if (!cancelled) setBundle(data);
      } catch {
        if (!cancelled) toast.error("Bundle not found");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [bundleId]);

  const onPurchase = async () => {
    if (!user) {
      toast("Please sign in to buy a season pass");
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await api.post(`/bundles/${bundleId}/purchase`, {
        origin_url: window.location.origin,
      });
      if (data.url) window.location.href = data.url;
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Checkout failed");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div className="text-center py-20" style={{ color: "var(--text-muted)" }}>Loading...</div>;
  if (!bundle) return <div className="text-center py-20">Bundle not available</div>;

  return (
    <div className="max-w-4xl mx-auto px-4 py-10">
      {bundle.image_url && (
        <div className="relative h-[280px] overflow-hidden rounded-2xl mb-6">
          <img src={bundle.image_url} alt={bundle.title} className="w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-[color:var(--bg)] to-transparent" />
        </div>
      )}

      <div className="flex items-center gap-2 text-xs uppercase tracking-widest mb-3" style={{ color: "var(--accent)" }}>
        <Package size={14} /> Season pass · {bundle.events?.length} events
      </div>
      <h1 className="serif text-4xl sm:text-5xl mb-3" data-testid="bundle-title">{bundle.title}</h1>
      <p className="text-sm mb-8" style={{ color: "var(--text-muted)" }}>{bundle.description}</p>

      <div className="grid md:grid-cols-[2fr_1fr] gap-8">
        <div data-testid="bundle-events-list">
          <div className="text-xs uppercase tracking-widest mb-3" style={{ color: "var(--text-dim)" }}>Included events</div>
          <div className="space-y-3">
            {bundle.events?.map((e) => (
              <Link
                key={e.event_id}
                to={`/events/${e.event_id}`}
                className="flex gap-4 p-3 rounded-xl border hover:border-2 transition"
                style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
                data-testid={`bundle-event-${e.event_id}`}
              >
                <img src={e.image_url} alt={e.title} className="w-20 h-20 object-cover rounded-lg flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="font-medium truncate">{e.title}</div>
                  <div className="text-xs mt-1 flex items-center gap-2 flex-wrap" style={{ color: "var(--text-muted)" }}>
                    <Calendar size={11} /> {e.date ? new Date(e.date).toLocaleDateString() : "TBA"}
                    <span>•</span>
                    <MapPin size={11} /> {e.venue}, {e.city}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>

        <aside>
          <div
            className="rounded-2xl border p-5 sticky top-24"
            style={{ borderColor: "var(--border-strong)", background: "var(--bg-card)" }}
            data-testid="bundle-purchase-card"
          >
            <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>Season pass</div>
            <div className="serif text-5xl mb-2" style={{ color: "var(--accent)" }} data-testid="bundle-price">
              {formatMoney(bundle.price, bundle.currency)}
            </div>
            {bundle.savings > 0 && (
              <div className="flex items-center gap-1 text-xs mb-4" style={{ color: "var(--accent)" }} data-testid="bundle-savings">
                <Sparkles size={11} /> Save {formatMoney(bundle.savings, bundle.currency)} vs buying separately
              </div>
            )}
            {bundle.capacity != null && (
              <div className="text-xs mb-3" style={{ color: "var(--text-muted)" }}>
                {Math.max(0, bundle.capacity - (bundle.sold_count || 0))} of {bundle.capacity} passes left
              </div>
            )}
            <button
              onClick={onPurchase}
              disabled={submitting}
              className="btn-primary w-full justify-center mt-2"
              data-testid="buy-bundle-btn"
            >
              {submitting ? "Redirecting..." : "Buy season pass"} <ArrowRight size={14} />
            </button>
            <div className="text-xs mt-3" style={{ color: "var(--text-muted)" }}>
              One booking per included event will appear in your Profile after payment.
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
