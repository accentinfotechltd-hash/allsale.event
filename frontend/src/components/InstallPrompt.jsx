import { useEffect, useState } from "react";
import { Download, X } from "lucide-react";

/**
 * InstallPrompt — surfaces the "Add to Home Screen" experience.
 *  • Android / Desktop Chrome: uses the native beforeinstallprompt event.
 *  • iOS Safari: shows manual "Tap Share → Add to Home Screen" instructions
 *    (since iOS doesn't support beforeinstallprompt).
 * Honours a "dismissed" flag in localStorage so we don't nag users.
 */
const DISMISS_KEY = "allsale_install_dismissed_at";
const DISMISS_DAYS = 14;

function isIOS() {
  if (typeof navigator === "undefined") return false;
  return /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
}

function isStandalone() {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    window.navigator.standalone === true
  );
}

function wasRecentlyDismissed() {
  try {
    const ts = parseInt(localStorage.getItem(DISMISS_KEY) || "0", 10);
    if (!ts) return false;
    const ageDays = (Date.now() - ts) / (1000 * 60 * 60 * 24);
    return ageDays < DISMISS_DAYS;
  } catch {
    return false;
  }
}

export default function InstallPrompt() {
  const [deferred, setDeferred] = useState(null);
  const [show, setShow] = useState(false);
  const [iosHint, setIosHint] = useState(false);

  useEffect(() => {
    if (isStandalone() || wasRecentlyDismissed()) return;

    // Chrome / Edge / Android — capture the install prompt
    const onBeforeInstall = (e) => {
      e.preventDefault();
      setDeferred(e);
      setShow(true);
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstall);

    // iOS Safari — no event fires, so show our manual hint after a small delay
    if (isIOS()) {
      const t = setTimeout(() => {
        setIosHint(true);
        setShow(true);
      }, 3000);
      return () => {
        clearTimeout(t);
        window.removeEventListener("beforeinstallprompt", onBeforeInstall);
      };
    }

    return () => window.removeEventListener("beforeinstallprompt", onBeforeInstall);
  }, []);

  const dismiss = () => {
    try { localStorage.setItem(DISMISS_KEY, String(Date.now())); } catch {}
    setShow(false);
  };

  const install = async () => {
    if (!deferred) return;
    deferred.prompt();
    const choice = await deferred.userChoice;
    if (choice?.outcome === "accepted") {
      setShow(false);
    } else {
      dismiss();
    }
    setDeferred(null);
  };

  if (!show) return null;

  return (
    <div
      role="dialog"
      aria-live="polite"
      data-testid="install-prompt"
      className="fixed left-4 right-4 z-[9000] rounded-2xl shadow-2xl border p-4 flex items-center gap-3"
      style={{
        bottom: "calc(16px + env(safe-area-inset-bottom, 0px))",
        background: "var(--bg-card, #ffffff)",
        borderColor: "var(--border, #e7e5e4)",
        color: "var(--text, #1c1917)",
        maxWidth: "440px",
        marginLeft: "auto",
        marginRight: "auto",
      }}
    >
      <div
        className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0"
        style={{ background: "#0D9488", color: "#fff" }}
      >
        <Download className="w-6 h-6" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold leading-tight">
          {iosHint ? "Install Allsale Events" : "Install our app"}
        </div>
        <div className="text-xs mt-0.5" style={{ color: "var(--text-muted, #57534e)" }}>
          {iosHint
            ? "Tap Share → \u201CAdd to Home Screen\u201D"
            : "Faster check-in, offline tickets, one-tap launch."}
        </div>
      </div>
      {!iosHint && deferred && (
        <button
          type="button"
          onClick={install}
          data-testid="install-prompt-install"
          className="px-3 py-2 text-sm font-medium rounded-full"
          style={{ background: "#0D9488", color: "#fff" }}
        >
          Install
        </button>
      )}
      <button
        type="button"
        onClick={dismiss}
        aria-label="Dismiss install prompt"
        data-testid="install-prompt-dismiss"
        className="p-2 rounded-full hover:opacity-70 transition"
        style={{ color: "var(--text-muted, #57534e)" }}
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}
