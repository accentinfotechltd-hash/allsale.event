import { useEffect, useState, useRef } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { invalidateFeeSettingsCache } from "@/lib/fees";
import MessageReactions from "@/components/MessageReactions";
import { useAuth } from "@/lib/auth";
import useChatLive from "@/lib/useChatLive";
import { Check, X, Star, Users, Calendar, Search, ShieldCheck, ShieldAlert, UserCog, Ban, RotateCcw, Mail, MessageCircle, CheckCircle2, AlertTriangle, MinusCircle, Wallet, Settings as SettingsIcon, Clock, XCircle, BanknoteIcon, Eye, Trash2, Sparkles, RefreshCw, Send, Pencil, UserPlus, MessagesSquare, FileText, Handshake, Tag, DollarSign, BarChart3, Download } from "lucide-react";
import { toast } from "sonner";
import AdminUserDetailDrawer from "@/components/AdminUserDetailDrawer";
import StripeAdminDiagnostics from "@/components/StripeAdminDiagnostics";
import AdminBlogTab from "@/components/AdminBlogTab";
import AdminMarketingPartnersTab from "@/components/AdminMarketingPartnersTab";
import AdminFlyersTab from "@/components/AdminFlyersTab";
import AdminRecruitmentLeadsTab from "@/components/AdminRecruitmentLeadsTab";
import AdminCreatorCodesTab from "@/components/AdminCreatorCodesTab";
import AdminStripeConnectStatusTab from "@/components/AdminStripeConnectStatusTab";
import AdminPartnerApplicationsTab from "@/components/AdminPartnerApplicationsTab";

export default function Admin() {
  const { user } = useAuth();
  // Tab can be deep-linked via ?tab=… (used by emails: `/admin?tab=org-chat&organizer=…`).
  const initialTab = (() => {
    if (typeof window === "undefined") return "events";
    const t = new URLSearchParams(window.location.search).get("tab");
    const valid = ["events", "users", "payouts", "stripe", "stripe-connect", "emails", "chats", "org-chat", "protection", "blog", "partners", "partner-applications", "flyers", "leads", "creator-codes", "settings"];
    return valid.includes(t) ? t : "events";
  })();
  const [tab, setTab] = useState(initialTab);

  if (!user || user.role !== "admin") {
    return <div className="text-center py-20" style={{ color: "var(--text-muted)" }}>Admin access required.</div>;
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-12">
      <div className="mb-8 flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Admin</div>
          <h1 className="serif text-5xl">Control center</h1>
        </div>
        <Link
          to="/admin/revenue"
          className="btn-primary inline-flex items-center gap-2"
          data-testid="admin-revenue-link"
        >
          <DollarSign className="w-4 h-4" /> Revenue dashboard
        </Link>
      </div>

      <AdminHeroStrip onClickProtection={() => setTab("protection")} onClickPartners={() => setTab("partners")} />

      <div className="border-b mb-8" style={{ borderColor: "var(--border)" }}>
        <div
          className="flex gap-0 overflow-x-auto scrollbar-thin"
          style={{ scrollbarWidth: "thin" }}
          data-testid="admin-tabs-row"
        >
          <TabBtn id="events" current={tab} onClick={setTab} icon={<Calendar className="w-4 h-4" />} label="Events" />
          <TabBtn id="users" current={tab} onClick={setTab} icon={<Users className="w-4 h-4" />} label="Users" />
          <TabBtn id="payouts" current={tab} onClick={setTab} icon={<Wallet className="w-4 h-4" />} label="Payouts" />
          <TabBtn id="stripe" current={tab} onClick={setTab} icon={<ShieldCheck className="w-4 h-4" />} label="Stripe" />
          <TabBtn id="stripe-connect" current={tab} onClick={setTab} icon={<Handshake className="w-4 h-4" />} label="Connect" />
          <TabBtn id="emails" current={tab} onClick={setTab} icon={<Mail className="w-4 h-4" />} label="Emails" />
          <TabBtn id="chats" current={tab} onClick={setTab} icon={<MessageCircle className="w-4 h-4" />} label="Live chat" />
          <TabBtn id="org-chat" current={tab} onClick={setTab} icon={<MessagesSquare className="w-4 h-4" />} label="Org chat" />
          <TabBtn id="protection" current={tab} onClick={setTab} icon={<ShieldAlert className="w-4 h-4" />} label="Claims" />
          <TabBtn id="blog" current={tab} onClick={setTab} icon={<FileText className="w-4 h-4" />} label="Blog" />
          <TabBtn id="partners" current={tab} onClick={setTab} icon={<Handshake className="w-4 h-4" />} label="Partners" />
          <TabBtn id="partner-applications" current={tab} onClick={setTab} icon={<Mail className="w-4 h-4" />} label="Applications" />
          <TabBtn id="flyers" current={tab} onClick={setTab} icon={<Mail className="w-4 h-4" />} label="Flyers" />
          <TabBtn id="leads" current={tab} onClick={setTab} icon={<UserPlus className="w-4 h-4" />} label="Leads" />
          <TabBtn id="creator-codes" current={tab} onClick={setTab} icon={<Tag className="w-4 h-4" />} label="Creators" />
          <TabBtn id="settings" current={tab} onClick={setTab} icon={<SettingsIcon className="w-4 h-4" />} label="Settings" />
        </div>
      </div>

      {tab === "events" ? <EventsTab /> : tab === "users" ? <UsersTab currentUser={user} /> : tab === "payouts" ? <PayoutsTab /> : tab === "stripe" ? <StripeAdminDiagnostics /> : tab === "stripe-connect" ? <AdminStripeConnectStatusTab /> : tab === "emails" ? <EmailsTab /> : tab === "chats" ? <SupportChatTab /> : tab === "org-chat" ? <OrganizerChatTab /> : tab === "protection" ? <ProtectionClaimsTab /> : tab === "blog" ? <AdminBlogTab /> : tab === "partners" ? <AdminMarketingPartnersTab /> : tab === "partner-applications" ? <AdminPartnerApplicationsTab /> : tab === "flyers" ? <AdminFlyersTab /> : tab === "leads" ? <AdminRecruitmentLeadsTab /> : tab === "creator-codes" ? <AdminCreatorCodesTab /> : <SettingsTab />}
    </div>
  );
}

function TabBtn({ id, current, onClick, icon, label }) {
  const active = current === id;
  return (
    <button
      onClick={() => onClick(id)}
      className="flex items-center gap-1.5 px-2.5 py-2.5 text-xs whitespace-nowrap flex-shrink-0 transition relative hover:text-[color:var(--text)]"
      style={{ color: active ? "var(--accent)" : "var(--text-muted)" }}
      data-testid={`admin-tab-${id}`}
    >
      <span className="inline-flex items-center" style={{ transform: "scale(0.9)" }}>{icon}</span>
      <span>{label}</span>
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
      <SubmissionTrend />
      <Section title="Pending approval" events={pending} act={act} del={del} showApprove />
      <Section title="Approved events" events={approved} act={act} del={del} showFeature />
      {rejected.length > 0 && (
        <Section title="Rejected" events={rejected} act={act} del={del} />
      )}
    </>
  );
}

function SubmissionTrend() {
  const [data, setData] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get("/admin/events/submission-trend?days=14");
        if (!cancelled) setData(data);
      } catch {
        if (!cancelled) setData(null);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (!data) return null;

  // Pad series with zero-buckets so the sparkline always shows 14 days.
  const today = new Date();
  const padded = [];
  for (let i = data.days - 1; i >= 0; i -= 1) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    const row = data.series.find((s) => s.date === key);
    padded.push({ date: key, count: row?.count || 0 });
  }
  const maxCount = Math.max(...padded.map((p) => p.count), 1);
  const deltaSign = data.delta_pct == null ? 0 : Math.sign(data.delta_pct);
  const deltaColor = deltaSign > 0 ? "rgb(46,160,67)" : deltaSign < 0 ? "rgb(198,40,40)" : "var(--text-dim)";
  const deltaLabel = data.delta_pct == null
    ? "—"
    : `${data.delta_pct > 0 ? "+" : ""}${data.delta_pct}% vs previous 24h`;

  return (
    <div
      className="mb-8 border rounded-2xl p-5"
      style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
      data-testid="admin-submission-trend"
    >
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div>
          <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>Last 24 hours</div>
          <div className="flex items-baseline gap-3">
            <div className="serif text-4xl" data-testid="admin-submitted-24h">{data.submitted_24h}</div>
            <div className="text-xs" style={{ color: "var(--text-muted)" }}>event{data.submitted_24h === 1 ? "" : "s"} submitted</div>
            <div className="text-xs" style={{ color: deltaColor }} data-testid="admin-submitted-delta">
              {deltaLabel}
            </div>
          </div>
        </div>
        <div className="text-xs" style={{ color: "var(--text-dim)" }}>
          {data.total_in_window} in last {data.days} days
        </div>
      </div>

      {/* Sparkline */}
      <div className="flex items-end gap-1 h-16">
        {padded.map((p) => (
          <div
            key={p.date}
            className="flex-1 rounded-t"
            style={{
              height: `${(p.count / maxCount) * 100}%`,
              minHeight: "2px",
              background: p.count > 0 ? "var(--accent)" : "var(--border)",
            }}
            title={`${p.date}: ${p.count} submission${p.count === 1 ? "" : "s"}`}
          />
        ))}
      </div>
      <div className="flex justify-between text-[10px] mt-1" style={{ color: "var(--text-dim)" }}>
        <span>{padded[0]?.date}</span>
        <span>{padded[padded.length - 1]?.date}</span>
      </div>
    </div>
  );
}

