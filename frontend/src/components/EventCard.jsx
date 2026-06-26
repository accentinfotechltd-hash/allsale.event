import { Link } from "react-router-dom";
import { MapPin, Star, Flame } from "lucide-react";
import { formatMoney } from "@/lib/currencies";
import { flagForCountry } from "@/lib/countries";

export default function EventCard({ event, index = 0 }) {
  const date = new Date(event.date);
  const dateStr = date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  const minPrice = event.has_seatmap
    ? event.seat_price
    : Math.min(...(event.tiers || []).map((t) => t.price));
  const currency = event.currency || "NZD";

  return (
    <Link
      to={`/events/${event.event_id}`}
      className="card-event fade-up block group"
      style={{ animationDelay: `${index * 0.05}s`, opacity: event.is_past ? 0.7 : 1 }}
      data-testid={`event-card-${event.event_id}`}
    >
      <div className="relative aspect-[4/5] overflow-hidden">
        <img
          src={event.image_url}
          alt={event.title}
          className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
          style={event.is_past ? { filter: "grayscale(0.6)" } : undefined}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent" />
        <div className="absolute top-3 left-3 flex flex-col gap-1.5 items-start">
          <span className="chip chip-accent" style={{ fontSize: "0.65rem" }}>{event.category}</span>
          {event.is_past && (
            <span
              data-testid={`past-badge-${event.event_id}`}
              className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase tracking-widest font-medium backdrop-blur-md"
              style={{ background: "rgba(255,255,255,0.85)", color: "#222" }}
            >
              Past event
            </span>
          )}
          {event.is_boosted && (
            <span
              data-testid={`trending-badge-${event.event_id}`}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] uppercase tracking-widest font-medium backdrop-blur-md"
              style={{ background: "linear-gradient(90deg, #FF6B35, #F08A2A)", color: "#FFFFFF" }}
              title="Trending — boosted by the organizer"
            >
              <Flame className="w-2.5 h-2.5 fill-current" />
              Trending
            </span>
          )}
          {event.featured && (
            <span
              data-testid={`featured-badge-${event.event_id}`}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] uppercase tracking-widest font-medium backdrop-blur-md"
              style={{ background: "rgba(255,255,255,0.95)", color: "#111" }}
              title="Featured — handpicked by Allsale"
            >
              <Star className="w-2.5 h-2.5 fill-current" />
              Featured
            </span>
          )}
          {!event.is_past && event.waitlist_count > 0 && (
            <span
              data-testid={`waitlist-count-${event.event_id}`}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] uppercase tracking-widest font-medium backdrop-blur-md"
              style={{ background: "rgba(240, 138, 42, 0.95)", color: "#FFFFFF" }}
            >
              {event.waitlist_count} waiting
            </span>
          )}
          {event.avg_stars && event.reviews_count > 0 && (
            <span
              data-testid={`rating-badge-${event.event_id}`}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium backdrop-blur-md"
              style={{ background: "rgba(0,0,0,0.6)", color: "#FFD66E" }}
              title={`Average rating ${event.avg_stars} from ${event.reviews_count} reviews`}
            >
              <Star className="w-2.5 h-2.5 fill-current" />
              <span className="text-white">{event.avg_stars}</span>
              <span className="text-white/70">({event.reviews_count})</span>
            </span>
          )}
        </div>
        <div className="absolute bottom-3 left-3 right-3 flex items-end justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>{dateStr}</div>
          </div>
          <div className="text-right">
            {minPrice > 0 && (
              <div className="text-[10px] uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>from</div>
            )}
            <div
              className="serif text-2xl leading-none"
              style={{ color: "var(--accent)" }}
              data-testid={`event-card-price-${event.event_id}`}
            >
              {formatMoney(minPrice, currency, { minimumFractionDigits: 0, maximumFractionDigits: 0, free: true })}
            </div>
          </div>
        </div>
      </div>
      <div className="p-4">
        <h3 className="serif text-xl leading-tight mb-1 line-clamp-2 group-hover:text-[color:var(--accent)] transition-colors">{event.title}</h3>
        <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--text-muted)" }}>
          <MapPin className="w-3 h-3" />
          {event.venue} · {event.city}
          {event.country && (
            <span className="ml-1" title={event.country} data-testid={`event-flag-${event.event_id}`}>{flagForCountry(event.country)}</span>
          )}
        </div>

        {(event.organizer_name || (event.featured_creators && event.featured_creators.length > 0)) && (
          <div className="mt-3 pt-3 border-t flex items-center justify-between gap-2" style={{ borderColor: "var(--border)" }} data-testid={`event-card-faces-${event.event_id}`}>
            {event.organizer_name && (
              <div className="flex items-center gap-1.5 min-w-0">
                {event.organizer_picture ? (
                  <img
                    src={event.organizer_picture}
                    alt={event.organizer_name}
                    className="w-5 h-5 rounded-full object-cover flex-shrink-0"
                    onError={(e) => { e.currentTarget.style.display = "none"; }}
                  />
                ) : (
                  <div className="w-5 h-5 rounded-full grid place-items-center text-[10px] font-medium flex-shrink-0" style={{ background: "var(--accent)", color: "#000" }}>
                    {event.organizer_name[0]?.toUpperCase()}
                  </div>
                )}
                <span className="text-[11px] truncate" style={{ color: "var(--text-muted)" }} title={`Organized by ${event.organizer_name}`}>
                  {event.organizer_name}
                </span>
              </div>
            )}
            {event.featured_creators && event.featured_creators.length > 0 && (
              <div className="flex items-center -space-x-2 flex-shrink-0" title={`Promoted by ${event.featured_creators.map(c => c.display_name).filter(Boolean).join(", ")}`} data-testid={`event-card-creators-${event.event_id}`}>
                {event.featured_creators.slice(0, 3).map((c) => (
                  <div
                    key={c.creator_id}
                    className="w-5 h-5 rounded-full border-2 overflow-hidden flex-shrink-0"
                    style={{ borderColor: "var(--bg-card, #111)", background: "var(--accent)" }}
                  >
                    {c.avatar_url ? (
                      <img src={c.avatar_url} alt={c.display_name || ""} className="w-full h-full object-cover" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                    ) : (
                      <div className="w-full h-full grid place-items-center text-[9px] font-semibold" style={{ color: "#000" }}>
                        {(c.display_name || "?")[0]?.toUpperCase()}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </Link>
  );
}
