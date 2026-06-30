import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Sparkles, Loader2, AlertCircle, Check, X, Edit3, Image as ImageIcon } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";

/**
 * /migrate-eventbrite — paste an Eventbrite event URL, we fetch the public
 * JSON-LD, show a preview, and one-click create on Allsale with the data
 * pre-filled into CreateEvent. Removes the entire "recreate manually" step
 * from the vs-eventbrite landing page.
 */
const FMT_DATE = (iso) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-NZ", {
      weekday: "short", day: "numeric", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
};

// Convert our backend payload → CreateEvent's `form` shape + tiers, then
// drop into sessionStorage so the create page picks it up on mount.
const stashForCreatePage = (draft) => {
  const prefill = {
    title: draft.title || "",
    description: draft.description || "",
    venue: draft.venue_name || "",
    city: draft.city || "",
    country: (draft.country || "").toUpperCase() === "NZ" ? "New Zealand" : (draft.country || "New Zealand"),
    date: (draft.start_date || "").slice(0, 16),    // strip TZ for datetime-local input
    end_date: (draft.end_date || "").slice(0, 16),
    image_url: draft.image_url || "",
    currency: draft.currency || "NZD",
  };
  const tiers = (draft.tiers || []).slice(0, 8).map((t) => ({
    name: t.name,
    price: t.price,
    capacity: 100,  // user can edit — we don't know Eventbrite's capacity
  }));
  // If Eventbrite didn't expose tiers (sold out / private), seed one tier so
  // the user has somewhere to start.
  if (tiers.length === 0) tiers.push({ name: "General", price: 50.0, capacity: 100 });

  sessionStorage.setItem("allsale_eventbrite_prefill", JSON.stringify({ form: prefill, tiers }));
};

