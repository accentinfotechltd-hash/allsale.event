import { useEffect, useState, useRef, useCallback } from "react";
import { Mail, Eye, Send, Loader2, Upload, Clock, Trash2, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

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

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function AdminFlyersTab() {
  const [selected, setSelected] = useState(FLYERS[0].kind);
  const [recipients, setRecipients] = useState("");
  const [label, setLabel] = useState("");
  const [scheduleMode, setScheduleMode] = useState("now"); // "now" | "later"
  const [scheduledFor, setScheduledFor] = useState("");
  const [sending, setSending] = useState(false);
  const [previewHtml, setPreviewHtml] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [campaigns, setCampaigns] = useState([]);
  const fileInputRef = useRef(null);

  // Fetch the rendered HTML preview via api (carries the JWT).
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

  const refreshCampaigns = useCallback(async () => {
    try {
      const r = await api.get("/admin/marketing/flyer-campaigns?limit=20");
      setCampaigns(r.data?.items || []);
    } catch {
      // ignore — non-critical
    }
  }, []);

  useEffect(() => { refreshCampaigns(); }, [refreshCampaigns]);

  const parseEmails = () => {
    const seen = new Set();
    return recipients
      .split(/[\n,;\s]+/)
      .map((e) => e.trim().toLowerCase())
      .filter((e) => {
        if (!EMAIL_RE.test(e) || seen.has(e)) return false;
        seen.add(e);
        return true;
      });
  };

  const handleCsvFile = (file) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result || "");
      // Auto-detect: split on commas, newlines, tabs; pick anything that looks like an email
      const found = text.match(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g) || [];
      const dedup = Array.from(new Set(found.map((e) => e.toLowerCase())));
      if (dedup.length === 0) {
        toast.error("No valid email addresses found in that CSV");
        return;
      }
      setRecipients(dedup.join("\n"));
      toast.success(`Loaded ${dedup.length} unique emails from CSV`);
    };
    reader.onerror = () => toast.error("Failed to read file");
    reader.readAsText(file);
  };

  const onDrop = (e) => {
    e.preventDefault();
    const file = e.dataTransfer?.files?.[0];
    if (file) handleCsvFile(file);
  };

  const submit = async () => {
    const emails = parseEmails();
    if (emails.length === 0) {
      toast.error("Add at least one valid email address");
      return;
    }
    let scheduled_for = null;
    if (scheduleMode === "later") {
      if (!scheduledFor) { toast.error("Pick a date & time"); return; }
      const dt = new Date(scheduledFor);
      if (Number.isNaN(dt.getTime()) || dt.getTime() <= Date.now() + 60_000) {
        toast.error("Scheduled time must be at least 1 minute in the future");
        return;
      }
      scheduled_for = dt.toISOString();
      if (emails.length > 5000) { toast.error("Max 5000 recipients per scheduled campaign"); return; }
    } else if (emails.length > 200) {
      toast.error("Max 200 when sending now — switch to 'Schedule for later'");
      return;
    }
    const verb = scheduled_for ? `Schedule for ${new Date(scheduledFor).toLocaleString()}` : "Send now";
    if (!window.confirm(`${verb} to ${emails.length} recipient(s)?`)) return;
    setSending(true);
    try {
      const res = await api.post("/admin/marketing/flyer-send", {
        kind: selected,
        emails,
        scheduled_for,
        label: label || null,
      });
      if (res.data.status === "scheduled") {
        toast.success(`Scheduled ${emails.length} send(s) for ${new Date(scheduledFor).toLocaleString()}`);
      } else {
        toast.success(`Sent ${res.data.sent}/${res.data.total_recipients} (${res.data.failed} failed)`);
      }
      setRecipients("");
      setLabel("");
      setScheduledFor("");
      refreshCampaigns();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to send flyer");
    } finally {
      setSending(false);
    }
  };

  const openInNewTab = () => {
    if (!previewHtml) return;
    const blob = new Blob([previewHtml], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener");
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  };

  const cancelCampaign = async (cid) => {
    if (!window.confirm("Cancel this scheduled campaign?")) return;
    try {
      await api.delete(`/admin/marketing/flyer-campaigns/${cid}`);
      toast.success("Cancelled");
      refreshCampaigns();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't cancel");
    }
  };

  const validCount = parseEmails().length;

  return (
    <div data-testid="admin-flyers-tab">
      <div className="flex items-center gap-2 text-xs uppercase tracking-widest mb-2" style={{ color: "var(--accent)" }}>
        <Mail size={13} /> Recruitment flyers
      </div>
      <h2 className="font-serif text-2xl mb-1" style={{ color: "var(--text)" }}>
        Send pitch emails to organizers &amp; influencers
      </h2>
      <p className="text-sm mb-6" style={{ color: "var(--text)" }}>
        Preview the email, paste or drop a CSV of recipients, schedule for later if you like.
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
        {/* Preview */}
        <div className="lg:col-span-3 rounded-xl border overflow-hidden" style={{ borderColor: "var(--border)" }}>
          <div className="flex items-center justify-between px-4 py-2 border-b text-xs" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
            <span><Eye size={12} className="inline mr-1" /> {previewLoading ? "Loading…" : "Live preview"}</span>
            <button type="button" onClick={openInNewTab} disabled={!previewHtml} className="underline disabled:opacity-40" style={{ color: "var(--accent)" }} data-testid="flyer-open-in-tab">
              Open in new tab ↗
            </button>
          </div>
          <iframe key={selected} srcDoc={previewHtml} title="Flyer preview" className="w-full" style={{ height: 620, background: "#0B0B0E", border: 0 }} data-testid="flyer-preview-iframe" />
        </div>

        {/* Send form */}
        <div className="lg:col-span-2 rounded-xl border p-4 space-y-4" style={{ borderColor: "var(--border)" }}>
          {/* Optional campaign label */}
          <div>
            <label className="block text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>Campaign label <span className="opacity-60">(optional)</span></label>
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value.slice(0, 80))}
              placeholder="e.g. Q1 2026 organizer push"
              className="w-full px-3 py-2 rounded-md border text-sm"
              style={{ borderColor: "var(--border)", background: "transparent", color: "var(--text)" }}
              data-testid="flyer-label-input"
            />
          </div>

          {/* Schedule mode */}
          <div>
            <div className="block text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>When</div>
            <div className="flex gap-2">
              <button type="button" onClick={() => setScheduleMode("now")} className="flex-1 text-sm py-2 rounded-md border transition" style={{ borderColor: scheduleMode === "now" ? "var(--accent)" : "var(--border)", background: scheduleMode === "now" ? "rgba(240,138,42,0.08)" : "transparent", color: "var(--text)" }} data-testid="schedule-now-btn">
                <Send size={12} className="inline mr-1.5" /> Send now
              </button>
              <button type="button" onClick={() => setScheduleMode("later")} className="flex-1 text-sm py-2 rounded-md border transition" style={{ borderColor: scheduleMode === "later" ? "var(--accent)" : "var(--border)", background: scheduleMode === "later" ? "rgba(240,138,42,0.08)" : "transparent", color: "var(--text)" }} data-testid="schedule-later-btn">
                <Clock size={12} className="inline mr-1.5" /> Schedule
              </button>
            </div>
            {scheduleMode === "later" && (
              <input
                type="datetime-local"
                value={scheduledFor}
                onChange={(e) => setScheduledFor(e.target.value)}
                className="w-full mt-2 px-3 py-2 rounded-md border text-sm"
                style={{ borderColor: "var(--border)", background: "transparent", color: "var(--text)" }}
                data-testid="flyer-scheduled-for-input"
              />
            )}
          </div>

          {/* Recipients */}
          <div>
            <label className="block text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>Recipients</label>
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={onDrop}
              className="relative"
            >
              <textarea
                value={recipients}
                onChange={(e) => setRecipients(e.target.value)}
                placeholder="paste emails, drop a .csv, or click 'Upload CSV' below"
                rows={8}
                className="w-full px-3 py-2 rounded-md border text-sm font-mono"
                style={{ borderColor: "var(--border)", background: "transparent", color: "var(--text)" }}
                data-testid="flyer-recipients-textarea"
              />
            </div>
            <div className="flex items-center justify-between mt-2">
              <span className="text-xs" style={{ color: "var(--text-dim)" }}>
                {validCount} valid recipient(s){validCount > 200 && scheduleMode === "now" ? " — switch to Schedule" : ""}
              </span>
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="text-xs inline-flex items-center gap-1 underline"
                style={{ color: "var(--accent)" }}
                data-testid="flyer-csv-upload-btn"
              >
                <Upload size={11} /> Upload CSV
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,text/csv,.txt,text/plain"
                onChange={(e) => handleCsvFile(e.target.files?.[0])}
                style={{ display: "none" }}
                data-testid="flyer-csv-input"
              />
            </div>
          </div>

          <button
            onClick={submit}
            disabled={sending || validCount === 0}
            className="btn-primary w-full justify-center text-sm inline-flex items-center gap-1.5"
            data-testid="flyer-send-btn"
          >
            {sending ? (<><Loader2 className="animate-spin" size={14} /> Working…</>) : scheduleMode === "later" ? (<><Clock size={14} /> Schedule {validCount} send(s)</>) : (<><Send size={14} /> Send to {validCount} recipient(s)</>)}
          </button>
          <p className="text-xs" style={{ color: "var(--text-dim)" }}>
            Personalised salutation if we have the recipient on file. Opens / clicks tracked via Resend webhooks.
          </p>
        </div>
      </div>

      {/* Campaigns history */}
      <div className="mt-10 rounded-xl border" style={{ borderColor: "var(--border)" }} data-testid="flyer-campaigns-list">
        <div className="px-4 py-3 border-b flex items-center justify-between" style={{ borderColor: "var(--border)" }}>
          <h3 className="font-serif text-lg" style={{ color: "var(--text)" }}>Recent campaigns</h3>
          <button onClick={refreshCampaigns} className="text-xs inline-flex items-center gap-1 underline" style={{ color: "var(--accent)" }} data-testid="flyer-refresh-campaigns-btn">
            <RefreshCw size={11} /> Refresh
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
                <th className="text-left px-4 py-2">Status</th>
                <th className="text-left px-4 py-2">Label / Kind</th>
                <th className="text-left px-4 py-2">When</th>
                <th className="text-right px-4 py-2">Sent</th>
                <th className="text-right px-4 py-2">Opened</th>
                <th className="text-right px-4 py-2">Clicked</th>
                <th className="text-right px-4 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.length === 0 && (
                <tr><td colSpan={7} className="text-center py-6" style={{ color: "var(--text-dim)" }}>No campaigns yet</td></tr>
              )}
              {campaigns.map((c) => {
                const openRate = c.sent_count > 0 ? Math.round((c.opened / c.sent_count) * 100) : 0;
                const clickRate = c.sent_count > 0 ? Math.round((c.clicked / c.sent_count) * 100) : 0;
                return (
                  <tr key={c.campaign_id} className="border-t" style={{ borderColor: "var(--border)" }} data-testid={`campaign-row-${c.campaign_id}`}>
                    <td className="px-4 py-3"><StatusPill status={c.status} /></td>
                    <td className="px-4 py-3" style={{ color: "var(--text)" }}>
                      <div className="font-medium">{c.label || c.kind.replace(/_/g, " ")}</div>
                      <div className="text-xs" style={{ color: "var(--text-dim)" }}>{c.kind}</div>
                    </td>
                    <td className="px-4 py-3 text-xs" style={{ color: "var(--text)" }}>
                      {c.scheduled_for ? new Date(c.scheduled_for).toLocaleString() : new Date(c.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-right" style={{ color: "var(--text)" }}>{c.sent_count}/{c.total}</td>
                    <td className="px-4 py-3 text-right" style={{ color: "var(--text)" }}>{c.opened} <span className="text-xs opacity-60">({openRate}%)</span></td>
                    <td className="px-4 py-3 text-right" style={{ color: "var(--text)" }}>{c.clicked} <span className="text-xs opacity-60">({clickRate}%)</span></td>
                    <td className="px-4 py-3 text-right">
                      {c.status === "scheduled" && (
                        <button onClick={() => cancelCampaign(c.campaign_id)} className="text-xs inline-flex items-center gap-1" style={{ color: "#E74C3C" }} data-testid={`cancel-campaign-${c.campaign_id}`}>
                          <Trash2 size={11} /> Cancel
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function StatusPill({ status }) {
  const map = {
    scheduled: { bg: "rgba(240,138,42,0.12)", color: "var(--accent)", text: "Scheduled" },
    sending: { bg: "rgba(27,122,158,0.18)", color: "var(--primary)", text: "Sending…" },
    sent: { bg: "rgba(46,204,113,0.15)", color: "#27AE60", text: "Sent" },
    cancelled: { bg: "rgba(231,76,60,0.12)", color: "#E74C3C", text: "Cancelled" },
    failed: { bg: "rgba(231,76,60,0.12)", color: "#E74C3C", text: "Failed" },
  };
  const s = map[status] || { bg: "rgba(150,150,150,0.1)", color: "var(--text-dim)", text: status };
  return <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: s.bg, color: s.color }}>{s.text}</span>;
}
