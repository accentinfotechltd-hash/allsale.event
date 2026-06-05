import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Calendar, MapPin, Mail, Users } from "lucide-react";

import api from "../lib/api";
import { useAuth } from "../lib/auth";
import EventCard from "../components/EventCard";
import { ContactOrganizerButton } from "../components/ContactOrganizerDialog";

/**
 * Public organizer profile page at /organizer/:id.
 * - Shows organizer's display name, picture, bio, and stats
 * - Lists their upcoming approved events
 * - "Contact organizer" button opens the message dialog
 */
export default function OrganizerProfile() {
  const { id } = useParams();
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setNotFound(false);
      try {
        const { data } = await api.get(`/organizers/${id}`);
        setData(data);
      } catch (err) {
        if (err?.response?.status === 404) setNotFound(true);
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" data-testid="organizer-profile-loading">
        <p style={{ color: "var(--text-muted)" }}>Loading organizer…</p>
      </div>
    );
  }

  if (notFound || !data) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6" data-testid="organizer-profile-not-found">
        <div className="text-center max-w-sm">
          <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>404</div>
          <h1 className="serif text-3xl mb-3">Organizer not found</h1>
          <p className="text-sm mb-6" style={{ color: "var(--text-muted)" }}>
            This organizer may have removed their profile, or the link is broken.
          </p>
          <Link to="/events" className="btn-primary">Browse events</Link>
        </div>
      </div>
    );
  }

  const { organizer, upcoming_events: upcoming } = data;
  const joined = organizer.joined_at ? new Date(organizer.joined_at).toLocaleDateString(undefined, { year: "numeric", month: "long" }) : null;

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-12" data-testid="organizer-profile-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start gap-6 mb-12">
        {organizer.picture ? (
          <img
            src={organizer.picture}
            alt={organizer.name}
            className="w-24 h-24 sm:w-32 sm:h-32 rounded-2xl object-cover flex-shrink-0"
            style={{ border: "1px solid var(--border)" }}
          />
        ) : (
          <div
            className="w-24 h-24 sm:w-32 sm:h-32 rounded-2xl flex items-center justify-center flex-shrink-0 serif text-4xl"
            style={{ background: "var(--bg-card)", border: "1px solid var(--border)", color: "var(--accent)" }}
          >
            {(organizer.name || "?").charAt(0).toUpperCase()}
          </div>
        )}

        <div className="flex-1 min-w-0">
          <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>
            Organizer
          </div>
          <h1 className="serif text-4xl sm:text-5xl mb-3" data-testid="organizer-name">
            {organizer.name}
          </h1>

          <div className="flex flex-wrap gap-4 text-sm mb-4" style={{ color: "var(--text-muted)" }}>
            <span className="flex items-center gap-1.5">
              <Calendar className="w-4 h-4" /> {organizer.total_events} event{organizer.total_events === 1 ? "" : "s"} hosted
            </span>
            {joined && (
              <span className="flex items-center gap-1.5">
                <Users className="w-4 h-4" /> Joined {joined}
              </span>
            )}
          </div>

          {organizer.bio && (
            <p className="text-base mb-5 max-w-prose" style={{ color: "var(--text)" }} data-testid="organizer-bio">
              {organizer.bio}
            </p>
          )}

          <ContactOrganizerButton
            organizerId={organizer.user_id}
            organizerName={organizer.name}
            user={user}
            className="btn-primary"
            label="Contact organizer"
            testid="organizer-profile-contact-btn"
          />
        </div>
      </div>

      {/* Upcoming events */}
      <div>
        <h2 className="serif text-3xl mb-2">Upcoming events</h2>
        <p className="text-sm mb-6" style={{ color: "var(--text-muted)" }}>
          {upcoming.length === 0
            ? "No upcoming events listed right now — check back soon."
            : `${upcoming.length} event${upcoming.length === 1 ? "" : "s"} on sale.`}
        </p>

        {upcoming.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="organizer-events-grid">
            {upcoming.map((e) => (
              <EventCard key={e.event_id} ev={e} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
