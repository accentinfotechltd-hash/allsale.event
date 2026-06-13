import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Heart } from "lucide-react";

/**
 * "Recommended by X" social-proof banner shown at the top of EventDetail
 * when the visitor arrived via an affiliate link (aff_code cookie set).
 *
 * Reads the cookie → fetches /api/affiliate/{code} for the partner_name →
 * renders a slim acknowledgement strip. Silently hides if no cookie or
 * cookie code is invalid/inactive.
 *
 * UX rationale:
 *   - Buyer-trust signal: confirms the influencer link they clicked is real
 *   - Visible credit for the influencer (low-effort retention of partners)
 *   - Dismissable per-session so it doesn't get annoying on repeat visits
 */
const DISMISS_KEY = "allsale_aff_banner_dismissed";

function readCookie(name) {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split("; ")
    .find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=")[1]) : null;
}

export default function AffiliateBanner() {
  const [partner, setPartner] = useState(null);
  const [dismissed, setDismissed] = useState(() => {
    if (typeof window === "undefined") return false;
    return !!sessionStorage.getItem(DISMISS_KEY);
  });

  useEffect(() => {
    if (dismissed) return;
    const code = readCookie("aff_code");
    if (!code) return;
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get(`/affiliate/${code}`);
        if (!cancelled) setPartner(data);
      } catch {
        // Inactive or unknown code — silently skip
      }
    })();
    return () => { cancelled = true; };
  }, [dismissed]);

  if (dismissed || !partner) return null;

  return (
    <div
      className="mb-6 px-4 py-2.5 rounded-xl border flex items-center gap-3"
      style={{
        background: "linear-gradient(135deg, rgba(240,138,42,0.10), rgba(240,138,42,0.04))",
        borderColor: "rgba(240,138,42,0.25)",
      }}
      data-testid="affiliate-banner"
    >
      <Heart className="w-4 h-4 flex-shrink-0" style={{ color: "var(--accent)" }} />
      <div className="flex-1 text-sm" style={{ color: "var(--text)" }}>
        Recommended by <strong data-testid="affiliate-banner-partner">{partner.partner_name}</strong>
        <span className="hidden sm:inline" style={{ color: "var(--text-muted)" }}> — thanks for supporting through their link 🎟️</span>
      </div>
      <button
        onClick={() => { sessionStorage.setItem(DISMISS_KEY, "1"); setDismissed(true); }}
        className="text-xs"
        style={{ color: "var(--text-dim)" }}
        title="Dismiss"
        data-testid="affiliate-banner-dismiss"
      >
        ×
      </button>
    </div>
  );
}
