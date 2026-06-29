import { useEffect, useState } from "react";
import { Loader2, CheckCircle2, XCircle, Clock, Mail, ExternalLink } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

const STATUS_META = {
  pending: { label: "Pending", icon: Clock, chip: "bg-amber-50 text-amber-700 border-amber-200" },
  approved: { label: "Approved", icon: CheckCircle2, chip: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  rejected: { label: "Rejected", icon: XCircle, chip: "bg-rose-50 text-rose-700 border-rose-200" },
};

const fmtDate = (iso) => {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString(undefined, { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }); }
  catch { return iso.slice(0, 16); }
};

export default function AdminPartnerApplicationsTab() {
  const [data, setData] = useState({ items: [], summary: { pending: 0, approved: 0, rejected: 0 } });
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("pending");
  const [busy, setBusy] = useState(null); // application_id currently being acted on

  const load = async () => {
    setLoading(true);
    try {
      const { data: d } = await api.get("/admin/partners/applications", {
        params: { status: filter === "all" ? undefined : filter },
      });
      setData(d);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load applications");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [filter]);

  const act = async (id, action) => {
    const note = action === "reject"
      ? window.prompt("(Optional) Internal rejection note — for your records only, not emailed to applicant:") || ""
      : window.prompt("(Optional) Personal note to include in the approval email:") || "";
    setBusy(id);
    try {
      await api.post(`/admin/partners/applications/${id}/${action}`, { note });
      toast.success(action === "approve" ? "Approved + applicant emailed" : "Rejected");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || `Couldn't ${action}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div data-testid="admin-partner-applications-tab" className="space-y-5">
      <div>
        <h2 className="text-2xl font-semibold text-slate-900">Partner applications</h2>
        <p className="text-sm text-slate-600 mt-1 max-w-3xl">
          Submissions from <a href="/become-partner" className="underline">/become-partner</a>. Approval emails the applicant + flips status; rejection is silent (chase manually if you want).
        </p>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {[
          { id: "pending", count: data.summary.pending, accent: "amber" },
          { id: "approved", count: data.summary.approved, accent: "emerald" },
          { id: "rejected", count: data.summary.rejected, accent: "rose" },
        ].map((s) => {
          const accentBg = { amber: "bg-amber-50/40 border-amber-200", emerald: "bg-emerald-50/40 border-emerald-200", rose: "bg-rose-50/40 border-rose-200" }[s.accent];
          return (
            <button
              key={s.id}
              onClick={() => setFilter(s.id)}
              data-testid={`partner-apps-filter-${s.id}`}
              className={`text-left rounded-xl border p-4 transition-all ${accentBg} ${filter === s.id ? "ring-2 ring-offset-1 ring-slate-900" : ""}`}
            >
              <div className="text-xs uppercase tracking-wider text-slate-500 font-medium">{STATUS_META[s.id].label}</div>
              <div className="text-2xl font-semibold text-slate-900 mt-1 tabular-nums">{s.count}</div>
            </button>
          );
        })}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16 text-slate-500">
          <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading…
        </div>
      ) : data.items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 p-12 text-center text-slate-500" data-testid="partner-apps-empty">
          No <b>{filter}</b> applications yet.
        </div>
      ) : (
        <div className="space-y-3">
          {data.items.map((app) => {
            const meta = STATUS_META[app.status] || STATUS_META.pending;
            const Icon = meta.icon;
            const isBusy = busy === app.application_id;
            return (
              <div
                key={app.application_id}
                data-testid={`partner-app-${app.application_id}`}
                className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
              >
                <div className="flex items-start justify-between gap-4 mb-3 flex-wrap">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-lg font-semibold text-slate-900">{app.full_name}</h3>
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-medium ${meta.chip}`}>
                        <Icon className="w-3 h-3" /> {meta.label}
                      </span>
                    </div>
                    <div className="text-sm text-slate-600 flex flex-wrap gap-x-3 gap-y-1">
                      <span><Mail className="w-3.5 h-3.5 inline-block mr-1 opacity-50" />{app.email}</span>
                      {app.phone && <span>{app.phone}</span>}
                      {app.company && <span>· {app.company}</span>}
                    </div>
                    <div className="text-xs text-slate-400 mt-1">
                      Submitted {fmtDate(app.created_at)}
                      {app.reviewed_at && <span> · Reviewed {fmtDate(app.reviewed_at)}</span>}
                    </div>
                  </div>
                  {app.status === "pending" && (
                    <div className="flex gap-2 shrink-0">
                      <button
                        data-testid={`partner-app-approve-${app.application_id}`}
                        onClick={() => act(app.application_id, "approve")}
                        disabled={isBusy}
                        className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-300 text-white text-sm font-medium inline-flex items-center gap-1"
                      >
                        {isBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                        Approve
                      </button>
                      <button
                        data-testid={`partner-app-reject-${app.application_id}`}
                        onClick={() => act(app.application_id, "reject")}
                        disabled={isBusy}
                        className="px-3 py-1.5 rounded-lg border border-slate-300 hover:bg-slate-50 text-sm font-medium text-slate-700 inline-flex items-center gap-1 disabled:opacity-50"
                      >
                        <XCircle className="w-3.5 h-3.5" /> Reject
                      </button>
                    </div>
                  )}
                </div>

                {(app.channels?.length > 0 || app.audience_size) && (
                  <div className="text-xs text-slate-600 mb-2 flex flex-wrap gap-2">
                    {app.channels?.map((c) => (
                      <span key={c} className="inline-flex items-center px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">{c}</span>
                    ))}
                    {app.audience_size && <span className="text-slate-500">Reach: {app.audience_size}</span>}
                  </div>
                )}

                <div className="text-sm text-slate-700 italic border-l-2 border-slate-200 pl-3 mt-2 whitespace-pre-wrap">
                  &ldquo;{app.why_partner}&rdquo;
                </div>

                {app.decision_note && (
                  <div className="text-xs text-slate-500 mt-3 border-t border-slate-100 pt-2">
                    <b>Internal note:</b> {app.decision_note}
                  </div>
                )}

                {app.status === "approved" && (
                  <a
                    href="/admin?tab=partners"
                    className="text-xs text-emerald-700 hover:underline mt-3 inline-flex items-center gap-1"
                  >
                    Set commission % in Marketing partners <ExternalLink className="w-3 h-3" />
                  </a>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
