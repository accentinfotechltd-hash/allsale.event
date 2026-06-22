import { useEffect, useState } from "react";
import { Plus, Pencil, Trash2, Search, X as XIcon, Users, DollarSign, Receipt, CheckCircle2, KeyRound, Mail, MailPlus } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

/**
 * AdminMarketingPartnersTab — admin-controlled lead-partner program.
 *
 * Flow:
 *   1. Admin creates a partner with a commission % (e.g. 20%)
 *   2. Admin attaches one-or-more organizers to that partner
 *   3. Every time an attached organizer's booking gets paid, the platform
 *      commission slice is multiplied by the partner's % and recorded as an
 *      unpaid earning. Admin marks earnings paid in batches.
 */
export default function AdminMarketingPartnersTab() {
  const [partners, setPartners] = useState([]);
  const [editing, setEditing] = useState(null);
  const [detail, setDetail] = useState(null);
  const [sending, setSending] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get("/admin/marketing-partners");
      setPartners(data || []);
    } catch { toast.error("Couldn't load partners"); }
  };
  useEffect(() => { load(); }, []);

  const remove = async (p) => {
    if (!window.confirm(`Delete partner "${p.name}"? Their organizers will be detached. Past earnings are kept.`)) return;
    try {
      await api.delete(`/admin/marketing-partners/${p.partner_id}`);
      toast.success("Partner deleted");
      load();
    } catch { toast.error("Delete failed"); }
  };

  const sendStatements = async () => {
    if (!window.confirm(`Send a monthly statement email to every active partner with an email on file? (${partners.filter(p => p.status === "active" && p.email).length} partner${partners.filter(p => p.status === "active" && p.email).length === 1 ? "" : "s"})`)) return;
    setSending(true);
    const t = toast.loading("Sending statements...");
    try {
      const { data } = await api.post("/admin/marketing-partners/send-statements", {});
      toast.success(`Statements sent: ${data.sent} delivered${data.skipped ? `, ${data.skipped} skipped (no email)` : ""}${data.failed ? `, ${data.failed} failed` : ""}`, { id: t });
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Send failed", { id: t });
    } finally { setSending(false); }
  };

  const resendInvite = async (p) => {
    if (!window.confirm(`Re-send the welcome email to ${p.portal_email}? A NEW temporary password will be generated and the old one will stop working.`)) return;
    const t = toast.loading("Rotating password & sending...");
    try {
      const { data } = await api.post(`/admin/marketing-partners/${p.partner_id}/resend-invitation`);
      if (data.email_sent) {
        toast.success(`Welcome email re-sent to ${p.portal_email} with a new password`, { id: t, duration: 8000 });
      } else {
        toast.error(`Password rotated but email failed. Share manually: ${p.portal_email} / ${data.fallback_password}`, { id: t, duration: 16000 });
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Resend failed", { id: t });
    }
  };

  return (
    <div className="space-y-4" data-testid="admin-marketing-partners-tab">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-serif" style={{ color: "var(--text)" }}>Marketing Lead Partners</h2>
          <p className="text-sm" style={{ color: "var(--text-dim)" }}>
            Pay a % of platform commission to anyone who brings you organizers. Recurring on every paid booking.
          </p>
        </div>
        <button onClick={() => setEditing({ name: "", email: "", contact: "", commission_pct: 20, notes: "" })} className="btn-primary" data-testid="add-partner-btn">
          <Plus size={14} /> Add partner
        </button>
      </div>

      {partners.length > 0 && (
        <div className="flex items-center justify-end -mt-2 mb-2">
          <button onClick={sendStatements} disabled={sending} className="btn-ghost text-xs" data-testid="send-statements-btn">
            <Mail size={12} /> {sending ? "Sending..." : "Email monthly statements"}
          </button>
        </div>
      )}

      {partners.length === 0 ? (
        <div className="rounded-xl border py-10 text-center text-sm" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }} data-testid="partners-empty">
          No lead partners yet. Add your first to start tracking referred organizers.
        </div>
      ) : (
        <div className="rounded-xl border overflow-hidden" style={{ borderColor: "var(--border)" }}>
          <table className="w-full text-sm">
            <thead style={{ color: "var(--text-dim)" }}>
              <tr className="text-left">
                <th className="px-4 py-3 font-medium">Partner</th>
                <th className="px-4 py-3 font-medium">Commission</th>
                <th className="px-4 py-3 font-medium">Organizers</th>
                <th className="px-4 py-3 font-medium">Lifetime</th>
                <th className="px-4 py-3 font-medium">Unpaid</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {partners.map((p) => (
                <tr key={p.partner_id} className="border-t" style={{ borderColor: "var(--border)" }} data-testid={`partner-row-${p.partner_id}`}>
                  <td className="px-4 py-3">
                    <button onClick={() => setDetail(p.partner_id)} className="text-left" data-testid={`partner-name-${p.partner_id}`}>
                      <div style={{ color: "var(--text)", fontWeight: 500 }}>{p.name}</div>
                      <div className="text-xs" style={{ color: "var(--text-dim)" }}>{p.email || "no email"}</div>
                    </button>
                  </td>
                  <td className="px-4 py-3" style={{ color: "var(--text)" }}>{p.commission_pct}%</td>
                  <td className="px-4 py-3" style={{ color: "var(--text-dim)" }}>{p.organizer_count}</td>
                  <td className="px-4 py-3" style={{ color: "var(--text)" }}>NZD {p.lifetime_earnings.toFixed(2)}</td>
                  <td className="px-4 py-3">
                    <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: p.unpaid_balance > 0 ? "rgba(240,138,42,0.15)" : "rgba(46,204,113,0.12)", color: p.unpaid_balance > 0 ? "#F08A2A" : "#2ECC71" }}>
                      NZD {p.unpaid_balance.toFixed(2)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    {p.has_portal_access && (
                      <button onClick={() => resendInvite(p)} className="p-2 rounded hover:bg-black/5" title={`Re-send welcome email to ${p.portal_email}`} style={{ color: "var(--accent)" }} data-testid={`partner-resend-${p.partner_id}`}>
                        <MailPlus size={14} />
                      </button>
                    )}
                    <button onClick={() => setEditing(p)} className="p-2 rounded hover:bg-black/5" title="Edit" data-testid={`partner-edit-${p.partner_id}`}>
                      <Pencil size={14} />
                    </button>
                    <button onClick={() => remove(p)} className="p-2 rounded hover:bg-black/5" title="Delete" style={{ color: "#ef4444" }} data-testid={`partner-delete-${p.partner_id}`}>
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing && <PartnerEditor draft={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
      {detail && <PartnerDetailDrawer partnerId={detail} onClose={() => { setDetail(null); load(); }} />}
    </div>
  );
}

function PartnerEditor({ draft, onClose, onSaved }) {
  const [form, setForm] = useState(draft);
  const [busy, setBusy] = useState(false);
  const isEdit = !!draft.partner_id;
  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    if (!form.name?.trim()) { toast.error("Name is required"); return; }
    setBusy(true);
    try {
      if (isEdit) {
        await api.patch(`/admin/marketing-partners/${form.partner_id}`, {
          name: form.name, email: form.email, contact: form.contact,
          commission_pct: Number(form.commission_pct), notes: form.notes, status: form.status,
        });
      } else {
        await api.post(`/admin/marketing-partners`, {
          name: form.name, email: form.email || null, contact: form.contact || null,
          commission_pct: Number(form.commission_pct), notes: form.notes,
        });
      }
      toast.success(isEdit ? "Partner updated" : "Partner added");
      onSaved();
    } catch (e) { toast.error(e?.response?.data?.detail || "Save failed"); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end" style={{ background: "rgba(15,42,58,0.55)" }} onClick={onClose}>
      <div className="h-full w-full max-w-md overflow-y-auto p-6" style={{ background: "var(--bg, #ffffff)", borderLeft: "1px solid var(--border)" }} onClick={(e) => e.stopPropagation()} data-testid="partner-editor">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-xl font-serif" style={{ color: "var(--text)" }}>{isEdit ? "Edit partner" : "New lead partner"}</h3>
          <button onClick={onClose}><XIcon size={18} /></button>
        </div>
        <div className="space-y-3">
          <Field label="Name">
            <input type="text" value={form.name || ""} onChange={(e) => update("name", e.target.value)} className="w-full" placeholder="Acme Lead Gen Ltd" data-testid="partner-form-name" />
          </Field>
          <Field label="Email">
            <input type="email" value={form.email || ""} onChange={(e) => update("email", e.target.value)} className="w-full" placeholder="sales@acme.co" data-testid="partner-form-email" />
          </Field>
          <Field label="Phone / WhatsApp">
            <input type="text" value={form.contact || ""} onChange={(e) => update("contact", e.target.value)} className="w-full" placeholder="+64 21..." data-testid="partner-form-contact" />
          </Field>
          <Field label="Commission %" hint="Percent of platform commission this partner earns on every paid booking from their referred organizers.">
            <input type="number" min="0" max="100" step="0.5" value={form.commission_pct} onChange={(e) => update("commission_pct", e.target.value)} className="w-full" data-testid="partner-form-pct" />
          </Field>
          <Field label="Notes">
            <textarea rows={3} value={form.notes || ""} onChange={(e) => update("notes", e.target.value)} className="w-full" placeholder="Deal terms, contact context, etc." data-testid="partner-form-notes" />
          </Field>
          {isEdit && (
            <Field label="Status">
              <select value={form.status || "active"} onChange={(e) => update("status", e.target.value)} className="w-full" data-testid="partner-form-status">
                <option value="active">Active</option>
                <option value="inactive">Inactive (stop earning new commission)</option>
              </select>
            </Field>
          )}
        </div>
        <div className="sticky bottom-0 mt-6 pt-4 border-t flex justify-end gap-2" style={{ borderColor: "var(--border)", background: "var(--bg, #ffffff)" }}>
          <button onClick={save} disabled={busy} className="btn-primary" data-testid="partner-form-save">{busy ? "Saving..." : "Save"}</button>
        </div>
      </div>
    </div>
  );
}

function PartnerDetailDrawer({ partnerId, onClose }) {
  const [partner, setPartner] = useState(null);
  const [earnings, setEarnings] = useState([]);
  const [attaching, setAttaching] = useState(false);
  const [search, setSearch] = useState("");
  const [results, setResults] = useState([]);

  const reload = async () => {
    try {
      const [{ data: p }, { data: e }] = await Promise.all([
        api.get(`/admin/marketing-partners/${partnerId}`),
        api.get(`/admin/marketing-partners/${partnerId}/earnings`),
      ]);
      setPartner(p);
      setEarnings(e || []);
    } catch { toast.error("Couldn't load partner"); }
  };
  useEffect(() => { reload(); }, [partnerId]);

  const runSearch = async (q) => {
    setSearch(q);
    if (q.length < 1) { setResults([]); return; }
    try {
      const { data } = await api.get(`/admin/marketing-partners-organizer-search?q=${encodeURIComponent(q)}`);
      setResults(data || []);
    } catch { setResults([]); }
  };

  const attach = async (userId) => {
    try {
      await api.post(`/admin/marketing-partners/${partnerId}/organizers`, { user_id: userId });
      toast.success("Organizer attached");
      setSearch(""); setResults([]); setAttaching(false);
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || "Attach failed"); }
  };

  const detach = async (userId) => {
    if (!window.confirm("Detach this organizer? Future bookings won't credit this partner.")) return;
    try {
      await api.delete(`/admin/marketing-partners/${partnerId}/organizers/${userId}`);
      toast.success("Detached");
      reload();
    } catch { toast.error("Detach failed"); }
  };

  const markAllPaid = async () => {
    if (!window.confirm(`Mark all ${partner.unpaid_balance.toFixed(2)} NZD as paid? This locks the earnings into a payout batch.`)) return;
    const ref = window.prompt("Optional payout reference (bank txn ID, transfer note):", "") || "";
    try {
      const { data } = await api.post(`/admin/marketing-partners/${partnerId}/earnings/mark-paid`, { payout_reference: ref });
      toast.success(`Marked ${data.marked_paid} earning${data.marked_paid === 1 ? "" : "s"} paid (batch ${data.batch_id})`);
      reload();
    } catch { toast.error("Failed"); }
  };

  const grantPortal = async () => {
    const email = window.prompt("Partner login email (we'll email the invite here):", partner?.email || "");
    if (!email) return;
    const password = window.prompt("Set a temporary password (min 6 chars). The partner will be emailed this password and asked to change it on first login.", "");
    if (!password || password.length < 6) { toast.error("Password too short"); return; }
    try {
      const { data } = await api.post(`/admin/marketing-partners/${partnerId}/grant-portal-access`, { email, password, name: partner?.name, send_invitation_email: true });
      const action = data.action === "linked-existing" ? "Linked existing user" : "Created new login";
      if (data.invitation_email_sent) {
        toast.success(`${action} · Welcome email sent to ${email}`, { duration: 8000 });
      } else {
        toast.error(`${action}, but email failed: ${data.invitation_email_error || "unknown error"}. Share credentials manually: ${email} / ${password}`, { duration: 14000 });
      }
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end" style={{ background: "rgba(15,42,58,0.55)" }} onClick={onClose}>
      <div className="h-full w-full max-w-2xl overflow-y-auto p-6" style={{ background: "var(--bg, #ffffff)", borderLeft: "1px solid var(--border)" }} onClick={(e) => e.stopPropagation()} data-testid="partner-detail-drawer">
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="text-xs uppercase tracking-widest" style={{ color: "var(--accent)" }}>Lead partner</div>
            <h3 className="text-2xl font-serif" style={{ color: "var(--text)" }}>{partner?.name || "..."}</h3>
            <div className="text-xs" style={{ color: "var(--text-dim)" }}>{partner?.email || ""} · {partner?.commission_pct}% per paid booking</div>
          </div>
          <button onClick={onClose}><XIcon size={18} /></button>
        </div>

        {partner && (
          <>
            <div className="grid grid-cols-3 gap-3 mb-6">
              <Stat icon={<Users size={14} />} label="Organizers" value={partner.organizer_count} />
              <Stat icon={<DollarSign size={14} />} label="Lifetime earnings" value={`NZD ${partner.lifetime_earnings.toFixed(2)}`} />
              <Stat icon={<Receipt size={14} />} label="Unpaid balance" value={`NZD ${partner.unpaid_balance.toFixed(2)}`} accent={partner.unpaid_balance > 0} />
            </div>

            <div className="flex items-center justify-end gap-2 mb-4">
              <button onClick={grantPortal} className="btn-ghost text-xs" data-testid="grant-portal-btn">
                <KeyRound size={12} /> Grant /partner login
              </button>
            </div>

            {/* Organizers */}
            <section className="mb-6">
              <div className="flex items-center justify-between mb-2">
                <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>Attached organizers</div>
                <button onClick={() => setAttaching(!attaching)} className="text-xs underline" style={{ color: "var(--accent)" }} data-testid="attach-organizer-btn">
                  {attaching ? "Cancel" : "+ Attach organizer"}
                </button>
              </div>
              {attaching && (
                <div className="rounded-lg border p-3 mb-2" style={{ borderColor: "var(--border)" }}>
                  <div className="flex items-center gap-2">
                    <Search size={14} style={{ color: "var(--text-dim)" }} />
                    <input
                      type="text"
                      value={search}
                      onChange={(e) => runSearch(e.target.value)}
                      placeholder="Search organizer by name or email"
                      className="flex-1 text-sm"
                      data-testid="organizer-search-input"
                    />
                  </div>
                  {results.length > 0 && (
                    <div className="mt-2 max-h-56 overflow-y-auto">
                      {results.map((r) => (
                        <button key={r.user_id} onClick={() => attach(r.user_id)} disabled={r.marketing_partner_id} className="w-full text-left p-2 text-sm rounded hover:bg-black/5 flex items-center justify-between" data-testid={`attach-result-${r.user_id}`}>
                          <span>
                            <span style={{ color: "var(--text)" }}>{r.name || "(no name)"}</span>
                            <span className="ml-2" style={{ color: "var(--text-dim)" }}>{r.email}</span>
                          </span>
                          {r.marketing_partner_id ? (
                            <span className="text-xs" style={{ color: "var(--text-dim)" }}>{r.marketing_partner_id === partnerId ? "already attached" : "linked to another partner"}</span>
                          ) : <span className="text-xs" style={{ color: "var(--accent)" }}>Attach →</span>}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {partner.organizers.length === 0 ? (
                <div className="text-sm" style={{ color: "var(--text-dim)" }}>No organizers attached yet.</div>
              ) : (
                <div className="space-y-1">
                  {partner.organizers.map((o) => (
                    <div key={o.user_id} className="flex items-center justify-between text-sm rounded p-2 border" style={{ borderColor: "var(--border)" }} data-testid={`attached-${o.user_id}`}>
                      <div>
                        <span style={{ color: "var(--text)" }}>{o.name || "(no name)"}</span>
                        <span className="ml-2" style={{ color: "var(--text-dim)" }}>{o.email}</span>
                      </div>
                      <button onClick={() => detach(o.user_id)} className="text-xs underline" style={{ color: "#ef4444" }} data-testid={`detach-${o.user_id}`}>
                        Detach
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Earnings ledger */}
            <section>
              <div className="flex items-center justify-between mb-2">
                <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>Earnings ledger</div>
                {partner.unpaid_balance > 0 && (
                  <button onClick={markAllPaid} className="btn-ghost text-xs" data-testid="mark-all-paid-btn">
                    <CheckCircle2 size={12} /> Mark all unpaid as paid
                  </button>
                )}
              </div>
              {earnings.length === 0 ? (
                <div className="text-sm py-4 rounded border text-center" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>No earnings yet — they&apos;ll appear here automatically once attached organizers process bookings.</div>
              ) : (
                <table className="w-full text-sm">
                  <thead style={{ color: "var(--text-dim)" }}>
                    <tr className="text-left">
                      <th className="px-2 py-2 font-medium">Date</th>
                      <th className="px-2 py-2 font-medium">Event</th>
                      <th className="px-2 py-2 font-medium">Platform fee</th>
                      <th className="px-2 py-2 font-medium">Earning</th>
                      <th className="px-2 py-2 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {earnings.slice(0, 100).map((e) => (
                      <tr key={e.earning_id} className="border-t" style={{ borderColor: "var(--border)" }} data-testid={`earning-row-${e.earning_id}`}>
                        <td className="px-2 py-2" style={{ color: "var(--text-dim)" }}>{fmtDate(e.created_at)}</td>
                        <td className="px-2 py-2" style={{ color: "var(--text)" }}>{e.event_title}</td>
                        <td className="px-2 py-2" style={{ color: "var(--text-dim)" }}>{e.currency} {e.platform_fee.toFixed(2)}</td>
                        <td className="px-2 py-2" style={{ color: "var(--text)", fontWeight: 500 }}>{e.currency} {e.earning_amount.toFixed(2)}</td>
                        <td className="px-2 py-2">
                          <span className="text-xs px-2 py-0.5 rounded-full" style={{
                            background: e.status === "paid" ? "rgba(46,204,113,0.15)" : "rgba(240,138,42,0.15)",
                            color: e.status === "paid" ? "#2ECC71" : "#F08A2A",
                          }}>{e.status}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}

function Field({ label, hint, children }) {
  return (
    <label className="block">
      <div className="text-xs uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>{label}</div>
      {children}
      {hint && <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>{hint}</div>}
    </label>
  );
}

function Stat({ icon, label, value, accent }) {
  return (
    <div className="rounded-xl border p-3" style={{ borderColor: "var(--border)" }}>
      <div className="text-[10px] uppercase tracking-widest inline-flex items-center gap-1" style={{ color: "var(--text-dim)" }}>{icon} {label}</div>
      <div className="text-lg font-medium mt-1" style={{ color: accent ? "#F08A2A" : "var(--text)" }}>{value}</div>
    </div>
  );
}

function fmtDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
  } catch { return "—"; }
}
