import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Flame, ChevronLeft, ChevronRight, ArrowRight, Calendar, MapPin } from "lucide-react";
import api from "@/lib/api";
import { formatMoney } from "@/lib/currencies";

/**
 * TrendingCarousel — horizontal-scrolling rail of currently-boosted events.
 * Mounted on the landing page right under FeatureShowcase. Renders nothing
 * when there are zero live boosts, keeping the page tidy on quiet days.
 *
 * Visual choices:
 *   • Bigger tiles than the regular grid (350px wide) so it feels premium
 *   • Heat-gradient header echoing the 🔥 Trending pill on the cards
 *   • Native overflow-x scroll + arrow buttons (no animation library
 *     dependency; smooth-scroll via scrollBy)
 */
export default function TrendingCarousel() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const scrollerRef = useRef(null);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/events/trending");
        setEvents(data || []);
      } catch {
        setEvents([]);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return null;
  if (!events.length) return null; // hide section entirely when no boosts

  const scroll = (dx) => {
    scrollerRef.current?.scrollBy({ left: dx, behavior: "smooth" });
  };

  return (
    <section className="max-w-7xl mx-auto px-6 py-16" data-testid="trending-carousel-section">
      <div className="flex items-end justify-between mb-6">
        <div>
          <div
            className="inline-flex items-center gap-1.5 text-xs uppercase tracking-[0.3em] mb-2 px-2.5 py-1 rounded-full"
            style={{
              background: "linear-gradient(90deg, rgba(255,107,53,0.18), rgba(240,138,42,0.06))",
              color: "#F08A2A",
            }}
          >
            <Flame size={11} className="fill-current" /> Trending this week
          </div>
          <h2 className="serif text-4xl">Boosted by their organizers right now</h2>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
            Hand-picked moments — fresh boosts surface here for 72 hours.
          </p>
        </div>
        <div className="hidden md:flex items-center gap-2">
          <button
            onClick={() => scroll(-380)}
            className="p-2 rounded-full border hover:opacity-80"
            style={{ borderColor: "var(--border)" }}
            data-testid="trending-scroll-left"
            aria-label="Previous"
          >
            <ChevronLeft size={14} />
          </button>
          <button
            onClick={() => scroll(380)}
            className="p-2 rounded-full border hover:opacity-80"
            style={{ borderColor: "var(--border)" }}
            data-testid="trending-scroll-right"
            aria-label="Next"
          >
            <ChevronRight size={14} />
          </button>
          <Link
            to="/events?trending=1"
            className="ml-2 inline-flex items-center gap-1 text-sm hover:opacity-80"
            style={{ color: "var(--text-muted)" }}
            data-testid="see-all-trending"
          >
            See all <ArrowRight size={12} />
          </Link>
        </div>
      </div>

      <div
        ref={scrollerRef}
        className="flex gap-4 overflow-x-auto pb-3 snap-x snap-mandatory -mx-6 px-6"
        style={{ scrollbarWidth: "none" }}
        data-testid="trending-scroller"
      >
        {events.map((e, i) => (
          <TrendingTile key={e.event_id} event={e} index={i} />
        ))}
      </div>
    </section>
  );
}

function TrendingTile({ event, index }) {
  const lowestPrice = (() => {
    if (event.has_seatmap && event.seat_price) return event.seat_price;
    const tiers = event.tiers || [];
    if (!tiers.length) return null;
    return Math.min(...tiers.map((t) => Number(t.price) || 0));
  })();

  return (
    <Link
      to={`/events/${event.event_id}`}
      className="group relative flex-shrink-0 w-[330px] snap-start rounded-2xl overflow-hidden border fade-up"
      style={{ borderColor: "var(--border)", animationDelay: `${index * 0.05}s` }}
      data-testid={`trending-tile-${event.event_id}`}
    >
      <div className="relative h-[200px] overflow-hidden">
        <img
          src={event.image_url}
          alt={event.title}
          className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
        />
        <div
          className="absolute inset-0"
          style={{ background: "linear-gradient(180deg, rgba(0,0,0,0) 50%, rgba(0,0,0,0.65) 100%)" }}
        />
        <div className="absolute top-3 left-3 flex gap-1.5">
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] uppercase tracking-widest font-medium"
            style={{ background: "linear-gradient(90deg, #FF6B35, #F08A2A)", color: "#FFFFFF" }}
          >
            <Flame className="w-2.5 h-2.5 fill-current" /> Trending
          </span>
          {event.avg_stars && event.reviews_count > 0 && (
            <span
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium backdrop-blur-md"
              style={{ background: "rgba(0,0,0,0.55)", color: "#FFD66E" }}
            >
              ★ <span className="text-white">{event.avg_stars}</span>
            </span>
          )}
        </div>
        {lowestPrice != null && (
          <div
            className="absolute bottom-3 right-3 px-2.5 py-1 rounded-full text-xs font-medium backdrop-blur-md"
            style={{ background: "rgba(0,0,0,0.65)", color: "#FFFFFF" }}
          >
            {lowestPrice > 0 ? `From ${formatMoney(lowestPrice, event.currency)}` : "Free"}
          </div>
        )}
      </div>
      <div className="p-4">
        <div className="font-medium text-base truncate mb-2" data-testid={`trending-title-${event.event_id}`}>
          {event.title}
        </div>
        <div className="flex items-center gap-3 text-xs" style={{ color: "var(--text-muted)" }}>
          <span className="inline-flex items-center gap-1">
            <Calendar size={11} />
            {event.date ? new Date(event.date).toLocaleDateString(undefined, { day: "numeric", month: "short" }) : "TBA"}
          </span>
          <span className="inline-flex items-center gap-1 truncate">
            <MapPin size={11} /> {event.city}
          </span>
        </div>
      </div>
    </Link>
  );
}
