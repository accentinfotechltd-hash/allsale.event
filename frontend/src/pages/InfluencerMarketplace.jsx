import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Search, Users, Instagram, Music, Twitter, Youtube, MapPin } from "lucide-react";
import api from "@/lib/api";

const CATS = ["", "music", "comedy", "sports", "tech", "food", "art", "fitness", "nightlife", "family"];

export default function InfluencerMarketplace() {
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ category: "", city: "", min_followers: 0 });

  const load = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filters.category) params.set("category", filters.category);
      if (filters.city) params.set("city", filters.city);
      if (filters.min_followers) params.set("min_followers", String(filters.min_followers));
      const { data } = await api.get(`/influencers?${params.toString()}`);
      setList(data || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []); // eslint-disable-line

  return (
    <div className="container mx-auto px-6 py-10 max-w-6xl" data-testid="influencer-marketplace">
      <h1 className="serif text-4xl sm:text-5xl mb-3">Creator marketplace</h1>
      <p className="opacity-70 mb-8 max-w-2xl">Browse Allsale's roster of event promoters, ambassadors and creators. Reach out to partner with them on your next event.</p>

      <div className="flex flex-wrap gap-3 mb-8" data-testid="marketplace-filters">
        <select
          value={filters.category}
          onChange={(e) => setFilters({ ...filters, category: e.target.value })}
          className="rounded-lg border px-3 py-2 text-sm bg-transparent"
          style={{ borderColor: "var(--border)" }}
          data-testid="filter-category"
        >
          {CATS.map((c) => <option key={c} value={c} style={{ background: "var(--surface)" }}>{c || "All categories"}</option>)}
        </select>
        <input
          placeholder="City"
          value={filters.city}
          onChange={(e) => setFilters({ ...filters, city: e.target.value })}
          className="rounded-lg border px-3 py-2 text-sm bg-transparent"
          style={{ borderColor: "var(--border)" }}
          data-testid="filter-city"
        />
        <input
          type="number"
          min="0"
          placeholder="Min followers"
          value={filters.min_followers || ""}
          onChange={(e) => setFilters({ ...filters, min_followers: Number(e.target.value) || 0 })}
          className="rounded-lg border px-3 py-2 text-sm bg-transparent w-36"
          style={{ borderColor: "var(--border)" }}
          data-testid="filter-min-followers"
        />
        <button
          onClick={load}
          className="px-4 py-2 rounded-lg text-sm font-medium inline-flex items-center gap-2"
          style={{ background: "var(--accent)", color: "#000" }}
          data-testid="filter-apply"
        >
          <Search size={14} /> Search
        </button>
      </div>

      {loading ? (
        <div className="opacity-70">Loading creators…</div>
      ) : list.length === 0 ? (
        <div className="rounded-xl border p-10 text-center opacity-70" style={{ background: "var(--surface)", borderColor: "var(--border)" }}>
          No creators match those filters yet.
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {list.map((p) => (
            <Card key={p.user_id} profile={p} />
          ))}
        </div>
      )}
    </div>
  );
}

function Card({ profile }) {
  const h = profile.social_handles || {};
  return (
    <Link
      to={`/influencers/${profile.user_id}`}
      className="rounded-xl border p-5 block hover:opacity-90 transition-opacity"
      style={{ background: "var(--surface)", borderColor: "var(--border)" }}
      data-testid={`creator-${profile.user_id}`}
    >
      <div className="flex items-center gap-3 mb-3">
        {profile.avatar_url ? (
          <img src={profile.avatar_url} alt="" className="w-12 h-12 rounded-full object-cover" />
        ) : (
          <div className="w-12 h-12 rounded-full grid place-items-center text-lg font-medium" style={{ background: "var(--accent)", color: "#000" }}>
            {profile.display_name?.[0] || "?"}
          </div>
        )}
        <div>
          <div className="font-medium">{profile.display_name}</div>
          {profile.city && <div className="text-xs opacity-60 flex items-center gap-1"><MapPin size={10} /> {profile.city}</div>}
        </div>
      </div>
      {profile.bio && <p className="text-sm opacity-80 line-clamp-2 mb-3">{profile.bio}</p>}
      <div className="flex items-center gap-3 text-xs opacity-70">
        <span className="inline-flex items-center gap-1"><Users size={12} /> {Number(profile.follower_count_total || 0).toLocaleString()}</span>
        {h.instagram && <Instagram size={12} />}
        {h.tiktok && <Music size={12} />}
        {h.twitter && <Twitter size={12} />}
        {h.youtube && <Youtube size={12} />}
      </div>
      {profile.categories?.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-3">
          {profile.categories.slice(0, 3).map((c) => (
            <span key={c} className="px-2 py-0.5 rounded-full text-xs" style={{ background: "rgba(255,79,0,0.1)", color: "var(--accent)" }}>{c}</span>
          ))}
        </div>
      )}
    </Link>
  );
}
