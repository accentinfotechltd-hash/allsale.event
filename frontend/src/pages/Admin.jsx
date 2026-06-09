import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Check, X, Star, Users, Calendar, Search, ShieldCheck, ShieldAlert, UserCog, Ban, RotateCcw, Mail, CheckCircle2, AlertTriangle, MinusCircle, Wallet, Settings as SettingsIcon, Clock, XCircle, BanknoteIcon, Eye, Trash2, Sparkles, RefreshCw, Send } from "lucide-react";
import { toast } from "sonner";
import AdminUserDetailDrawer from "@/components/AdminUserDetailDrawer";

export default function Admin() {
  const { user } = useAuth();
  const [tab, setTab] = useState("events");

  if (!user || user.role !== "admin") {
    return <div className="text-center py-20" style={{ color: "var(--text-muted)" }}>Admin access required.</div>;
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-12">
      <div className="mb-8">
        <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Admin</div>
        <h1 className="serif text-5xl">Control center</h1>
      </div>

      <div className="border-b mb-8" style={{ borderColor: "var(--border)" }}>
        <div className="flex gap-1">
          <TabBtn id="events" current={tab} onClick={setTab} icon={<Calendar className="w-4 h-4" />} label="Events" />
          <TabBtn id="users" current={tab} onClick={setTab} icon={<Users className="w-4 h-4" />} label="Users" />
          <TabBtn id="payouts" current={tab} onClick={setTab} icon={<Wallet className="w-4 h-4" />} label="Payouts" />
          <TabBtn id="emails" current={tab} onClick={setTab} icon={<Mail className="w-4 h-4" />} label="Emails" />
          <TabBtn id="settings" current={tab} onClick={setTab} icon={<SettingsIcon className="w-4 h-4" />} label="Settings" />
        </div>
      </div>

      {tab === "events" ? <EventsTab /> : tab === "users" ? <UsersTab currentUser={user} /> : tab === "payouts" ? <PayoutsTab /> : tab === "emails" ? <EmailsTab /> : <SettingsTab />}
    </div>
  );
}

function TabBtn({ id, current, onClick, icon, label }) {
  const active = current === id;
  return (
    <button
      onClick={() => onClick(id)}
      className="flex items-center gap-2 px-5 py-3 text-sm transition relative"
      style={{ color: active ? "var(--accent)" : "var(--text-muted)" }}
      data-testid={`admin-tab-${id}`}
    >
      {icon} {label}
      {active && <div className="absolute bottom-0 inset-x-0 h-0.5" style={{ background: "var(--accent)" }} />}
    </button>
  );
}

// ============================================================================
// EVENTS TAB
// ============================================================================
function EventsTab() {
  const [events, setEvents] = useState([]);

  const load = async () => {
    try {
      const { data } = await api.get("/admin/events");
      setEvents(data);
    } catch { /* noop */ }
  };
  useEffect(() => { load(); }, []);

  const act = async (id, kind) => {
    try {
      await api.post(`/admin/events/${id}/${kind}`);
      toast.success(`Event ${kind}d`);
      load();
    } catch { toast.error("Failed"); }
  };

  const del = async (ev) => {
    const title = ev?.title || "this event";
    const confirmText =
      `Permanently delete "${title}"?\n\n` +
      `This will also remove ALL related bookings, seat holds, scanner tokens, ` +
      `team grants, waitlist entries, and discount codes for this event.\n\n` +
      `Type "delete" to confirm.`;
    const answer = window.prompt(confirmText);
    if (!answer || answer.trim().toLowerCase() !== "delete") {
      toast("Cancelled");
      return;
    }
    try {
      const { data } = await api.delete(`/events/${ev.event_id}`);
      const c = data?.cascade || {};
      const cleaned = Object.entries(c)
        .filter(([, n]) => n > 0)
        .map(([k, n]) => `${n} ${k.replace(/_/g, " ")}`)
        .join(", ");
      toast.success(cleaned ? `Deleted "${title}". Also cleaned: ${cleaned}.` : `Deleted "${title}".`);
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to delete");
    }
  };

  const pending = events.filter((e) => e.status === "pending");
  const approved = events.filter((e) => e.status === "approved");
  const rejected = events.filter((e) => e.status === "rejected");

  return (
    <>
      <Section title="Pending approval" events={pending} act={act} del={del} showApprove />
      <Section title="Approved events" events={approved} act={act} del={del} showFeature />
      {rejected.length > 0 && (
        <Section title="Rejected" events={rejected} act={act} del={del} />
      )}
    </>
  );
}

