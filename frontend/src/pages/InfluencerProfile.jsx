import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Instagram, Music, Twitter, Youtube, Users, MapPin, MousePointerClick, Megaphone, ExternalLink } from "lucide-react";
import api from "@/lib/api";

const SOCIAL_URL = {
  instagram: (h) => `https://instagram.com/${h}`,
  tiktok: (h) => `https://tiktok.com/@${h}`,
  twitter: (h) => `https://twitter.com/${h}`,
  youtube: (h) => `https://youtube.com/@${h}`,
};

export default function InfluencerProfile() {
  const { id } = useParams();
  const [profile, setProfile] = useState(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/influencers/${id}`);
        setProfile(data);
      } catch {
        setNotFound(true);
      }
    })();
  }, [id]);

  if (notFound) return (
    <div className="container mx-auto px-6 py-20 text-center">
      <div className="serif text-3xl mb-2">Creator not found</div>
      <Link to="/influencers" className="text-sm" style={{ color: "var(--accent)" }}>← Back to marketplace</Link>
    </div>
  );
  if (!profile) return <div className="container mx-auto px-6 py-20 text-center opacity-70">Loading…</div>;

  const h = profile.social_handles || {};
  return (
    <div className="container mx-auto px-6 py-10 max-w-3xl" data-testid="influencer-profile">
      <Link to="/influencers" className="text-sm opacity-70 hover:opacity-100">← Marketplace</Link>
      <div className="flex items-center gap-5 mt-6 mb-6 flex-wrap">
        {profile.avatar_url ? (
          <img src={profile.avatar_url} alt="" className="w-24 h-24 rounded-full object-cover" data-testid="profile-avatar" />
        ) : (
          <div className="w-24 h-24 rounded-full grid place-items-center text-4xl font-medium" style={{ background: "var(--accent)", color: "#000" }}>
            {profile.display_name?.[0] || "?"}
          </div>
        )}
        <div>
          <h1 className="serif text-4xl" data-testid="profile-name">{profile.display_name}</h1>
          {profile.city && <div className="opacity-70 mt-1 inline-flex items-center gap-1"><MapPin size={14} /> {profile.city}</div>}
        </div>
      </div>

      {profile.bio && <p className="text-lg opacity-90 mb-6 max-w-prose">{profile.bio}</p>}

      <div className="grid grid-cols-3 gap-3 mb-8">
        <Stat icon={Users} label="Followers" value={Number(profile.follower_count_total || 0).toLocaleString()} />
        <Stat icon={Megaphone} label="Campaigns" value={profile.stats?.campaigns_total || 0} />
        <Stat icon={MousePointerClick} label="Clicks driven" value={profile.stats?.total_clicks_driven || 0} />
      </div>

      {profile.categories?.length > 0 && (
        <div className="mb-6">
          <div className="text-xs uppercase opacity-60 mb-2">Categories</div>
          <div className="flex flex-wrap gap-2">
            {profile.categories.map((c) => (
              <span key={c} className="px-3 py-1 rounded-full text-sm" style={{ background: "rgba(255,79,0,0.1)", color: "var(--accent)" }}>{c}</span>
            ))}
          </div>
        </div>
      )}

      <div className="mb-8">
        <div className="text-xs uppercase opacity-60 mb-2">Find them on</div>
        <div className="flex flex-wrap gap-3">
          {Object.entries(h).map(([k, v]) => v ? (
            <a key={k} href={SOCIAL_URL[k]?.(v)} target="_blank" rel="noopener noreferrer"
              data-testid={`profile-social-${k}`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm hover:opacity-80"
              style={{ borderColor: "var(--border)" }}>
              {k === "instagram" && <Instagram size={14} />}
              {k === "tiktok" && <Music size={14} />}
              {k === "twitter" && <Twitter size={14} />}
              {k === "youtube" && <Youtube size={14} />}
              @{v}
              <ExternalLink size={11} className="opacity-50" />
            </a>
          ) : null)}
        </div>
      </div>

      <div className="rounded-xl border p-6" style={{ background: "var(--surface)", borderColor: "var(--border)" }}>
        <div className="font-medium mb-1">Want to partner with {profile.display_name?.split(" ")[0]}?</div>
        <p className="text-sm opacity-70 mb-3">Open your event's affiliate program from the organizer dashboard, and any creator can join with one click.</p>
        <Link to="/organizer" className="inline-block px-4 py-2 rounded-lg text-sm font-medium" style={{ background: "var(--accent)", color: "#000" }}>
          Go to organizer dashboard
        </Link>
      </div>
    </div>
  );
}

function Stat({ icon: Icon, label, value }) {
  return (
    <div className="rounded-xl border p-4" style={{ background: "var(--surface)", borderColor: "var(--border)" }}>
      <div className="flex items-center gap-2 text-xs uppercase tracking-wider opacity-60">
        <Icon size={12} /> <span>{label}</span>
      </div>
      <div className="serif text-2xl mt-1">{value}</div>
    </div>
  );
}
