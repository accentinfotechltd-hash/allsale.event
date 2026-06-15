import { useState } from "react";
import { ScanLine, Smartphone, Copy, ExternalLink } from "lucide-react";
import { toast } from "sonner";

/**
 * ScannerInstallCard
 * Sits on the Organizer dashboard. Shows a QR code pointing to /scan so
 * door staff can install the Scanner PWA on their phone in 5 seconds —
 * no copy-pasting URLs, no app-store search.
 *
 * Why a free QR API? We already ship `html5-qrcode` (scanner side), but not
 * a QR generator on the frontend. A 200×200 PNG from `api.qrserver.com`
 * keeps the bundle lean and is publicly cacheable.
 */
export default function ScannerInstallCard() {
  const origin = typeof window !== "undefined" ? window.location.origin : "https://www.allsale.events";
  const scanUrl = `${origin}/scan`;
  const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=220x220&margin=0&color=0e0e10&bgcolor=ffffff&data=${encodeURIComponent(scanUrl)}`;
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard?.writeText(scanUrl);
    setCopied(true);
    toast.success("Scanner URL copied!");
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div
      className="rounded-2xl border p-5 sm:p-6 mb-8"
      style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}
      data-testid="scanner-install-card"
    >
      <div className="flex items-start gap-5 flex-wrap">
        <div className="flex-shrink-0 p-2 rounded-xl bg-white" style={{ width: 220 }}>
          <img
            src={qrUrl}
            alt={`QR code linking to ${scanUrl}`}
            width={200}
            height={200}
            className="block mx-auto"
            data-testid="scanner-qr-img"
          />
        </div>

        <div className="flex-1 min-w-[240px]">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs mb-3" style={{ background: "rgba(255,79,0,0.1)", color: "var(--accent)" }}>
            <ScanLine size={12} /> DOOR CHECK-IN
          </div>
          <h3 className="serif text-2xl mb-2">Install the Scanner app</h3>
          <p className="text-sm opacity-80 mb-4 max-w-prose">
            Point your phone's camera at the QR code, tap the notification,
            then on the page that opens: tap your browser's <strong>Share</strong> button →{" "}
            <strong>Add to Home Screen</strong>. A dedicated <em>Scanner</em> icon will
            appear — no app store needed.
          </p>

          <div className="rounded-lg border p-3 flex items-center gap-2 mb-4 text-xs font-mono break-all" style={{ borderColor: "var(--border)", background: "rgba(0,0,0,0.2)" }}>
            <Smartphone size={14} className="flex-shrink-0 opacity-70" />
            <span className="flex-1" data-testid="scanner-install-url">{scanUrl}</span>
          </div>

          <div className="flex gap-2 flex-wrap">
            <button
              type="button"
              onClick={copy}
              data-testid="scanner-install-copy"
              className="px-3 py-2 rounded-lg text-sm border inline-flex items-center gap-1.5"
              style={{ borderColor: "var(--border)" }}
            >
              <Copy size={14} /> {copied ? "Copied!" : "Copy link"}
            </button>
            <a
              href={scanUrl}
              target="_blank"
              rel="noopener noreferrer"
              data-testid="scanner-install-open"
              className="px-3 py-2 rounded-lg text-sm font-medium inline-flex items-center gap-1.5"
              style={{ background: "var(--accent)", color: "#000" }}
            >
              <ExternalLink size={14} /> Open Scanner page
            </a>
          </div>

          <details className="mt-4 text-xs opacity-80">
            <summary className="cursor-pointer hover:opacity-100">📲 Step-by-step instructions for your team</summary>
            <ol className="mt-2 space-y-1 list-decimal list-inside opacity-90">
              <li>Open your phone's camera and point it at the QR above.</li>
              <li>Tap the notification that pops up — it opens <code className="font-mono">/scan</code>.</li>
              <li><strong>iPhone:</strong> Tap the Share icon → "Add to Home Screen" → Add.</li>
              <li><strong>Android Chrome:</strong> Tap the menu (⋮) → "Install app" / "Add to Home screen".</li>
              <li>A "Scanner" icon appears. Tap it any time to start checking tickets at the door.</li>
            </ol>
          </details>
        </div>
      </div>
    </div>
  );
}
