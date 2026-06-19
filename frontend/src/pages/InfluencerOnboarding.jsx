import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles, Instagram, Music, Twitter, Youtube, Facebook } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";

const CATEGORY_OPTIONS = ["music", "comedy", "sports", "tech", "food", "art", "fitness", "nightlife", "family"];

export default function InfluencerOnboarding() {
  const { user, loading: authLoading } = useAuth();
  const nav = useNavigate();
  const [loading, setLoading] = useState(false);
  const [existing, setExisting] = useState(null);
  const [form, setForm] = useState({
    display_name: "",
    bio: "",
    follower_count_total: "",
    city: "",
    categories: [],
    social_handles: { instagram: "", tiktok: "", twitter: "", youtube: "", facebook: "" },
  });

  useEffect(() => {
    if (authLoading) return;
    if (!user) { nav("/login"); return; }
    (async () => {
      try {
        const { data } = await api.get("/influencer/me");
        if (data?.enabled) {
          setExisting(data);
          setForm({
            display_name: data.display_name || user.name || "",
            bio: data.bio || "",
            follower_count_total: data.follower_count_total || "",
            city: data.city || "",
            categories: data.categories || [],
            social_handles: {
              instagram: data.social_handles?.instagram || "",
              tiktok: data.social_handles?.tiktok || "",
              twitter: data.social_handles?.twitter || "",
              youtube: data.social_handles?.youtube || "",
              facebook: data.social_handles?.facebook || "",
            },
          });
        } else {
          setForm((f) => ({ ...f, display_name: user.name || "" }));
        }
      } catch {
        setForm((f) => ({ ...f, display_name: user?.name || "" }));
      }
    })();
  }, [user, authLoading, nav]);

  const toggleCategory = (cat) => {
    setForm((f) => ({
      ...f,
      categories: f.categories.includes(cat)
        ? f.categories.filter((c) => c !== cat)
        : [...f.categories, cat],
    }));
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!form.display_name.trim()) { toast.error("Display name is required"); return; }
    setLoading(true);
    try {
      await api.post("/influencer/enable", {
        ...form,
        follower_count_total: Number(form.follower_count_total) || 0,
      });
      toast.success(existing ? "Profile updated!" : "Welcome to the creator program! 🎉");
      nav("/influencer");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't save profile");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container mx-auto px-6 py-10 max-w-3xl" data-testid="influencer-onboarding">
      <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs mb-3" style={{ background: "rgba(255,79,0,0.1)", color: "var(--accent)" }}>
        <Sparkles size={12} /> CREATOR PROGRAM
      </div>
      <h1 className="serif text-4xl sm:text-5xl mb-3">
        {existing ? "Edit your creator profile" : "Become an Allsale creator"}
      </h1>
      <p className="opacity-70 mb-8 max-w-xl">
        Earn 10% commission (or more) on every ticket sold through your unique link. Promote events you love.
        Get paid monthly via Stripe. No minimum followers required.
      </p>

      <form onSubmit={submit} className="space-y-5">
        <div>
          <label className="text-sm opacity-80 block mb-1">Display name *</label>
          <input
            data-testid="onboard-display-name"
            value={form.display_name}
            onChange={(e) => setForm({ ...form, display_name: e.target.value })}
            className="w-full rounded-lg border px-4 py-3 bg-transparent"
            style={{ borderColor: "var(--border)" }}
            placeholder="Your stage / brand name"
            required
          />
        </div>

        <div>
          <label className="text-sm opacity-80 block mb-1">Short bio</label>
          <textarea
            data-testid="onboard-bio"
            value={form.bio}
            onChange={(e) => setForm({ ...form, bio: e.target.value })}
            rows={3}
            maxLength={600}
            className="w-full rounded-lg border px-4 py-3 bg-transparent"
            style={{ borderColor: "var(--border)" }}
            placeholder="What kind of events do you promote? (max 600 chars)"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="text-sm opacity-80 block mb-1">Total followers across platforms</label>
            <input
              data-testid="onboard-followers"
              type="number"
              min="0"
              value={form.follower_count_total}
              onChange={(e) => setForm({ ...form, follower_count_total: e.target.value })}
              className="w-full rounded-lg border px-4 py-3 bg-transparent"
              style={{ borderColor: "var(--border)" }}
              placeholder="e.g. 25000"
            />
          </div>
          <div>
            <label className="text-sm opacity-80 block mb-1">City</label>
            <input
              data-testid="onboard-city"
              value={form.city}
              onChange={(e) => setForm({ ...form, city: e.target.value })}
              className="w-full rounded-lg border px-4 py-3 bg-transparent"
              style={{ borderColor: "var(--border)" }}
              placeholder="Auckland"
            />
          </div>
        </div>

        <div>
          <label className="text-sm opacity-80 block mb-2">Social handles (without the @)</label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Handle icon={Instagram} placeholder="Instagram" value={form.social_handles.instagram} onChange={(v) => setForm({ ...form, social_handles: { ...form.social_handles, instagram: v } })} testid="onboard-instagram" />
            <Handle icon={Music} placeholder="TikTok" value={form.social_handles.tiktok} onChange={(v) => setForm({ ...form, social_handles: { ...form.social_handles, tiktok: v } })} testid="onboard-tiktok" />
            <Handle icon={Twitter} placeholder="X / Twitter" value={form.social_handles.twitter} onChange={(v) => setForm({ ...form, social_handles: { ...form.social_handles, twitter: v } })} testid="onboard-twitter" />
            <Handle icon={Youtube} placeholder="YouTube" value={form.social_handles.youtube} onChange={(v) => setForm({ ...form, social_handles: { ...form.social_handles, youtube: v } })} testid="onboard-youtube" />
            <Handle icon={Facebook} placeholder="Facebook" value={form.social_handles.facebook} onChange={(v) => setForm({ ...form, social_handles: { ...form.social_handles, facebook: v } })} testid="onboard-facebook" />
          </div>
        </div>

        <div>
          <label className="text-sm opacity-80 block mb-2">Categories you cover (pick up to 5)</label>
          <div className="flex flex-wrap gap-2">
            {CATEGORY_OPTIONS.map((c) => (
              <button
                type="button"
                key={c}
                data-testid={`onboard-cat-${c}`}
                onClick={() => toggleCategory(c)}
                disabled={!form.categories.includes(c) && form.categories.length >= 5}
                className={`px-3 py-1.5 rounded-full text-sm border transition-all ${form.categories.includes(c) ? "" : "opacity-60 hover:opacity-100"}`}
                style={{
                  background: form.categories.includes(c) ? "var(--accent)" : "transparent",
                  color: form.categories.includes(c) ? "#000" : "var(--text)",
                  borderColor: form.categories.includes(c) ? "var(--accent)" : "var(--border)",
                }}
              >
                {c}
              </button>
            ))}
          </div>
        </div>

        <button
          type="submit"
          disabled={loading}
          data-testid="onboard-submit"
          className="w-full sm:w-auto px-6 py-3 rounded-lg font-medium disabled:opacity-50"
          style={{ background: "var(--accent)", color: "#000" }}
        >
          {loading ? "Saving…" : existing ? "Save changes" : "Create my creator profile →"}
        </button>
      </form>
    </div>
  );
}

function Handle({ icon: Icon, placeholder, value, onChange, testid }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border px-3 py-2" style={{ borderColor: "var(--border)" }}>
      <Icon size={16} className="opacity-60" />
      <input
        data-testid={testid}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="flex-1 bg-transparent text-sm focus:outline-none"
      />
    </div>
  );
}
