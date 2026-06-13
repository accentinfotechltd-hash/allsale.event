import { useEffect, useState } from "react";
import { Download, X, Smartphone } from "lucide-react";
import { useAuth } from "@/lib/auth";

/**
 * PWA install banner.
 *
 * Shown to organizers (and admins) only — attendees rarely benefit from
 * an installed app, but organizers visit the dashboard daily and gain
 * shortcuts + offline-resilient nav.
 *
 * Behavior:
 *  - Listens for the browser's `beforeinstallprompt` event (Chrome/Edge/Brave).
 *  - On iOS Safari there's no programmatic prompt, so we render a short
 *    instructional banner instead ("Add to Home Screen via Share").
 *  - Dismissals (X button or successful install) are remembered in
 *    localStorage so we don't nag.
 *  - Honors `display-mode: standalone` so we never show inside an already
 *    installed PWA.
 */
const DISMISS_KEY = "allsale_pwa_dismissed_v1";
const SNOOZE_DAYS = 14;

function isStandalone() {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    window.navigator.standalone === true
  );
}

function isIosSafari() {
  if (typeof window === "undefined") return false;
  const ua = window.navigator.userAgent || "";
  const ios = /iPad|iPhone|iPod/.test(ua) && !window.MSStream;
  const safari = /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua);
  return ios && safari;
}

function getDismissed() {
  try {
    const raw = localStorage.getItem(DISMISS_KEY);
    if (!raw) return false;
    const at = parseInt(raw, 10);
    if (!at) return false;
    const ageDays = (Date.now() - at) / (1000 * 60 * 60 * 24);
    return ageDays < SNOOZE_DAYS;
  } catch {
    return false;
  }
}

export default function PwaInstallBanner() {
  const { user } = useAuth();
  const [deferred, setDeferred] = useState(null);
  const [showIos, setShowIos] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!user || (user.role !== "organizer" && user.role !== "admin")) return;
    if (isStandalone() || getDismissed()) return;

    const onPrompt = (e) => {
      e.preventDefault();
      setDeferred(e);
      setVisible(true);
    };
    const onInstalled = () => {
      setVisible(false);
      try { localStorage.setItem(DISMISS_KEY, String(Date.now())); } catch { /* empty */ }
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);

    // iOS Safari fallback — show after a short delay so the banner doesn't
    // race with the rest of the page rendering.
    if (isIosSafari()) {
      const t = setTimeout(() => { setShowIos(true); setVisible(true); }, 1200);
      return () => {
        clearTimeout(t);
        window.removeEventListener("beforeinstallprompt", onPrompt);
        window.removeEventListener("appinstalled", onInstalled);
      };
    }

    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, [user]);

  if (!visible) return null;

  const dismiss = () => {
    try { localStorage.setItem(DISMISS_KEY, String(Date.now())); } catch { /* empty */ }
    setVisible(false);
  };

  const install = async () => {
    if (!deferred) return;
    deferred.prompt();
    try {
      await deferred.userChoice;
    } catch {
      /* ignore */
    }
    setDeferred(null);
    dismiss();
  };

  return (
    <div
      className="fixed bottom-4 right-4 z-[60] max-w-sm rounded-2xl shadow-2xl border p-4 flex items-start gap-3"
      style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}
      data-testid="pwa-install-banner"
    >
      <div
        className="shrink-0 w-10 h-10 rounded-xl flex items-center justify-center"
        style={{ background: "var(--accent)", color: "white" }}
      >
        <Smartphone className="w-5 h-5" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="font-medium text-sm" style={{ color: "var(--text)" }}>
          Install Allsale Events
        </div>
        <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
          {showIos
            ? "Tap Share → Add to Home Screen to use Allsale like a native app."
            : "One tap to add your organizer dashboard to home screen — works offline-friendly."}
        </div>
        {!showIos && (
          <button
            onClick={install}
            className="btn-primary mt-3 !py-1.5 !px-3 text-xs"
            data-testid="pwa-install-btn"
          >
            <Download className="w-3.5 h-3.5" /> Install app
          </button>
        )}
      </div>
      <button
        onClick={dismiss}
        className="shrink-0 p-1 rounded-md hover:opacity-80"
        style={{ color: "var(--text-dim)" }}
        title="Not now"
        data-testid="pwa-dismiss-btn"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}
