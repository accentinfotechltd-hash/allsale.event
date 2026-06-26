/**
 * CreatorSpotlight — landing-page strip showcasing enrolled Allsale creators.
 *
 * Pulls the public `/api/influencers` marketplace list, ranks by follower
 * count, and renders the top six as a row of avatar+bio mini-cards. Includes
 * a primary CTA for newcomers to join as a creator. Renders nothing if no
 * creators have enrolled yet — keeps the page clean during cold-start.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Sparkles, Users, ArrowRight, Megaphone } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function CreatorSpotlight() {
  const [creators, setCreators] = useState([]);
  const [loading, setLoading] = useState(true);
  const { user } = useAuth();

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/influencers?limit=12");
        setCreators(Array.isArray(data) ? data : []);
      } catch {
        setCreators([]);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // Show the section even with zero creators IF the visitor isn't an
  // enrolled creator already — the "join" CTA is the whole point of being
  // on the landing page. Only suppress when 0 creators AND the visitor IS
  // a creator (because they don't need a recruitment pitch).
  const isEnrolledCreator = !!user?.is_influencer;
  if (loading) return null;
  if (creators.length === 0 && isEnrolledCreator) return null;

  const targetUrl = isEnrolledCreator ? "/influencer" : "/influencer/onboarding";
  const ctaLabel = isEnrolledCreator ? "Go to creator hub" : "Become a creator";

  return (
    <section className="max-w-7xl mx-auto px-4 sm:px-6 pb-16" data-testid="creator-spotlight">
      <div
        className="rounded-3xl border p-6 sm:p-10 relative overflow-hidden"
        style={{
          borderColor: "var(--border)",
          background:
            "linear-gradient(135deg, rgba(255,79,0,0.10), transparent 55%), var(--bg-card)",
        }}
      >
        <div className="flex items-end justify-between flex-wrap gap-6 mb-8">
          <div className="max-w-xl">
            <div
              className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs uppercase tracking-[0.25em] mb-3"
              style={{ background: "rgba(255,79,0,0.12)", color: "var(--accent)" }}
            >
              <Sparkles size={12} /> Creator program
            </div>
            <h2 className="serif text-3xl sm:text-4xl leading-tight mb-3">
              Join Allsale&apos;s creator network
            </h2>
            <p className="text-sm sm:text-base" style={{ color: "var(--text)" }}>
              Promoters, comedians, DJs, influencers — earn commission on every ticket sold through
              your unique link. Free to enrol, no follower minimums, paid via Stripe.
            </p>
          </div>
          <div className="flex gap-2 flex-wrap">
            <Link
              to={targetUrl}
              className="btn-primary !py-2.5 !px-5 text-sm"
              data-testid="spotlight-cta-primary"
            >
              {ctaLabel} <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              to="/influencers"
              className="btn-ghost !py-2.5 !px-5 text-sm"
              data-testid="spotlight-cta-browse"
            >
              Browse all creators
            </Link>
          </div>
        </div>

        {creators.length > 0 ? (
          <div
            className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3"
            data-testid="spotlight-creators-grid"
          >
            {creators.slice(0, 6).map((c) => (
              <Link
                key={c.user_id}
                to={`/influencers/${c.user_id}`}
                className="rounded-xl border p-3 flex flex-col items-center text-center transition hover:-translate-y-0.5 hover:shadow-sm"
                style={{ background: "var(--surface)", borderColor: "var(--border)" }}
                data-testid={`spotlight-creator-${c.user_id}`}
              >
                {c.avatar_url ? (
                  <img
                    src={c.avatar_url}
                    alt={c.display_name}
                    className="w-16 h-16 rounded-full object-cover mb-2 border-2"
                    style={{ borderColor: "var(--accent)" }}
                    onError={(e) => { e.currentTarget.style.display = "none"; }}
                  />
                ) : (
                  <div
                    className="w-16 h-16 rounded-full grid place-items-center text-xl font-semibold mb-2 border-2"
                    style={{ background: "var(--accent)", color: "#000", borderColor: "var(--accent)" }}
                  >
                    {(c.display_name || "?")[0]?.toUpperCase()}
                  </div>
                )}
                <div className="text-sm font-medium truncate w-full" title={c.display_name}>
                  {c.display_name}
                </div>
                {c.follower_count_total > 0 && (
                  <div className="text-[11px] opacity-70 inline-flex items-center gap-1 mt-1">
                    <Users size={10} />
                    {Number(c.follower_count_total).toLocaleString()}
                  </div>
                )}
                {c.categories?.[0] && (
                  <div
                    className="mt-2 px-2 py-0.5 rounded-full text-[10px] uppercase tracking-wider"
                    style={{ background: "rgba(255,79,0,0.10)", color: "var(--accent)" }}
                  >
                    {c.categories[0]}
                  </div>
                )}
              </Link>
            ))}
          </div>
        ) : (
          <div
            className="rounded-xl border p-8 text-center"
            style={{ borderColor: "var(--border-strong)", background: "var(--bg-elev)" }}
            data-testid="spotlight-empty-state"
          >
            <Megaphone className="w-8 h-8 mx-auto mb-3" style={{ color: "var(--accent)" }} />
            <div className="font-medium mb-1">Be the first creator on Allsale</div>
            <div className="text-sm" style={{ color: "var(--text-muted)" }}>
              Sign up now and own the spotlight on day one.
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
