import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Megaphone, TrendingUp, MousePointerClick, Users, DollarSign,
  ExternalLink, Sparkles, Tag, Calendar, Wallet,
} from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";

const Stat = ({ icon: Icon, label, value, accent, testid }) => (
  <div
    className="rounded-xl border p-5"
    style={{ background: "var(--surface)", borderColor: "var(--border)" }}
    data-testid={testid}
  >
    <div className="flex items-center gap-2 text-xs uppercase tracking-wider opacity-70">
      <Icon size={14} />
      <span>{label}</span>
    </div>
    <div className="serif text-3xl mt-2" style={{ color: accent || "var(--text)" }}>{value}</div>
  </div>
);

export default function InfluencerHub() {
  const { user, loading: authLoading } = useAuth();
  const nav = useNavigate();
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState(null);
  const [dash, setDash] = useState(null);
  const [myCodes, setMyCodes] = useState({ items: [], summary: { codes_total: 0, earnings_paid_total: 0, earnings_unpaid_total: 0 } });

  useEffect(() => {
    if (authLoading) return;
    if (!user) { nav("/login"); return; }
    (async () => {
      try {
        const { data: prof } = await api.get("/influencer/me");
        if (!prof?.enabled) { nav("/influencer/onboarding"); return; }
        setProfile(prof);
        const [{ data }, { data: codes }] = await Promise.all([
          api.get("/influencer/dashboard"),
          api.get("/influencer/my-codes").catch(() => ({ data: { items: [], summary: {} } })),
        ]);
        setDash(data);
        setMyCodes(codes || { items: [], summary: {} });
      } catch (e) {
        // not enabled or error → onboarding
        nav("/influencer/onboarding");
      } finally {
        setLoading(false);
      }
    })();
  }, [user, authLoading, nav]);

  if (loading) return <div className="container mx-auto px-6 py-20 text-center opacity-70">Loading creator hub…</div>;
  if (!dash) return null;

  const s = dash.summary;
  const cs = myCodes.summary || {};
  // Combine campaign + code earnings into a single "pending payout" headline so
  // the creator sees ONE number that reflects everything they've earned.
  const pendingAll = (s.pending_payout || 0) + (cs.earnings_unpaid_total || 0);

  return (
    <div className="container mx-auto px-6 py-10 max-w-6xl" data-testid="influencer-hub">
      <div className="flex items-start justify-between gap-4 flex-wrap mb-8">
        <div className="flex items-center gap-4 flex-wrap">
          {profile?.avatar_url ? (
            <img
              src={profile.avatar_url}
              alt=""
              className="w-16 h-16 rounded-full object-cover border-2"
              style={{ borderColor: "var(--accent)" }}
              data-testid="hub-avatar"
            />
          ) : null}
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs" style={{ background: "rgba(255,79,0,0.1)", color: "var(--accent)" }}>
              <Sparkles size={12} /> CREATOR HUB
            </div>
            <h1 className="serif text-4xl sm:text-5xl mt-3" data-testid="influencer-hub-title">
              Welcome back, {profile?.display_name?.split(" ")[0] || "Creator"}
            </h1>
            <p className="opacity-70 mt-2">Drive ticket sales. Earn commission. Get paid via Stripe.</p>
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Link to="/influencer/onboarding" data-testid="hub-edit-profile" className="px-4 py-2 rounded-lg text-sm font-medium border" style={{ borderColor: "var(--border)" }}>
            Edit profile
          </Link>
          <Link to="/influencer/campaigns" data-testid="hub-browse-campaigns" className="px-4 py-2 rounded-lg text-sm font-medium" style={{ background: "var(--accent)", color: "#000" }}>
            Browse campaigns →
          </Link>
          <Link to="/influencer/payouts" data-testid="hub-payouts" className="px-4 py-2 rounded-lg text-sm font-medium border" style={{ borderColor: "var(--border)" }}>
            Payouts
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
        <Stat icon={MousePointerClick} label="Clicks driven" value={s.total_clicks} testid="stat-clicks" />
        <Stat icon={Users} label="Tickets sold" value={s.total_conversions} testid="stat-conversions" />
        <Stat icon={TrendingUp} label="Conversion rate" value={`${s.conversion_rate_pct}%`} testid="stat-conv-rate" />
        <Stat
          icon={DollarSign}
          label="Pending payout"
          value={`$${pendingAll.toFixed(2)}`}
          accent="var(--accent)"
          testid="stat-pending"
        />
      </div>

      {!profile.stripe_payouts_ready && (
        <div className="rounded-xl border p-5 mb-8 flex items-center justify-between flex-wrap gap-3" style={{ background: "rgba(255,79,0,0.05)", borderColor: "rgba(255,79,0,0.3)" }}>
          <div>
            <div className="font-medium">Connect Stripe to receive payouts</div>
            <div className="text-sm opacity-70 mt-1">Your earnings are tracked but can&apos;t be paid out until you complete a 5-min KYC flow with Stripe.</div>
          </div>
          <Link to="/influencer/payouts" className="px-4 py-2 rounded-lg text-sm font-medium" style={{ background: "var(--accent)", color: "#000" }} data-testid="connect-stripe-cta">
            Connect Stripe
          </Link>
        </div>
      )}

      {/* Admin-assigned promo codes — show only if the creator has any */}
      {myCodes.items.length > 0 && (
        <section className="mb-10" data-testid="my-codes-section">
          <div className="flex items-end justify-between mb-4 flex-wrap gap-2">
            <div>
              <h2 className="serif text-2xl">Your promo codes</h2>
              <p className="text-sm opacity-70 mt-1">
                Codes the Allsale team has set up for you. Share them — buyers get a discount, you earn commission.
              </p>
            </div>
            <div className="text-sm opacity-80 flex items-center gap-2">
              <Wallet size={14} style={{ color: "var(--accent)" }} />
              <span>
                Unpaid earnings:{" "}
                <strong style={{ color: "var(--accent)" }}>
                  ${(cs.earnings_unpaid_total || 0).toFixed(2)}
                </strong>
              </span>
            </div>
          </div>
          <div className="space-y-3">
            {myCodes.items.map((c) => <CreatorCodeRow key={c.code_id} code={c} />)}
          </div>
        </section>
      )}

      <h2 className="serif text-2xl mb-4">Your campaigns</h2>
      {dash.campaigns.length === 0 ? (
        <div className="rounded-xl border p-10 text-center" style={{ background: "var(--surface)", borderColor: "var(--border)" }}>
          <Megaphone size={32} className="mx-auto opacity-50 mb-3" />
          <div className="opacity-80 mb-4">No self-joined campaigns yet. Browse open events and join one to get your trackable link.</div>
          <Link to="/influencer/campaigns" className="inline-block px-4 py-2 rounded-lg text-sm font-medium" style={{ background: "var(--accent)", color: "#000" }}>
            Find campaigns
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {dash.campaigns.map((c) => (
            <CampaignRow key={c.affiliate_id} campaign={c} />
          ))}
        </div>
      )}
    </div>
  );
}

