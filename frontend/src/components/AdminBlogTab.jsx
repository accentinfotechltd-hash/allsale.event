import { useEffect, useState } from "react";
import { Plus, Pencil, Trash2, Eye, FileText, ExternalLink, Send } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import RichTextEditor from "@/components/RichTextEditor";
import ImageUploader from "@/components/ImageUploader";
import NewsletterUnsubscribeReasons from "@/components/NewsletterUnsubscribeReasons";

/**
 * AdminBlogTab — admin CMS for /blog.
 *
 * Lists all posts (draft + published) with inline status controls and an
 * editor drawer for creating / editing. Body is the same WYSIWYG editor used
 * for event descriptions so admins don't learn a new tool.
 */
export default function AdminBlogTab() {
  const [posts, setPosts] = useState([]);
  const [editing, setEditing] = useState(null); // null | {slug?:string, ...payload}
  const [subs, setSubs] = useState(null); // {total, active, items}

  const load = async () => {
    try {
      const { data } = await api.get("/admin/blog");
      setPosts(data || []);
    } catch (e) {
      toast.error("Couldn't load posts");
    }
  };
  const loadSubs = async () => {
    try {
      const { data } = await api.get("/admin/newsletter/subscribers?limit=200");
      setSubs(data);
    } catch { /* hide section if it fails */ }
  };
  useEffect(() => { load(); loadSubs(); }, []);

  const removeSub = async (email) => {
    if (!window.confirm(`Remove ${email}?`)) return;
    try {
      await api.delete(`/admin/newsletter/subscribers/${encodeURIComponent(email)}`);
      toast.success("Removed");
      loadSubs();
    } catch { toast.error("Couldn't remove"); }
  };

  const exportCsv = () => {
    if (!subs?.items?.length) { toast.error("No subscribers yet"); return; }
    const rows = [["email", "source", "status", "created_at"]];
    subs.items.forEach((s) => rows.push([s.email, s.source || "", s.status || "", s.created_at || ""]));
    const csv = rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `allsale-blog-subscribers-${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const startNew = () => {
    setEditing({
      slug: null,
      title: "",
      excerpt: "",
      cover_url: "",
      body_html: "",
      tags: [],
      status: "draft",
      meta_title: "",
      meta_description: "",
    });
  };

  const startEdit = async (slug) => {
    try {
      const { data } = await api.get(`/admin/blog/${slug}`);
      setEditing(data);
    } catch (_e) { toast.error("Couldn't load post"); }
  };

  const handleDelete = async (slug) => {
    if (!window.confirm("Delete this post permanently? This cannot be undone.")) return;
    try {
      await api.delete(`/admin/blog/${slug}`);
      toast.success("Post deleted");
      load();
    } catch (_e) { toast.error("Delete failed"); }
  };

  const togglePublish = async (post) => {
    const nextStatus = post.status === "published" ? "draft" : "published";
    try {
      await api.put(`/admin/blog/${post.slug}`, { status: nextStatus });
      toast.success(nextStatus === "published" ? "Published" : "Unpublished");
      load();
    } catch (_e) { toast.error("Status update failed"); }
  };

  const notifySubscribers = async (post) => {
    const activeCount = subs?.active || 0;
    if (activeCount === 0) {
      toast.error("No active subscribers yet — share /blog to get the first ones.");
      return;
    }
    if (!window.confirm(`Send "${post.title}" to ${activeCount} subscriber${activeCount === 1 ? "" : "s"}? Anyone already notified for this post will be skipped.`)) return;
    const t = toast.loading("Fanning out the post...");
    try {
      const { data } = await api.post(`/admin/blog/${post.slug}/notify-subscribers`);
      if (data.sent === 0 && data.skipped > 0) {
        toast.success(`Already sent to all ${data.skipped} subscriber${data.skipped === 1 ? "" : "s"}.`, { id: t });
      } else {
        toast.success(`Sent to ${data.sent}${data.failed ? ` (${data.failed} failed)` : ""}${data.skipped ? `, skipped ${data.skipped} already notified` : ""}.`, { id: t });
      }
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Couldn't send", { id: t });
    }
  };

  return (
    <div className="space-y-4" data-testid="admin-blog-tab">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-serif" style={{ color: "var(--text)" }}>Blog</h2>
          <p className="text-sm" style={{ color: "var(--text-dim)" }}>
            Write SEO-rich stories that turn search traffic into organizer signups.
          </p>
        </div>
        <button onClick={startNew} className="btn-primary" data-testid="admin-blog-new-btn">
          <Plus size={14} /> New post
        </button>
      </div>

      {posts.length === 0 ? (
        <div className="text-sm py-10 text-center rounded-xl border" style={{ borderColor: "var(--border)", color: "var(--text-dim)" }} data-testid="admin-blog-empty">
          No posts yet. Create your first to start ranking.
        </div>
      ) : (
        <div className="rounded-xl border overflow-hidden" style={{ borderColor: "var(--border)" }}>
          <table className="w-full text-sm">
            <thead style={{ background: "var(--bg-soft, transparent)", color: "var(--text-dim)" }}>
              <tr className="text-left">
                <th className="px-4 py-3 font-medium">Title</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Updated</th>
                <th className="px-4 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {posts.map((p) => (
                <tr key={p.slug} className="border-t" style={{ borderColor: "var(--border)" }} data-testid={`admin-blog-row-${p.slug}`}>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <FileText size={14} style={{ color: "var(--text-dim)" }} />
                      <div>
                        <div style={{ color: "var(--text)" }}>{p.title}</div>
                        <div className="text-xs" style={{ color: "var(--text-dim)" }}>/blog/{p.slug}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => togglePublish(p)}
                      className="text-xs px-2 py-1 rounded-full"
                      style={{
                        background: p.status === "published" ? "rgba(34,197,94,0.12)" : "rgba(240,138,42,0.12)",
                        color: p.status === "published" ? "#22c55e" : "#F08A2A",
                      }}
                      data-testid={`admin-blog-toggle-${p.slug}`}
                    >
                      {p.status === "published" ? "Published" : "Draft"}
                    </button>
                  </td>
                  <td className="px-4 py-3" style={{ color: "var(--text-dim)" }}>{fmtDate(p.updated_at)}</td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex items-center gap-1">
                      {p.status === "published" && (
                        <>
                          <button
                            onClick={() => notifySubscribers(p)}
                            className="p-2 rounded hover:bg-black/5"
                            title="Email this post to newsletter subscribers"
                            style={{ color: "var(--accent)" }}
                            data-testid={`admin-blog-notify-${p.slug}`}
                          >
                            <Send size={14} />
                          </button>
                          <a href={`/blog/${p.slug}`} target="_blank" rel="noreferrer" className="p-2 rounded hover:bg-black/5" title="View live" data-testid={`admin-blog-view-${p.slug}`}>
                            <ExternalLink size={14} />
                          </a>
                        </>
                      )}
                      <button onClick={() => startEdit(p.slug)} className="p-2 rounded hover:bg-black/5" title="Edit" data-testid={`admin-blog-edit-${p.slug}`}>
                        <Pencil size={14} />
                      </button>
                      <button onClick={() => handleDelete(p.slug)} className="p-2 rounded hover:bg-black/5" title="Delete" style={{ color: "#ef4444" }} data-testid={`admin-blog-delete-${p.slug}`}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing && <PostEditor draft={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}

      {subs && (
        <div className="mt-8 rounded-xl border" style={{ borderColor: "var(--border)" }} data-testid="admin-blog-subscribers">
          <div className="flex items-center justify-between p-4 border-b" style={{ borderColor: "var(--border)" }}>
            <div>
              <div className="text-xs uppercase tracking-widest" style={{ color: "var(--accent)" }}>Newsletter</div>
              <div className="font-serif text-lg" style={{ color: "var(--text)" }}>
                {subs.active} active <span style={{ color: "var(--text-dim)", fontWeight: 400 }}>· {subs.total} total</span>
              </div>
            </div>
            <button onClick={exportCsv} className="btn-ghost text-xs" data-testid="admin-blog-subs-export">
              Export CSV
            </button>
          </div>
          {subs.items.length === 0 ? (
            <div className="p-4 text-sm" style={{ color: "var(--text-dim)" }}>No subscribers yet — the form is live on /blog.</div>
          ) : (
            <table className="w-full text-sm">
              <thead style={{ color: "var(--text-dim)" }}>
                <tr className="text-left">
                  <th className="px-4 py-2 font-medium">Email</th>
                  <th className="px-4 py-2 font-medium">Source</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Joined</th>
                  <th className="px-4 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {subs.items.slice(0, 100).map((s) => (
                  <tr key={s.email} className="border-t" style={{ borderColor: "var(--border)" }} data-testid={`subscriber-${s.email}`}>
                    <td className="px-4 py-2" style={{ color: "var(--text)" }}>{s.email}</td>
                    <td className="px-4 py-2" style={{ color: "var(--text-dim)" }}>{s.source || "—"}</td>
                    <td className="px-4 py-2">
                      <span
                        className="text-xs px-2 py-0.5 rounded-full"
                        style={{
                          background: s.status === "active" ? "rgba(34,197,94,0.12)" : "rgba(231,76,60,0.12)",
                          color: s.status === "active" ? "#22c55e" : "#E74C3C",
                        }}
                      >
                        {s.status}
                      </span>
                    </td>
                    <td className="px-4 py-2" style={{ color: "var(--text-dim)" }}>{fmtDate(s.created_at)}</td>
                    <td className="px-4 py-2 text-right">
                      <button onClick={() => removeSub(s.email)} className="text-xs" style={{ color: "#ef4444" }} data-testid={`subscriber-remove-${s.email}`}>
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Why-people-unsubscribe widget — surfaces feedback so admin can iterate on cadence/content */}
      <NewsletterUnsubscribeReasons />
    </div>
  );
}

function PostEditor({ draft, onClose, onSaved }) {
  const [form, setForm] = useState(draft);
  const [saving, setSaving] = useState(false);
  const isNew = !draft.slug;

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async (statusOverride) => {
    const payload = { ...form };
    if (statusOverride) payload.status = statusOverride;
    if (!payload.title?.trim()) { toast.error("Title is required"); return; }
    if (!payload.body_html?.trim()) { toast.error("Body is required"); return; }
    setSaving(true);
    try {
      if (isNew) {
        const { data } = await api.post("/admin/blog", payload);
        toast.success(payload.status === "published" ? "Published!" : "Draft saved");
        onSaved(data);
      } else {
        await api.put(`/admin/blog/${form.slug}`, payload);
        toast.success(payload.status === "published" ? "Published!" : "Saved");
        onSaved();
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      style={{ background: "rgba(15,42,58,0.55)" }}
      onClick={onClose}
    >
      <div
        className="h-full w-full max-w-3xl overflow-y-auto p-6"
        style={{ background: "var(--bg, #ffffff)", borderLeft: "1px solid var(--border)" }}
        onClick={(e) => e.stopPropagation()}
        data-testid="admin-blog-editor"
      >
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="text-xs uppercase tracking-widest" style={{ color: "var(--accent)" }}>
              {isNew ? "New post" : "Edit post"}
            </div>
            <h3 className="text-2xl font-serif" style={{ color: "var(--text)" }}>{form.title || "Untitled"}</h3>
          </div>
          <button onClick={onClose} className="text-sm" style={{ color: "var(--text-dim)" }}>Close</button>
        </div>

        <div className="space-y-4">
          <Field label="Title">
            <input
              type="text"
              value={form.title}
              onChange={(e) => update("title", e.target.value)}
              placeholder="A killer headline (60 chars max for best SEO)"
              data-testid="blog-editor-title"
              className="w-full"
            />
          </Field>

          <Field label="Excerpt" hint="1-2 sentence summary shown on the index card and meta description fallback (160 chars).">
            <textarea
              rows={3}
              value={form.excerpt || ""}
              onChange={(e) => update("excerpt", e.target.value)}
              placeholder="Hook the reader in one or two sentences."
              data-testid="blog-editor-excerpt"
              className="w-full"
            />
          </Field>

          <Field label="Cover image" hint="16:9 hero image used on the blog index card + OG share preview.">
            <ImageUploader
              value={form.cover_url}
              onUploaded={(url) => update("cover_url", url)}
              label="Drop cover image or click to upload"
              aspect="16/9"
              testid="blog-editor-cover"
            />
          </Field>

          <Field label="Tags" hint="Comma-separated. Used for related-posts grouping.">
            <input
              type="text"
              value={(form.tags || []).join(", ")}
              onChange={(e) => update("tags", e.target.value.split(",").map((t) => t.trim()).filter(Boolean))}
              placeholder="organizers, marketing, nz events"
              data-testid="blog-editor-tags"
              className="w-full"
            />
          </Field>

          <Field label="Body">
            <RichTextEditor
              value={form.body_html}
              onChange={(html) => update("body_html", html)}
              placeholder="Write your post. Use headings to break up sections — Google loves H2s."
              testid="blog-editor-body"
            />
          </Field>

          <details className="rounded-lg border p-3" style={{ borderColor: "var(--border)" }}>
            <summary className="text-sm cursor-pointer" style={{ color: "var(--text-muted)" }}>SEO meta overrides (optional)</summary>
            <div className="mt-3 space-y-3">
              <Field label="Meta title" hint="Defaults to post title.">
                <input
                  type="text"
                  value={form.meta_title || ""}
                  onChange={(e) => update("meta_title", e.target.value)}
                  placeholder="Custom <title> tag"
                  className="w-full"
                  data-testid="blog-editor-meta-title"
                />
              </Field>
              <Field label="Meta description" hint="Defaults to excerpt.">
                <textarea
                  rows={2}
                  value={form.meta_description || ""}
                  onChange={(e) => update("meta_description", e.target.value)}
                  placeholder="Custom search-result snippet"
                  className="w-full"
                  data-testid="blog-editor-meta-desc"
                />
              </Field>
            </div>
          </details>
        </div>

        <div className="sticky bottom-0 mt-8 pt-4 border-t flex justify-end gap-2" style={{ borderColor: "var(--border)", background: "var(--bg, #ffffff)" }}>
          <button onClick={() => save("draft")} disabled={saving} className="btn-ghost" data-testid="blog-editor-save-draft">
            Save draft
          </button>
          <button onClick={() => save("published")} disabled={saving} className="btn-primary" data-testid="blog-editor-publish">
            {form.status === "published" ? "Save & keep live" : "Publish"}
          </button>
        </div>
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

function fmtDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  } catch { return "—"; }
}
