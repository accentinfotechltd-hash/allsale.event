import { useEffect, useState } from "react";
import { Mail, Eye, Send, Loader2 } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

/**
 * Admin tab for previewing and sending the two recruitment email flyers
 * (organizer pitch / influencer pitch). The preview iframe fetches HTML via
 * the authenticated api client and injects it via `srcDoc` (bare iframe src
 * couldn't pass the Bearer token); the send box posts a comma- or
 * newline-delimited list of email addresses to the `flyer-send` endpoint
 * (cap of 200 per call enforced server-side).
 */

const FLYERS = [
  {
    kind: "organizer_features_flyer",
    title: "Organizer pitch flyer",
    audience: "Event organizers (existing or prospects)",
    description: "Pitches every feature that helps organizers sell more, work less, and keep 100% of the ticket price.",
  },
  {
    kind: "influencer_features_flyer",
    title: "Influencer pitch flyer",
    audience: "Influencers / marketing partners",
    description: "Pitches the Marketing Partner program — recurring commission, monthly statements, payouts on the 5th, ready-made assets.",
  },
];

export default function AdminFlyersTab() {
  const [selected, setSelected] = useState(FLYERS[0].kind);
  const [recipients, setRecipients] = useState("");
  const [sending, setSending] = useState(false);
  const [previewHtml, setPreviewHtml] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);

  // Fetch the rendered HTML via api (carries the JWT) and inject into iframe srcDoc.
  useEffect(() => {
    let cancelled = false;
    setPreviewLoading(true);
    api
      .get(`/admin/marketing/flyer-preview/${selected}`, { responseType: "text", transformResponse: (d) => d })
      .then((res) => { if (!cancelled) setPreviewHtml(res.data); })
      .catch(() => { if (!cancelled) setPreviewHtml("<p style='color:#fff;padding:24px;'>Failed to load preview</p>"); })
      .finally(() => { if (!cancelled) setPreviewLoading(false); });
    return () => { cancelled = true; };
  }, [selected]);

  const parseEmails = () =>
    recipients
      .split(/[\n,;\s]+/)
      .map((e) => e.trim().toLowerCase())
      .filter((e) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e));

  const submit = async () => {
    const emails = parseEmails();
    if (emails.length === 0) {
      toast.error("Add at least one valid email address");
      return;
    }
    if (emails.length > 200) {
      toast.error("Max 200 recipients per send — split the list into batches");
      return;
    }
    if (!window.confirm(`Send this flyer to ${emails.length} recipient(s)?`)) return;
    setSending(true);
    try {
      const res = await api.post("/admin/marketing/flyer-send", { kind: selected, emails });
      toast.success(`Queued ${res.data.queued}/${res.data.total_recipients} sends`);
      setRecipients("");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to send flyer");
    } finally {
      setSending(false);
    }
  };

  // Open the live preview in a new browser tab using a Blob URL — works around
  // the fact that the GET endpoint requires a Bearer token (a raw URL wouldn't).
  const openInNewTab = () => {
    if (!previewHtml) return;
    const blob = new Blob([previewHtml], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener");
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  };

  return (
    <div data-testid="admin-flyers-tab">      <div className="flex items-center gap-2 text-xs uppercase tracking-widest mb-2" style={{ color: "var(--accent)" }}>
        <Mail size={13} /> Recruitment flyers
      </div>
      <h2 className="font-serif text-2xl mb-1" style={{ color: "var(--text)" }}>
        Send pitch emails to organizers &amp; influencers
      </h2>
      <p className="text-sm mb-6" style={{ color: "var(--text)" }}>
        Preview the email below, then paste a list of addresses (newline / comma / space separated) and hit send.
      </p>

      {/* Flyer picker */}
      <div className="grid sm:grid-cols-2 gap-3 mb-6">
        {FLYERS.map((f) => {
          const active = f.kind === selected;
          return (
            <button
              key={f.kind}
              type="button"
              onClick={() => setSelected(f.kind)}
              className="text-left rounded-xl border p-4 transition"
              style={{
                borderColor: active ? "var(--accent)" : "var(--border)",
                background: active ? "rgba(240,138,42,0.05)" : "transparent",
              }}
              data-testid={`flyer-pick-${f.kind}`}
            >
              <div className="font-semibold text-sm mb-1" style={{ color: "var(--text)" }}>{f.title}</div>
              <div className="text-xs mb-1.5" style={{ color: "var(--accent)" }}>{f.audience}</div>
              <div className="text-xs leading-relaxed" style={{ color: "var(--text)" }}>{f.description}</div>
            </button>
          );
        })}
      </div>

      <div className="grid lg:grid-cols-5 gap-6">
        {/* Preview pane */}
        <div className="lg:col-span-3 rounded-xl border overflow-hidden" style={{ borderColor: "var(--border)" }}>
          <div className="flex items-center justify-between px-4 py-2 border-b text-xs" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
            <span>
              <Eye size={12} className="inline mr-1" />
              {previewLoading ? "Loading preview…" : "Live preview"}
            </span>
            <button
              type="button"
              onClick={openInNewTab}
              disabled={!previewHtml}
              className="underline disabled:opacity-40"
              style={{ color: "var(--accent)" }}
              data-testid="flyer-open-in-tab"
            >
              Open in new tab ↗
            </button>
          </div>
          <iframe
            key={selected}
            srcDoc={previewHtml}
            title="Flyer preview"
            className="w-full"
            style={{ height: 620, background: "#0B0B0E", border: 0 }}
            data-testid="flyer-preview-iframe"
          />
        </div>

        {/* Send form */}
        <div className="lg:col-span-2 rounded-xl border p-4" style={{ borderColor: "var(--border)" }}>
          <div className="text-xs uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>Recipients</div>
          <textarea
            value={recipients}
            onChange={(e) => setRecipients(e.target.value)}
            placeholder="alice@example.com, bob@example.com&#10;or paste one per line&#10;(max 200)"
            rows={12}
            className="w-full px-3 py-2 rounded-md border text-sm font-mono"
            style={{ borderColor: "var(--border)", background: "transparent", color: "var(--text)" }}
            data-testid="flyer-recipients-textarea"
          />
          <div className="text-xs mt-2 mb-3" style={{ color: "var(--text-dim)" }}>
            {parseEmails().length} valid recipient(s) detected
          </div>
          <button
            onClick={submit}
            disabled={sending || parseEmails().length === 0}
            className="btn-primary w-full justify-center text-sm inline-flex items-center gap-1.5"
            data-testid="flyer-send-btn"
          >
            {sending ? (
              <>
                <Loader2 className="animate-spin" size={14} /> Sending…
              </>
            ) : (
              <>
                <Send size={14} /> Send to {parseEmails().length || 0} recipient(s)
              </>
            )}
          </button>
          <p className="text-xs mt-3" style={{ color: "var(--text-dim)" }}>
            Each email is personalized with the recipient&apos;s name if we already have them on file. Bounces and failures are logged in the Emails tab.
          </p>
        </div>
      </div>
    </div>
  );
}