function Section({ title, events, act, del, showApprove, showFeature }) {
  const BACKEND = process.env.REACT_APP_BACKEND_URL;
  const downloadAttendeesCsv = async (ev) => {
    try {
      const token = localStorage.getItem("aura_token");
      const r = await fetch(`${BACKEND}/api/organizer/events/${ev.event_id}/attendees.csv`, {
        headers: { Authorization: `Bearer ${token}` },
        credentials: "include",
      });
      if (!r.ok) throw new Error("Download failed");
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const safe = (ev.title || "event").replace(/[^a-z0-9_-]+/gi, "_").slice(0, 50);
      a.download = `attendees_${safe}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success(`Downloaded attendees for "${ev.title}"`);
    } catch {
      toast.error("CSV download failed");
    }
  };
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
                {e.sales && (
                  <div
                    className="grid grid-cols-3 gap-2 mb-3 text-xs rounded-lg border p-2"
                    style={{ borderColor: "var(--border)", background: "var(--bg-elev)" }}
                    data-testid={`admin-event-sales-${e.event_id}`}
                  >
                    <div>
                      <div className="opacity-60 text-[10px] uppercase tracking-widest">Tickets</div>
                      <div className="text-sm font-medium" style={{ color: "var(--text)" }}>{e.sales.tickets_sold}</div>
                    </div>
                    <div>
                      <div className="opacity-60 text-[10px] uppercase tracking-widest">Bookings</div>
                      <div className="text-sm font-medium" style={{ color: "var(--text)" }}>{e.sales.bookings_count}</div>
                    </div>
                    <div>
                      <div className="opacity-60 text-[10px] uppercase tracking-widest">Revenue</div>
                      <div className="text-sm font-medium" style={{ color: "var(--accent)" }} title={e.sales.refunded > 0 ? `Gross $${e.sales.revenue.toFixed(2)} · Refunded $${e.sales.refunded.toFixed(2)}` : undefined}>
                        ${e.sales.net_revenue.toFixed(2)}
                      </div>
                    </div>
                  </div>
                )}
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
                  <Link
                    to={`/organizer/events/${e.event_id}`}
                    className="btn-ghost !py-1.5 !px-3 text-xs"
                    data-testid={`admin-open-event-${e.event_id}`}
                    title="Open the full event report (analytics, attendees, refunds)"
                  >
                    <BarChart3 className="w-3 h-3" /> Open
                  </Link>
                  <Link
                    to={`/organizer/buyers?event_id=${e.event_id}`}
                    className="btn-ghost !py-1.5 !px-3 text-xs"
                    data-testid={`admin-buyers-${e.event_id}`}
                    title="See everyone who bought tickets to this event"
                  >
                    <Users className="w-3 h-3" /> Buyers
                  </Link>
                  <button
                    onClick={() => downloadAttendeesCsv(e)}
                    className="btn-ghost !py-1.5 !px-3 text-xs"
                    data-testid={`admin-csv-${e.event_id}`}
                    title="Download attendees CSV for this event"
                  >
                    <Download className="w-3 h-3" /> CSV
                  </button>
                  <Link
                    to={`/organizer/events/${e.event_id}/edit`}
                    className="btn-ghost !py-1.5 !px-3 text-xs"
                    data-testid={`admin-edit-${e.event_id}`}
                    title="Edit event details, tiers, seat map, etc."
                  >
                    <Pencil className="w-3 h-3" /> Edit
                  </Link>
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
// ============================================================================
// CreateUserDialog — modal for admin to seed a new account
// ============================================================================
function CreateUserDialog({ onClose, onCreated }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("organizer");
  const [sendWelcome, setSendWelcome] = useState(true);
  const [busy, setBusy] = useState(false);

  const generatePassword = () => {
    // 12-char base64-ish password — easy to read aloud yet uncommon.
    const arr = new Uint8Array(9);
    window.crypto.getRandomValues(arr);
    setPassword(btoa(String.fromCharCode(...arr)).replace(/[+/=]/g, "").slice(0, 12));
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!name.trim() || !email.trim() || !password.trim()) {
      toast.error("Name, email and password are required");
      return;
    }
    if (password.length < 6) {
      toast.error("Password must be at least 6 characters");
      return;
    }
    setBusy(true);
    try {
      const { data } = await api.post("/admin/users", {
        name: name.trim(),
        email: email.trim().toLowerCase(),
        password,
        role,
        send_welcome_email: sendWelcome,
      });
      toast.success(sendWelcome
        ? `Created ${data.email} — welcome email sent`
        : `Created ${data.email}`);
      onCreated();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to create user");
    } finally { setBusy(false); }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.6)" }}
      onClick={onClose}
      data-testid="create-user-dialog"
    >
      <form
        onSubmit={submit}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md border rounded-2xl p-6"
        style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}
      >
        <div className="flex items-center justify-between mb-5">
          <h3 className="serif text-2xl">Create user</h3>
          <button type="button" onClick={onClose} className="text-sm opacity-60 hover:opacity-100" data-testid="create-user-close">
            <X className="w-5 h-5" />
          </button>
        </div>

        <label className="block text-xs uppercase tracking-widest mb-1.5" style={{ color: "var(--text-dim)" }}>Name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} className="w-full mb-4" required data-testid="create-user-name" />

        <label className="block text-xs uppercase tracking-widest mb-1.5" style={{ color: "var(--text-dim)" }}>Email</label>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="w-full mb-4" required data-testid="create-user-email" />

        <label className="block text-xs uppercase tracking-widest mb-1.5" style={{ color: "var(--text-dim)" }}>Password</label>
        <div className="flex gap-2 mb-4">
          <input value={password} onChange={(e) => setPassword(e.target.value)} className="flex-1" required minLength={6} data-testid="create-user-password" />
          <button type="button" onClick={generatePassword} className="btn-ghost !py-2 !px-3 text-xs inline-flex items-center gap-1" data-testid="create-user-gen-pwd">
            <RefreshCw className="w-3 h-3" /> Generate
          </button>
        </div>

        <label className="block text-xs uppercase tracking-widest mb-1.5" style={{ color: "var(--text-dim)" }}>Role</label>
        <select value={role} onChange={(e) => setRole(e.target.value)} className="w-full mb-4" data-testid="create-user-role">
          <option value="attendee">Attendee</option>
          <option value="organizer">Organizer</option>
          <option value="admin">Admin</option>
        </select>

        <label className="flex items-center gap-2 mb-5 text-sm cursor-pointer" data-testid="create-user-welcome-toggle">
          <input type="checkbox" checked={sendWelcome} onChange={(e) => setSendWelcome(e.target.checked)} />
          Email login credentials to the user
        </label>

        <div className="flex gap-2 justify-end">
          <button type="button" onClick={onClose} className="btn-ghost !py-2 !px-4 text-sm" data-testid="create-user-cancel">Cancel</button>
          <button type="submit" disabled={busy} className="btn-primary !py-2 !px-4 text-sm" data-testid="create-user-submit">
            {busy ? "Creating…" : "Create user"}
          </button>
        </div>
      </form>
    </div>
  );
}


function UsersTab({ currentUser }) {
  const [users, setUsers] = useState([]);
  const [stats, setStats] = useState(null);
  const [q, setQ] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // user_id being role-edited
  const [viewingUserId, setViewingUserId] = useState(null); // drawer drill-down
  const [showCreate, setShowCreate] = useState(false);

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

  useEffect(() => { load();   }, [roleFilter, statusFilter]);

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
        <button
          onClick={() => setShowCreate(true)}
          className="btn-primary !py-2 !px-4 text-sm inline-flex items-center gap-1.5"
          data-testid="admin-create-user-btn"
        >
          <UserPlus className="w-4 h-4" /> Create user
        </button>
      </div>

      {showCreate && (
        <CreateUserDialog
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); load(); }}
        />
      )}

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
              <th className="text-left p-4 hidden lg:table-cell">Stripe</th>
              <th className="text-left p-4">Status</th>
              <th className="text-right p-4">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan="9" className="p-10 text-center" style={{ color: "var(--text-dim)" }}>Loading users...</td></tr>
            ) : users.length === 0 ? (
              <tr><td colSpan="9" className="p-10 text-center" style={{ color: "var(--text-dim)" }}>No users match these filters.</td></tr>
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
                <td className="p-4 hidden lg:table-cell">
                  <StripePill user={u} />
                </td>
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

function StripePill({ user }) {
  const hasAccount = !!user.stripe_account_id;
  if (!hasAccount) {
    if (user.role !== "organizer" && user.role !== "admin") {
      return <span className="text-xs" style={{ color: "var(--text-dim)" }}>—</span>;
    }
    return (
      <span
        className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase tracking-widest font-medium"
        style={{ background: "var(--bg-elev)", color: "var(--text-dim)" }}
        title="Organizer hasn't started Stripe onboarding yet"
        data-testid={`stripe-pill-none-${user.user_id}`}
      >
        Not connected
      </span>
    );
  }
  const verified = user.stripe_charges_enabled && user.stripe_payouts_enabled;
  if (verified) {
    return (
      <span
        className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase tracking-widest font-medium"
        style={{ background: "rgba(46,160,67,0.14)", color: "rgb(46,160,67)" }}
        title={`Account ${user.stripe_account_id}`}
        data-testid={`stripe-pill-verified-${user.user_id}`}
      >
        Verified
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase tracking-widest font-medium"
      style={{ background: "rgba(240,138,42,0.14)", color: "var(--accent)" }}
      title={`Account ${user.stripe_account_id} — onboarding not complete`}
      data-testid={`stripe-pill-pending-${user.user_id}`}
    >
      Pending
    </span>
  );
}

function Stat({ label, value, icon, accent }) {  return (
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

  useEffect(() => { load();   }, [template, status]);

  return (
    <div data-testid="admin-emails-tab">
      <div className="grid sm:grid-cols-3 gap-3 mb-6">
        <Stat label="Sent" value={data.stats.sent} icon={<CheckCircle2 className="w-4 h-4" />} accent="var(--success)" />
        <Stat label="Failed" value={data.stats.failed} icon={<AlertTriangle className="w-4 h-4" />} accent="var(--danger)" />
        <Stat label="Skipped" value={data.stats.skipped} icon={<MinusCircle className="w-4 h-4" />} />
      </div>

      <OrganizerWelcomeBackfill />

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
// Welcome-email backfill — one-shot re-engagement of legacy organizers
// ============================================================================
function OrganizerWelcomeBackfill() {
  const [eligible, setEligible] = useState(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);

  const dryRun = async () => {
    setLoading(true);
    try {
      const { data } = await api.post("/admin/organizers/backfill-welcome-emails", { dry_run: true });
      setEligible(data.eligible || 0);
      setResult(null);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't preview");
    } finally { setLoading(false); }
  };

  const send = async () => {
    if (eligible == null) {
      toast.error("Run a preview first");
      return;
    }
    if (eligible === 0) {
      toast.message("Nothing to send — every organizer already received the welcome email.");
      return;
    }
    if (!window.confirm(
      `Send the welcome email to ${eligible} organizer${eligible === 1 ? "" : "s"} who have never received it?\n\nThis is idempotent — re-runs will skip anyone already stamped.`
    )) return;
    setRunning(true);
    try {
      const { data } = await api.post("/admin/organizers/backfill-welcome-emails", { dry_run: false });
      setResult(data);
      // Refresh preview so the badge updates immediately.
      await dryRun();
      toast.success(`Sent ${data.sent} welcome email${data.sent === 1 ? "" : "s"}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Send failed");
    } finally { setRunning(false); }
  };

  return (
    <div
      className="border rounded-2xl p-5 mb-6"
      style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
      data-testid="organizer-welcome-backfill"
    >
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex-1 min-w-[240px]">
          <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--accent)" }}>
            One-shot — backfill
          </div>
          <h3 className="serif text-xl mb-1">Welcome email for legacy organizers</h3>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            Sends the 3-step welcome (create event · connect Stripe · set refund policy) to every
            organizer who joined before the email funnel existed. Idempotent — each user is
            stamped on send and skipped on re-runs.
          </p>
          {eligible !== null && (
            <div
              className="mt-3 inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm"
              style={{ background: "var(--accent-soft)", color: "var(--accent)" }}
              data-testid="welcome-backfill-eligible"
            >
              <strong>{eligible.toLocaleString()}</strong>
              {eligible === 1 ? "organizer eligible" : "organizers eligible"}
            </div>
          )}
          {result && (
            <div className="mt-3 text-xs" style={{ color: "var(--text-muted)" }} data-testid="welcome-backfill-result">
              Last run: sent <strong style={{ color: "var(--success)" }}>{result.sent}</strong>
              {result.errors?.length ? <> · <span style={{ color: "var(--danger)" }}>{result.errors.length} failed</span></> : null}
              {result.remaining ? <> · {result.remaining} remaining</> : null}
            </div>
          )}
        </div>
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={dryRun}
            disabled={loading || running}
            className="btn-ghost"
            data-testid="welcome-backfill-preview-btn"
          >
            {loading ? "Counting…" : "Preview count"}
          </button>
          <button
            onClick={send}
            disabled={running || loading || eligible == null || eligible === 0}
            className="btn-primary"
            data-testid="welcome-backfill-send-btn"
          >
            {running ? "Sending…" : eligible == null ? "Send welcome emails" : `Send to ${eligible.toLocaleString()}`}
          </button>
        </div>
      </div>
    </div>
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

  useEffect(() => { load();   }, [status]);

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
  const [autoPayout, setAutoPayout] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get("/admin/platform-settings");
      setSettings(data);
      setPercent(String(data.commission_percent));
      setFlat(String(data.commission_flat_fee_per_ticket));
      setAutoPayout(Boolean(data.marketing_partners_auto_payout));
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
        marketing_partners_auto_payout: autoPayout,
      });
      setSettings(data);
      // Bust the in-memory fee-settings cache so listing pages re-fetch the
      // new rate within the next render instead of showing stale fees for
      // up to a minute (or until a hard refresh).
      invalidateFeeSettingsCache();
      toast.success("Settings saved — new rate is live on all listing pages now");
    } catch (e) {
      toast.error(e?.response?.data?.detail?.[0]?.msg || "Save failed");
    } finally { setSaving(false); }
  };

  if (!settings) return <div className="p-10 text-center" style={{ color: "var(--text-dim)" }}>Loading…</div>;

  return (
    <div data-testid="admin-settings-tab" className="max-w-2xl space-y-6">
      <SiteContentPanel />

      <EditorPickPanel />

      <SupportChatSettingsPanel />

      <StripeReconcilePanel />

      <EmailDiagnosticsPanel />

      <BlastPanel />

      <DemoDataPanel />

      <div className="border rounded-2xl p-8" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
        <h2 className="serif text-2xl mb-1">Commission & fees</h2>
        <p className="text-sm mb-7" style={{ color: "var(--text-muted)" }}>
          Drives both checkout (buyer-pays-fees) and payouts. Changes take effect on the next booking — past bookings keep their snapshotted values.
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
              Processing fee per ticket (NZD)
            </label>
            <input
              type="number" min="0" max="20" step="0.01"
              value={flat} onChange={(e) => setFlat(e.target.value)}
              className="w-full" data-testid="commission-flat-input"
            />
          </div>
          <div className="pt-3 border-t" style={{ borderColor: "var(--border)" }}>
            <div className="text-xs uppercase tracking-widest mb-3" style={{ color: "var(--text-dim)" }}>Preview · NZ$1,000 gross / 50 tickets</div>
            <div className="space-y-1 text-sm">
              <Row label="Gross" value="NZ$1,000.00" />
              <Row label={`Commission (${percent}%)`} value={`− NZ$${(1000 * parseFloat(percent || 0) / 100).toFixed(2)}`} accent="var(--danger)" />
              <Row label={`Processing (50 × NZ$${flat})`} value={`− NZ$${(50 * parseFloat(flat || 0)).toFixed(2)}`} accent="var(--danger)" />
              <Row label="Net to organizer" value={`NZ$${(1000 - (1000 * parseFloat(percent || 0) / 100) - (50 * parseFloat(flat || 0))).toFixed(2)}`} accent="var(--success)" bold />
            </div>
          </div>

          {/* Buyer-side preview at 3 representative price points — uses the SAME math
              as the live `lib/fees.js::estimateBuyerFees` so admin sees the exact
              numbers buyers will see on listing pages before clicking Save. */}
          <BuyerPricePreview percent={percent} flat={flat} />
          <div className="pt-3 border-t" style={{ borderColor: "var(--border)" }}>
            <label className="flex items-start gap-3 cursor-pointer" data-testid="auto-payout-toggle">
              <input
                type="checkbox"
                checked={autoPayout}
                onChange={(e) => setAutoPayout(e.target.checked)}
                className="mt-1"
              />
              <span>
                <span className="block text-sm" style={{ color: "var(--text)" }}>Auto-batch marketing partner payouts on the 5th of each month</span>
                <span className="block text-xs mt-1" style={{ color: "var(--text-muted)" }}>
                  Statements go out on the 1st, then partners have 4 days to flag issues. On the 5th the scheduler marks all unpaid earnings as <code>paid</code> in batch <code>pbat_auto_YYYYMM</code>. You still need to wire the actual money transfer outside the platform.
                </span>
              </span>
            </label>
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


// Buyer-side fee preview shown below the rate inputs. Uses the SAME formula
// as `lib/fees.js::estimateBuyerFees` so admin sees the exact numbers a buyer
// would see on a listing for `face_value` tickets before saving any change.
//
// Reads `percent` + `flat` as STRINGS from the form inputs (so live as you
// type), and uses the hard-coded Stripe 2.7% + $0.30 (those aren't admin
// configurable — they're contractual with Stripe NZ).
function BuyerPricePreview({ percent, flat }) {
  const pPct = (parseFloat(percent) || 0) / 100;
  const pFlat = parseFloat(flat) || 0;
  const sPct = 0.027;
  const sFlat = 0.30;
  const SAMPLE_PRICES = [25, 50, 100];

  const rows = SAMPLE_PRICES.map((face) => {
    const platform = face * pPct + pFlat;
    const total = (face + platform + sFlat) / (1 - sPct);
    const fees = total - face;
    const stripeFee = total - face - platform;
    return {
      face,
      fees: round2(fees),
      total: round2(total),
      platformCut: round2(platform),
      stripeFee: round2(stripeFee),
      // Organizer net = what the organizer keeps = face value (exclusive mode)
      organizerNet: round2(face),
    };
  });

  return (
    <div
      className="pt-3 border-t"
      style={{ borderColor: "var(--border)" }}
      data-testid="buyer-price-preview"
    >
      <div className="text-xs uppercase tracking-widest mb-3" style={{ color: "var(--text-dim)" }}>
        Preview · what BUYERS will see
      </div>
      <div className="rounded-lg border overflow-hidden" style={{ borderColor: "var(--border)" }}>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs uppercase tracking-wider" style={{ background: "var(--bg-soft, rgba(0,0,0,0.03))", color: "var(--text-dim)" }}>
              <th className="text-left p-2.5 font-medium">Ticket price</th>
              <th className="text-right p-2.5 font-medium">+ Fees</th>
              <th className="text-right p-2.5 font-medium">Buyer pays</th>
              <th className="text-right p-2.5 font-medium" title="Your platform commission (net of Stripe processing)">Your cut</th>
              <th className="text-right p-2.5 font-medium" title="Organizer's net (= face value in exclusive mode)">Organizer</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr
                key={r.face}
                style={{ borderTop: i ? "1px solid var(--border)" : "none" }}
                data-testid={`buyer-preview-row-${r.face}`}
              >
                <td className="p-2.5 tabular-nums">NZ${r.face.toFixed(2)}</td>
                <td className="p-2.5 text-right tabular-nums" style={{ color: "var(--text-muted)" }}>+ NZ${r.fees.toFixed(2)}</td>
                <td className="p-2.5 text-right tabular-nums font-medium" style={{ color: "var(--text)" }}>NZ${r.total.toFixed(2)}</td>
                <td className="p-2.5 text-right tabular-nums" style={{ color: "var(--accent)" }}>NZ${r.platformCut.toFixed(2)}</td>
                <td className="p-2.5 text-right tabular-nums" style={{ color: "var(--success)" }}>NZ${r.organizerNet.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="text-[11px] mt-2 leading-relaxed" style={{ color: "var(--text-dim)" }}>
        Includes Stripe 2.7% + NZ$0.30 (your contractual processing rate) — buyer sees
        the &ldquo;+ Fees&rdquo; line on listings; your cut shows in <a href="/admin/revenue" className="underline">/admin/revenue</a> after each booking.
      </div>
    </div>
  );
}

function round2(n) { return Math.round(n * 100) / 100; }


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
  // `picks` is now an array — [{event_id, blurb}, ...]
  const [picks, setPicks] = useState([]);
  const [badge, setBadge] = useState("Editor's Pick");

  useEffect(() => {
    (async () => {
      try {
        const [settings, list] = await Promise.all([
          api.get("/site-settings"),
          api.get("/admin/events"),
        ]);
        const ep = settings.data?.editor_pick || {};
        // Hydrate the array: prefer the new `picks` list, fall back to the
        // legacy singular `event_id` so old admins don't lose their pick.
        const rawPicks = Array.isArray(ep.picks) ? ep.picks.filter(p => p?.event_id) : [];
        if (rawPicks.length === 0 && ep.event_id) {
          rawPicks.push({ event_id: ep.event_id, blurb: ep.blurb || "" });
        }
        setPicks(rawPicks.map(p => ({ event_id: p.event_id, blurb: p.blurb || "" })));
        setBadge(ep.badge_text || "Editor's Pick");
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
      const clean = picks.filter(p => p.event_id);
      const { data } = await api.patch("/admin/site-settings", {
        editor_pick: {
          // Clear the legacy single field so it never overrides `picks` again.
          event_id: null,
          blurb: "",
          badge_text: (badge || "").trim() || "Editor's Pick",
          picks: clean,
        },
      });
      const ep = data.editor_pick || {};
      const newPicks = Array.isArray(ep.picks) ? ep.picks : [];
      setPicks(newPicks.map(p => ({ event_id: p.event_id, blurb: p.blurb || "" })));
      setBadge(ep.badge_text || "Editor's Pick");
      toast.success(clean.length === 0
        ? "All Editor's Picks cleared — landing page reverts to the first featured event"
        : `Saved ${clean.length} Editor's Pick${clean.length === 1 ? "" : "s"} — visible on the landing page`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save Editor's Picks");
    } finally { setSaving(false); }
  };

  const addPick = () => setPicks(prev => [...prev, { event_id: "", blurb: "" }]);
  const removePick = (i) => setPicks(prev => prev.filter((_, idx) => idx !== i));
  const updatePick = (i, patch) => setPicks(prev => prev.map((p, idx) => idx === i ? { ...p, ...patch } : p));
  const movePick = (i, dir) => {
    const j = i + dir;
    if (j < 0 || j >= picks.length) return;
    const next = [...picks];
    [next[i], next[j]] = [next[j], next[i]];
    setPicks(next);
  };

  if (loading) return null;

  // Events already selected — don't show them in subsequent dropdowns to avoid dupes.
  const taken = new Set(picks.map(p => p.event_id).filter(Boolean));

  return (
    <div
      className="border rounded-2xl p-8"
      style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
      data-testid="editor-pick-panel"
    >
      <h2 className="serif text-2xl mb-1 flex items-center gap-2">
        <Sparkles className="w-5 h-5" style={{ color: "var(--accent)" }} /> Editor&apos;s Picks
      </h2>
      <p className="text-sm mb-6" style={{ color: "var(--text-muted)" }}>
        Pin one or more curated events to the landing-page hero spotlight. When multiple picks are set the landing page auto-rotates between them.
      </p>

      <div className="space-y-3 mb-5">
        {picks.length === 0 && (
          <div className="text-sm py-4 px-3 rounded-lg" style={{ background: "var(--bg-elev)", color: "var(--text-muted)" }} data-testid="editor-pick-empty">
            No picks yet — the landing-page hero will show the first featured event. Click &quot;Add pick&quot; below to spotlight specific events.
          </div>
        )}
        {picks.map((pick, i) => {
          const picked = events.find(e => e.event_id === pick.event_id);
          return (
            <div
              key={i}
              className="border rounded-xl p-4 space-y-3"
              style={{ borderColor: "var(--border)", background: "var(--bg-elev)" }}
              data-testid={`editor-pick-row-${i}`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="text-xs uppercase tracking-widest" style={{ color: "var(--accent)" }}>Pick #{i + 1}</div>
                <div className="flex items-center gap-1">
                  <button type="button" onClick={() => movePick(i, -1)} disabled={i === 0} className="btn-ghost !p-1 text-xs disabled:opacity-30" data-testid={`pick-up-${i}`} title="Move up">↑</button>
                  <button type="button" onClick={() => movePick(i, 1)} disabled={i === picks.length - 1} className="btn-ghost !p-1 text-xs disabled:opacity-30" data-testid={`pick-down-${i}`} title="Move down">↓</button>
                  <button type="button" onClick={() => removePick(i)} className="btn-ghost !p-1 text-xs" data-testid={`pick-remove-${i}`} title="Remove">✕</button>
                </div>
              </div>

              <select
                value={pick.event_id}
                onChange={(e) => updatePick(i, { event_id: e.target.value })}
                className="w-full"
                data-testid={`editor-pick-select-${i}`}
              >
                <option value="">— Choose an event —</option>
                {events
                  .filter(e => e.event_id === pick.event_id || !taken.has(e.event_id))
                  .map((e) => (
                    <option key={e.event_id} value={e.event_id}>
                      {e.title} · {e.venue}, {e.city}
                    </option>
                  ))}
              </select>

              <textarea
                value={pick.blurb}
                onChange={(e) => updatePick(i, { blurb: e.target.value })}
                rows={2}
                maxLength={220}
                placeholder="Optional curator blurb — appears under the event title on the hero."
                className="w-full"
                data-testid={`editor-pick-blurb-${i}`}
              />

              {picked && (
                <div
                  className="p-3 rounded-lg border flex gap-3 items-center"
                  style={{ borderColor: "var(--accent)", background: "rgba(240,138,42,0.06)" }}
                  data-testid={`editor-pick-preview-${i}`}
                >
                  {picked.image_url && (
                    <img src={picked.image_url} alt="" className="w-12 h-12 rounded-lg object-cover flex-shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="text-[10px] uppercase tracking-widest" style={{ color: "var(--accent)" }}>{badge || "Editor's Pick"}</div>
                    <div className="font-medium truncate text-sm">{picked.title}</div>
                    <div className="text-xs" style={{ color: "var(--text-dim)" }}>{picked.venue} · {picked.city}</div>
                  </div>
                </div>
              )}
            </div>
          );
        })}

        <button
          type="button"
          onClick={addPick}
          className="btn-ghost text-sm w-full justify-center"
          data-testid="editor-pick-add"
        >
          + Add another pick
        </button>
      </div>

      <label className="block mb-4">
        <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>Badge text (shared across all picks)</div>
        <input
          value={badge}
          onChange={(e) => setBadge(e.target.value)}
          maxLength={32}
          placeholder="Editor's Pick"
          className="w-full"
          data-testid="editor-pick-badge"
        />
        <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>
          Override to e.g. &quot;Trending now&quot;, &quot;Don&apos;t miss&quot;, &quot;Hand-picked&quot;. Defaults to &quot;Editor&apos;s Pick&quot;.
        </div>
      </label>

      <div className="flex justify-end gap-2 pt-2">
        <button type="button" onClick={save} disabled={saving} className="btn-primary" data-testid="editor-pick-save">
          {saving ? "Saving…" : `Save ${picks.length || ""} pick${picks.length === 1 ? "" : "s"}`.replace(/\s+/g, " ")}
        </button>
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
        Send a custom email to a filtered audience. Use sparingly — it&apos;s logged.
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
        Verify the production Resend config, send yourself a diagnostic email, and resend booking confirmations to customers whose tickets didn&apos;t arrive.
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
            Paste a customer&apos;s email to find all their tickets, or a booking ID for a single one.
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
        Re-pull every pending checkout session from Stripe and finalise any that have actually been paid — issues the e-ticket, sends the confirmation email, and frees the seat hold. Use this when the live webhook hasn&apos;t been configured yet, or any time a customer&apos;s payment succeeded but their ticket didn&apos;t arrive.
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
          When Stripe shows the charge as Succeeded but the reconcile job can&apos;t query it cleanly, paste the booking ID here to manually issue the ticket. <strong style={{ color: "var(--danger)" }}>Verify the charge succeeded in your Stripe dashboard first.</strong>
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
        etc.) and the demo organizer/attendee accounts. Real events you&apos;ve created
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


// ============================================================================
// SUPPORT CHAT TAB — admin sees every live-chat thread + can reply inline.
// Polls every 8s while open so it feels real-time without a websocket.
// ============================================================================
function SupportChatTab() {
  const [sessions, setSessions] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [visitorTyping, setVisitorTyping] = useState(false);
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const [canned, setCanned] = useState([]);
  const listRef = useRef(null);
  const typingPingRef = useRef(0);

  // Fetch admin-configurable canned replies from site_settings. Defaults
  // baked into the backend if the admin hasn't customised them yet.
  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/site-settings");
        const list = data?.support_chat?.canned_replies;
        if (Array.isArray(list) && list.length > 0) setCanned(list);
      } catch { /* ignore */ }
    })();
  }, []);

  const reloadSessions = async () => {
    try {
      const { data } = await api.get("/admin/support/sessions");
      setSessions(Array.isArray(data) ? data : []);
    } catch { /* ignore */ }
  };

  const reloadThread = async (sid) => {
    if (!sid) return;
    try {
      const { data } = await api.get(`/admin/support/sessions/${sid}`);
      setMsgs(data.messages || []);
      setVisitorTyping(!!data.session?.visitor_is_typing);
    } catch { /* ignore */ }
  };

  useEffect(() => {
    reloadSessions();
    const id = setInterval(reloadSessions, 8000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!activeId) return undefined;
    reloadThread(activeId);
    // Poll every 4s instead of 8s for snappier typing-indicator response.
    const id = setInterval(() => reloadThread(activeId), 4000);
    return () => clearInterval(id);
  }, [activeId]);

  // Throttled "admin is typing" ping — fires at most every 2s while typing.
  const pingTyping = () => {
    if (!activeId) return;
    const now = Date.now();
    if (now - typingPingRef.current < 2000) return;
    typingPingRef.current = now;
    api.post("/admin/support/typing", { session_id: activeId }).catch(() => { /* silent */ });
  };

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [msgs]);

  const send = async (e) => {
    e?.preventDefault();
    const body = reply.trim();
    if (!body || !activeId) return;
    setBusy(true);
    setReply("");
    try {
      await api.post("/admin/support/reply", { session_id: activeId, text: body });
      reloadThread(activeId);
      reloadSessions();
    } catch { toast.error("Couldn't send"); }
    finally { setBusy(false); }
  };

  const close = async () => {
    if (!activeId) return;
    if (!window.confirm("Close this conversation? The visitor can still reply to reopen it.")) return;
    await api.post(`/admin/support/${activeId}/close`);
    toast.success("Chat closed");
    setActiveId(null);
    reloadSessions();
  };

  return (
    <div className="grid lg:grid-cols-[320px_1fr] gap-4 min-h-[600px]" data-testid="support-chat-tab">
      {/* Sessions list */}
      <aside
        className="rounded-2xl border overflow-y-auto"
        style={{ borderColor: "var(--border)", background: "var(--bg-card)", maxHeight: 700 }}
        data-testid="support-sessions-list"
      >
        <div className="p-3 border-b font-medium text-sm" style={{ borderColor: "var(--border)" }}>
          Conversations ({sessions.length})
        </div>
        {sessions.length === 0 ? (
          <div className="p-4 text-sm" style={{ color: "var(--text-muted)" }}>
            No chats yet. When visitors open the chat widget on the website, they appear here.
          </div>
        ) : sessions.map((s) => (
          <button
            key={s.session_id}
            onClick={() => setActiveId(s.session_id)}
            className="block w-full text-left px-3 py-3 border-b hover:bg-[color:var(--bg-elev)]"
            style={{
              borderColor: "var(--border)",
              background: activeId === s.session_id ? "var(--bg-elev)" : "transparent",
            }}
            data-testid={`support-session-${s.session_id}`}
          >
            <div className="flex items-center justify-between gap-2 mb-0.5">
              <div className="font-medium text-sm truncate">{s.visitor_name || "Anonymous"}</div>
              {s.unread_admin_count > 0 && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: "var(--accent)", color: "#0F2A3A" }}>
                  {s.unread_admin_count}
                </span>
              )}
            </div>
            <div className="text-xs truncate mb-0.5" style={{ color: "var(--text-muted)" }}>
              {s.last_message_sender === "admin" ? "You: " : ""}{s.last_message_preview || "(empty)"}
            </div>
            <div className="text-[10px]" style={{ color: "var(--text-dim)" }}>
              {s.visitor_email || "no email"} · {s.last_msg_at ? new Date(s.last_msg_at).toLocaleString() : ""}
            </div>
          </button>
        ))}
      </aside>

      {/* Thread */}
      <div
        className="rounded-2xl border flex flex-col"
        style={{ borderColor: "var(--border)", background: "var(--bg-card)", minHeight: 600 }}
      >
        {!activeId ? (
          <div className="flex-1 grid place-items-center text-center p-8" style={{ color: "var(--text-muted)" }}>
            <div>
              <MessageCircle size={32} className="mx-auto mb-3 opacity-50" />
              Select a conversation to reply.
            </div>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: "var(--border)" }}>
              <div>
                <div className="font-medium text-sm flex items-center gap-2">
                  {sessions.find(s => s.session_id === activeId)?.visitor_name || "Anonymous"}
                  {(() => {
                    const rating = sessions.find(s => s.session_id === activeId)?.rating;
                    if (!rating?.stars) return null;
                    return (
                      <span className="inline-flex items-center gap-0.5 text-xs px-2 py-0.5 rounded-full" style={{ background: "rgba(240,138,42,0.15)", color: "var(--accent)" }} data-testid="session-rating">
                        ⭐ {rating.stars}/5
                      </span>
                    );
                  })()}
                </div>
                <div className="text-xs" style={{ color: "var(--text-dim)" }}>
                  {sessions.find(s => s.session_id === activeId)?.visitor_email || "no email"}
                </div>
              </div>
              <button onClick={close} className="text-xs px-3 py-1.5 rounded border hover:opacity-80" style={{ borderColor: "var(--border)" }} data-testid="support-close-chat">
                Close chat
              </button>
              <a
                href={`${process.env.REACT_APP_BACKEND_URL}/api/admin/support/sessions/${activeId}/export.csv`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs px-3 py-1.5 rounded border hover:opacity-80 ml-2"
                style={{ borderColor: "var(--border)" }}
                data-testid="support-export-csv"
              >
                ⇣ CSV
              </a>
            </div>
            <div ref={listRef} className="flex-1 overflow-y-auto p-4 space-y-2" style={{ background: "var(--bg-elev)" }}>
              {msgs.map((m) => {
                if (m.sender === "system") {
                  return (
                    <div key={m.message_id} className="text-center text-xs italic py-1" style={{ color: "var(--text-muted)" }}>
                      {m.text}
                    </div>
                  );
                }
                return (
                  <div key={m.message_id} className={`group flex ${m.sender === "admin" ? "justify-end" : ""}`}>
                    <div className="flex flex-col" style={{ maxWidth: "70%" }}>
                      <div
                        className="px-3 py-2 text-sm leading-snug"
                        style={{
                          background: m.sender === "admin" ? "var(--accent)" : "var(--bg-card)",
                          color: m.sender === "admin" ? "#0F2A3A" : "var(--text)",
                          border: m.sender === "visitor" ? "1px solid var(--border)" : "none",
                          borderRadius: m.sender === "admin" ? "14px 14px 4px 14px" : "14px 14px 14px 4px",
                        }}
                      >
                        {m.attachment && <AdminAttachment att={m.attachment} />}
                        <AdminMessageText
                          text={m.text}
                          translatedText={m.translated_text}
                          originalLang={m.original_lang}
                        />
                        <div className="text-[10px] mt-1 opacity-60">{new Date(m.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</div>
                      </div>
                      <div className={`mt-1 ${m.sender === "admin" ? "self-end" : "self-start"}`}>
                        <MessageReactions
                          message={m}
                          align={m.sender === "admin" ? "right" : "left"}
                          onReact={(reactions) => setMsgs(prev => prev.map(p => p.message_id === m.message_id ? { ...p, reactions } : p))}
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
              {visitorTyping && (
                <div
                  className="max-w-[70%] px-3 py-2 text-sm italic"
                  style={{
                    background: "var(--bg-card)",
                    color: "var(--text-muted)",
                    border: "1px solid var(--border)",
                    borderRadius: "14px 14px 14px 4px",
                  }}
                  data-testid="visitor-typing-indicator"
                >
                  Visitor is typing<span className="dots-pulse">…</span>
                </div>
              )}
            </div>

            {/* Canned-replies strip */}
            <div className="px-3 py-2 border-t flex gap-1.5 overflow-x-auto" style={{ borderColor: "var(--border)" }} data-testid="canned-replies">
              {canned.map((c, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setReply(c)}
                  className="text-xs px-2.5 py-1 rounded-full border whitespace-nowrap hover:opacity-80 flex-shrink-0"
                  style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}
                  data-testid={`canned-${i}`}
                  title="Click to insert into the reply box"
                >
                  {c.length > 32 ? c.slice(0, 30) + "…" : c}
                </button>
              ))}
              {canned.length === 0 && (
                <span className="text-xs italic flex-shrink-0" style={{ color: "var(--text-dim)" }}>
                  No canned replies set — add some in Settings tab.
                </span>
              )}
            </div>

            <form onSubmit={send} className="flex items-center gap-2 p-3 border-t" style={{ borderColor: "var(--border)" }}>
              <button
                type="button"
                onClick={async () => {
                  try {
                    setBusy(true);
                    const { data } = await api.post("/admin/support/suggest", { session_id: activeId });
                    setReply(data.suggestion || "");
                  } catch (err) {
                    toast.error(err?.response?.data?.detail || "AI suggest failed");
                  } finally { setBusy(false); }
                }}
                disabled={busy}
                className="text-xs px-2 py-1.5 rounded-full border whitespace-nowrap"
                style={{ borderColor: "var(--accent)", color: "var(--accent)" }}
                data-testid="ai-suggest-btn"
                title="Generate a reply with AI"
              >
                ✨ AI
              </button>
              <input
                value={reply}
                onChange={(e) => { setReply(e.target.value); pingTyping(); }}
                placeholder="Type your reply…"
                className="flex-1 px-3 py-2 rounded-full border bg-transparent text-sm"
                style={{ borderColor: "var(--border)" }}
                data-testid="support-reply-input"
                autoFocus
              />
              <button
                type="submit"
                disabled={!reply.trim() || busy}
                data-testid="support-reply-send"
                className="rounded-full p-2 disabled:opacity-40"
                style={{ background: "var(--accent)", color: "#0F2A3A" }}
                aria-label="Send"
              >
                <Send size={16} />
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}




// ============================================================================
// SUPPORT-CHAT SETTINGS PANEL — admin manages canned replies + Slack webhook.
// Each canned reply gets a remove button; new ones add at the bottom.
// ============================================================================
function SupportChatSettingsPanel() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [canned, setCanned] = useState([]);
  const [slackUrl, setSlackUrl] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/site-settings");
        const sc = data?.support_chat || {};
        setCanned(Array.isArray(sc.canned_replies) ? sc.canned_replies : []);
        setSlackUrl(sc.slack_webhook_url || "");
      } catch { /* ignore */ } finally { setLoading(false); }
    })();
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const clean = canned.map(s => (s || "").trim()).filter(Boolean);
      await api.patch("/admin/site-settings", {
        support_chat: {
          canned_replies: clean,
          slack_webhook_url: slackUrl.trim(),
        },
      });
      setCanned(clean);
      toast.success("Support-chat settings saved");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't save");
    } finally { setSaving(false); }
  };

  const addRow = () => setCanned(prev => [...prev, ""]);
  const removeRow = (i) => setCanned(prev => prev.filter((_, idx) => idx !== i));
  const update = (i, v) => setCanned(prev => prev.map((s, idx) => idx === i ? v : s));

  if (loading) return null;

  return (
    <div
      className="border rounded-2xl p-8"
      style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
      data-testid="support-chat-settings-panel"
    >
      <h2 className="serif text-2xl mb-1 flex items-center gap-2">
        <MessageCircle className="w-5 h-5" style={{ color: "var(--accent)" }} /> Live chat settings
      </h2>
      <p className="text-sm mb-6" style={{ color: "var(--text-muted)" }}>
        Edit the canned-reply templates that appear above the reply box, and (optionally) wire up a Slack channel for instant notifications.
      </p>

      {/* Canned replies */}
      <div className="mb-6">
        <div className="text-xs uppercase tracking-widest mb-3" style={{ color: "var(--text-dim)" }}>
          Canned replies ({canned.length}/30)
        </div>
        <div className="space-y-2">
          {canned.map((reply, i) => (
            <div key={i} className="flex gap-2 items-center" data-testid={`canned-row-${i}`}>
              <input
                value={reply}
                onChange={(e) => update(i, e.target.value)}
                maxLength={220}
                className="flex-1"
                placeholder="e.g. Hi! What's your booking ID?"
                data-testid={`canned-input-${i}`}
              />
              <button
                type="button"
                onClick={() => removeRow(i)}
                className="btn-ghost !p-2 text-xs"
                data-testid={`canned-remove-${i}`}
                aria-label="Remove reply"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          ))}
          {canned.length === 0 && (
            <div className="text-sm py-3 px-3 rounded-lg" style={{ background: "var(--bg-elev)", color: "var(--text-muted)" }}>
              No canned replies yet. Add a few to speed up your responses.
            </div>
          )}
          <button
            type="button"
            onClick={addRow}
            disabled={canned.length >= 30}
            className="btn-ghost text-sm w-full justify-center disabled:opacity-50"
            data-testid="canned-add"
          >
            + Add reply template
          </button>
        </div>
      </div>

      {/* Slack webhook */}
      <div className="mb-6">
        <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>
          Slack webhook URL <span className="opacity-60">(optional)</span>
        </div>
        <input
          value={slackUrl}
          onChange={(e) => setSlackUrl(e.target.value)}
          placeholder="https://hooks.slack.com/services/T.../B.../..."
          className="w-full font-mono text-xs"
          data-testid="slack-webhook-input"
        />
        <div className="text-xs mt-2 leading-relaxed" style={{ color: "var(--text-dim)" }}>
          When set, new visitor messages also post to this Slack channel (in addition to admin email).
          <br />
          Create one at <a href="https://api.slack.com/messaging/webhooks" target="_blank" rel="noreferrer" style={{ color: "var(--accent)" }}>Slack → Incoming Webhooks</a> → choose your channel → copy the URL.
        </div>
      </div>

      <div className="flex justify-end gap-2">
        <button type="button" onClick={save} disabled={saving} className="btn-primary" data-testid="support-chat-settings-save">
          {saving ? "Saving…" : "Save settings"}
        </button>
      </div>
    </div>
  );
}


