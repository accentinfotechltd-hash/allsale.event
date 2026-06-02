/**
 * TeamPanel — manage who has rights on an event.
 *
 * Lets the event owner invite team members by email. Backend resolves whether
 * the email is an existing user (instant access) or sends an invitation. Shows
 * a list with role + remove. Supports per-event grants from this page; the
 * "Org-wide" toggle adds the member to ALL the owner's events.
 */
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Users, Plus, Trash2, Shield, ShieldCheck, ScanLine, Mail, Clock } from "lucide-react";

const ROLES = [
  { id: "co_organizer", label: "Co-organizer", desc: "Full access (edit, refunds, analytics, check-in)", icon: ShieldCheck },
  { id: "manager", label: "Manager", desc: "Edit + analytics + check-in (no refunds)", icon: Shield },
  { id: "door_staff", label: "Door staff", desc: "Check-in only", icon: ScanLine },
];

const ROLE_LABEL = Object.fromEntries(ROLES.map((r) => [r.id, r.label]));

export default function TeamPanel({ eventId, event }) {
  const [team, setTeam] = useState([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("manager");
  const [scope, setScope] = useState("event");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get(`/organizer/team/event/${eventId}`);
      setTeam(data.items || []);
    } catch {
      toast.error("Could not load team");
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [eventId]);

  const add = async (e) => {
    e?.preventDefault?.();
    if (!email.trim()) return toast.message("Enter an email");
    setBusy(true);
    try {
      const payload = { email: email.trim(), role };
      if (scope === "event") payload.event_id = eventId;
      const { data } = await api.post("/organizer/team", payload);
      if (data.status === "invited") {
        toast.success("Invitation sent — they'll get access once they sign up");
      } else {
        toast.success(`${data.member_email} added as ${ROLE_LABEL[data.role] || data.role}`);
      }
      setEmail("");
      load();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      const msg = typeof detail === "string" ? detail : "Could not add team member";
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (m) => {
    if (!window.confirm(`Remove ${m.member_email} from this team?`)) return;
    try {
      await api.delete(`/organizer/team/${m.member_id}`);
      toast.success("Removed");
      load();
    } catch {
      toast.error("Failed to remove");
    }
  };

  return (
    <div className="border rounded-2xl p-6 lg:p-8 mb-8" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }} data-testid="team-panel">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-5">
        <div>
          <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Team</div>
          <h2 className="serif text-3xl">Add staff &amp; co-organizers</h2>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
            Invite by email. Existing users get instant access; new emails receive a sign-up invitation.
          </p>
        </div>
        <div className="text-right">
          <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>Active</div>
          <div className="serif text-3xl flex items-center gap-2"><Users className="w-5 h-5" /> {team.length}</div>
        </div>
      </div>

      <form onSubmit={add} className="grid lg:grid-cols-[1fr_220px_180px_auto] gap-3 mb-6 items-stretch">
        <div className="relative">
          <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: "var(--text-dim)" }} />
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="teammate@example.com"
            className="w-full pl-10"
            data-testid="team-email-input"
          />
        </div>
        <select value={role} onChange={(e) => setRole(e.target.value)} className="!w-full" data-testid="team-role-select">
          {ROLES.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
        </select>
        <select value={scope} onChange={(e) => setScope(e.target.value)} className="!w-full" data-testid="team-scope-select">
          <option value="event">This event only</option>
          <option value="organization">All my events</option>
        </select>
        <button type="submit" disabled={busy} className="btn-primary" data-testid="team-add-btn">
          <Plus className="w-4 h-4" /> {busy ? "Adding…" : "Add"}
        </button>
      </form>

      <div className="text-xs mb-3" style={{ color: "var(--text-dim)" }}>
        Selected role: <strong style={{ color: "var(--text-muted)" }}>{ROLE_LABEL[role]}</strong> — {ROLES.find((r) => r.id === role)?.desc}
      </div>

      {team.length === 0 ? (
        <div className="border rounded-xl p-6 text-center text-sm" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
          No team members yet. Add your first one above.
        </div>
      ) : (
        <div className="border rounded-xl overflow-hidden" style={{ borderColor: "var(--border)" }}>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-xs uppercase tracking-widest" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
                <th className="text-left p-3">Member</th>
                <th className="text-left p-3 hidden sm:table-cell">Role</th>
                <th className="text-left p-3 hidden md:table-cell">Scope</th>
                <th className="text-left p-3 hidden lg:table-cell">Status</th>
                <th className="text-right p-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {team.map((m) => {
                const RoleIcon = ROLES.find((r) => r.id === m.role)?.icon || Shield;
                return (
                  <tr key={m.member_id} className="border-b" style={{ borderColor: "var(--border)" }} data-testid={`team-row-${m.member_id}`}>
                    <td className="p-3">
                      <div className="font-medium">{m.member_name || m.member_email}</div>
                      {m.member_name && <div className="text-xs" style={{ color: "var(--text-dim)" }}>{m.member_email}</div>}
                    </td>
                    <td className="p-3 hidden sm:table-cell">
                      <span className="chip" style={{ fontSize: "0.65rem" }}>
                        <RoleIcon className="w-3 h-3" /> {ROLE_LABEL[m.role] || m.role}
                      </span>
                    </td>
                    <td className="p-3 text-xs hidden md:table-cell" style={{ color: "var(--text-muted)" }}>
                      {m.scope === "organization" ? "All my events" : "This event"}
                    </td>
                    <td className="p-3 hidden lg:table-cell">
                      {m.status === "active" ? (
                        <span className="chip chip-accent" style={{ fontSize: "0.6rem" }}>Active</span>
                      ) : (
                        <span className="chip" style={{ fontSize: "0.6rem", color: "var(--warn)", borderColor: "var(--warn)" }}>
                          <Clock className="w-3 h-3" /> Invited
                        </span>
                      )}
                    </td>
                    <td className="p-3 text-right">
                      <button
                        onClick={() => remove(m)}
                        className="btn-ghost !py-1 !px-2 text-xs"
                        title="Remove"
                        data-testid={`team-remove-${m.member_id}`}
                      ><Trash2 className="w-3 h-3" /></button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
