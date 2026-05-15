import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Check, X, Star } from "lucide-react";
import { toast } from "sonner";

export default function Admin() {
  const { user } = useAuth();
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

  if (!user || user.role !== "admin") {
    return <div className="text-center py-20" style={{ color: "var(--text-muted)" }}>Admin access required.</div>;
  }

  const pending = events.filter((e) => e.status === "pending");
  const approved = events.filter((e) => e.status === "approved");

  return (
    <div className="max-w-7xl mx-auto px-6 py-12">
      <div className="mb-10">
        <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>Admin</div>
        <h1 className="serif text-5xl">Moderation</h1>
      </div>

      <Section title="Pending approval" events={pending} act={act} showApprove />
      <Section title="Approved events" events={approved} act={act} showFeature />
    </div>
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
                <div className="flex gap-2">
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
