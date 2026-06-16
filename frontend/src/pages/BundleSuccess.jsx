import { useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { CheckCircle2, ArrowRight, Package } from "lucide-react";

/**
 * BundleSuccess — landing page after Stripe checkout returns for a bundle.
 * The webhook mints one booking per included event, so the user just heads
 * to Profile → My Tickets to find them.
 */
export default function BundleSuccess() {
  const { bundleId } = useParams();
  useEffect(() => { /* placeholder for analytics */ }, [bundleId]);

  return (
    <div className="max-w-xl mx-auto px-4 py-24 text-center">
      <div className="mb-6 inline-flex items-center justify-center w-16 h-16 rounded-full" style={{ background: "var(--accent-soft)" }}>
        <CheckCircle2 size={32} style={{ color: "var(--accent)" }} />
      </div>
      <h1 className="serif text-4xl mb-3">Your season pass is confirmed 🎟️</h1>
      <p className="text-sm mb-8" style={{ color: "var(--text-muted)" }} data-testid="bundle-success-msg">
        We&apos;re generating one QR ticket per included event. Find them under <strong>Profile → My Tickets</strong>.
      </p>
      <div className="flex gap-3 justify-center">
        <Link to="/profile" className="btn-primary" data-testid="goto-profile">
          See my tickets <ArrowRight size={14} />
        </Link>
        <Link to={`/bundles/${bundleId}`} className="btn-ghost" data-testid="back-to-bundle">
          <Package size={14} /> Back to bundle
        </Link>
      </div>
    </div>
  );
}
