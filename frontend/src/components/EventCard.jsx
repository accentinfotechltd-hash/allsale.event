import { Link } from "react-router-dom";
import { MapPin, Star, Flame, Calendar } from "lucide-react";
import { formatMoney } from "@/lib/currencies";
import { flagForCountry } from "@/lib/countries";

export default function EventCard({ event, index = 0 }) {
  const date = new Date(event.date);
  // Compact, all-caps date — matches the reference cards: "FRI, JUL 03RD 2026 07:30 PM".
  // We fall back to a clean en-US fallback when toLocale* returns junk on
  // older mobile webviews.
  const dateLine = (() => {
    if (Number.isNaN(date.getTime())) return "DATE TBA";
    try {
      const weekday = date.toLocaleDateString("en-US", { weekday: "short" }).toUpperCase();
      const month = date.toLocaleDateString("en-US", { month: "short" }).toUpperCase();
      const day = String(date.getDate()).padStart(2, "0");
      const year = date.getFullYear();
      const time = date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
      return `${weekday}, ${month} ${day}, ${year} · ${time}`;
    } catch {
      return date.toUTCString();
    }
  })();
  // Compute the lowest VALID positive price for the badge. We deliberately
  // separate three cases here:
  //   - At least one positive tier/seat price → show "from $X"
  //   - Every configured price is exactly 0      → show "Free" (organizer's choice)
  //   - No tiers configured AND no seat price   → show "TBA" (price not set yet)
  // The old code conflated the last two and made unfinished events look free.
  const seatPrice = Number(event.seat_price);
  const tierPrices = (event.tiers || [])
    .map((t) => Number(t.price))
    .filter((p) => !Number.isNaN(p));
  const configuredPrices = event.has_seatmap
    ? (Number.isFinite(seatPrice) ? [seatPrice] : [])
    : tierPrices;
  const positivePrices = configuredPrices.filter((p) => p > 0);
  const minPrice = positivePrices.length > 0 ? Math.min(...positivePrices) : 0;
  const priceState =
    positivePrices.length > 0 ? "price"
    : configuredPrices.length > 0 ? "free"
    : "tba";
  const currency = event.currency || "NZD";

  return (
    <Link
      to={`/events/${event.event_id}`}
      className="card-event fade-up block group"
      style={{ animationDelay: `${index * 0.05}s`, opacity: event.is_past ? 0.7 : 1 }}
      data-testid={`event-card-${event.event_id}`}
    >
      {/* POSTER — keeps its natural composition. No text overlay on the
          poster itself so the organizer's design isn't fighting with our
          chrome. Badges (Featured/Trending/Past) sit on a subtle top
          scrim so they're readable but don't dominate. */}
      <div className="relative aspect-[4/5] overflow-hidden">
        <img
          src={event.image_url}
          alt={event.title}
          className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
          style={event.is_past ? { filter: "grayscale(0.6)" } : undefined}
        />
        {/* Top scrim only (about 25%), purely for badge legibility — the
            poster art below stays clean. */}
        <div className="absolute inset-x-0 top-0 h-1/4 bg-gradient-to-b from-black/55 to-transparent pointer-events-none" />
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
      </div>

      {/* TEXT BLOCK — sits cleanly below the poster. Reads top-to-bottom:
          price headline → date/venue → title → organizer & promoters. */}
      <div className="p-4">
        {/* Price block */}
        {priceState === "price" && (
          <div className="mb-2">
            <div
              className="text-[10px] uppercase tracking-widest"
              style={{ color: "var(--text-muted)" }}
            >
              Starts from
            </div>
            <div
              className="serif text-2xl leading-tight"
              style={{ color: "var(--accent)" }}
              data-testid={`event-card-price-${event.event_id}`}
            >
              {formatMoney(minPrice, currency, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          </div>
        )}
        {priceState === "free" && (
          <div className="mb-2">
            <div
              className="serif text-2xl leading-tight"
              style={{ color: "var(--accent)" }}
              data-testid={`event-card-price-${event.event_id}`}
            >
              Free
            </div>
          </div>
        )}
        {priceState === "tba" && (
          <div className="mb-2">
            <div
              className="serif text-xl leading-tight opacity-80"
              style={{ color: "var(--text-muted)" }}
              data-testid={`event-card-price-${event.event_id}`}
              title="Tickets not yet on sale"
            >
              TBA
            </div>
          </div>
        )}

        {/* Date / time */}
        <div
          className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider mb-3"
          style={{ color: "var(--text-muted)" }}
          data-testid={`event-card-date-${event.event_id}`}
        >
          <Calendar className="w-3 h-3 flex-shrink-0" aria-hidden />
          <span className="truncate">{dateLine}</span>
        </div>

        {/* Title */}
        <h3 className="serif text-xl leading-tight mb-2 line-clamp-2 group-hover:text-[color:var(--accent)] transition-colors">{event.title}</h3>

        {/* Venue */}
        <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--text-muted)" }}>
          <MapPin className="w-3 h-3" />
          <span className="truncate">{event.venue} · {event.city}</span>
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