/**
 * AdminMessageText — renders the message text with a "Show original" toggle
 * when auto-translate detected a non-English source. Default view shows the
 * English translation so the admin can respond fast.
 */
function AdminMessageText({ text, translatedText, originalLang }) {
  const [showOriginal, setShowOriginal] = useState(false);
  if (!translatedText) {
    // No translation available — render the original as-is.
    return <span>{text}</span>;
  }
  return (
    <span data-testid="admin-msg-with-translation">
      {showOriginal ? text : translatedText}
      <button
        type="button"
        onClick={() => setShowOriginal((v) => !v)}
        className="block text-[10px] mt-1 italic underline opacity-70 hover:opacity-100"
        data-testid="translation-toggle"
      >
        {showOriginal ? `Show translation` : `Show original${originalLang ? ` (${originalLang.toUpperCase()})` : ""}`}
      </button>
    </span>
  );
}


/**
 * AdminAttachment — admin-side renderer (same shape as the visitor one but
 * lives here so Admin.jsx stays self-contained and we don't have to weave
 * a shared import through the chunk-splitter).
 */
function AdminAttachment({ att }) {
  if (!att) return null;
  if (att.mime?.startsWith("image/")) {
    return (
      <a href={att.data_url} target="_blank" rel="noopener noreferrer" className="block mb-1.5">
        <img
          src={att.data_url}
          alt={att.filename || "attachment"}
          className="rounded-lg max-w-[280px] max-h-[280px] object-contain"
        />
      </a>
    );
  }
  return (
    <a
      href={att.data_url}
      download={att.filename || "file.pdf"}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-2 px-2 py-1.5 rounded-lg border text-xs mb-1.5 hover:opacity-80"
      style={{ borderColor: "var(--border)" }}
    >
      📎 {att.filename || "attachment"}
    </a>
  );
}