function CampaignRow({ campaign }) {
  const [copied, setCopied] = useState(false);
  const origin = typeof window !== "undefined" ? window.location.origin : "https://www.allsale.events";
  const link = `${origin}/api/affiliate/track?code=${encodeURIComponent(campaign.code)}&event_id=${encodeURIComponent(campaign.event_id || "")}`;
  const ev = campaign.event || {};
  return (
    <div className="rounded-xl border p-4 flex items-center gap-4 flex-wrap" style={{ background: "var(--surface)", borderColor: "var(--border)" }} data-testid={`campaign-${campaign.code}`}>
      {ev.cover_image_url && <img src={ev.cover_image_url} alt="" className="w-20 h-20 rounded-lg object-cover" />}
      <div className="flex-1 min-w-[200px]">
        <div className="font-medium">{ev.title || "Event"}</div>
        <div className="text-xs opacity-60 mt-1">Code: <span className="font-mono">{campaign.code}</span> · {campaign.commission_pct}% commission</div>
        <div className="grid grid-cols-3 gap-3 mt-3 text-sm">
          <div><span className="opacity-60">Clicks</span> <span className="ml-1">{campaign.clicks || 0}</span></div>
          <div><span className="opacity-60">Sales</span> <span className="ml-1">{campaign.conversions || 0}</span></div>
          <div><span className="opacity-60">Earned</span> <span className="ml-1" style={{ color: "var(--accent)" }}>${campaign.commission_owed?.toFixed(2)}</span></div>
        </div>
      </div>
      <div className="flex gap-2 flex-shrink-0">
        <button
          onClick={() => { navigator.clipboard?.writeText(link); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
          className="px-3 py-2 rounded-lg text-sm border"
          style={{ borderColor: "var(--border)" }}
          data-testid={`copy-link-${campaign.code}`}
        >
          {copied ? "✓ Copied!" : "Copy link"}
        </button>
        {ev.event_id && (
          <Link to={`/events/${ev.event_id}`} className="px-3 py-2 rounded-lg text-sm border inline-flex items-center gap-1" style={{ borderColor: "var(--border)" }}>
            <ExternalLink size={14} /> View
          </Link>
        )}
      </div>
    </div>
  );
}

function CreatorCodeRow({ code }) {
  const [copied, setCopied] = useState(false);
  const ev = code.event || {};
  const discountLabel = code.kind === "flat"
    ? `$${Number(code.value || 0).toFixed(2)} off`
    : `${Number(code.value || 0)}% off`;
  const usesLabel = code.max_uses ? `${code.uses_count} / ${code.max_uses}` : `${code.uses_count}`;
  const inactive = !code.active;
  const eventUrl = ev.event_id
    ? `${typeof window !== "undefined" ? window.location.origin : ""}/events/${ev.event_id}?promo=${encodeURIComponent(code.code)}`
    : "";

  return (
    <div
      className="rounded-xl border p-4 flex items-center gap-4 flex-wrap"
      style={{ background: "var(--surface)", borderColor: "var(--border)", opacity: inactive ? 0.55 : 1 }}
      data-testid={`mycode-${code.code}`}
    >
      {ev.cover_image_url ? (
        <img src={ev.cover_image_url} alt="" className="w-20 h-20 rounded-lg object-cover flex-shrink-0" />
      ) : (
        <div className="w-20 h-20 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: "var(--bg-elev)" }}>
          <Calendar size={22} className="opacity-50" />
        </div>
      )}
      <div className="flex-1 min-w-[220px]">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="font-medium">{ev.title || "Event"}</div>
          {inactive && (
            <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full border" style={{ borderColor: "var(--border-strong)" }} data-testid={`mycode-${code.code}-inactive`}>
              Inactive
            </span>
          )}
        </div>
        <div className="text-xs opacity-70 mt-1 flex items-center gap-2 flex-wrap">
          <Tag size={12} />
          <span className="font-mono font-semibold" style={{ color: "var(--accent)" }}>{code.code}</span>
          <span>·</span>
          <span>{discountLabel} for buyers</span>
          {Number(code.commission_percent) > 0 && (
            <>
              <span>·</span>
              <span>{Number(code.commission_percent).toFixed(0)}% commission to you</span>
            </>
          )}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3 text-sm">
          <div><span className="opacity-60">Uses</span> <span className="ml-1">{usesLabel}</span></div>
          <div><span className="opacity-60">Tickets</span> <span className="ml-1">{code.tickets_sold || 0}</span></div>
          <div><span className="opacity-60">Revenue</span> <span className="ml-1">${Number(code.revenue || 0).toFixed(2)}</span></div>
          <div>
            <span className="opacity-60">Earned</span>{" "}
            <span className="ml-1" style={{ color: "var(--accent)" }} data-testid={`mycode-${code.code}-earned`}>
              ${Number(code.earnings_unpaid || 0).toFixed(2)}
            </span>
          </div>
        </div>
      </div>
      <div className="flex gap-2 flex-shrink-0">
        <button
          onClick={() => { navigator.clipboard?.writeText(code.code); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
          className="px-3 py-2 rounded-lg text-sm border"
          style={{ borderColor: "var(--border)" }}
          data-testid={`mycode-${code.code}-copy`}
        >
          {copied ? "✓ Copied!" : "Copy code"}
        </button>
        {eventUrl && (
          <button
            onClick={() => { navigator.clipboard?.writeText(eventUrl); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
            className="px-3 py-2 rounded-lg text-sm border"
            style={{ borderColor: "var(--border)" }}
            data-testid={`mycode-${code.code}-share`}
          >
            Copy share link
          </button>
        )}
        {ev.event_id && (
          <Link
            to={`/events/${ev.event_id}`}
            className="px-3 py-2 rounded-lg text-sm border inline-flex items-center gap-1"
            style={{ borderColor: "var(--border)" }}
            data-testid={`mycode-${code.code}-view`}
          >
            <ExternalLink size={14} /> View
          </Link>
        )}
      </div>
    </div>
  );
}
