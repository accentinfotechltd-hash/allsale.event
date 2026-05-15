import { Link } from "react-router-dom";
import { Calendar, MapPin } from "lucide-react";

export default function EventCard({ event, index = 0 }) {
  const date = new Date(event.date);
  const dateStr = date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  const minPrice = event.has_seatmap
    ? event.seat_price
    : Math.min(...(event.tiers || []).map((t) => t.price));

  return (
    <Link
      to={`/events/${event.event_id}`}
      className="card-event fade-up block group"
      style={{ animationDelay: `${index * 0.05}s` }}
      data-testid={`event-card-${event.event_id}`}
    >
      <div className="relative aspect-[4/5] overflow-hidden">
        <img
          src={event.image_url}
          alt={event.title}
          className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent" />
        <div className="absolute top-3 left-3 flex flex-col gap-1.5 items-start">
          <span className="chip chip-accent" style={{ fontSize: "0.65rem" }}>{event.category}</span>
          {event.waitlist_count > 0 && (
            <span
              data-testid={`waitlist-count-${event.event_id}`}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] uppercase tracking-widest font-medium backdrop-blur-md"
              style={{ background: "rgba(255,79,0,0.92)", color: "#000" }}
            >
              {event.waitlist_count} waiting
            </span>
          )}
        </div>
        <div className="absolute bottom-3 left-3 right-3 flex items-end justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>{dateStr}</div>
          </div>
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>from</div>
            <div className="serif text-2xl leading-none" style={{ color: "var(--accent)" }}>${minPrice}</div>
          </div>
        </div>
      </div>
      <div className="p-4">
        <h3 className="serif text-xl leading-tight mb-1 line-clamp-2 group-hover:text-[color:var(--accent)] transition-colors">{event.title}</h3>
        <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--text-muted)" }}>
          <MapPin className="w-3 h-3" />
          {event.venue} · {event.city}
        </div>
      </div>
    </Link>
  );
}