export default function MigrateEventbrite() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState(null);
  const [error, setError] = useState("");

  const fetchEvent = async (e) => {
    if (e) e.preventDefault();
    const trimmed = url.trim();
    if (!trimmed) { setError("Paste your Eventbrite event URL above first."); return; }
    setLoading(true);
    setError("");
    setDraft(null);
    try {
      const { data } = await api.post("/migrate/eventbrite", { url: trimmed });
      setDraft(data);
      if (data._warning) toast.warning(data._warning);
    } catch (err) {
      setError(err?.response?.data?.detail || "Couldn't fetch that event. Check the URL and try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = () => {
    if (!user) {
      // Stash the prefill and bounce to signup — we'll continue migrating after.
      stashForCreatePage(draft);
      sessionStorage.setItem("allsale_post_signup_redirect", "/organizer/new?from=eventbrite");
      navigate("/signup?role=organizer");
      return;
    }
    if (user.role === "attendee") {
      stashForCreatePage(draft);
      sessionStorage.setItem("allsale_post_signup_redirect", "/organizer/new?from=eventbrite");
      navigate("/become-organizer");
      return;
    }
    stashForCreatePage(draft);
    navigate("/organizer/new?from=eventbrite");
  };

  return (
    <div data-testid="migrate-eventbrite-page">
      {/* Hero */}
      <section className="border-b" style={{ borderColor: "var(--border)" }}>
        <div className="max-w-4xl mx-auto px-6 py-16 lg:py-20">
          <div className="text-xs uppercase tracking-[0.3em] mb-3" style={{ color: "var(--accent)" }}>
            Migration · 60 seconds
          </div>
          <h1 className="serif text-4xl sm:text-5xl mb-5 leading-tight">
            Move your event from Eventbrite — in one paste.
          </h1>
          <p className="text-lg mb-8 max-w-2xl" style={{ color: "var(--text-muted)" }}>
            Drop your Eventbrite link below. We&apos;ll fetch the title, date, venue, image, and ticket tiers
            from the public event page — you just confirm and publish on Allsale. No manual retyping.
          </p>

          <form onSubmit={fetchEvent} className="flex flex-col sm:flex-row gap-3 max-w-2xl">
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://www.eventbrite.com/e/your-event-tickets-1234567890"
              className="flex-1 px-4 py-3 rounded-lg border bg-transparent text-sm"
              style={{ borderColor: "var(--border)", color: "var(--text)" }}
              disabled={loading}
              data-testid="migrate-url-input"
            />
            <button
              type="submit"
              disabled={loading || !url.trim()}
              className="btn-primary"
              data-testid="migrate-fetch-btn"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              {loading ? "Fetching…" : "Fetch event"}
              {!loading && <ArrowRight className="w-4 h-4" />}
            </button>
          </form>

          {error && (
            <div
              className="mt-4 flex items-start gap-2 text-sm px-3 py-2 rounded-lg max-w-2xl"
              style={{ background: "rgba(239,68,68,0.08)", color: "var(--danger)" }}
              data-testid="migrate-error"
            >
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}
        </div>
      </section>

      {/* Preview card */}
      {draft && (
        <section className="border-b" style={{ borderColor: "var(--border)", background: "var(--bg-elev)" }}>
          <div className="max-w-4xl mx-auto px-6 py-12">
            <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>
              Preview — confirm the details
            </div>
            <h2 className="serif text-3xl mb-6">Looks like this. Looks right?</h2>

            <div
              className="border rounded-2xl overflow-hidden"
              style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
              data-testid="migrate-preview-card"
            >
              {/* Hero image */}
              {draft.image_url ? (
                <div className="relative aspect-[21/9] overflow-hidden" style={{ background: "var(--bg)" }}>
                  <img
                    src={draft.image_url}
                    alt={draft.title}
                    className="w-full h-full object-cover"
                    data-testid="migrate-preview-image"
                    onError={(e) => { e.currentTarget.style.display = "none"; }}
                  />
                </div>
              ) : (
                <div
                  className="aspect-[21/9] flex items-center justify-center"
                  style={{ background: "var(--bg)", color: "var(--text-dim)" }}
                >
                  <div className="flex items-center gap-2 text-sm"><ImageIcon className="w-4 h-4" /> No image found</div>
                </div>
              )}

              <div className="p-6 space-y-5">
                <Field label="Event title" value={draft.title} testid="migrate-preview-title" />
                <div className="grid sm:grid-cols-2 gap-5">
                  <Field label="Starts" value={FMT_DATE(draft.start_date)} testid="migrate-preview-start" />
                  <Field label="Ends" value={FMT_DATE(draft.end_date)} testid="migrate-preview-end" />
                  <Field label="Venue" value={draft.venue_name || "—"} testid="migrate-preview-venue" />
                  <Field label="City / Country" value={`${draft.city || "—"}${draft.country ? ` · ${draft.country}` : ""}`} testid="migrate-preview-city" />
                  <Field label="Currency" value={draft.currency || "NZD"} testid="migrate-preview-currency" />
                  <Field label="Originally listed by" value={draft.source_organizer_name || "—"} testid="migrate-preview-organizer" />
                </div>

                {/* Description */}
                {draft.description && (
                  <Field
                    label="Description (first 300 chars)"
                    value={draft.description.slice(0, 300) + (draft.description.length > 300 ? "…" : "")}
                    multiline
                    testid="migrate-preview-description"
                  />
                )}

                {/* Tiers */}
                <div>
                  <div className="text-[10px] uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>
                    Ticket tiers ({draft.tiers?.length || 0})
                  </div>
                  {draft.tiers?.length ? (
                    <div className="grid gap-2">
                      {draft.tiers.map((t, i) => (
                        <div
                          key={i}
                          className="flex items-center justify-between px-4 py-2.5 rounded-lg border"
                          style={{ borderColor: "var(--border)", background: "var(--bg)" }}
                          data-testid={`migrate-preview-tier-${i}`}
                        >
                          <div style={{ color: "var(--text)" }}>{t.name}</div>
                          <div className="font-mono text-sm" style={{ color: "var(--accent)" }}>
                            {t.currency} ${t.price.toFixed(2)}
                            {!t.available && <span className="ml-2 text-xs" style={{ color: "var(--text-dim)" }}>(sold out)</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div
                      className="text-xs italic px-3 py-2 rounded-lg"
                      style={{ color: "var(--text-muted)", background: "var(--bg)" }}
                    >
                      Eventbrite didn&apos;t expose ticket tier data for this event (it may be sold out, private, or RSVP-only).
                      You can add tiers manually on the next step.
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="flex flex-col sm:flex-row gap-3 mt-6 justify-end">
              <button
                onClick={() => { setDraft(null); setUrl(""); }}
                className="btn-ghost"
                data-testid="migrate-restart-btn"
              >
                <X className="w-4 h-4" /> Try another URL
              </button>
              <button
                onClick={handleCreate}
                className="btn-primary"
                data-testid="migrate-create-btn"
              >
                <Edit3 className="w-4 h-4" />
                {user && user.role !== "attendee" ? "Continue to event setup" : "Create my account & migrate"}
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>

            <p className="mt-4 text-xs" style={{ color: "var(--text-dim)" }}>
              You can edit every field on the next step. Buyer data and email lists stay on Eventbrite — export those separately if you need them.
            </p>
          </div>
        </section>
      )}

      {/* "What gets copied" — set expectations before they paste */}
      {!draft && (
        <section className="border-b" style={{ borderColor: "var(--border)" }}>
          <div className="max-w-4xl mx-auto px-6 py-14">
            <h2 className="serif text-2xl mb-6">What we copy across</h2>
            <div className="grid sm:grid-cols-2 gap-4">
              <Bullet pos icon={<Check className="w-4 h-4" />} title="Event title &amp; description" />
              <Bullet pos icon={<Check className="w-4 h-4" />} title="Date &amp; time (with timezone)" />
              <Bullet pos icon={<Check className="w-4 h-4" />} title="Venue name &amp; address" />
              <Bullet pos icon={<Check className="w-4 h-4" />} title="Hero image" />
              <Bullet pos icon={<Check className="w-4 h-4" />} title="Ticket tier names &amp; prices" />
              <Bullet pos icon={<Check className="w-4 h-4" />} title="Currency" />

              <Bullet icon={<X className="w-4 h-4" />} title="Buyer / attendee list (export from Eventbrite separately)" />
              <Bullet icon={<X className="w-4 h-4" />} title="Past sales data &amp; refunds" />
              <Bullet icon={<X className="w-4 h-4" />} title="Eventbrite-specific add-ons or merch" />
            </div>

            <div className="mt-10 text-sm" style={{ color: "var(--text-muted)" }}>
              Don&apos;t have an Eventbrite event yet? <Link to="/organizer/new" className="underline" style={{ color: "var(--accent)" }}>Start fresh →</Link>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
function Field({ label, value, multiline, testid }) {
  return (
    <div data-testid={testid}>
      <div className="text-[10px] uppercase tracking-widest mb-1" style={{ color: "var(--text-dim)" }}>{label}</div>
      <div
        className={multiline ? "text-sm leading-relaxed" : "text-base"}
        style={{ color: "var(--text)" }}
      >
        {value}
      </div>
    </div>
  );
}

function Bullet({ pos, icon, title }) {
  return (
    <div className="flex items-start gap-2.5 py-1">
      <span
        className="flex-shrink-0 mt-0.5"
        style={{ color: pos ? "var(--success)" : "var(--text-dim)" }}
      >
        {icon}
      </span>
      <span className="text-sm" style={{ color: pos ? "var(--text)" : "var(--text-muted)" }}>{title}</span>
    </div>
  );
}
