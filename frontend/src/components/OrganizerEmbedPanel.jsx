import { useEffect, useState } from "react";
import { Code2, Copy, Check, BarChart3, MousePointerClick, Eye, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/lib/auth";
import api from "@/lib/api";

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

      <EmbedAnalytics />
    </div>
  );
}

function EmbedAnalytics() {
  const [data, setData] = useState(null);
  const [days, setDays] = useState(30);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get(`/organizer/embed/analytics?days=${days}`);
        if (!cancelled) setData(data);
      } catch {
        if (!cancelled) setData({ totals: { impressions: 0, clicks: 0, ctr_pct: 0 }, by_host: [], by_event: [], daily: [] });
      }
    })();
    return () => { cancelled = true; };
  }, [days]);

  return (
    <div
      className="mt-6 pt-5 border-t"
      style={{ borderColor: "var(--border)" }}
      data-testid="embed-analytics-section"
    >
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="text-sm font-semibold flex items-center gap-2">
          <BarChart3 className="w-4 h-4" style={{ color: "var(--accent)" }} />
          Embed traffic
        </div>
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="!py-1 !px-2 !text-xs"
          data-testid="embed-analytics-range"
        >
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
      </div>

      {!data ? (
        <div className="text-xs flex items-center gap-2" style={{ color: "var(--text-dim)" }}>
          <Loader2 className="w-3 h-3 animate-spin" /> Loading widget stats…
        </div>
      ) : (
        <>
          <div className="grid sm:grid-cols-3 gap-3 mb-4">
            <Kpi icon={<Eye className="w-4 h-4" />} label="Impressions" value={data.totals.impressions.toLocaleString()} testid="embed-kpi-impressions" />
            <Kpi icon={<MousePointerClick className="w-4 h-4" />} label="Clicks" value={data.totals.clicks.toLocaleString()} testid="embed-kpi-clicks" />
            <Kpi icon={<BarChart3 className="w-4 h-4" />} label="CTR" value={`${data.totals.ctr_pct}%`} testid="embed-kpi-ctr" />
          </div>

          {data.by_host.length === 0 ? (
            <div className="text-xs text-center py-4" style={{ color: "var(--text-dim)" }}>
              No widget traffic yet — once your embed renders on an external site, hosts will appear here.
            </div>
          ) : (
            <div className="grid md:grid-cols-2 gap-4">
              <HostTable rows={data.by_host} />
              <EventTable rows={data.by_event} />
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Kpi({ icon, label, value, testid }) {
  return (
    <div
      className="border rounded-xl p-3 flex items-center justify-between"
      style={{ borderColor: "var(--border)", background: "var(--bg-elev)" }}
      data-testid={testid}
    >
      <div>
        <div className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>{label}</div>
        <div className="text-xl serif" style={{ color: "var(--text)" }}>{value}</div>
      </div>
      <div style={{ color: "var(--accent)" }}>{icon}</div>
    </div>
  );
}

function HostTable({ rows }) {
  return (
    <div className="border rounded-xl overflow-hidden" style={{ borderColor: "var(--border)" }}>
      <div className="px-3 py-2 text-[10px] uppercase tracking-widest border-b" style={{ borderColor: "var(--border)", background: "var(--bg-elev)", color: "var(--text-dim)" }}>
        Top referring sites
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
            <th className="text-left p-2">Host</th>
            <th className="text-right p-2">Views</th>
            <th className="text-right p-2">Clicks</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.host} className="border-b" style={{ borderColor: "var(--border)" }}>
              <td className="p-2 truncate max-w-[180px]" title={r.host}>{r.host}</td>
              <td className="p-2 text-right">{r.impressions}</td>
              <td className="p-2 text-right">{r.clicks}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EventTable({ rows }) {
  return (
    <div className="border rounded-xl overflow-hidden" style={{ borderColor: "var(--border)" }}>
      <div className="px-3 py-2 text-[10px] uppercase tracking-widest border-b" style={{ borderColor: "var(--border)", background: "var(--bg-elev)", color: "var(--text-dim)" }}>
        Top events
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
            <th className="text-left p-2">Event</th>
            <th className="text-right p-2">Views</th>
            <th className="text-right p-2">Clicks</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.event_id} className="border-b" style={{ borderColor: "var(--border)" }}>
              <td className="p-2 truncate max-w-[180px]" title={r.title}>{r.title || r.event_id}</td>
              <td className="p-2 text-right">{r.impressions}</td>
              <td className="p-2 text-right">{r.clicks}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
