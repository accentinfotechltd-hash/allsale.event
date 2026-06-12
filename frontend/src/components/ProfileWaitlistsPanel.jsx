import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Bell, Clock, CheckCircle2, X } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

/**
 * Attendee-facing "My waitlists" panel for the Profile page.
 *
 * Shows every event the user is on a waitlist for, with their current state:
 *   – "Seat offered!" → green card with a Claim button (deep-links back to
 *     the event detail where the booking flow can take over).
 *   – "Waiting"      → muted card showing position-in-line.
 *
 * Hides itself entirely when there are no waitlist entries so the Profile
 * page stays clean for the majority of users who never queue.
 */
export default function ProfileWaitlistsPanel() {
  const [entries, setEntries] = useState(null);

  const load = async () => {
    try {
      const { data } = await api.get("/me/waitlist");
      setEntries(Array.isArray(data) ? data : []);
    } catch {
      setEntries([]);
    }
  };

  useEffect(() => { load(); }, []);

  if (!entries || entries.length === 0) return null;

  const leave = async (eventId) => {
    if (!window.confirm("Leave this waitlist? You won't be notified if a seat opens up.")) return;
    try {
      await api.delete(`/events/${eventId}/waitlist/me`);
      toast.success("Removed from waitlist");
      load();
    } catch {
      toast.error("Couldn't leave the waitlist");
    }
  };

  return (
    <>
      <h2 className="serif text-2xl mb-4" data-testid="profile-waitlists-heading">My waitlists</h2>
      <div className="grid md:grid-cols-2 gap-4 mb-12" data-testid="profile-waitlists-grid">
        {entries.map((e) => {
          const offered = e.status === "offered" && e.offer_expires_at && new Date(e.offer_expires_at) > new Date();
          const heroStyle = offered
            ? { background: "rgba(46,160,67,0.08)", border: "1px solid rgba(46,160,67,0.4)" }
            : { background: "var(--bg-card)", border: "1px solid var(--border)" };
          return (
            <div
              key={e.waitlist_id}
              className="rounded-2xl overflow-hidden flex"
              style={heroStyle}
              data-testid={`waitlist-entry-${e.waitlist_id}`}
            >
              <div className="w-24 relative shrink-0">
                {e.event_image && <img src={e.event_image} alt="" className="w-full h-full object-cover" />}
              </div>
              <div className="flex-1 p-4">
                <div className="serif text-lg leading-tight mb-1">{e.event_title || "Event"}</div>
                {offered ? (
                  <>
                    <div className="text-xs flex items-center gap-1 mb-2" style={{ color: "rgb(46,160,67)" }}>
                      <CheckCircle2 className="w-3 h-3" /> Seat offered — claim before {new Date(e.offer_expires_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
                    </div>
                    <Link
                      to={`/events/${e.event_id}`}
                      className="btn-primary !py-1.5 !px-3 text-xs"
                      data-testid={`claim-offer-${e.waitlist_id}`}
                    >
                      <Bell className="w-3 h-3" /> Claim my seat
                    </Link>
                  </>
                ) : (
                  <>
                    <div className="text-xs flex items-center gap-1 mb-2" style={{ color: "var(--text-muted)" }}>
                      <Clock className="w-3 h-3" /> Waiting{typeof e.position === "number" ? ` · #${e.position} in line` : ""}
                    </div>
                    <div className="flex gap-2">
                      <Link
                        to={`/events/${e.event_id}`}
                        className="btn-ghost !py-1.5 !px-3 text-xs"
                        data-testid={`waitlist-view-${e.waitlist_id}`}
                      >
                        View event
                      </Link>
                      <button
                        onClick={() => leave(e.event_id)}
                        className="btn-ghost !py-1.5 !px-3 text-xs"
                        style={{ color: "var(--text-dim)" }}
                        data-testid={`waitlist-leave-${e.waitlist_id}`}
                      >
                        <X className="w-3 h-3" /> Leave
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
