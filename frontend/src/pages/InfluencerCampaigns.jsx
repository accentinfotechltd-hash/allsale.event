import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Calendar, MapPin, Sparkles } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function InfluencerCampaigns() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);

  const reload = async () => {
    try {
      const { data } = await api.get("/influencer/campaigns/available");
      setList(data);
    } catch (err) {
      if (err?.response?.status === 404) { nav("/influencer/onboarding"); return; }
      toast.error("Couldn't load campaigns");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!user) { nav("/login"); return; }
    reload();
  }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

  const join = async (eventId) => {
    try {
      const { data } = await api.post("/influencer/campaigns/join", { event_id: eventId });
      toast.success(`Joined! Your code: ${data.code}`);
      reload();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't join campaign");
    }
  };

  return (
    <div className="container mx-auto px-6 py-10 max-w-6xl" data-testid="influencer-campaigns">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="serif text-4xl sm:text-5xl">Open campaigns</h1>
          <p className="opacity-70 mt-2">Events accepting creators right now. Join with one click — get a trackable link instantly.</p>
        </div>
        <Link to="/influencer" className="px-3 py-2 rounded-lg text-sm border" style={{ borderColor: "var(--border)" }}>← Back to hub</Link>
      </div>

      {loading ? (
        <div className="opacity-70">Loading…</div>
      ) : list.length === 0 ? (
        <div className="rounded-xl border p-10 text-center" style={{ background: "var(--surface)", borderColor: "var(--border)" }}>
          <Sparkles size={32} className="mx-auto opacity-50 mb-3" />
          <div className="opacity-80">No open campaigns right now — check back soon, or message an organizer to open theirs.</div>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="campaigns-grid">
          {list.map((ev) => (
            <div key={ev.event_id} className="rounded-xl border overflow-hidden" style={{ background: "var(--surface)", borderColor: "var(--border)" }} data-testid={`avail-${ev.event_id}`}>
              {ev.cover_image_url && <img src={ev.cover_image_url} alt="" className="w-full h-40 object-cover" />}
              <div className="p-4">
                <div className="font-medium">{ev.title}</div>
                <div className="text-xs opacity-60 mt-1 flex flex-col gap-0.5">
                  <span className="inline-flex items-center gap-1"><Calendar size={12} /> {ev.starts_at ? new Date(ev.starts_at).toLocaleDateString() : "TBD"}</span>
                  {ev.city && <span className="inline-flex items-center gap-1"><MapPin size={12} /> {ev.city}</span>}
                </div>
                <div className="mt-3 text-sm">
                  Commission: <span style={{ color: "var(--accent)" }}>{ev.default_commission_pct}%</span>
                </div>
                <button
                  onClick={() => join(ev.event_id)}
                  data-testid={`join-${ev.event_id}`}
                  className="mt-3 w-full px-3 py-2 rounded-lg text-sm font-medium"
                  style={{ background: "var(--accent)", color: "#000" }}
                >
                  Join campaign
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
