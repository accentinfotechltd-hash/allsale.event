import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { QrCode, ScanLine, ArrowRight, Loader2, AlertCircle } from "lucide-react";
import api from "@/lib/api";
import { toast } from "sonner";
import { useScannerManifest } from "@/lib/useScannerManifest";

/**
 * Allsale Scanner — entry point at /scan.
 *
 * This is a separate installable PWA scoped to /scan/* (see
 * public/scanner.webmanifest). When opened, the device prompts to "Add to
 * Home Screen" → installs as its own app icon labelled "Scanner".
 *
 * Two ways to start a scan session:
 *   1. The organizer shares a "magic link" with door staff:
 *      https://www.allsale.events/scan?t=tok_xxx&event=evt_xxx
 *      → auto-redirects into the live CheckIn screen.
 *   2. Door staff with no link can paste their token here.
 *
 * UX intentionally kiosk-friendly: dark background, big buttons, no nav
 * chrome (Layout hides itself on /scan/*).
 */
export default function ScannerEntry() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const tokenInUrl = params.get("t") || params.get("token");
  const eventInUrl = params.get("event") || params.get("event_id");
  const [token, setToken] = useState("");
  const [event, setEvent] = useState("");
  const [validating, setValidating] = useState(false);

  // Mutate the existing <link rel="manifest"> href so the "Add to Home Screen"
  // prompt advertises the Scanner PWA (scope=/scan), then restore on unmount.
  // See /app/frontend/src/lib/useScannerManifest.js for the rationale (Chrome
  // honours the FIRST manifest link in tree order — appending a second one is
  // a no-op for installability).
  useScannerManifest();

  // Auto-flow: if a complete magic link was provided in the URL, hop
  // straight to the CheckIn page without making the user paste anything.
  useEffect(() => {
    if (tokenInUrl && eventInUrl) {
      navigate(`/events/${eventInUrl}/check-in?t=${tokenInUrl}`, { replace: true });
    }
  }, [tokenInUrl, eventInUrl, navigate]);

  const start = async () => {
    const t = token.trim();
    const e = event.trim();
    if (!t || !e) {
      toast.error("Both token and event ID required");
      return;
    }
    setValidating(true);
    try {
      // Validate by pre-fetching scanner-context. If it fails, error.
      await api.get(`/organizer/scanner-context`, { params: { event_id: e, token: t } });
      navigate(`/events/${e}/check-in?t=${t}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Invalid token or event");
    } finally {
      setValidating(false);
    }
  };

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center px-6"
      style={{ background: "#0e0e10", color: "#f5f4ef" }}
      data-testid="scanner-entry"
    >
      <div className="w-full max-w-sm text-center">
        <div
          className="w-20 h-20 rounded-3xl mx-auto mb-5 flex items-center justify-center"
          style={{ background: "linear-gradient(135deg, #FF4F00, #ff8a2a)" }}
        >
          <ScanLine className="w-10 h-10" />
        </div>
        <h1 className="text-3xl font-light mb-1" style={{ fontFamily: "Georgia, serif" }}>Allsale Scanner</h1>
        <p className="text-sm mb-8" style={{ color: "#9a988f" }}>
          Door check-in for event staff. Add this page to your home screen for a one-tap scanner app.
        </p>

        {tokenInUrl && eventInUrl ? (
          <div className="flex items-center gap-3 justify-center" style={{ color: "#9a988f" }}>
            <Loader2 className="w-4 h-4 animate-spin" />
            Opening scanner…
          </div>
        ) : (
          <>
            <div className="space-y-3 text-left">
              <div>
                <label className="text-xs uppercase tracking-widest" style={{ color: "#9a988f" }}>Event ID</label>
                <input
                  value={event}
                  onChange={(e) => setEvent(e.target.value)}
                  placeholder="evt_xxxxxxxx"
                  className="w-full mt-1 px-3 py-3 rounded-lg border bg-transparent text-base"
                  style={{ borderColor: "#26262a", color: "#f5f4ef" }}
                  data-testid="scanner-event-input"
                  autoComplete="off"
                />
              </div>
              <div>
                <label className="text-xs uppercase tracking-widest" style={{ color: "#9a988f" }}>Scanner token</label>
                <input
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="tok_xxxxxxxx"
                  className="w-full mt-1 px-3 py-3 rounded-lg border bg-transparent text-base"
                  style={{ borderColor: "#26262a", color: "#f5f4ef" }}
                  data-testid="scanner-token-input"
                  autoComplete="off"
                />
              </div>
              <button
                onClick={start}
                disabled={validating}
                className="w-full mt-2 px-4 py-3 rounded-lg font-semibold flex items-center justify-center gap-2"
                style={{ background: "#FF4F00", color: "#fff" }}
                data-testid="scanner-start-btn"
              >
                {validating ? <Loader2 className="w-4 h-4 animate-spin" /> : <QrCode className="w-4 h-4" />}
                Start scanning
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>

            <div className="mt-8 p-4 rounded-xl text-xs flex items-start gap-2 text-left" style={{ background: "rgba(255,79,0,0.08)", color: "#cab8a0" }}>
              <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" style={{ color: "#FF4F00" }} />
              <span>
                Don&apos;t have a token? Ask the organizer — they generate scanner links from their event dashboard → <strong>Door check-in</strong> → <strong>Share scanner link</strong>.
              </span>
            </div>

            <p className="mt-8 text-[11px]" style={{ color: "#666560" }}>
              Tip: install this as a home-screen app for fastest access at the door.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
