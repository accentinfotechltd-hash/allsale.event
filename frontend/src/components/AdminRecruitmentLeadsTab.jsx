import { useEffect, useState, useMemo } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Search, X, Plus, Upload, Send, Trash2, CheckCircle2, Clock, MinusCircle, Sparkles } from "lucide-react";

/**
 * AdminRecruitmentLeadsTab — pipeline for inviting organizers + influencers.
 *
 * Workflow:
 *   1. Admin or VA harvests prospects from any public source (Eventfinda
 *      website, LinkedIn, news articles, IG promoter lists, etc.) and pastes
 *      "Name, email" lines into the Add Leads modal.
 *   2. Tab shows leads sorted by event_count (volume signal) so the highest-
 *      value targets surface first.
 *   3. Bulk-select + "Send recruitment flyer" pushes the appropriate flyer
 *      template via the existing fire-and-forget Resend pipeline. Status
 *      auto-flips new → contacted; no one ever gets the same flyer twice
 *      unless the admin manually resets them.
 *   4. When a contacted lead signs up at /signup the backend hook stamps the
 *      lead "signed_up" and links the new user_id — this tab then shows that
 *      conversion in the table.
 */
export default function AdminRecruitmentLeadsTab() {
  const [data, setData] = useState({ items: [], summary: { total: 0, new: 0, contacted: 0, signed_up: 0, declined: 0, ignored: 0 } });
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("new");
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState(new Set());
  const [showAdd, setShowAdd] = useState(false);
  const [sending, setSending] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const params = {};
      if (status) params.status = status;
      if (kind) params.kind = kind;
      if (q.trim()) params.q = q.trim();
      const { data } = await api.get("/admin/recruitment-leads", { params });
      setData(data);
      // Drop any selections that no longer exist in the filtered view.
      const visible = new Set((data.items || []).map((l) => l.lead_id));
      setSelected((prev) => new Set([...prev].filter((id) => visible.has(id))));
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't load leads");
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [status, kind]);

  const toggle = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selected.size === data.items.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(data.items.map((l) => l.lead_id)));
    }
  };

  const sendFlyer = async () => {
    if (selected.size === 0) { toast.error("Select at least one lead"); return; }
    if (!window.confirm(
      `Send the recruitment flyer to ${selected.size} lead${selected.size === 1 ? "" : "s"}?\n\n` +
      `Influencers receive the influencer flyer; organizers receive the organizer flyer.\n` +
      `Status will flip to "contacted" — re-sending requires manually resetting them.`
    )) return;
    setSending(true);
    try {
      const { data: res } = await api.post("/admin/recruitment-leads/send-flyer", {
        lead_ids: Array.from(selected),
      });
      const errCount = (res.errors || []).length;
      if (errCount) toast.error(`Sent ${res.sent}, ${errCount} failed`);
      else toast.success(`Sent ${res.sent} flyer${res.sent === 1 ? "" : "s"}`);
      setSelected(new Set());
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Send failed");
    } finally { setSending(false); }
  };

  const updateStatus = async (lead_id, newStatus) => {
    try {
      await api.patch(`/admin/recruitment-leads/${lead_id}`, { status: newStatus });
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't update");
    }
  };

  const del = async (lead) => {
    if (!window.confirm(`Delete lead "${lead.name} <${lead.email}>"? This cannot be undone.`)) return;
    try {
      await api.delete(`/admin/recruitment-leads/${lead.lead_id}`);
      toast.success("Lead deleted");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't delete");
    }
  };

  const summary = data.summary || {};

  return (
    <div data-testid="admin-recruitment-leads-tab">
      {/* Status summary strip */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-3 mb-6">
        <StatusChip label="New" value={summary.new || 0} active={status === "new"} onClick={() => setStatus("new")} icon={<Clock className="w-4 h-4" />} testid="leads-chip-new" />
        <StatusChip label="Contacted" value={summary.contacted || 0} active={status === "contacted"} onClick={() => setStatus("contacted")} icon={<Send className="w-4 h-4" />} testid="leads-chip-contacted" />
        <StatusChip label="Signed up" value={summary.signed_up || 0} active={status === "signed_up"} onClick={() => setStatus("signed_up")} icon={<CheckCircle2 className="w-4 h-4" />} accent="var(--success)" testid="leads-chip-signed-up" />
        <StatusChip label="Declined" value={summary.declined || 0} active={status === "declined"} onClick={() => setStatus("declined")} icon={<MinusCircle className="w-4 h-4" />} testid="leads-chip-declined" />
        <StatusChip label="All" value={summary.total || 0} active={status === "all"} onClick={() => setStatus("all")} icon={<Sparkles className="w-4 h-4" />} testid="leads-chip-all" />
      </div>

      {/* Filters + actions */}
      <div className="flex flex-wrap items-center gap-3 mb-5">
        <form onSubmit={(e) => { e.preventDefault(); load(); }} className="relative flex-1 min-w-[240px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: "var(--text-dim)" }} />
          <input
            value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Search name, email, notes…"
            className="pl-10 w-full"
            data-testid="leads-search-input"
          />
        </form>
        <select value={kind} onChange={(e) => setKind(e.target.value)} data-testid="leads-kind-filter">
          <option value="">All types</option>
          <option value="organizer">Organizer leads</option>
          <option value="influencer">Influencer leads</option>
        </select>
        <button
          onClick={sendFlyer}
          disabled={sending || selected.size === 0}
          className="btn-primary"
          data-testid="leads-send-flyer-btn"
        >
          <Send className="w-4 h-4" />
          {sending ? "Sending…" : selected.size > 0 ? `Send flyer to ${selected.size}` : "Send flyer"}
        </button>
        <button
          onClick={() => setShowAdd(true)}
          className="btn-ghost"
          data-testid="leads-add-btn"
        >
          <Plus className="w-4 h-4" /> Add leads
        </button>
      </div>

      {/* Leads table */}
      <div className="border rounded-2xl overflow-hidden" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
        {loading ? (
          <div className="p-10 text-center" style={{ color: "var(--text-dim)" }}>Loading leads…</div>
        ) : data.items.length === 0 ? (
          <div className="p-10 text-center" style={{ color: "var(--text-dim)" }}>
            No leads match. <button onClick={() => setShowAdd(true)} className="underline ml-1" data-testid="leads-empty-add">Add some.</button>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr style={{ background: "var(--bg)", color: "var(--text-muted)" }}>
                <th className="px-4 py-3 w-8">
                  <input
                    type="checkbox"
                    checked={selected.size === data.items.length && data.items.length > 0}
                    onChange={toggleAll}
                    data-testid="leads-select-all"
                  />
                </th>
                <th className="text-left px-4 py-3 text-xs uppercase tracking-widest font-medium">Name / Email</th>
                <th className="text-left px-4 py-3 text-xs uppercase tracking-widest font-medium">Kind</th>
                <th className="text-left px-4 py-3 text-xs uppercase tracking-widest font-medium">Source</th>
                <th className="text-right px-4 py-3 text-xs uppercase tracking-widest font-medium">Events</th>
                <th className="text-left px-4 py-3 text-xs uppercase tracking-widest font-medium">Status</th>
                <th className="text-right px-4 py-3 text-xs uppercase tracking-widest font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((l) => (
                <tr key={l.lead_id} className="border-t hover:bg-[color:var(--bg-elev)] transition" style={{ borderColor: "var(--border)" }} data-testid={`lead-row-${l.lead_id}`}>
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={selected.has(l.lead_id)}
                      onChange={() => toggle(l.lead_id)}
                      data-testid={`lead-checkbox-${l.lead_id}`}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <div style={{ color: "var(--text)" }}>{l.name}</div>
                    <div className="text-xs" style={{ color: "var(--text-muted)" }}>{l.email}</div>
                    {l.notes && <div className="text-[11px] mt-1" style={{ color: "var(--text-dim)" }}>{l.notes.slice(0, 80)}{l.notes.length > 80 ? "…" : ""}</div>}
                  </td>
                  <td className="px-4 py-3 text-xs" style={{ color: "var(--text-muted)" }}>{l.kind || "organizer"}</td>
                  <td className="px-4 py-3 text-xs" style={{ color: "var(--text-muted)" }}>
                    {l.source_url ? (
                      <a href={l.source_url} target="_blank" rel="noopener noreferrer" className="underline" style={{ color: "var(--accent)" }}>
                        {l.source || "link"}
                      </a>
                    ) : (l.source || "manual")}
                  </td>
                  <td className="px-4 py-3 text-right">{l.event_count ?? "—"}</td>
                  <td className="px-4 py-3">
                    <LeadStatusBadge lead={l} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex gap-1.5 justify-end flex-wrap">
                      {l.status === "new" && (
                        <button onClick={() => updateStatus(l.lead_id, "ignored")} className="btn-ghost !py-1 !px-2 text-xs" data-testid={`lead-ignore-${l.lead_id}`} title="Skip this lead">
                          Ignore
                        </button>
                      )}
                      {l.status === "contacted" && (
                        <button onClick={() => updateStatus(l.lead_id, "declined")} className="btn-ghost !py-1 !px-2 text-xs" data-testid={`lead-declined-${l.lead_id}`} title="They said no thanks">
                          Declined
                        </button>
                      )}
                      {l.status !== "new" && l.status !== "signed_up" && (
                        <button onClick={() => updateStatus(l.lead_id, "new")} className="btn-ghost !py-1 !px-2 text-xs" data-testid={`lead-reset-${l.lead_id}`} title="Reset to new — allows re-sending the flyer">
                          Reset
                        </button>
                      )}
                      <button onClick={() => del(l)} className="btn-ghost !py-1 !px-2 text-xs" style={{ color: "var(--danger)" }} data-testid={`lead-delete-${l.lead_id}`}>
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showAdd && <AddLeadsModal onClose={() => setShowAdd(false)} onAdded={() => { setShowAdd(false); load(); }} />}
    </div>
  );
}

function StatusChip({ label, value, active, onClick, icon, accent, testid }) {
  return (
    <button
      onClick={onClick}
      className="border rounded-2xl p-4 text-left transition"
      style={{
        borderColor: active ? "var(--accent)" : "var(--border)",
        background: active ? "var(--accent-soft)" : "var(--bg-card)",
      }}
      data-testid={testid}
    >
      <div className="flex items-center justify-between mb-2 text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
        <span>{label}</span>
        <span style={{ color: accent || "var(--accent)" }}>{icon}</span>
      </div>
      <div className="serif text-3xl" style={{ color: accent || "var(--text)" }}>{value.toLocaleString()}</div>
    </button>
  );
}

function LeadStatusBadge({ lead }) {
  const map = {
    new: { color: "var(--accent)", bg: "var(--accent-soft)", label: "New" },
    contacted: { color: "var(--warn)", bg: "rgba(251,191,36,0.12)", label: "Contacted" },
    signed_up: { color: "var(--success)", bg: "rgba(52,211,153,0.12)", label: "Signed up ✓" },
    declined: { color: "var(--text-muted)", bg: "rgba(154,154,163,0.12)", label: "Declined" },
    ignored: { color: "var(--text-muted)", bg: "rgba(154,154,163,0.12)", label: "Ignored" },
  };
  const m = map[lead.status] || map.new;
  return (
    <div className="flex flex-col items-start gap-0.5">
      <span className="inline-flex px-2 py-0.5 rounded-full text-xs" style={{ color: m.color, background: m.bg }}>
        {m.label}
      </span>
      {lead.contacted_at && lead.status !== "new" && (
        <span className="text-[10px]" style={{ color: "var(--text-dim)" }}>
          {new Date(lead.contacted_at).toLocaleDateString([], { month: "short", day: "numeric" })}
        </span>
      )}
    </div>
  );
}

function AddLeadsModal({ onClose, onAdded }) {
  const [tab, setTab] = useState("paste"); // 'paste' | 'single'
  const [pasted, setPasted] = useState("");
  const [kind, setKind] = useState("organizer");
  const [source, setSource] = useState("eventfinda");
  const [busy, setBusy] = useState(false);
  // Single-add fields
  const [singleName, setSingleName] = useState("");
  const [singleEmail, setSingleEmail] = useState("");
  const [singleEventCount, setSingleEventCount] = useState("");
  const [singleNotes, setSingleNotes] = useState("");
  const [singleUrl, setSingleUrl] = useState("");

  // Parse "Name <email@x.com>" OR "Name, email@x.com" OR "Name,email,event_count"
  // — one per line. Skip blanks and obvious header rows.
  const parsed = useMemo(() => {
    if (tab !== "paste") return [];
    return pasted
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        // Try "Name <email>" pattern first
        const angle = line.match(/^([^<]+)<([^>]+)>$/);
        if (angle) {
          return { name: angle[1].trim(), email: angle[2].trim().toLowerCase() };
        }
        // Comma-separated columns: name, email[, event_count][, source_url]
        const cols = line.split(/[,\t;]/).map((s) => s.trim());
        if (cols.length >= 2) {
          const email = cols.find((c) => c.includes("@")) || "";
          const name = cols[0].includes("@") ? (cols[1] || "") : cols[0];
          // Event count is the first pure-numeric column AFTER email
          const eventCountCol = cols.find((c) => /^\d+$/.test(c));
          const urlCol = cols.find((c) => /^https?:\/\//.test(c));
          return {
            name: name || email.split("@")[0],
            email: email.toLowerCase(),
            event_count: eventCountCol ? parseInt(eventCountCol, 10) : undefined,
            source_url: urlCol || undefined,
          };
        }
        return null;
      })
      .filter((r) => r && r.email && r.email.includes("@"));
  }, [pasted, tab]);

  const submitPaste = async () => {
    if (parsed.length === 0) { toast.error("No valid leads detected. Use one per line: 'Name, email@x.com'"); return; }
    setBusy(true);
    try {
      const leads = parsed.map((p) => ({ ...p, kind, source }));
      const { data } = await api.post("/admin/recruitment-leads", { leads });
      toast.success(`${data.created} new · ${data.updated} updated · ${data.skipped} skipped`);
      onAdded();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't add leads");
    } finally { setBusy(false); }
  };

  const submitSingle = async () => {
    if (!singleName.trim() || !singleEmail.trim()) {
      toast.error("Name and email are required");
      return;
    }
    setBusy(true);
    try {
      const { data } = await api.post("/admin/recruitment-leads", {
        leads: [{
          name: singleName.trim(),
          email: singleEmail.trim().toLowerCase(),
          kind,
          source,
          source_url: singleUrl.trim() || undefined,
          event_count: singleEventCount ? parseInt(singleEventCount, 10) : undefined,
          notes: singleNotes.trim() || undefined,
        }],
      });
      toast.success(data.created ? "Lead added" : "Lead already existed — updated");
      onAdded();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't add lead");
    } finally { setBusy(false); }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.6)" }}
      onClick={onClose}
      data-testid="add-leads-modal"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-2xl border rounded-2xl p-6"
        style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}
      >
        <div className="flex items-center justify-between mb-5">
          <h3 className="serif text-2xl">Add recruitment leads</h3>
          <button onClick={onClose} className="text-sm opacity-60 hover:opacity-100" data-testid="add-leads-close">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Common: kind + source */}
        <div className="grid sm:grid-cols-2 gap-3 mb-5">
          <div>
            <label className="text-xs uppercase tracking-widest mb-1 block" style={{ color: "var(--text-dim)" }}>Lead type</label>
            <select value={kind} onChange={(e) => setKind(e.target.value)} className="w-full" data-testid="add-leads-kind">
              <option value="organizer">Organizer (gets organizer flyer)</option>
              <option value="influencer">Influencer (gets influencer flyer)</option>
            </select>
          </div>
          <div>
            <label className="text-xs uppercase tracking-widest mb-1 block" style={{ color: "var(--text-dim)" }}>Source</label>
            <select value={source} onChange={(e) => setSource(e.target.value)} className="w-full" data-testid="add-leads-source">
              <option value="eventfinda">Eventfinda</option>
              <option value="instagram">Instagram</option>
              <option value="linkedin">LinkedIn</option>
              <option value="news">News article</option>
              <option value="referral">Referral</option>
              <option value="manual">Manual</option>
            </select>
          </div>
        </div>

        {/* Tab switcher */}
        <div className="flex border-b mb-4" style={{ borderColor: "var(--border)" }}>
          <TabBtn active={tab === "paste"} onClick={() => setTab("paste")} testid="add-leads-tab-paste">Bulk paste</TabBtn>
          <TabBtn active={tab === "single"} onClick={() => setTab("single")} testid="add-leads-tab-single">Single lead</TabBtn>
        </div>

        {tab === "paste" ? (
          <>
            <p className="text-xs mb-2" style={{ color: "var(--text-muted)" }}>
              Paste one lead per line. Supported formats:
              <code className="ml-2 text-[10px]">Jane Doe, jane@example.com</code> ·
              <code className="ml-2 text-[10px]">Name &lt;email&gt;</code> ·
              <code className="ml-2 text-[10px]">name, email, events, url</code>
            </p>
            <textarea
              value={pasted}
              onChange={(e) => setPasted(e.target.value)}
              rows={10}
              placeholder={"Jane Doe, jane@example.com\nMike Smith <mike@example.com>, 24, https://eventfinda.co.nz/profile/mike"}
              className="w-full px-3 py-2 rounded-lg border bg-transparent text-sm font-mono"
              style={{ borderColor: "var(--border)", color: "var(--text)" }}
              data-testid="add-leads-paste-textarea"
            />
            <div className="text-xs mt-2" style={{ color: parsed.length > 0 ? "var(--success)" : "var(--text-dim)" }} data-testid="add-leads-parsed-count">
              {parsed.length === 0 ? "No valid leads detected" : `${parsed.length} valid lead${parsed.length === 1 ? "" : "s"} ready to import`}
            </div>
            <div className="flex gap-2 justify-end mt-5">
              <button onClick={onClose} className="btn-ghost !py-2 !px-4 text-sm" data-testid="add-leads-cancel">Cancel</button>
              <button onClick={submitPaste} disabled={busy || parsed.length === 0} className="btn-primary !py-2 !px-4 text-sm" data-testid="add-leads-submit-paste">
                <Upload className="w-4 h-4" />
                {busy ? "Importing…" : `Import ${parsed.length} lead${parsed.length === 1 ? "" : "s"}`}
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="grid sm:grid-cols-2 gap-3 mb-3">
              <input value={singleName} onChange={(e) => setSingleName(e.target.value)} placeholder="Full name" data-testid="add-leads-single-name" />
              <input type="email" value={singleEmail} onChange={(e) => setSingleEmail(e.target.value)} placeholder="Email" data-testid="add-leads-single-email" />
              <input type="number" min="0" value={singleEventCount} onChange={(e) => setSingleEventCount(e.target.value)} placeholder="Event count (optional)" data-testid="add-leads-single-events" />
              <input value={singleUrl} onChange={(e) => setSingleUrl(e.target.value)} placeholder="Source URL (optional)" data-testid="add-leads-single-url" />
            </div>
            <textarea
              value={singleNotes}
              onChange={(e) => setSingleNotes(e.target.value)}
              rows={3}
              placeholder="Notes — anything you've learned about them"
              className="w-full px-3 py-2 rounded-lg border bg-transparent text-sm"
              style={{ borderColor: "var(--border)", color: "var(--text)" }}
              data-testid="add-leads-single-notes"
            />
            <div className="flex gap-2 justify-end mt-5">
              <button onClick={onClose} className="btn-ghost !py-2 !px-4 text-sm" data-testid="add-leads-single-cancel">Cancel</button>
              <button onClick={submitSingle} disabled={busy} className="btn-primary !py-2 !px-4 text-sm" data-testid="add-leads-submit-single">
                {busy ? "Saving…" : "Add lead"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function TabBtn({ active, onClick, children, testid }) {
  return (
    <button
      onClick={onClick}
      className="px-4 py-2 text-sm relative"
      style={{ color: active ? "var(--accent)" : "var(--text-muted)" }}
      data-testid={testid}
    >
      {children}
      {active && <div className="absolute bottom-0 inset-x-0 h-0.5" style={{ background: "var(--accent)" }} />}
    </button>
  );
}