/**
 * ProtectionClaimsTab — admin queue of Ticket Protection refund claims.
 *
 * Lifecycle the admin sees:
 *   pending → approve / deny
 *     • approve → claim flips to "approved", booking gets `refund_requested_at`
 *       stamp. Actual Stripe refund happens via the existing /admin → Bookings
 *       refund button (we deliberately keep the two-step so admin can sanity-
 *       check the booking record before sending money back).
 *     • deny → claim flips to "denied" with an optional internal note.
 */
// ============================================================================
// OrganizerChatTab — admin sees every organizer thread + can chat with each
// ============================================================================
function OrganizerChatTab() {
  const [threads, setThreads] = useState([]);
  const [selected, setSelected] = useState(null); // organizer_id
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [orgInfo, setOrgInfo] = useState(null);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  // Organizer-is-typing indicator. Cleared on inbound real message or timeout.
  const [orgTyping, setOrgTyping] = useState(false);
  const typingTimerRef = useRef(null);
  const endRef = useRef(null);
  const seenIds = useRef(new Set());

  // Live updates for the currently-selected thread.
  const { sendTyping } = useChatLive(selected, {
    onMessage: (msg) => {
      if (!msg?.message_id || seenIds.current.has(msg.message_id)) return;
      seenIds.current.add(msg.message_id);
      setMessages((prev) => [...prev, msg]);
      // Refresh sidebar so previews + unread counters stay accurate across threads.
      loadThreads();
      setOrgTyping(false);
    },
    onTyping: (evt) => {
      if (evt?.by !== "organizer") return;
      setOrgTyping(!!evt.is_typing);
      if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
      if (evt.is_typing) {
        typingTimerRef.current = setTimeout(() => setOrgTyping(false), 3000);
      }
    },
  });

  const loadThreads = async () => {
    try {
      const { data } = await api.get("/admin/organizer-threads");
      setThreads(data);
    } catch { /* noop */ }
  };

  // Deep-link from email: ?organizer=user_xxx preselects that thread.
  useEffect(() => {
    loadThreads();
    const qs = new URLSearchParams(window.location.search);
    const target = qs.get("organizer");
    if (target) setSelected(target);
  }, []);

  const loadThread = async (uid) => {
    try {
      const { data } = await api.get(`/admin/organizer-threads/${uid}/messages`);
      const msgs = data.messages || [];
      setMessages(msgs);
      seenIds.current = new Set(msgs.map((m) => m.message_id));
      setOrgInfo(data.organizer);
      // refresh sidebar to clear unread badge
      loadThreads();
    } catch { /* noop */ }
  };

  useEffect(() => { if (selected) loadThread(selected); }, [selected]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  // Reset the typing indicator whenever we switch threads (it belonged to the
  // previous organizer).
  useEffect(() => { setOrgTyping(false); }, [selected]);

  const send = async () => {
    const body = draft.trim();
    if (!body || !selected) return;
    setBusy(true);
    try {
      await api.post(`/admin/organizer-threads/${selected}/messages`, { body });
      setDraft("");
      try { sendTyping(false); } catch { /* ignore */ }
      loadThread(selected);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to send");
    } finally { setBusy(false); }
  };

  const filtered = threads.filter((t) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (t.organizer_name || "").toLowerCase().includes(q)
      || (t.organizer_email || "").toLowerCase().includes(q);
  });

  return (
    <div className="grid lg:grid-cols-[320px_1fr] gap-4 min-h-[600px]" data-testid="organizer-chat-tab">
      {/* Sidebar — thread list */}
      <div className="border rounded-2xl overflow-hidden" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
        <div className="p-3 border-b" style={{ borderColor: "var(--border)" }}>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: "var(--text-dim)" }} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search organizers"
              className="w-full !pl-9 text-sm"
              data-testid="org-chat-search"
            />
          </div>
        </div>
        <div className="max-h-[680px] overflow-y-auto">
          {filtered.length === 0 && (
            <div className="p-6 text-sm text-center" style={{ color: "var(--text-dim)" }}>No organizers match.</div>
          )}
          {filtered.map((t) => (
            <button
              key={t.organizer_id}
              onClick={() => setSelected(t.organizer_id)}
              className={`w-full text-left p-3 border-b transition ${selected === t.organizer_id ? "" : "hover:opacity-80"}`}
              style={{
                borderColor: "var(--border)",
                background: selected === t.organizer_id ? "rgba(255,79,0,0.08)" : "transparent",
              }}
              data-testid={`org-chat-thread-${t.organizer_id}`}
            >
              <div className="flex items-center gap-2">
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate" style={{ color: "var(--text)" }}>{t.organizer_name}</div>
                  <div className="text-xs truncate" style={{ color: "var(--text-dim)" }}>
                    {t.last_message_preview || "No messages yet"}
                  </div>
                </div>
                {t.unread_count > 0 && (
                  <span
                    className="px-1.5 py-0.5 rounded-full text-xs font-bold"
                    style={{ background: "var(--accent)", color: "#0F0F0F", minWidth: 18, textAlign: "center" }}
                    data-testid={`org-chat-unread-${t.organizer_id}`}
                  >
                    {t.unread_count}
                  </span>
                )}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Right pane — selected thread */}
      <div className="border rounded-2xl flex flex-col" style={{ borderColor: "var(--border)", background: "var(--bg-card)", minHeight: 600 }}>
        {!selected ? (
          <div className="flex-1 flex items-center justify-center text-sm" style={{ color: "var(--text-dim)" }}>
            Select an organizer on the left to start chatting.
          </div>
        ) : (
          <>
            <div className="p-4 border-b" style={{ borderColor: "var(--border)" }}>
              <div className="font-medium" style={{ color: "var(--text)" }} data-testid="org-chat-header-name">
                {orgInfo?.name || "…"}
              </div>
              <div className="text-xs" style={{ color: "var(--text-dim)" }}>{orgInfo?.email}</div>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-3" data-testid="org-chat-messages">
              {messages.length === 0 && (
                <div className="text-sm text-center py-10" style={{ color: "var(--text-dim)" }}>
                  No messages yet — say hi.
                </div>
              )}
              {messages.map((m) => {
                const mine = m.sender_role === "admin";
                return (
                  <div key={m.message_id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                    <div
                      className="max-w-[75%] px-3 py-2 rounded-2xl text-sm"
                      style={{
                        background: mine ? "var(--accent)" : "var(--bg)",
                        color: mine ? "#0F0F0F" : "var(--text)",
                        whiteSpace: "pre-wrap",
                      }}
                      data-testid={`org-chat-msg-${m.message_id}`}
                    >
                      {m.body}
                      <div className="text-[10px] opacity-70 mt-1">
                        {new Date(m.created_at).toLocaleString()}
                      </div>
                    </div>
                  </div>
                );
              })}
              <div ref={endRef} />
            </div>
            {orgTyping && (
              <div
                className="px-4 pb-1 text-xs inline-flex items-center gap-1"
                style={{ color: "var(--text-dim)" }}
                data-testid="org-chat-typing"
              >
                {orgInfo?.name || "Organizer"} is typing<span className="dots-pulse">…</span>
              </div>
            )}
            <div className="p-3 border-t flex gap-2" style={{ borderColor: "var(--border)" }}>
              <textarea
                value={draft}
                onChange={(e) => {
                  setDraft(e.target.value);
                  try { sendTyping(e.target.value.trim().length > 0); } catch { /* ignore */ }
                }}
                onBlur={() => { try { sendTyping(false); } catch { /* ignore */ } }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
                }}
                placeholder="Type a message — Enter to send, Shift+Enter for newline"
                className="flex-1 text-sm"
                rows={2}
                data-testid="org-chat-input"
              />
              <button
                onClick={send}
                disabled={busy || !draft.trim()}
                className="btn-primary !py-2 !px-4 text-sm self-end inline-flex items-center gap-1"
                data-testid="org-chat-send"
              >
                <Send className="w-4 h-4" /> Send
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}



function ProtectionClaimsTab() {
  const [claims, setClaims] = useState([]);
  const [filter, setFilter] = useState("pending");
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const url = filter === "all"
        ? "/admin/ticket-protection/claims"
        : `/admin/ticket-protection/claims?status=${filter}`;
      const { data } = await api.get(url);
      setClaims(data || []);
    } catch {
      toast.error("Couldn't load claims");
    } finally {
      setLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      const { data } = await api.get("/admin/ticket-protection/stats");
      setStats(data);
    } catch { /* widget will just hide */ }
  };

  useEffect(() => { load();   }, [filter]);
  useEffect(() => { loadStats(); }, []);

  const decide = async (claim, decision) => {
    const note = window.prompt(`Optional internal note for this ${decision}:`, "") || "";
    try {
      await api.post(
        `/admin/ticket-protection/claims/${claim.claim_id}/${decision}`,
        { admin_note: note }
      );
      toast.success(`Claim ${decision === "approve" ? "approved" : "denied"}`);
      load();
      loadStats();
    } catch (e) {
      toast.error(e?.response?.data?.detail || `Couldn't ${decision} claim`);
    }
  };

  const statusColor = (s) => ({
    pending: { bg: "rgba(255,165,0,0.15)", fg: "#ff9100" },
    approved: { bg: "rgba(46,204,113,0.15)", fg: "#2ECC71" },
    denied: { bg: "rgba(231,76,60,0.15)", fg: "#E74C3C" },
  }[s] || { bg: "var(--bg-elev)", fg: "var(--text-muted)" });

  return (
    <div className="space-y-4" data-testid="admin-protection-tab">
      {stats && <ProtectionPLWidget stats={stats} />}
      <div className="flex items-center gap-2 flex-wrap">
        {["pending", "approved", "denied", "all"].map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className="px-3 py-1.5 rounded-full text-xs transition"
            style={{
              background: filter === f ? "var(--accent)" : "transparent",
              color: filter === f ? "#000" : "var(--text-muted)",
              border: "1px solid " + (filter === f ? "var(--accent)" : "var(--border)"),
              fontWeight: filter === f ? 600 : 400,
              textTransform: "capitalize",
            }}
            data-testid={`protection-filter-${f}`}
          >
            {f}
          </button>
        ))}
        <button
          onClick={load}
          className="ml-auto inline-flex items-center gap-1 text-xs px-2 py-1.5 rounded-lg"
          style={{ color: "var(--text-muted)", border: "1px solid var(--border)" }}
          data-testid="protection-refresh"
        >
          <RefreshCw className="w-3 h-3" /> Refresh
        </button>
      </div>

      {loading ? (
        <div className="text-sm py-10 text-center" style={{ color: "var(--text-dim)" }}>Loading…</div>
      ) : claims.length === 0 ? (
        <div className="text-sm py-10 text-center rounded-xl border" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }} data-testid="protection-empty">
          No {filter === "all" ? "" : filter} claims right now.
        </div>
      ) : (
        <div className="space-y-3">
          {claims.map((c) => {
            const col = statusColor(c.status);
            return (
              <div key={c.claim_id} className="rounded-xl p-4 border" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }} data-testid={`claim-${c.claim_id}`}>
                <div className="flex items-start justify-between gap-3 flex-wrap mb-3">
                  <div className="min-w-0 flex-1">
                    <div className="serif text-lg mb-0.5">{c.event_title || "Event"}</div>
                    <div className="text-xs flex flex-wrap gap-x-3 gap-y-1" style={{ color: "var(--text-dim)" }}>
                      <span>👤 {c.user_name || c.user_email}</span>
                      <span>💵 {c.currency} {Number(c.amount || 0).toFixed(2)}</span>
                      <span>📅 {new Date(c.created_at).toLocaleString()}</span>
                      <span className="font-mono">{c.booking_id}</span>
                    </div>
                  </div>
                  <span
                    className="px-2.5 py-1 rounded-full text-[10px] uppercase tracking-widest shrink-0"
                    style={{ background: col.bg, color: col.fg }}
                  >
                    {c.status}
                  </span>
                </div>
                <div className="text-sm rounded-lg p-3 mb-3" style={{ background: "var(--bg-elev)", color: "var(--text)" }}>
                  {c.reason || <em style={{ color: "var(--text-dim)" }}>No reason provided</em>}
                  {c.evidence_url && (
                    <div className="mt-2 text-xs">
                      Evidence: <a href={c.evidence_url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent)" }}>{c.evidence_url}</a>
                    </div>
                  )}
                </div>
                {c.admin_note && (
                  <div className="text-xs mb-3 italic" style={{ color: "var(--text-muted)" }}>
                    Admin note: {c.admin_note}
                  </div>
                )}
                {c.status === "pending" ? (
                  <div className="flex gap-2">
                    <button
                      onClick={() => decide(c, "approve")}
                      className="btn-primary !py-1.5 !px-3 text-xs"
                      data-testid={`approve-claim-${c.claim_id}`}
                    >
                      <Check className="w-3 h-3" /> Approve & stage refund
                    </button>
                    <button
                      onClick={() => decide(c, "deny")}
                      className="btn-ghost !py-1.5 !px-3 text-xs"
                      data-testid={`deny-claim-${c.claim_id}`}
                    >
                      <X className="w-3 h-3" /> Deny
                    </button>
                  </div>
                ) : (
                  <div className="text-xs" style={{ color: "var(--text-dim)" }}>
                    Decided {c.decided_at ? new Date(c.decided_at).toLocaleString() : ""}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/**
 * ProtectionPLWidget — at-a-glance P&L for the DIY insurance pool.
 *
 * Premiums collected vs claims paid out, with 30-day and lifetime views plus
 * the running net pool balance. Industry insurers target a 30-50% loss ratio;
 * we surface that so the admin can spot trouble (e.g. claim_ratio creeping
 * above 70% means we're losing money on the line).
 */
function ProtectionPLWidget({ stats }) {
  const fmt = (n) => `${stats.currency || "NZD"} ${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const netPositive = (stats.net_pool_lifetime || 0) >= 0;
  return (
    <div
      className="rounded-2xl border p-5"
      style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
      data-testid="protection-pl-widget"
    >
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div>
          <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--accent)" }}>Ticket Protection · Pool P&amp;L</div>
          <div className="serif text-2xl" style={{ color: "var(--text)" }}>
            Net pool: <span style={{ color: netPositive ? "#2ECC71" : "#E74C3C" }} data-testid="pl-net-lifetime">{fmt(stats.net_pool_lifetime)}</span>
          </div>
          <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>
            Charged at {(stats.protection_pct_bps / 100).toFixed(2)}% per ticket · 30-day net <strong style={{ color: stats.net_pool_30d >= 0 ? "#2ECC71" : "#E74C3C" }} data-testid="pl-net-30d">{fmt(stats.net_pool_30d)}</strong>
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs" style={{ color: "var(--text-dim)" }}>Loss ratio</div>
          <div className="text-3xl serif" style={{ color: stats.claim_ratio_pct > 70 ? "#E74C3C" : stats.claim_ratio_pct > 50 ? "#ff9100" : "#2ECC71" }} data-testid="pl-claim-ratio">
            {stats.claim_ratio_pct}%
          </div>
          <div className="text-[10px]" style={{ color: "var(--text-dim)" }}>Industry healthy: &lt;50%</div>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 md:grid-cols-4 gap-3">
        <PLCard label="Premiums (lifetime)" value={fmt(stats.premiums_lifetime)} sub={`+ ${fmt(stats.premiums_30d)} last 30d`} positive testid="pl-premiums" />
        <PLCard label="Claims paid (lifetime)" value={fmt(stats.claims_paid_lifetime)} sub={`+ ${fmt(stats.claims_paid_30d)} last 30d`} negative testid="pl-claims" />
        <PLCard label="Pending claims" value={String(stats.pending_count)} sub={`${stats.approved_count} approved · ${stats.denied_count} denied`} testid="pl-pending" />
        <PLCard label="Opt-in rate (30d)" value={`${stats.opt_in_rate_30d_pct}%`} sub="of paid bookings" testid="pl-optin" />
      </div>
    </div>
  );
}

function PLCard({ label, value, sub, positive, negative, testid }) {
  const valueColor = positive ? "#2ECC71" : negative ? "#E74C3C" : "var(--text)";
  return (
    <div
      className="rounded-xl border p-3"
      style={{ borderColor: "var(--border)", background: "var(--bg)" }}
      data-testid={testid}
    >
      <div className="text-[10px] uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>{label}</div>
      <div className="text-lg font-medium" style={{ color: valueColor }}>{value}</div>
      {sub && <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>{sub}</div>}
    </div>
  );
}



/**
 * AdminHeroStrip — at-a-glance row above the tabs.
 *
 * Currently surfaces Protection pool health + Lead-partner exposure so the
 * admin sees both lines every time they open `/admin`, not just when they
 * remember to click the right tab. Stays compact (one row of 4 cards) so it
 * doesn't push the tabs below the fold.
 */
function AdminHeroStrip({ onClickProtection, onClickPartners }) {
  const [pStats, setPStats] = useState(null);
  const [partners, setPartners] = useState([]);
  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/admin/ticket-protection/stats");
        setPStats(data);
      } catch { /* hide if endpoint fails */ }
      try {
        const { data } = await api.get("/admin/marketing-partners");
        setPartners(data || []);
      } catch { /* hide */ }
    })();
  }, []);
  if (!pStats && partners.length === 0) return null;

  const fmt = (n, c = "NZD") => `${c} ${Number(n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const partnerUnpaid = partners.reduce((sum, p) => sum + (p.unpaid_balance || 0), 0);
  const partnerLifetime = partners.reduce((sum, p) => sum + (p.lifetime_earnings || 0), 0);
  const netPositive = pStats ? (pStats.net_pool_lifetime || 0) >= 0 : true;

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6" data-testid="admin-hero-strip">
      {pStats && (
        <>
          <HeroCard
            onClick={onClickProtection}
            label="Protection · Net pool"
            value={fmt(pStats.net_pool_lifetime, pStats.currency || "NZD")}
            accentColor={netPositive ? "#2ECC71" : "#E74C3C"}
            sub={`${pStats.claim_ratio_pct}% loss ratio · ${pStats.pending_count} pending`}
            testid="hero-protection-net"
          />
          <HeroCard
            onClick={onClickProtection}
            label="Protection · Pending claims"
            value={String(pStats.pending_count)}
            accentColor={pStats.pending_count > 0 ? "#F08A2A" : "var(--text)"}
            sub={`${pStats.opt_in_rate_30d_pct}% opt-in (30d)`}
            testid="hero-protection-pending"
          />
        </>
      )}
      {partners.length > 0 && (
        <>
          <HeroCard
            onClick={onClickPartners}
            label="Lead partners · Unpaid"
            value={fmt(partnerUnpaid)}
            accentColor={partnerUnpaid > 0 ? "#F08A2A" : "#2ECC71"}
            sub={`${partners.length} active · ${fmt(partnerLifetime)} lifetime`}
            testid="hero-partners-unpaid"
          />
          <HeroCard
            onClick={onClickPartners}
            label="Lead partners · Active"
            value={String(partners.filter((p) => p.status === "active").length)}
            accentColor="var(--text)"
            sub={`${partners.reduce((s, p) => s + (p.organizer_count || 0), 0)} organizers attached`}
            testid="hero-partners-count"
          />
        </>
      )}
    </div>
  );
}

function HeroCard({ onClick, label, value, sub, accentColor, testid }) {
  return (
    <button
      onClick={onClick}
      className="rounded-xl border p-4 text-left transition hover:translate-y-[-1px]"
      style={{ borderColor: "var(--border)", background: "var(--bg)" }}
      data-testid={testid}
    >
      <div className="text-[10px] uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>{label}</div>
      <div className="text-xl font-medium" style={{ color: accentColor }}>{value}</div>
      {sub && <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>{sub}</div>}
    </button>
  );
}
