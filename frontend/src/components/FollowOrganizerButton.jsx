import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Heart, HeartOff, Loader2, Users } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useNavigate } from "react-router-dom";

/**
 * Compact follow/unfollow button used on event detail pages and organizer
 * public profile pages. Self-fetches initial state via
 * `/api/organizers/{id}/follow`.
 *
 * Props:
 *   organizerId   (required)
 *   organizerName (optional, for toasts)
 *   showCount     (default: true) — render follower count to the right
 *   size          ("sm" | "md") — defaults to "md"
 */
export default function FollowOrganizerButton({
  organizerId,
  organizerName,
  showCount = true,
  size = "md",
}) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [following, setFollowing] = useState(false);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // Unauthenticated users get a public count via the organizer page
        // endpoint; logged-in users get both state + count.
        const url = user ? `/organizers/${organizerId}/follow` : `/organizers/${organizerId}/public`;
        const { data } = await api.get(url);
        if (cancelled) return;
        if (user) {
          setFollowing(!!data.following);
          setCount(data.follower_count || 0);
        } else {
          setFollowing(false);
          setCount(data.follower_count || 0);
        }
      } catch {
        // Silently fall back to a zero state.
        if (!cancelled) setCount(0);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [organizerId, user]);

  const toggle = async () => {
    if (!user) {
      navigate("/login");
      return;
    }
    setSubmitting(true);
    try {
      const { data } = following
        ? await api.delete(`/organizers/${organizerId}/follow`)
        : await api.post(`/organizers/${organizerId}/follow`);
      setFollowing(data.following);
      setCount(data.follower_count || 0);
      toast.success(data.following ? `Following ${organizerName || "organizer"}` : "Unfollowed");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Couldn't update follow state");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return null;

  const isSm = size === "sm";

  return (
    <div className="inline-flex items-center gap-2" data-testid={`follow-${organizerId}`}>
      <button
        onClick={toggle}
        disabled={submitting}
        className={`${following ? "btn-ghost" : "btn-primary"} ${isSm ? "!py-1 !px-2.5 text-xs" : "!py-1.5 !px-3.5 text-sm"} flex items-center gap-1.5`}
        data-testid={following ? "unfollow-btn" : "follow-btn"}
      >
        {submitting ? (
          <Loader2 className={`${isSm ? "w-3 h-3" : "w-3.5 h-3.5"} animate-spin`} />
        ) : following ? (
          <HeartOff className={isSm ? "w-3 h-3" : "w-3.5 h-3.5"} />
        ) : (
          <Heart className={isSm ? "w-3 h-3" : "w-3.5 h-3.5"} />
        )}
        {following ? "Following" : "Follow"}
      </button>
      {showCount && (
        <span className="text-xs flex items-center gap-1" style={{ color: "var(--text-dim)" }} data-testid="follower-count">
          <Users className="w-3 h-3" /> {count}
        </span>
      )}
    </div>
  );
}
