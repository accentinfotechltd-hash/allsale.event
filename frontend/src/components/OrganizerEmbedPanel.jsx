import { useState } from "react";
import { Code2, Copy, Check } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";

/**
 * Organizer-facing "Embed on your site" panel.
 *
 * Generates a 2-line HTML snippet the organizer can paste onto any external
 * marketing site to render their upcoming events. Uses the public embed
 * endpoints in `routers/embed.py` (no auth required).
 */
export default function OrganizerEmbedPanel() {
  const { user } = useAuth();
  const [copied, setCopied] = useState(false);
  const [theme, setTheme] = useState("light");
  const [limit, setLimit] = useState(6);

  if (!user || (user.role !== "organizer" && user.role !== "admin")) return null;

  const apiBase = process.env.REACT_APP_BACKEND_URL || window.location.origin;
  const snippet = `<div data-allsale-events data-organizer-id="${user.user_id}" data-theme="${theme}" data-limit="${limit}"></div>
<script src="${apiBase}/api/embed/events.js" async></script>`;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(snippet);
      setCopied(true);
      toast.success("Embed code copied — paste it into your site's HTML.");
      setTimeout(() => setCopied(false), 2500);
    } catch {
      toast.error("Couldn't copy — select and copy manually");
    }
  };

  return (
    <div
      className="mt-10 border rounded-2xl p-6"
      style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
      data-testid="organizer-embed-panel"
    >
      <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>For your website</div>
      <h2 className="serif text-2xl mb-2 flex items-center gap-2"><Code2 className="w-5 h-5" style={{ color: "var(--accent)" }} /> Embed your events on any site</h2>
      <p className="text-sm mb-4" style={{ color: "var(--text-muted)" }}>
        Drop these two lines anywhere on your website (WordPress, Squarespace, Wix, plain HTML). Your latest events render automatically — buyers click through to allsale.events to book.
      </p>

      <div className="flex items-center gap-3 mb-3 flex-wrap text-xs">
        <label className="inline-flex items-center gap-1.5" style={{ color: "var(--text-dim)" }}>
          Theme
          <select
            value={theme}
            onChange={(e) => setTheme(e.target.value)}
            className="!py-1 !px-2 !text-xs"
            data-testid="embed-theme-select"
          >
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </label>
        <label className="inline-flex items-center gap-1.5" style={{ color: "var(--text-dim)" }}>
          Show up to
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="!py-1 !px-2 !text-xs"
            data-testid="embed-limit-select"
          >
            {[3, 6, 9, 12].map((n) => <option key={n} value={n}>{n} events</option>)}
          </select>
        </label>
      </div>

      <div
        className="rounded-lg border p-3 text-xs font-mono whitespace-pre-wrap break-all relative"
        style={{ borderColor: "var(--border)", background: "var(--bg-elev)", color: "var(--text)" }}
        data-testid="embed-snippet"
      >
        {snippet}
        <button
          type="button"
          onClick={copy}
          className="absolute top-2 right-2 inline-flex items-center gap-1 px-2 py-1 rounded-md text-[10px] uppercase tracking-widest font-medium"
          style={{ background: "var(--accent)", color: "#fff" }}
          data-testid="embed-copy-btn"
        >
          {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>

      <p className="text-[11px] mt-3" style={{ color: "var(--text-dim)" }}>
        Tip: the snippet updates in real time — when you add a new event here, it appears on your embedded sites within ~10 minutes (CDN cache). To embed a single event, swap <code>data-organizer-id</code> for <code>data-event-id=&quot;evt_…&quot;</code>.
      </p>
    </div>
  );
}
