/**
 * AdminUserDetailDrawer — admin drill-down for a single user.
 *
 * Shows the user's full record, their bookings (as attendee), and their
 * events (as organizer). Lets admin edit name/email/phone inline.
 */
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { X, Mail, Phone, User, Save, Calendar, Ticket } from "lucide-react";

export default function AdminUserDetailDrawer({ userId, onClose, onUserUpdated }) {
  const [data, setData] = useState(null);
  const [edit, setEdit] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", phone: "", notification_email: "" });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!userId) return;
    (async () => {
      try {
        const { data } = await api.get(`/admin/users/${userId}`);
        setData(data);
        setForm({ name: data.name || "", email: data.email || "", phone: data.phone || "", notification_email: data.notification_email || "" });
      } catch {
        toast.error("Could not load user");
        onClose?.();
      }
    })();
  }, [userId, onClose]);

  const save = async () => {
    setBusy(true);
    try {
      const { data: updated } = await api.patch(`/admin/users/${userId}`, form);
      setData((d) => ({ ...d, ...updated }));
      onUserUpdated?.(updated);
      setEdit(false);
      toast.success("User details updated");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Update failed");
    } finally {
      setBusy(false);
    }
  };

  if (!userId) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex justify-end" onClick={onClose} data-testid="admin-user-drawer">
      <div
        className="w-full max-w-2xl h-full overflow-y-auto shadow-2xl"
        style={{ background: "var(--bg)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between p-5 border-b" style={{ borderColor: "var(--border)", background: "var(--bg)" }}>
          <div>
            <div className="text-xs uppercase tracking-[0.3em]" style={{ color: "var(--accent)" }}>User details</div>
            <div className="serif text-2xl">{data?.name || "Loading…"}</div>
          </div>
          <button onClick={onClose} className="p-2" data-testid="close-user-drawer-btn">
            <X className="w-5 h-5" />
          </button>
        </div>

        {!data ? (
          <div className="p-10 text-center" style={{ color: "var(--text-dim)" }}>Loading…</div>
        ) : (
          <div className="p-5 space-y-6">
            {/* Contact card */}
            <div className="rounded-2xl border p-5" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
              <div className="flex items-center justify-between mb-4">
                <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>Contact</div>
                {!edit ? (
                  <button onClick={() => setEdit(true)} className="btn-ghost !py-1.5 !px-3 text-xs" data-testid="admin-edit-user-btn">Edit</button>
                ) : (
                  <div className="flex gap-2">
                    <button onClick={() => { setEdit(false); setForm({ name: data.name || "", email: data.email || "", phone: data.phone || "", notification_email: data.notification_email || "" }); }} className="text-xs" style={{ color: "var(--text-dim)" }}>Cancel</button>
                    <button onClick={save} disabled={busy} className="btn-primary !py-1.5 !px-3 text-xs" data-testid="admin-save-user-btn">
                      <Save className="w-3 h-3" /> {busy ? "Saving…" : "Save"}
                    </button>
                  </div>
                )}
              </div>
              {!edit ? (
                <div className="space-y-2 text-sm">
                  <Row icon={<User className="w-4 h-4" />} label="Name" value={data.name} />
                  <Row icon={<Mail className="w-4 h-4" />} label="Email" value={data.email} />
                  <Row
                    icon={<Mail className="w-4 h-4" />}
                    label="Notification email"
                    value={data.notification_email || <span style={{ color: "var(--text-dim)" }}>— (same as Email)</span>}
                  />
                  <Row icon={<Phone className="w-4 h-4" />} label="Phone" value={data.phone || "—"} />
                  <Row label="Role" value={<span className="capitalize">{data.role}</span>} />
                  <Row label="Status" value={data.active ? "Active" : <span style={{ color: "var(--danger)" }}>Suspended</span>} />
                  <Row label="Joined" value={new Date(data.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })} />
                  <Row label="Auth provider" value={data.auth_provider || "password"} />
                </div>
              ) : (
                <div className="space-y-3 text-sm">
                  <Input label="Name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} testid="admin-edit-name" />
                  <Input label="Email (used to log in)" type="email" value={form.email} onChange={(v) => setForm({ ...form, email: v })} testid="admin-edit-email" />
                  <Input
                    label="Notification email (optional)"
                    type="email"
                    value={form.notification_email}
                    onChange={(v) => setForm({ ...form, notification_email: v })}
                    placeholder="e.g. allsaletickets@gmail.com — leave blank to use Email above"
                    testid="admin-edit-notification-email"
                  />
                  <Input label="Phone" value={form.phone} onChange={(v) => setForm({ ...form, phone: v })} placeholder="+64 21 555 1234" testid="admin-edit-phone" />
                  <p className="text-xs" style={{ color: "var(--text-dim)" }}>
                    Email is the login. <b>Notification email</b>, when set, re-routes all automated emails (booking confirmations, organizer messages, payouts, approvals) to that address — useful when the login email&apos;s domain has no real mailbox.
                  </p>
                </div>
              )}
            </div>

            {/* Bookings */}
            <div>
              <div className="text-xs uppercase tracking-widest mb-3 flex items-center gap-2" style={{ color: "var(--text-dim)" }}>
                <Ticket className="w-3.5 h-3.5" /> Bookings ({data.bookings_count})
              </div>
              {data.bookings?.length === 0 ? (
                <div className="text-sm py-4 px-4 rounded-xl border" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
                  No bookings yet.
                </div>
              ) : (
                <div className="space-y-2">
                  {data.bookings.map((b) => (
                    <div key={b.booking_id} className="rounded-xl border p-3 text-sm flex items-center justify-between" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }} data-testid={`drawer-booking-${b.booking_id}`}>
                      <div>
                        <div className="font-medium">{b.event_title}</div>
                        <div className="text-xs" style={{ color: "var(--text-dim)" }}>
                          {b.seats?.length ? b.seats.join(", ") : b.tier_name} · {b.quantity} ticket{b.quantity === 1 ? "" : "s"} · {b.currency || "NZD"} {b.amount}
                        </div>
                      </div>
                      <span className="chip" style={{ fontSize: "0.6rem", color: b.status === "paid" ? "var(--success)" : "var(--text-dim)" }}>
                        {b.checked_in ? "checked in" : b.status}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Events organized */}
            {data.events_count > 0 && (
              <div>
                <div className="text-xs uppercase tracking-widest mb-3 flex items-center gap-2" style={{ color: "var(--text-dim)" }}>
                  <Calendar className="w-3.5 h-3.5" /> Events organized ({data.events_count})
                </div>
                <div className="space-y-2">
                  {data.events.map((e) => (
                    <div key={e.event_id} className="rounded-xl border p-3 text-sm flex items-center justify-between" style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}>
                      <div>
                        <div className="font-medium">{e.title}</div>
                        <div className="text-xs" style={{ color: "var(--text-dim)" }}>
                          {e.venue}, {e.city} · {new Date(e.date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                        </div>
                      </div>
                      <span className="chip" style={{ fontSize: "0.6rem" }}>{e.status}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Row({ icon, label, value }) {
  return (
    <div className="flex items-start gap-3">
      <div className="w-32 flex items-center gap-2 text-xs uppercase tracking-widest pt-0.5" style={{ color: "var(--text-dim)" }}>
        {icon}{label}
      </div>
      <div className="flex-1 text-sm" style={{ color: "var(--text)" }}>{value}</div>
    </div>
  );
}

function Input({ label, value, onChange, placeholder, type = "text", testid }) {
  return (
    <label className="block">
      <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>{label}</div>
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className="w-full" data-testid={testid} />
    </label>
  );
}