function Section({ title, events, act, del, showApprove, showFeature }) {
  return (
    <div className="mb-12">
      <h2 className="serif text-2xl mb-4">{title} <span className="text-sm" style={{ color: "var(--text-dim)" }}>({events.length})</span></h2>
      {events.length === 0 ? (
        <p className="p-6 border rounded-xl" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>None.</p>
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {events.map((e) => (
            <div key={e.event_id} className="border rounded-2xl overflow-hidden flex" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }} data-testid={`admin-event-${e.event_id}`}>
              <img src={e.image_url} alt="" className="w-32 h-full object-cover" />
              <div className="flex-1 p-4">
                <div className="serif text-xl mb-1">{e.title}</div>
                <div className="text-xs mb-3" style={{ color: "var(--text-dim)" }}>{e.organizer_name} · {e.venue}, {e.city}</div>
                <div className="flex gap-2 flex-wrap">
                  {showApprove && (
                    <>
                      <button onClick={() => act(e.event_id, "approve")} className="btn-primary !py-1.5 !px-3 text-xs" data-testid={`approve-${e.event_id}`}><Check className="w-3 h-3" /> Approve</button>
                      <button onClick={() => act(e.event_id, "reject")} className="btn-ghost !py-1.5 !px-3 text-xs" data-testid={`reject-${e.event_id}`}><X className="w-3 h-3" /> Reject</button>
                    </>
                  )}
                  {showFeature && (
                    <button onClick={() => act(e.event_id, "feature")} className="btn-ghost !py-1.5 !px-3 text-xs" data-testid={`feature-${e.event_id}`}>
                      <Star className="w-3 h-3" style={{ color: e.featured ? "var(--accent)" : "inherit" }} /> {e.featured ? "Unfeature" : "Feature"}
                    </button>
                  )}
                  {del && (
                    <button
                      onClick={() => del(e)}
                      className="btn-ghost !py-1.5 !px-3 text-xs"
                      style={{ color: "#c62828", borderColor: "rgba(198,40,40,0.35)" }}
                      data-testid={`delete-${e.event_id}`}
                    >
                      <Trash2 className="w-3 h-3" /> Delete
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// USERS TAB
// ============================================================================
function UsersTab({ currentUser }) {
  const [users, setUsers] = useState([]);
  const [stats, setStats] = useState(null);
  const [q, setQ] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // user_id being role-edited
  const [viewingUserId, setViewingUserId] = useState(null); // drawer drill-down

  const load = async () => {
    setLoading(true);
    try {
      const params = {};
      if (q) params.q = q;
      if (roleFilter) params.role = roleFilter;
      if (statusFilter === "active") params.active = true;
      if (statusFilter === "suspended") params.active = false;
      const [u, s] = await Promise.all([
        api.get("/admin/users", { params }),
        api.get("/admin/users/stats"),
      ]);
      setUsers(u.data);
      setStats(s.data);
    } catch (e) {
      toast.error("Failed to load users");
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [roleFilter, statusFilter]);

  const onSearch = (e) => { e.preventDefault(); load(); };

  const changeRole = async (uid, role, currentRole) => {
    if (role === currentRole) { setEditing(null); return; }
    try {
      await api.post(`/admin/users/${uid}/role`, { role });
      toast.success(`Role updated to ${role}`);
      setEditing(null);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  const toggleSuspend = async (u) => {
    const kind = u.active ? "suspend" : "unsuspend";
    if (kind === "suspend" && !window.confirm(`Suspend ${u.email}? They will be unable to log in until you unsuspend.`)) return;
    try {
      await api.post(`/admin/users/${u.user_id}/${kind}`);
      toast.success(u.active ? "User suspended" : "User unsuspended");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  return (
    <div>
      {stats && (
        <div className="grid sm:grid-cols-4 gap-4 mb-6">
          <Stat label="Total users" value={stats.total} icon={<Users className="w-4 h-4" />} />
          <Stat label="Attendees" value={stats.by_role.attendee} />
          <Stat label="Organizers" value={stats.by_role.organizer} />
          <Stat label="Suspended" value={stats.suspended} accent={stats.suspended > 0 ? "var(--danger)" : null} />
        </div>
      )}

      <div className="flex gap-3 mb-4 flex-wrap">
        <form onSubmit={onSearch} className="flex-1 min-w-[260px] relative">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: "var(--text-dim)" }} />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by name or email — press Enter"
            className="pl-10"
            data-testid="admin-user-search"
          />
        </form>
        <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)} className="!w-40" data-testid="admin-role-filter">
          <option value="">All roles</option>
          <option value="attendee">Attendee</option>
          <option value="organizer">Organizer</option>
          <option value="admin">Admin</option>
        </select>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="!w-40" data-testid="admin-status-filter">
          <option value="">All status</option>
          <option value="active">Active</option>
          <option value="suspended">Suspended</option>
        </select>
      </div>

      <div className="border rounded-2xl overflow-hidden" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-xs uppercase tracking-widest" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
              <th className="text-left p-4">User</th>
              <th className="text-left p-4 hidden md:table-cell">Phone</th>
              <th className="text-left p-4">Role</th>
              <th className="text-left p-4 hidden lg:table-cell">Joined</th>
              <th className="text-right p-4">Bookings</th>
              <th className="text-right p-4 hidden sm:table-cell">Events</th>
              <th className="text-left p-4">Status</th>
              <th className="text-right p-4">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan="8" className="p-10 text-center" style={{ color: "var(--text-dim)" }}>Loading users...</td></tr>
            ) : users.length === 0 ? (
              <tr><td colSpan="8" className="p-10 text-center" style={{ color: "var(--text-dim)" }}>No users match these filters.</td></tr>
            ) : users.map((u) => (
              <tr key={u.user_id} className="border-b" style={{ borderColor: "var(--border)", opacity: u.active ? 1 : 0.55 }} data-testid={`user-row-${u.user_id}`}>
                <td className="p-4">
                  <button onClick={() => setViewingUserId(u.user_id)} className="flex items-center gap-3 text-left hover:opacity-80 transition" data-testid={`view-user-${u.user_id}`}>
                    {u.picture ? (
                      <img src={u.picture} alt="" className="w-9 h-9 rounded-full object-cover" />
                    ) : (
                      <div className="w-9 h-9 rounded-full flex items-center justify-center" style={{ background: "var(--bg-elev)", color: "var(--text-muted)" }}>
                        {u.name.charAt(0).toUpperCase()}
                      </div>
                    )}
                    <div>
                      <div className="font-medium underline-offset-2 hover:underline">{u.name}</div>
                      <div className="text-xs" style={{ color: "var(--text-dim)" }}>{u.email}</div>
                    </div>
                  </button>
                </td>
                <td className="p-4 hidden md:table-cell text-sm" style={{ color: "var(--text-muted)" }}>{u.phone || "—"}</td>
                <td className="p-4">
                  {editing === u.user_id ? (
                    <select
                      defaultValue={u.role}
                      onChange={(e) => changeRole(u.user_id, e.target.value, u.role)}
                      onBlur={() => setEditing(null)}
                      autoFocus
                      className="!py-1 !text-sm"
                      data-testid={`role-select-${u.user_id}`}
                    >
                      <option value="attendee">attendee</option>
                      <option value="organizer">organizer</option>
                      <option value="admin">admin</option>
                    </select>
                  ) : (
                    <button onClick={() => setEditing(u.user_id)} disabled={u.user_id === currentUser.user_id} className="chip" style={{ color: u.role === "admin" ? "var(--accent)" : "var(--text-muted)", cursor: u.user_id === currentUser.user_id ? "default" : "pointer" }} data-testid={`role-chip-${u.user_id}`}>
                      {u.role === "admin" && <ShieldCheck className="w-3 h-3" />}
                      {u.role}
                    </button>
                  )}
                </td>
                <td className="p-4 hidden lg:table-cell" style={{ color: "var(--text-muted)" }}>
                  {new Date(u.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                </td>
                <td className="p-4 text-right" style={{ color: "var(--text-muted)" }}>{u.bookings_count}</td>
                <td className="p-4 text-right hidden sm:table-cell" style={{ color: "var(--text-muted)" }}>{u.events_count}</td>
                <td className="p-4">
                  {u.active ? (
                    <span className="chip chip-accent" style={{ fontSize: "0.65rem" }}>Active</span>
                  ) : (
                    <span className="chip" style={{ fontSize: "0.65rem", color: "var(--danger)", borderColor: "var(--danger)" }}>
                      <ShieldAlert className="w-3 h-3" /> Suspended
                    </span>
                  )}
                </td>
                <td className="p-4 text-right">
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => setViewingUserId(u.user_id)}
                      className="btn-ghost !py-1 !px-2 text-xs"
                      title="View details"
                      data-testid={`view-details-${u.user_id}`}
                    ><Eye className="w-3 h-3" /></button>
                    <button
                      onClick={() => setEditing(u.user_id)}
                      disabled={u.user_id === currentUser.user_id}
                      className="btn-ghost !py-1 !px-2 text-xs"
                      title="Change role"
                      data-testid={`edit-role-${u.user_id}`}
                    ><UserCog className="w-3 h-3" /></button>
                    <button
                      onClick={() => toggleSuspend(u)}
                      disabled={u.user_id === currentUser.user_id}
                      className="btn-ghost !py-1 !px-2 text-xs"
                      title={u.active ? "Suspend" : "Unsuspend"}
                      data-testid={`toggle-suspend-${u.user_id}`}
                    >
                      {u.active ? <Ban className="w-3 h-3" /> : <RotateCcw className="w-3 h-3" />}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs mt-3" style={{ color: "var(--text-dim)" }}>You cannot suspend or change your own role.</p>

      {viewingUserId && (
        <AdminUserDetailDrawer
          userId={viewingUserId}
          onClose={() => setViewingUserId(null)}
          onUserUpdated={() => load()}
        />
      )}
    </div>
  );
}

function Stat({ label, value, icon, accent }) {
  return (
    <div className="border rounded-2xl p-4" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
      <div className="flex items-center justify-between mb-1">
        <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>{label}</div>
        {icon && <div style={{ color: "var(--accent)" }}>{icon}</div>}
      </div>
      <div className="serif text-3xl" style={{ color: accent || "var(--text)" }}>{value}</div>
    </div>
  );
}


// ============================================================================
// EMAILS TAB — audit trail of every transactional email
// ============================================================================
const TEMPLATE_LABELS = {
  booking_confirmation: "Booking confirmed",
  hold_expired: "Hold expired",
  refund_issued: "Refund issued",
  organizer_event_approved: "Event approved",
  organizer_payout_issued: "Payout sent",
  waitlist_spot_opened: "Waitlist spot opened",
};

function EmailsTab() {
  const [data, setData] = useState({ items: [], stats: { sent: 0, failed: 0, skipped: 0 } });
  const [template, setTemplate] = useState("");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const params = {};
      if (template) params.template = template;
      if (status) params.status = status;
      if (q) params.q = q;
      const { data } = await api.get("/admin/email-logs", { params });
      setData(data);
    } catch {
      toast.error("Failed to load email logs");
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [template, status]);

  return (
    <div data-testid="admin-emails-tab">
      <div className="grid sm:grid-cols-3 gap-3 mb-6">
        <Stat label="Sent" value={data.stats.sent} icon={<CheckCircle2 className="w-4 h-4" />} accent="var(--success)" />
        <Stat label="Failed" value={data.stats.failed} icon={<AlertTriangle className="w-4 h-4" />} accent="var(--danger)" />
        <Stat label="Skipped" value={data.stats.skipped} icon={<MinusCircle className="w-4 h-4" />} />
      </div>

      <div className="flex flex-wrap gap-3 mb-5">
        <form onSubmit={(e) => { e.preventDefault(); load(); }} className="relative flex-1 min-w-[240px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: "var(--text-dim)" }} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by recipient email" className="pl-10 w-full" data-testid="email-search-input" />
        </form>
        <select value={template} onChange={(e) => setTemplate(e.target.value)} data-testid="email-template-filter">
          <option value="">All templates</option>
          {Object.entries(TEMPLATE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)} data-testid="email-status-filter">
          <option value="">All statuses</option>
          <option value="sent">Sent</option>
          <option value="failed">Failed</option>
          <option value="skipped">Skipped</option>
        </select>
      </div>

      <div className="border rounded-2xl overflow-hidden" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
        {loading ? (
          <div className="p-10 text-center" style={{ color: "var(--text-dim)" }}>Loading…</div>
        ) : data.items.length === 0 ? (
          <div className="p-10 text-center" style={{ color: "var(--text-dim)" }}>No emails match.</div>
        ) : (
          <table className="w-full text-sm" data-testid="email-logs-table">
            <thead>
              <tr style={{ background: "var(--bg)", color: "var(--text-muted)" }}>
                <th className="text-left px-4 py-3 font-medium text-xs uppercase tracking-widest">When</th>
                <th className="text-left px-4 py-3 font-medium text-xs uppercase tracking-widest">Template</th>
                <th className="text-left px-4 py-3 font-medium text-xs uppercase tracking-widest">To</th>
                <th className="text-left px-4 py-3 font-medium text-xs uppercase tracking-widest">Subject</th>
                <th className="text-left px-4 py-3 font-medium text-xs uppercase tracking-widest">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((l) => (
                <tr key={l.log_id} className="border-t" style={{ borderColor: "var(--border)" }} data-testid={`email-log-${l.log_id}`}>
                  <td className="px-4 py-3" style={{ color: "var(--text-muted)" }}>{new Date(l.created_at).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}</td>
                  <td className="px-4 py-3">{TEMPLATE_LABELS[l.template] || l.template}</td>
                  <td className="px-4 py-3 font-mono text-xs">{l.to}</td>
                  <td className="px-4 py-3" style={{ color: "var(--text-muted)" }}>{l.subject || "—"}</td>
                  <td className="px-4 py-3">
                    <StatusPill status={l.status} reason={l.reason} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function StatusPill({ status, reason }) {
  const map = {
    sent: { color: "var(--success)", bg: "rgba(52,211,153,0.12)", label: "Sent" },
    failed: { color: "var(--danger)", bg: "rgba(239,68,68,0.12)", label: "Failed" },
    skipped: { color: "var(--text-muted)", bg: "rgba(154,154,163,0.12)", label: "Skipped" },
  }[status] || { color: "var(--text-muted)", bg: "rgba(154,154,163,0.12)", label: status };
  return (
    <span title={reason || ""} className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium" style={{ color: map.color, background: map.bg }}>
      {map.label}
    </span>
  );
}

// ============================================================================
// PAYOUTS TAB
// ============================================================================
const PAYOUT_STATUS = {
  requested: { label: "Requested", color: "var(--warn)", bg: "rgba(251,191,36,0.12)", icon: Clock },
  paid: { label: "Paid", color: "var(--success)", bg: "rgba(52,211,153,0.12)", icon: CheckCircle2 },
  rejected: { label: "Rejected", color: "var(--danger)", bg: "rgba(239,68,68,0.12)", icon: XCircle },
};

function fmoney(v) { return `$${Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`; }

function PayoutsTab() {
  const [data, setData] = useState({ items: [], totals: null });
  const [status, setStatus] = useState("requested");
  const [acting, setActing] = useState(null);

  const load = async () => {
    try {
      const params = status ? { status } : {};
      const { data } = await api.get("/admin/payouts", { params });
      setData(data);
    } catch { toast.error("Failed to load payouts"); }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [status]);

  const markPaid = async (p) => {
    const ref = window.prompt(`Wire reference for ${fmoney(p.net_amount)} to ${p.organizer_email}?\n(e.g., WIRE12345, leave blank for none)`);
    if (ref === null) return;
    setActing(p.payout_id);
    try {
      await api.post(`/admin/payouts/${p.payout_id}/mark-paid`, { reference: ref || null });
      toast.success(`Marked ${p.payout_id} as paid — confirmation email queued`);
      await load();
    } catch (e) { toast.error("Failed to mark paid"); }
    finally { setActing(null); }
  };

  const reject = async (p) => {
    const reason = window.prompt(`Reject ${p.payout_id} (${fmoney(p.net_amount)})?\nReason:`);
    if (!reason) return;
    setActing(p.payout_id);
    try {
      await api.post(`/admin/payouts/${p.payout_id}/reject`, { reason });
      toast.success(`Rejected — bookings rolled back to organizer's balance`);
      await load();
    } catch { toast.error("Failed to reject"); }
    finally { setActing(null); }
  };

  return (
    <div data-testid="admin-payouts-tab">
      {data.totals && (
        <div className="grid sm:grid-cols-3 gap-3 mb-6">
          <Stat label="Pending" value={fmoney(data.totals.requested)} icon={<Clock className="w-4 h-4" />} accent="var(--warn)" />
          <Stat label="Paid (lifetime)" value={fmoney(data.totals.paid)} icon={<CheckCircle2 className="w-4 h-4" />} accent="var(--success)" />
          <Stat label="Rejected" value={fmoney(data.totals.rejected)} icon={<XCircle className="w-4 h-4" />} />
        </div>
      )}

      <div className="flex gap-2 mb-5">
        {["requested", "paid", "rejected", ""].map((s) => (
          <button
            key={s || "all"}
            onClick={() => setStatus(s)}
            className="px-4 py-2 rounded-full text-xs uppercase tracking-widest transition border"
            style={{
              background: status === s ? "var(--accent)" : "transparent",
              color: status === s ? "#FFFFFF" : "var(--text-muted)",
              borderColor: status === s ? "var(--accent)" : "var(--border)",
            }}
            data-testid={`payout-filter-${s || "all"}`}
          >
            {s ? PAYOUT_STATUS[s]?.label : "All"}
          </button>
        ))}
      </div>

      <div className="border rounded-2xl overflow-hidden" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
        {data.items.length === 0 ? (
          <div className="p-12 text-center" style={{ color: "var(--text-dim)" }}>No payouts match this filter.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr style={{ background: "var(--bg)", color: "var(--text-muted)" }}>
                <th className="text-left px-4 py-3 text-xs uppercase tracking-widest font-medium">Reference</th>
                <th className="text-left px-4 py-3 text-xs uppercase tracking-widest font-medium">Organizer</th>
                <th className="text-left px-4 py-3 text-xs uppercase tracking-widest font-medium">Requested</th>
                <th className="text-right px-4 py-3 text-xs uppercase tracking-widest font-medium">Gross</th>
                <th className="text-right px-4 py-3 text-xs uppercase tracking-widest font-medium">Net</th>
                <th className="text-right px-4 py-3 text-xs uppercase tracking-widest font-medium">Tickets</th>
                <th className="text-left px-4 py-3 text-xs uppercase tracking-widest font-medium">Status</th>
                <th className="text-right px-4 py-3 text-xs uppercase tracking-widest font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((p) => {
                const meta = PAYOUT_STATUS[p.status] || { label: p.status, color: "var(--text-muted)", bg: "transparent", icon: Clock };
                const Icon = meta.icon;
                return (
                  <tr key={p.payout_id} className="border-t" style={{ borderColor: "var(--border)" }} data-testid={`admin-payout-row-${p.payout_id}`}>
                    <td className="px-4 py-4 font-mono text-xs">{p.payout_id}</td>
                    <td className="px-4 py-4">
                      <div className="font-medium">{p.organizer_name}</div>
                      <div className="text-xs" style={{ color: "var(--text-dim)" }}>{p.organizer_email}</div>
                    </td>
                    <td className="px-4 py-4" style={{ color: "var(--text-muted)" }}>{p.requested_at ? new Date(p.requested_at).toLocaleString([], { dateStyle: "short", timeStyle: "short" }) : "—"}</td>
                    <td className="px-4 py-4 text-right">{fmoney(p.gross)}</td>
                    <td className="px-4 py-4 text-right font-semibold">{fmoney(p.net_amount)}</td>
                    <td className="px-4 py-4 text-right">{p.tickets_count}</td>
                    <td className="px-4 py-4">
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium" style={{ color: meta.color, background: meta.bg }}>
                        <Icon className="w-3.5 h-3.5" /> {meta.label}
                      </span>
                    </td>
                    <td className="px-4 py-4 text-right">
                      {p.status === "requested" ? (
                        <div className="flex gap-2 justify-end">
                          <button
                            onClick={() => markPaid(p)}
                            disabled={acting === p.payout_id}
                            className="btn-primary !py-1.5 !px-3 text-xs"
                            data-testid={`mark-paid-${p.payout_id}`}
                          >
                            <BanknoteIcon className="w-3 h-3" /> Mark paid
                          </button>
                          <button
                            onClick={() => reject(p)}
                            disabled={acting === p.payout_id}
                            className="btn-ghost !py-1.5 !px-3 text-xs"
                            data-testid={`reject-${p.payout_id}`}
                          >
                            Reject
                          </button>
                        </div>
                      ) : p.transfer_reference ? (
                        <span className="text-xs font-mono" style={{ color: "var(--text-dim)" }}>{p.transfer_reference}</span>
                      ) : p.rejection_reason ? (
                        <span className="text-xs" style={{ color: "var(--text-dim)" }} title={p.rejection_reason}>{p.rejection_reason.slice(0, 30)}…</span>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// SETTINGS TAB
// ============================================================================
function SettingsTab() {
  const [settings, setSettings] = useState(null);
  const [percent, setPercent] = useState("8");
  const [flat, setFlat] = useState("0.5");
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get("/admin/platform-settings");
      setSettings(data);
      setPercent(String(data.commission_percent));
      setFlat(String(data.commission_flat_fee_per_ticket));
    } catch { toast.error("Failed to load settings"); }
  };

  useEffect(() => { load(); }, []);

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const { data } = await api.put("/admin/platform-settings", {
        commission_percent: parseFloat(percent),
        commission_flat_fee_per_ticket: parseFloat(flat),
      });
      setSettings(data);
      toast.success("Settings saved");
    } catch (e) {
      toast.error(e?.response?.data?.detail?.[0]?.msg || "Save failed");
    } finally { setSaving(false); }
  };

  if (!settings) return <div className="p-10 text-center" style={{ color: "var(--text-dim)" }}>Loading…</div>;

  return (
    <div data-testid="admin-settings-tab" className="max-w-2xl space-y-6">
      <SiteContentPanel />

      <EditorPickPanel />

      <StripeReconcilePanel />

      <EmailDiagnosticsPanel />

      <BlastPanel />

      <DemoDataPanel />

      <div className="border rounded-2xl p-8" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
        <h2 className="serif text-2xl mb-1">Commission & fees</h2>
        <p className="text-sm mb-7" style={{ color: "var(--text-muted)" }}>
          Applied to every organizer payout. Future bookings keep using the values current at request time (snapshotted).
        </p>
        <form onSubmit={save} className="space-y-6">
          <div>
            <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>
              Platform commission (%)
            </label>
            <input
              type="number" min="0" max="50" step="0.1"
              value={percent} onChange={(e) => setPercent(e.target.value)}
              className="w-full" data-testid="commission-percent-input"
            />
          </div>
          <div>
            <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>
              Processing fee per ticket (USD)
            </label>
            <input
              type="number" min="0" max="20" step="0.01"
              value={flat} onChange={(e) => setFlat(e.target.value)}
              className="w-full" data-testid="commission-flat-input"
            />
          </div>
          <div className="pt-3 border-t" style={{ borderColor: "var(--border)" }}>
            <div className="text-xs uppercase tracking-widest mb-3" style={{ color: "var(--text-dim)" }}>Preview · $1,000 gross / 50 tickets</div>
            <div className="space-y-1 text-sm">
              <Row label="Gross" value="$1,000.00" />
              <Row label={`Commission (${percent}%)`} value={`− $${(1000 * parseFloat(percent || 0) / 100).toFixed(2)}`} accent="var(--danger)" />
              <Row label={`Processing (50 × $${flat})`} value={`− $${(50 * parseFloat(flat || 0)).toFixed(2)}`} accent="var(--danger)" />
              <Row label="Net to organizer" value={`$${(1000 - (1000 * parseFloat(percent || 0) / 100) - (50 * parseFloat(flat || 0))).toFixed(2)}`} accent="var(--success)" bold />
            </div>
          </div>
          <button type="submit" disabled={saving} className="btn-primary" data-testid="save-settings-btn">
            {saving ? "Saving…" : "Save settings"}
          </button>
        </form>
      </div>
    </div>
  );
}

function Row({ label, value, accent, bold }) {
  return (
    <div className="flex justify-between">
      <span style={{ color: "var(--text-muted)" }}>{label}</span>
      <span style={{ color: accent || "var(--text)", fontWeight: bold ? 700 : 400 }}>{value}</span>
    </div>
  );
}


// ============================================================================
// SITE CONTENT PANEL — admin edits About + Contact copy and contact details
// ============================================================================
function SiteContentPanel() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [about, setAbout] = useState({});
  const [contact, setContact] = useState({});

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/site-settings");
        setAbout(data.about || {});
        setContact(data.contact || {});
      } catch { /* noop */ }
      finally { setLoading(false); }
    })();
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.patch("/admin/site-settings", { about, contact });
      setAbout(data.about || {});
      setContact(data.contact || {});
      // Bust the cached settings so visitors see new content on next page load
      try { localStorage.removeItem("allsale_site_settings_v1"); } catch { /* noop */ }
      toast.success("Site content updated");
    } catch {
      toast.error("Could not save");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return null;

  return (
    <div className="border rounded-2xl p-8" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }} data-testid="site-content-panel">
      <h2 className="serif text-2xl mb-1">Site content</h2>
      <p className="text-sm mb-6" style={{ color: "var(--text-muted)" }}>
        Edit the About page, Contact page hero and contact details (email, phone, address). Changes go live on the next page load.
      </p>

      <h3 className="font-medium mb-3">About page</h3>
      <div className="space-y-3 mb-6">
        <SF label="Eyebrow" v={about.hero_eyebrow} on={(v) => setAbout({ ...about, hero_eyebrow: v })} testid="about-eyebrow" />
        <SF label="Hero title" v={about.hero_title} on={(v) => setAbout({ ...about, hero_title: v })} multiline rows={2} testid="about-title" />
        <SF label="Hero subtitle" v={about.hero_subtitle} on={(v) => setAbout({ ...about, hero_subtitle: v })} multiline rows={4} testid="about-subtitle" />
        <SF label="Story title" v={about.story_title} on={(v) => setAbout({ ...about, story_title: v })} testid="about-story-title" />
        <SF label="Story body" v={about.story_body} on={(v) => setAbout({ ...about, story_body: v })} multiline rows={6} testid="about-story-body" />
      </div>

      <h3 className="font-medium mb-3">Contact page</h3>
      <div className="space-y-3 mb-6">
        <SF label="Eyebrow" v={contact.hero_eyebrow} on={(v) => setContact({ ...contact, hero_eyebrow: v })} testid="contact-eyebrow" />
        <SF label="Hero title" v={contact.hero_title} on={(v) => setContact({ ...contact, hero_title: v })} testid="contact-title" />
        <SF label="Hero subtitle" v={contact.hero_subtitle} on={(v) => setContact({ ...contact, hero_subtitle: v })} multiline rows={3} testid="contact-subtitle" />
        <SF label="Email" v={contact.email} on={(v) => setContact({ ...contact, email: v })} testid="contact-email" />
        <SF label="Phone" v={contact.phone} on={(v) => setContact({ ...contact, phone: v })} testid="contact-phone" />
        <SF label="Address" v={contact.address} on={(v) => setContact({ ...contact, address: v })} testid="contact-address" />
        <SF label="Organizer note" v={contact.organizer_note} on={(v) => setContact({ ...contact, organizer_note: v })} multiline rows={2} testid="contact-orgnote" />
      </div>

      <div className="flex justify-end">
        <button onClick={save} disabled={saving} className="btn-primary" data-testid="save-site-content-btn">
          {saving ? "Saving…" : "Save changes"}
        </button>
      </div>
    </div>
  );
}

function SF({ label, v, on, multiline, rows, testid }) {
  return (
    <label className="block">
      <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>{label}</div>
      {multiline ? (
        <textarea value={v || ""} onChange={(e) => on(e.target.value)} rows={rows || 3} className="w-full" data-testid={testid} />
      ) : (
        <input value={v || ""} onChange={(e) => on(e.target.value)} className="w-full" data-testid={testid} />
      )}
    </label>
  );
}


// ============================================================================
// EDITOR'S PICK PANEL — admin pins one curated event to the landing hero +
// writes a quick blurb that renders under the title.
// ============================================================================
function EditorPickPanel() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [events, setEvents] = useState([]);
  const [eventId, setEventId] = useState("");
  const [blurb, setBlurb] = useState("");
  const [badge, setBadge] = useState("Editor's Pick");

  useEffect(() => {
    (async () => {
      try {
        const [settings, list] = await Promise.all([
          api.get("/site-settings"),
          api.get("/admin/events"),
        ]);
        const ep = settings.data?.editor_pick || {};
        setEventId(ep.event_id || "");
        setBlurb(ep.blurb || "");
        setBadge(ep.badge_text || "Editor's Pick");
        // Only approved events qualify for the landing-page hero spotlight.
        setEvents(
          (Array.isArray(list.data) ? list.data : [])
            .filter((e) => e.status === "approved")
            .sort((a, b) => new Date(a.date) - new Date(b.date))
        );
      } catch { /* noop */ } finally { setLoading(false); }
    })();
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.patch("/admin/site-settings", {
        editor_pick: {
          event_id: eventId || null,
          blurb: blurb.trim(),
          badge_text: (badge || "").trim() || "Editor's Pick",
        },
      });
      const ep = data.editor_pick || {};
      setEventId(ep.event_id || "");
      setBlurb(ep.blurb || "");
      setBadge(ep.badge_text || "Editor's Pick");
      toast.success(eventId ? "Editor's Pick updated — visible on the landing page" : "Editor's Pick cleared — landing page reverts to the first featured event");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save Editor's Pick");
    } finally { setSaving(false); }
  };

  const clear = () => {
    setEventId("");
    setBlurb("");
  };

  if (loading) return null;

  const picked = events.find((e) => e.event_id === eventId);

  return (
    <div
      className="border rounded-2xl p-8"
      style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
      data-testid="editor-pick-panel"
    >
      <h2 className="serif text-2xl mb-1 flex items-center gap-2">
        <Sparkles className="w-5 h-5" style={{ color: "var(--accent)" }} /> Editor's Pick
      </h2>
      <p className="text-sm mb-6" style={{ color: "var(--text-muted)" }}>
        Pin one curated event to the landing-page hero spotlight with a short curator blurb. Falls back to the first featured event when no pick is set.
      </p>

      <div className="space-y-4">
        <label className="block">
          <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>Pinned event</div>
          <select
            value={eventId}
            onChange={(e) => setEventId(e.target.value)}
            className="w-full"
            data-testid="editor-pick-select"
          >
            <option value="">— No pick (use first featured event) —</option>
            {events.map((e) => (
              <option key={e.event_id} value={e.event_id}>
                {e.title} · {e.venue}, {e.city}
              </option>
            ))}
          </select>
          {events.length === 0 && (
            <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>
              No approved events yet. Once you approve an event, it appears here.
            </div>
          )}
        </label>

        <label className="block">
          <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>Curator blurb</div>
          <textarea
            value={blurb}
            onChange={(e) => setBlurb(e.target.value)}
            rows={3}
            maxLength={220}
            placeholder={`e.g. "Two-night-only premiere — five-piece live band, sunset on Lake Wakatipu. Don't scroll past this one."`}
            className="w-full"
            data-testid="editor-pick-blurb"
          />
          <div className="text-xs mt-1 flex justify-between" style={{ color: "var(--text-dim)" }}>
            <span>Renders in italics under the event title on the landing hero.</span>
            <span>{blurb.length}/220</span>
          </div>
        </label>

        <label className="block">
          <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>Badge text</div>
          <input
            value={badge}
            onChange={(e) => setBadge(e.target.value)}
            maxLength={32}
            placeholder="Editor's Pick"
            className="w-full"
            data-testid="editor-pick-badge"
          />
          <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>
            Override to e.g. "Trending now", "Don't miss", "Last 50 seats". Defaults to "Editor's Pick".
          </div>
        </label>

        {picked && (
          <div
            className="p-4 rounded-xl border flex gap-3 items-center"
            style={{ borderColor: "var(--accent)", background: "rgba(240,138,42,0.06)" }}
            data-testid="editor-pick-preview"
          >
            {picked.image_url && (
              <img src={picked.image_url} alt="" className="w-16 h-16 rounded-lg object-cover flex-shrink-0" />
            )}
            <div className="flex-1 min-w-0">
              <div className="text-[10px] uppercase tracking-widest" style={{ color: "var(--accent)" }}>{badge || "Editor's Pick"}</div>
              <div className="font-medium truncate">{picked.title}</div>
              <div className="text-xs" style={{ color: "var(--text-dim)" }}>{picked.venue} · {picked.city}</div>
              {blurb && <div className="text-xs italic mt-1 line-clamp-2" style={{ color: "var(--text-muted)" }}>"{blurb}"</div>}
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          {eventId && (
            <button type="button" onClick={clear} className="btn-ghost" data-testid="editor-pick-clear">
              Clear
            </button>
          )}
          <button type="button" onClick={save} disabled={saving} className="btn-primary" data-testid="editor-pick-save">
            {saving ? "Saving…" : "Save Editor's Pick"}
          </button>
        </div>
      </div>
    </div>
  );
}


// ============================================================================
// BLAST PANEL — admin sends a custom email to a filtered audience
// ============================================================================
function BlastPanel() {
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [target, setTarget] = useState("marketing_optins");
  const [eventId, setEventId] = useState("");
  const [events, setEvents] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/admin/events");
        setEvents(Array.isArray(data) ? data : []);
      } catch { /* noop */ }
    })();
  }, []);

  const send = async (e) => {
    e.preventDefault();
    if (!subject.trim() || !body.trim()) return toast.error("Subject and body required");
    if (target === "event_attendees" && !eventId) return toast.error("Pick an event");
    if (!window.confirm("Send this email blast?\n\nThis will email every matching user. Cannot be undone.")) return;
    setBusy(true);
    try {
      const { data } = await api.post("/admin/blast", {
        subject: subject.trim(),
        body: body.trim(),
        target,
        event_id: eventId || null,
      });
      if (data.sent === 0) toast.message(data.skipped || "No recipients");
      else toast.success(`Sent to ${data.sent} recipients`);
      setSubject("");
      setBody("");
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Blast failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border rounded-2xl p-8" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }} data-testid="admin-blast-panel">
      <h2 className="serif text-2xl mb-1">Email blast</h2>
      <p className="text-sm mb-6" style={{ color: "var(--text-muted)" }}>
        Send a custom email to a filtered audience. Use sparingly — it's logged.
      </p>
      <form onSubmit={send} className="space-y-4">
        <div>
          <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>Audience</label>
          <select value={target} onChange={(e) => setTarget(e.target.value)} className="w-full" data-testid="blast-target-select">
            <option value="marketing_optins">Users opted-in to promotions</option>
            <option value="all_attendees">All paying attendees (any event)</option>
            <option value="event_attendees">Attendees of a specific event</option>
          </select>
        </div>

        {target === "event_attendees" && (
          <div>
            <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>Event</label>
            <select value={eventId} onChange={(e) => setEventId(e.target.value)} className="w-full" data-testid="blast-event-select">
              <option value="">— pick an event —</option>
              {events.map((e) => (
                <option key={e.event_id} value={e.event_id}>{e.title} · {new Date(e.date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</option>
              ))}
            </select>
          </div>
        )}

        <div>
          <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>Subject</label>
          <input value={subject} onChange={(e) => setSubject(e.target.value)} className="w-full" placeholder="What's the message?" data-testid="blast-subject-input" />
        </div>

        <div>
          <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>Body</label>
          <textarea value={body} onChange={(e) => setBody(e.target.value)} className="w-full" rows={6} placeholder="Write your message — line breaks preserved." data-testid="blast-body-input" />
        </div>

        <div className="flex justify-end pt-2">
          <button type="submit" disabled={busy} className="btn-primary" data-testid="blast-send-btn">
            {busy ? "Sending…" : "Send blast"}
          </button>
        </div>
      </form>
    </div>
  );
}



// ============================================================================
// EMAIL DIAGNOSTICS PANEL — admin can see Resend config, send a test email,
// and resend a booking confirmation when a customer's ticket email didn't
// land. Wired to /api/admin/email/{diagnostics,send-test,resend-booking}.
// ============================================================================
function EmailDiagnosticsPanel() {
  const [diag, setDiag] = useState(null);
  const [testTo, setTestTo] = useState("");
  const [busyTest, setBusyTest] = useState(false);
  const [resendQuery, setResendQuery] = useState("");
  const [bookingsFound, setBookingsFound] = useState([]);
  const [searching, setSearching] = useState(false);
  const [busyResend, setBusyResend] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get("/admin/email/diagnostics");
      setDiag(data);
    } catch { /* noop */ }
  };

  useEffect(() => { load(); }, []);

  const sendTest = async () => {
    if (!testTo || !testTo.includes("@")) {
      toast.error("Enter a valid email address");
      return;
    }
    setBusyTest(true);
    try {
      const { data } = await api.post("/admin/email/send-test", { to: testTo });
      if (data.ok) {
        toast.success(`Sent to ${data.to} — check the inbox (and spam)`);
      } else {
        toast.error(`Send failed: ${data.reason || "unknown error"}`);
      }
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Send failed");
    } finally { setBusyTest(false); }
  };

  const search = async () => {
    const q = resendQuery.trim();
    if (!q) return;
    setSearching(true);
    setBookingsFound([]);
    try {
      if (q.startsWith("bkg_")) {
        // Direct booking ID — wrap as a synthetic single-result list
        setBookingsFound([{ booking_id: q }]);
      } else if (q.includes("@")) {
        const { data } = await api.get(`/admin/bookings/lookup?email=${encodeURIComponent(q)}`);
        if (data.count === 0) {
          toast(`No bookings found for ${q}`);
        }
        setBookingsFound(data.bookings || []);
      } else {
        toast.error("Enter a booking ID (bkg_...) or an email address");
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Search failed");
    } finally { setSearching(false); }
  };

  const resendOne = async (bookingId) => {
    setBusyResend(true);
    try {
      const { data } = await api.post("/admin/email/resend-booking", { booking_id: bookingId });
      toast.success(`Queued for ${data.to || bookingId}`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Resend failed");
    } finally { setBusyResend(false); }
  };

  const resendAll = async () => {
    if (!bookingsFound.length) return;
    setBusyResend(true);
    let ok = 0, fail = 0;
    for (const b of bookingsFound) {
      try {
        await api.post("/admin/email/resend-booking", { booking_id: b.booking_id });
        ok += 1;
      } catch { fail += 1; }
    }
    toast.success(`Resent ${ok} email${ok === 1 ? "" : "s"}${fail ? `, ${fail} failed` : ""}`);
    load();
    setBusyResend(false);
  };

  const stat = (label, value, status) => (
    <div className="flex items-center justify-between py-1 text-sm">
      <span style={{ color: "var(--text-muted)" }}>{label}</span>
      <span className="flex items-center gap-2 font-mono text-xs">
        {status === "ok" && <span style={{ color: "var(--success)" }}>✓</span>}
        {status === "warn" && <span style={{ color: "var(--accent)" }}>⚠</span>}
        {status === "err" && <span style={{ color: "var(--danger)" }}>✗</span>}
        {value}
      </span>
    </div>
  );

  return (
    <div
      className="border rounded-2xl p-8"
      style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
      data-testid="email-diagnostics-panel"
    >
      <h2 className="serif text-2xl mb-1 flex items-center gap-2">
        <Mail className="w-5 h-5" style={{ color: "var(--accent)" }} /> Email delivery
      </h2>
      <p className="text-sm mb-5" style={{ color: "var(--text-muted)" }}>
        Verify the production Resend config, send yourself a diagnostic email, and resend booking confirmations to customers whose tickets didn't arrive.
      </p>

      {diag && (
        <div className="mb-5 p-4 rounded-xl" style={{ background: "var(--bg)", border: "1px solid var(--border)" }} data-testid="email-diag-stats">
          {stat("Resend SDK", diag.resend_available ? "available" : "missing", diag.resend_available ? "ok" : "err")}
          {stat("API key", diag.api_key_set ? `set (${diag.api_key_prefix}…)` : "MISSING", diag.api_key_set ? "ok" : "err")}
          {stat("From", diag.sender_email, diag.sender_is_sandbox ? "warn" : "ok")}
          {stat("Reply-To", diag.reply_to_email || "—", diag.reply_to_email ? "ok" : "warn")}
          {stat("App URL", diag.app_public_url, diag.app_public_url?.includes("allsale.events") ? "ok" : "warn")}
          {stat("Sent / Failed / Skipped", `${diag.stats?.sent || 0} / ${diag.stats?.failed || 0} / ${diag.stats?.skipped || 0}`, diag.stats?.sent > diag.stats?.failed ? "ok" : "warn")}
          <button type="button" onClick={load} className="text-xs mt-2 underline" style={{ color: "var(--text-dim)" }} data-testid="email-diag-refresh">
            Refresh
          </button>
        </div>
      )}

      <div className="space-y-4">
        <div>
          <div className="text-xs uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>Send a test email</div>
          <div className="flex gap-2">
            <input
              type="email"
              value={testTo}
              onChange={(e) => setTestTo(e.target.value)}
              placeholder="you@gmail.com"
              className="flex-1"
              data-testid="email-test-to-input"
            />
            <button type="button" onClick={sendTest} disabled={busyTest || !testTo} className="btn-primary" data-testid="email-test-send-btn">
              <Send className="w-4 h-4" /> {busyTest ? "Sending…" : "Send test"}
            </button>
          </div>
        </div>

        <div>
          <div className="text-xs uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>Resend a booking confirmation</div>
          <div className="flex gap-2">
            <input
              value={resendQuery}
              onChange={(e) => setResendQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && search()}
              placeholder="Customer email OR booking ID (bkg_...)"
              className="flex-1"
              data-testid="email-resend-query-input"
            />
            <button type="button" onClick={search} disabled={searching || !resendQuery} className="btn-ghost" data-testid="email-resend-search-btn">
              <Search className="w-4 h-4" /> {searching ? "Searching…" : "Search"}
            </button>
          </div>
          <p className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>
            Paste a customer's email to find all their tickets, or a booking ID for a single one.
          </p>

          {bookingsFound.length > 0 && (
            <div className="mt-3 border rounded-xl overflow-hidden" style={{ borderColor: "var(--border)" }} data-testid="email-resend-results">
              <div className="flex items-center justify-between px-4 py-2 text-xs" style={{ background: "var(--bg)", color: "var(--text-dim)" }}>
                <span>{bookingsFound.length} booking{bookingsFound.length === 1 ? "" : "s"} found</span>
                {bookingsFound.length > 1 && (
                  <button type="button" onClick={resendAll} disabled={busyResend} className="text-xs underline" data-testid="email-resend-all-btn">
                    {busyResend ? "Sending…" : `Resend all ${bookingsFound.length}`}
                  </button>
                )}
              </div>
              <div className="divide-y" style={{ borderColor: "var(--border)" }}>
                {bookingsFound.map((b) => (
                  <div key={b.booking_id} className="px-4 py-3 flex items-center justify-between gap-3" style={{ borderTop: "1px solid var(--border)" }}>
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-mono truncate" style={{ color: "var(--text)" }}>{b.booking_id}</div>
                      {b.event_title && (
                        <div className="text-xs truncate" style={{ color: "var(--text-muted)" }}>
                          {b.event_title} {b.status && <span style={{ color: b.status === "paid" ? "var(--success)" : "var(--accent)" }}>· {b.status}</span>}
                        </div>
                      )}
                    </div>
                    <button type="button" onClick={() => resendOne(b.booking_id)} disabled={busyResend} className="btn-ghost" data-testid={`email-resend-one-${b.booking_id}`}>
                      <RotateCcw className="w-4 h-4" /> Resend
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


// ============================================================================
// STRIPE RECONCILE PANEL — sweep pending checkout sessions and fulfil any
// that have actually been paid (used while live webhook is being set up, or
// to recover from webhook delivery failures).
// ============================================================================
function StripeReconcilePanel() {
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState(null);
  const [forceBookingId, setForceBookingId] = useState("");
  const [busyForce, setBusyForce] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/admin/payments/reconcile");
      setReport(data);
      if (data.fulfilled_count > 0) {
        toast.success(`Fulfilled ${data.fulfilled_count} paid booking${data.fulfilled_count === 1 ? "" : "s"}`);
      } else {
        toast(`Scanned ${data.scanned} pending session${data.scanned === 1 ? "" : "s"} — nothing new to fulfil`);
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Reconcile failed");
    } finally { setBusy(false); }
  };

  const forceOne = async () => {
    const id = forceBookingId.trim();
    if (!id.startsWith("bkg_")) {
      toast.error("Booking ID must start with 'bkg_'");
      return;
    }
    if (!window.confirm(
      `Force-fulfil booking ${id}?\n\nThis marks the booking PAID, generates the QR code, sends the confirmation email, and locks the seats — WITHOUT verifying with Stripe.\n\nOnly use this when you've already confirmed the charge succeeded in your Stripe Dashboard. Do NOT use for unpaid customers.`
    )) return;
    setBusyForce(true);
    try {
      const { data } = await api.post("/admin/payments/force-fulfil", { booking_id: id });
      toast.success(`✓ ${data.message} (to ${data.to})`);
      setForceBookingId("");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Force-fulfil failed");
    } finally { setBusyForce(false); }
  };

  return (
    <div
      className="border rounded-2xl p-8"
      style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
      data-testid="reconcile-panel"
    >
      <h2 className="serif text-2xl mb-1 flex items-center gap-2">
        <RefreshCw className="w-5 h-5" style={{ color: "var(--accent)" }} /> Reconcile Stripe payments
      </h2>
      <p className="text-sm mb-5" style={{ color: "var(--text-muted)" }}>
        Re-pull every pending checkout session from Stripe and finalise any that have actually been paid — issues the e-ticket, sends the confirmation email, and frees the seat hold. Use this when the live webhook hasn't been configured yet, or any time a customer's payment succeeded but their ticket didn't arrive.
      </p>
      <button
        type="button"
        onClick={run}
        disabled={busy}
        className="btn-primary"
        data-testid="reconcile-btn"
      >
        <RefreshCw className={`w-4 h-4 ${busy ? "animate-spin" : ""}`} /> {busy ? "Reconciling…" : "Reconcile now"}
      </button>
      {report && (
        <div className="mt-5 text-sm space-y-2" data-testid="reconcile-report">
          <div style={{ color: "var(--success)" }}>
            ✓ Scanned {report.scanned} pending · Fulfilled {report.fulfilled_count} new · {report.already_paid_count} already paid · {report.still_pending_count} still pending · {report.errors?.length || 0} errors
          </div>
          {(report.fulfilled || []).filter((f) => f.newly_fulfilled).length > 0 && (
            <ul className="text-xs space-y-1" style={{ color: "var(--text-dim)" }}>
              {report.fulfilled.filter((f) => f.newly_fulfilled).map((f) => (
                <li key={f.session_id}>✓ Fulfilled booking {f.booking_id}</li>
              ))}
            </ul>
          )}
          {(report.errors || []).length > 0 && (
            <details className="text-xs" style={{ color: "var(--text-dim)" }}>
              <summary className="cursor-pointer">{report.errors.length} error{report.errors.length === 1 ? "" : "s"} (click to expand)</summary>
              <ul className="mt-2 space-y-1">
                {report.errors.slice(0, 10).map((e, i) => (
                  <li key={i} className="truncate">{e.booking_id || e.session_id}: {e.error}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}

      <div className="mt-6 pt-5" style={{ borderTop: "1px dashed var(--border)" }}>
        <div className="text-xs uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>Force-fulfil a single booking</div>
        <p className="text-xs mb-3" style={{ color: "var(--text-muted)" }}>
          When Stripe shows the charge as Succeeded but the reconcile job can't query it cleanly, paste the booking ID here to manually issue the ticket. <strong style={{ color: "var(--danger)" }}>Verify the charge succeeded in your Stripe dashboard first.</strong>
        </p>
        <div className="flex gap-2">
          <input
            value={forceBookingId}
            onChange={(e) => setForceBookingId(e.target.value)}
            placeholder="bkg_xxxxxxxxxxxx"
            className="flex-1 font-mono"
            data-testid="force-fulfil-input"
          />
          <button type="button" onClick={forceOne} disabled={busyForce || !forceBookingId.trim().startsWith("bkg_")} className="btn-ghost" style={{ borderColor: "var(--danger)", color: "var(--danger)" }} data-testid="force-fulfil-btn">
            {busyForce ? "Working…" : "Force fulfil"}
          </button>
        </div>
      </div>
    </div>
  );
}


// ============================================================================
// DEMO DATA WIPE PANEL — one-shot cleanup of the seed events / demo accounts.
// ============================================================================
function DemoDataPanel() {
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState(null);

  const wipe = async () => {
    if (!window.confirm(
      "Remove the 10 seed demo events (Dune, Hamilton, AllBlacks, etc.) plus the "
      + "demo organizer/attendee accounts?\n\nReal events and real users created "
      + "by your own organizers are NOT touched. This action cannot be undone."
    )) return;
    setBusy(true);
    try {
      const { data } = await api.post("/admin/wipe-demo-data");
      setReport(data);
      toast.success(`Removed ${data.events_removed} demo event${data.events_removed === 1 ? "" : "s"} and ${data.users_removed} demo user${data.users_removed === 1 ? "" : "s"}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Wipe failed");
    } finally { setBusy(false); }
  };

  return (
    <div
      className="border rounded-2xl p-8"
      style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
      data-testid="demo-data-panel"
    >
      <h2 className="serif text-2xl mb-1 flex items-center gap-2">
        <Trash2 className="w-5 h-5" style={{ color: "var(--danger)" }} /> Demo data cleanup
      </h2>
      <p className="text-sm mb-5" style={{ color: "var(--text-muted)" }}>
        Wipe the sample events shipped with a fresh install (Dune, Hamilton, AllBlacks,
        etc.) and the demo organizer/attendee accounts. Real events you've created
        and real users that have signed up are left alone.
      </p>
      <button
        type="button"
        onClick={wipe}
        disabled={busy}
        className="btn-ghost"
        style={{ borderColor: "var(--danger)", color: "var(--danger)" }}
        data-testid="wipe-demo-btn"
      >
        <Trash2 className="w-4 h-4" /> {busy ? "Wiping…" : "Wipe demo data"}
      </button>
      {report && (
        <div className="mt-5 text-sm space-y-1" data-testid="wipe-demo-report">
          <div style={{ color: "var(--success)" }}>
            ✓ Removed {report.events_removed} event{report.events_removed === 1 ? "" : "s"}, {report.users_removed} user{report.users_removed === 1 ? "" : "s"}.
          </div>
          {report.cascade && (
            <div className="text-xs" style={{ color: "var(--text-dim)" }}>
              Cascade: {report.cascade.bookings} bookings · {report.cascade.holds} holds · {report.cascade.reservations} reservations · {report.cascade.scanner_tokens} scanner tokens · {report.cascade.waitlist} waitlist · {report.cascade.discount_codes} codes
            </div>
          )}
        </div>
      )}
    </div>
  );
}
