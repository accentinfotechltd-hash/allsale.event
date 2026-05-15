import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Check, X, Star, Users, Calendar, Search, ShieldCheck, ShieldAlert, UserCog, Ban, RotateCcw } from "lucide-react";
import { toast } from "sonner";

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
        </div>
      </div>

      {tab === "events" ? <EventsTab /> : <UsersTab currentUser={user} />}
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

  const pending = events.filter((e) => e.status === "pending");
  const approved = events.filter((e) => e.status === "approved");

  return (
    <>
      <Section title="Pending approval" events={pending} act={act} showApprove />
      <Section title="Approved events" events={approved} act={act} showFeature />
    </>
  );
}

function Section({ title, events, act, showApprove, showFeature }) {
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
              <th className="text-left p-4">Role</th>
              <th className="text-left p-4">Joined</th>
              <th className="text-right p-4">Bookings</th>
              <th className="text-right p-4">Events</th>
              <th className="text-left p-4">Status</th>
              <th className="text-right p-4">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan="7" className="p-10 text-center" style={{ color: "var(--text-dim)" }}>Loading users...</td></tr>
            ) : users.length === 0 ? (
              <tr><td colSpan="7" className="p-10 text-center" style={{ color: "var(--text-dim)" }}>No users match these filters.</td></tr>
            ) : users.map((u) => (
              <tr key={u.user_id} className="border-b" style={{ borderColor: "var(--border)", opacity: u.active ? 1 : 0.55 }} data-testid={`user-row-${u.user_id}`}>
                <td className="p-4">
                  <div className="flex items-center gap-3">
                    {u.picture ? (
                      <img src={u.picture} alt="" className="w-9 h-9 rounded-full" />
                    ) : (
                      <div className="w-9 h-9 rounded-full flex items-center justify-center" style={{ background: "var(--bg-elev)", color: "var(--text-muted)" }}>
                        {u.name.charAt(0).toUpperCase()}
                      </div>
                    )}
                    <div>
                      <div className="font-medium">{u.name}</div>
                      <div className="text-xs" style={{ color: "var(--text-dim)" }}>{u.email}</div>
                    </div>
                  </div>
                </td>
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
                <td className="p-4" style={{ color: "var(--text-muted)" }}>
                  {new Date(u.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                </td>
                <td className="p-4 text-right" style={{ color: "var(--text-muted)" }}>{u.bookings_count}</td>
                <td className="p-4 text-right" style={{ color: "var(--text-muted)" }}>{u.events_count}</td>
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
