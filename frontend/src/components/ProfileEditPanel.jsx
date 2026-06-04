/**
 * ProfileEditPanel — edit name, email, phone, picture and notification prefs.
 *
 * Email + phone changes take effect immediately. Future booking confirmations
 * and reminders are sent to the new email because the booking flow reads the
 * user record at booking time.
 */
import { useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";
import { User, Mail, Phone, Image as ImageIcon, Bell, Save, X } from "lucide-react";

export default function ProfileEditPanel() {
  const { user, setUser } = useAuth();
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    name: user?.name || "",
    email: user?.email || "",
    phone: user?.phone || "",
    picture: user?.picture || "",
  });
  const [prefs, setPrefs] = useState(
    user?.notification_prefs || {
      email_booking: true,
      email_reminders: true,
      email_marketing: false,
      email_cancellations: true,
    },
  );

  const open = () => {
    setForm({
      name: user?.name || "",
      email: user?.email || "",
      phone: user?.phone || "",
      picture: user?.picture || "",
    });
    setPrefs(
      user?.notification_prefs || {
        email_booking: true,
        email_reminders: true,
        email_marketing: false,
        email_cancellations: true,
      },
    );
    setEditing(true);
  };

  const onPicture = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 5_000_000) {
      toast.error("Picture must be under 5 MB");
      return;
    }
    const fd = new FormData();
    fd.append("file", file);
    try {
      const { data } = await api.post("/uploads", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      // Build the URL from file_id to bypass any host mis-config server-side.
      const backend = process.env.REACT_APP_BACKEND_URL;
      const url = data.file_id ? `${backend}/api/files/${data.file_id}` : (data.url || "");
      setForm((f) => ({ ...f, picture: url }));
      toast.success("Picture uploaded");
    } catch (err) {
      // Surface the real reason — network / 413 / unsupported format / etc.
      const d = err?.response?.data?.detail;
      const status = err?.response?.status;
      let msg = typeof d === "string" ? d : null;
      if (!msg && status === 413) msg = "Picture too large — try one under 5 MB.";
      if (!msg && status === 401) msg = "Please sign in again, then retry.";
      if (!msg && err?.message?.includes("Network")) msg = "Network hiccup — check your connection and retry.";
      toast.error(msg || `Upload failed${status ? ` (HTTP ${status})` : ""} — try a smaller JPG or PNG.`);
      // Reset the input so picking the same file again still re-triggers onChange.
      e.target.value = "";
    }
  };

  const save = async () => {
    setBusy(true);
    try {
      const { data } = await api.patch("/auth/me", {
        name: form.name,
        email: form.email,
        phone: form.phone || null,
        picture: form.picture || null,
        notification_prefs: prefs,
      });
      setUser((u) => ({ ...u, ...data }));
      toast.success("Profile updated — future notifications go to your new details");
      setEditing(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not update profile");
    } finally {
      setBusy(false);
    }
  };

  if (!user) return null;

  return (
    <div
      className="mb-10 rounded-2xl border overflow-hidden"
      style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
      data-testid="profile-edit-panel"
    >
      <div className="flex items-center justify-between p-5 border-b" style={{ borderColor: "var(--border)" }}>
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 overflow-hidden" style={{ background: "rgba(13, 148, 136, 0.1)", color: "var(--accent)" }}>
            {user.picture ? (
              <img src={user.picture} alt="" className="w-full h-full object-cover" />
            ) : (
              <User className="w-6 h-6" />
            )}
          </div>
          <div>
            <div className="text-xs uppercase tracking-[0.2em]" style={{ color: "var(--text-dim)" }}>Contact details</div>
            <div className="font-medium">{user.email}{user.phone ? ` · ${user.phone}` : ""}</div>
          </div>
        </div>
        {!editing ? (
          <button onClick={open} className="btn-ghost !py-2 !px-4 text-sm" data-testid="edit-profile-btn">Edit profile</button>
        ) : (
          <button onClick={() => setEditing(false)} className="text-sm flex items-center gap-1" style={{ color: "var(--text-dim)" }} data-testid="cancel-edit-btn">
            <X className="w-4 h-4" /> Cancel
          </button>
        )}
      </div>

      {editing && (
        <div className="p-5 space-y-5">
          {/* Picture */}
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-xl overflow-hidden flex items-center justify-center" style={{ background: "var(--bg-elev)", color: "var(--text-dim)" }}>
              {form.picture ? <img src={form.picture} alt="" className="w-full h-full object-cover" /> : <ImageIcon className="w-6 h-6" />}
            </div>
            <label className="btn-ghost !py-2 !px-4 text-sm cursor-pointer">
              <ImageIcon className="w-4 h-4" /> Upload picture
              <input type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif" onChange={onPicture} className="hidden" data-testid="profile-picture-input" />
            </label>
            {form.picture && (
              <button onClick={() => setForm((f) => ({ ...f, picture: "" }))} className="text-xs" style={{ color: "var(--text-dim)" }} data-testid="remove-picture-btn">Remove</button>
            )}
          </div>

          {/* Name */}
          <Field icon={<User className="w-4 h-4" />} label="Full name">
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full"
              data-testid="profile-name-input"
            />
          </Field>

          {/* Email */}
          <Field icon={<Mail className="w-4 h-4" />} label="Email" hint="Booking confirmations and reminders will route here.">
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              className="w-full"
              data-testid="profile-email-input"
            />
          </Field>

          {/* Phone */}
          <Field icon={<Phone className="w-4 h-4" />} label="Phone (optional)" hint="Used for urgent updates from organizers. Format: +64 21 555 1234">
            <input
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
              className="w-full"
              placeholder="+64 21 555 1234"
              data-testid="profile-phone-input"
            />
          </Field>

          {/* Notification prefs */}
          <div>
            <div className="text-xs uppercase tracking-widest mb-2 flex items-center gap-2" style={{ color: "var(--text-dim)" }}>
              <Bell className="w-3.5 h-3.5" /> Notification preferences
            </div>
            <div className="grid sm:grid-cols-2 gap-2">
              <Toggle id="email_booking" label="Booking confirmation" prefs={prefs} setPrefs={setPrefs} />
              <Toggle id="email_reminders" label="Event reminders (24h before)" prefs={prefs} setPrefs={setPrefs} />
              <Toggle id="email_cancellations" label="Cancellation alerts" prefs={prefs} setPrefs={setPrefs} />
              <Toggle id="email_marketing" label="Promotions &amp; new events" prefs={prefs} setPrefs={setPrefs} />
            </div>
          </div>

          <div className="flex justify-end pt-2">
            <button
              onClick={save}
              disabled={busy}
              className="btn-primary"
              data-testid="save-profile-btn"
            >
              <Save className="w-4 h-4" /> {busy ? "Saving…" : "Save changes"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ icon, label, hint, children }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-widest mb-2 flex items-center gap-2" style={{ color: "var(--text-dim)" }}>
        {icon}{label}
      </div>
      {children}
      {hint && <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>{hint}</div>}
    </div>
  );
}

function Toggle({ id, label, prefs, setPrefs }) {
  const on = !!prefs[id];
  return (
    <button
      type="button"
      onClick={() => setPrefs({ ...prefs, [id]: !on })}
      className="text-left px-3 py-2.5 rounded-lg border text-sm flex items-center gap-3 transition"
      style={{
        borderColor: on ? "var(--accent)" : "var(--border)",
        background: on ? "rgba(234, 88, 12, 0.06)" : "transparent",
      }}
      data-testid={`pref-${id}`}
    >
      <span
        className="w-9 h-5 rounded-full relative transition"
        style={{ background: on ? "var(--accent)" : "var(--border-strong)" }}
      >
        <span
          className="absolute top-0.5 w-4 h-4 bg-white rounded-full transition-all"
          style={{ left: on ? 18 : 2 }}
        />
      </span>
      <span style={{ color: on ? "var(--text)" : "var(--text-muted)" }}>{label}</span>
    </button>
  );
}
