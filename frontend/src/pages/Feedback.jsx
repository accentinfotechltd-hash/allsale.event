import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Star, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

/**
 * Public feedback page reached from the post-event NPS email.
 * URL: /feedback/:bookingId
 *
 * Renders a 5-star widget + optional comment field. Submitting POSTs to
 * `/api/feedback/:bookingId` and shows a thank-you screen. Re-visiting after
 * already rating shows the existing rating with an option to update.
 */
export default function Feedback() {
  const { id } = useParams();
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [event, setEvent] = useState(null);
  const [existing, setExisting] = useState(null);
  const [stars, setStars] = useState(0);
  const [hover, setHover] = useState(0);
  const [comment, setComment] = useState("");
  const [name, setName] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/feedback/${id}`);
        setEvent(data.event);
        setExisting(data.existing);
        if (data.existing) {
          setStars(data.existing.stars);
          setComment(data.existing.comment || "");
          setName(data.existing.display_name || "");
        }
      } catch {
        setNotFound(true);
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  const submit = async (e) => {
    e.preventDefault();
    if (stars < 1) { toast.error("Pick at least 1 star"); return; }
    setSaving(true);
    try {
      await api.post(`/feedback/${id}`, {
        stars,
        comment: comment.trim() || undefined,
        display_name: name.trim() || undefined,
      });
      setSubmitted(true);
    } catch (err) {
      toast.error("Couldn't submit — please try again");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="container mx-auto px-6 py-20 text-center opacity-70">Loading…</div>;
  if (notFound) return (
    <div className="container mx-auto px-6 py-20 text-center">
      <div className="serif text-3xl mb-2">Feedback link not found</div>
      <Link to="/" style={{ color: "var(--accent)" }}>← Back to Allsale</Link>
    </div>
  );

  if (submitted) return (
    <div className="container mx-auto px-6 py-20 max-w-lg text-center" data-testid="feedback-thanks">
      <CheckCircle2 size={48} className="mx-auto mb-4" style={{ color: "var(--accent)" }} />
      <h1 className="serif text-3xl mb-2">Thanks for the feedback! ⭐</h1>
      <p className="opacity-70 mb-6">It really helps the organizer plan better events.</p>
      <Link to="/" className="inline-block px-5 py-2.5 rounded-full text-sm font-medium" style={{ background: "var(--accent)", color: "#0F2A3A" }}>
        Discover more events
      </Link>
    </div>
  );

  return (
    <div className="container mx-auto px-6 py-12 max-w-lg" data-testid="feedback-page">
      {event?.image_url && (
        <img src={event.image_url} alt="" className="w-full h-40 object-cover rounded-2xl mb-6" />
      )}
      <h1 className="serif text-3xl mb-1">How was {event?.title || "your event"}?</h1>
      <p className="opacity-70 text-sm mb-6">{event?.venue}, {event?.city}</p>

      <form onSubmit={submit} className="space-y-5">
        <div>
          <label className="text-xs uppercase tracking-widest opacity-70 block mb-3">Rating</label>
          <div className="flex gap-2 justify-center" data-testid="feedback-stars">
            {[1, 2, 3, 4, 5].map((star) => (
              <button
                key={star}
                type="button"
                onMouseEnter={() => setHover(star)}
                onMouseLeave={() => setHover(0)}
                onClick={() => setStars(star)}
                className="transition-transform hover:scale-110"
                aria-label={`${star} stars`}
                data-testid={`star-${star}`}
              >
                <Star
                  size={42}
                  fill={(hover || stars) >= star ? "#F08A2A" : "transparent"}
                  stroke={(hover || stars) >= star ? "#F08A2A" : "var(--text-muted)"}
                />
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="text-xs uppercase tracking-widest opacity-70 block mb-1">Comment <span className="opacity-60">(optional, shown publicly)</span></label>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            rows={3}
            maxLength={600}
            className="w-full rounded-lg border px-4 py-3 bg-transparent"
            style={{ borderColor: "var(--border)" }}
            placeholder="Best night of the year — sound was perfect…"
            data-testid="feedback-comment"
          />
        </div>

        <div>
          <label className="text-xs uppercase tracking-widest opacity-70 block mb-1">Display name <span className="opacity-60">(optional)</span></label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={80}
            className="w-full rounded-lg border px-4 py-3 bg-transparent"
            style={{ borderColor: "var(--border)" }}
            placeholder="e.g. Sarah from Auckland"
            data-testid="feedback-name"
          />
        </div>

        <button
          type="submit"
          disabled={saving || stars < 1}
          className="w-full px-5 py-3 rounded-full font-medium disabled:opacity-50"
          style={{ background: "var(--accent)", color: "#0F2A3A" }}
          data-testid="feedback-submit"
        >
          {saving ? "Submitting…" : existing ? "Update my rating" : "Submit feedback"}
        </button>
      </form>
    </div>
  );
}
