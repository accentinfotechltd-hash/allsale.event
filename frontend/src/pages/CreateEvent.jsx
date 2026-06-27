import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import api, { formatApiErrorDetail } from "@/lib/api";
import { toast } from "sonner";
import { Plus, Trash2, Bookmark, BookmarkPlus, X, ShieldCheck } from "lucide-react";
import ImageUploader from "@/components/ImageUploader";
import SeatDesigner from "@/components/SeatDesigner";
import DateTimePicker from "@/components/DateTimePicker";
import { SUPPORTED_CURRENCIES, DEFAULT_CURRENCY, currencySymbol } from "@/lib/currencies";
import { COUNTRIES, DEFAULT_COUNTRY, currencyForCountry, timezoneForCountry } from "@/lib/countries";
import { useAuth } from "@/lib/auth";
import RichTextEditor from "@/components/RichTextEditor";
import FeePresentationToggle from "@/components/FeePresentationToggle";

const CATEGORIES = [
  { id: "movies", name: "Movies" },
  { id: "music", name: "Music" },
  { id: "comedy", name: "Comedy" },
  { id: "sports", name: "Sports" },
  { id: "theater", name: "Theater" },
  { id: "tech", name: "Tech" },
  { id: "workshops", name: "Workshops" },
  { id: "festivals", name: "Festivals" },
  { id: "arts", name: "Arts" },
];

export default function CreateEvent() {
  const nav = useNavigate();
  const { eventId } = useParams();
  const isEdit = !!eventId;
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  // Admin-only: create on behalf of any organizer. Defaults to "" = create as self.
  const [onBehalfOf, setOnBehalfOf] = useState("");
  const [organizerOptions, setOrganizerOptions] = useState([]);
  const [form, setForm] = useState({
    title: "",
    description: "",
    category: "music",
    venue: "",
    city: "",
    country: DEFAULT_COUNTRY,
    timezone: timezoneForCountry(DEFAULT_COUNTRY),
    date: "",
    end_date: "",
    image_url: "",
    banner_url: "",
    promo_video_url: "",
    poster_url: "",
    currency: DEFAULT_CURRENCY,
    has_seatmap: false,
    seat_rows: 6,
    seat_cols: 10,
    seat_price: 50.0,
    aisles: [],
    seat_map_image_url: "",
    seatmap_curved: false,
    seatmap_numbering_rtl: false,
    seatmap_sections: [],
    seatmap_backdrop_opacity: 0.4,
    seatmap_backdrop_offset_y: 0,
    seatmap_backdrop_offset_x: 0,
    seatmap_backdrop_scale: 1,
    group_discount_min_qty: 0,
    group_discount_pct_off: 0,
    seatmap_categories: {},
    seatmap_category_prices: {},
    seatmap_row_offsets: {},
    seatmap_custom_labels: {},
    // Fee presentation. False (default) = "fees on top" — buyer sees ticket
    // price + service fee separately. True = "fees included" — buyer sees one
    // clean number; platform + Stripe fees come out of the organizer's payout.
    absorb_fees: false,
  });
  const [tiers, setTiers] = useState([{ name: "General", price: 50.0, capacity: 200 }]);
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(isEdit);

  // Stripe Connect status — organizer MUST have payouts enabled before
  // they can publish a PAID event (free events skip this check). Admins
  // are exempt server-side, so we only fetch when the caller is not admin.
  const [stripeConnect, setStripeConnect] = useState(null); // null = loading
  useEffect(() => {
    if (isAdmin) return; // admins bypass the gate
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get("/stripe/connect/status");
        if (!cancelled) setStripeConnect(data);
      } catch {
        // 503 / network — treat as not-connected; the server will still
        // accept the request for free events and reject paid ones.
        if (!cancelled) setStripeConnect({ stripe_payouts_enabled: false });
      }
    })();
    return () => { cancelled = true; };
  }, [isAdmin]);

  // Paid-event = at least one tier (or seatmap seat) with price > 0.
  const hasPaidTier = form.has_seatmap
    ? Number(form.seat_price) > 0
    : tiers.some((t) => Number(t.price) > 0);
  const needsStripeForPaidEvent = !isAdmin
    && hasPaidTier
    && stripeConnect !== null
    && !stripeConnect.stripe_payouts_enabled;

  const onConnectStripe = async () => {
    try {
      const { data } = await api.post("/stripe/connect/onboard", {
        return_url: `${window.location.origin}/organizer?stripe_return=1`,
        refresh_url: window.location.href,
      });
      if (data?.url) {
        window.location.href = data.url;
      } else {
        toast.error("Couldn't start Stripe onboarding — open the organizer dashboard and try again.");
      }
    } catch (err) {
      const detail = err?.response?.data?.detail;
      toast.error(formatApiErrorDetail(detail) || "Couldn't start Stripe onboarding.");
    }
  };

  // Admin only & create mode: fetch list of organizers for the "create on behalf of" picker.
  useEffect(() => {
    if (!isAdmin || isEdit) return;
    (async () => {
      try {
        const { data } = await api.get("/admin/users", { params: { role: "organizer" } });
        setOrganizerOptions(data || []);
      } catch { /* silent — picker just won't show options */ }
    })();
  }, [isAdmin, isEdit]);

  // Load existing event when in edit mode
  useEffect(() => {
    if (!isEdit) return;
    (async () => {
      try {
        const { data } = await api.get(`/events/${eventId}`);
        setForm({
          title: data.title || "",
          description: data.description || "",
          category: data.category || "music",
          venue: data.venue || "",
          city: data.city || "",
          country: data.country || DEFAULT_COUNTRY,
          timezone: data.timezone || timezoneForCountry(data.country || DEFAULT_COUNTRY),
          // Trim the timezone suffix for the datetime-local input
          date: data.date ? data.date.slice(0, 16) : "",
          end_date: data.end_date ? data.end_date.slice(0, 16) : "",
          image_url: data.image_url || "",
          banner_url: data.banner_url || "",
          promo_video_url: data.promo_video_url || "",
          poster_url: data.poster_url || "",
          currency: data.currency || DEFAULT_CURRENCY,
          has_seatmap: !!data.has_seatmap,
          seat_rows: data.seat_rows || 6,
          seat_cols: data.seat_cols || 10,
          seat_price: data.seat_price || 50,
          aisles: data.aisles || [],
          seat_map_image_url: data.seat_map_image_url || "",
          seatmap_curved: !!data.seatmap_curved,
          seatmap_numbering_rtl: !!data.seatmap_numbering_rtl,
          seatmap_sections: data.seatmap_sections || [],
          seatmap_categories: data.seatmap_categories || {},
          seatmap_category_prices: data.seatmap_category_prices || {},
          seatmap_row_offsets: data.seatmap_row_offsets || {},
          seatmap_custom_labels: data.seatmap_custom_labels || {},
          group_discount_min_qty: data?.group_discount?.min_qty || 0,
          group_discount_pct_off: data?.group_discount?.pct_off || 0,
          absorb_fees: !!data.absorb_fees,
        });
        if (Array.isArray(data.tiers) && data.tiers.length) setTiers(data.tiers);
      } catch {
        toast.error("Could not load event");
      } finally {
        setLoading(false);
      }
    })();
  }, [isEdit, eventId]);
  const [seatmapFileId, setSeatmapFileId] = useState(null);
  const [detecting, setDetecting] = useState(false);
  const [detectResult, setDetectResult] = useState(null);
  const [describeText, setDescribeText] = useState("");
  const [showDescribe, setShowDescribe] = useState(false);

  const applyAiResult = (data) => {
    setDetectResult(data);
    if (data.rows > 0 && data.cols > 0) {
      setForm((f) => ({
        ...f,
        seat_rows: data.rows,
        seat_cols: data.cols,
        aisles: data.aisles || [],
        seatmap_sections: data.sections || [],
        seatmap_categories: data.seat_categories || {},
        seatmap_row_offsets: data.row_offsets || {},
        seatmap_curved: !!data.curved,
      }));
      const cats = data.seat_categories || {};
      const catCount = Object.values(cats).reduce((n, arr) => n + (arr?.length || 0), 0);
      const conf = Math.round((data.confidence || 0) * 100);
      toast.success(
        `Layout set: ${data.rows} × ${data.cols} seats, ${(data.aisles || []).length} aisles, ${catCount} categorised (${conf}% confidence)`
      );
      if (conf < 70) {
        // Low-confidence AI run → push the organizer to verify in the grid editor.
        toast.warning("⚠️ AI confidence is low — please verify the layout below before saving.");
      }
    } else {
      toast.message("Couldn't build a clear grid — please tweak the layout below");
    }
  };

  const detectSeatmap = async () => {
    if (!seatmapFileId) { toast.error("Upload a floor-plan image first"); return; }
    setDetecting(true);
    setDetectResult(null);
    try {
      const { data } = await api.post("/organizer/seatmap/detect", { file_id: seatmapFileId });
      applyAiResult(data);
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Detection failed — try the 'Describe in words' option below");
    } finally {
      setDetecting(false);
    }
  };

  // Fast offline text-parser — no LLM call. Try this BEFORE /describe so the
  // organizer gets instant feedback for well-structured layouts (the common case).
  const parseTextLayout = async () => {
    if (!describeText.trim()) { toast.error("Type a description first"); return; }
    setDetecting(true);
    setDetectResult(null);
    try {
      const { data } = await api.post("/organizer/seatmap/parse-text", { text: describeText.trim() });
      if (data.rows > 0 && data.cols > 0) {
        applyAiResult(data);
      } else {
        // Could not parse deterministically — fall back to LLM
        toast.message("Text parser couldn't figure it out — trying the AI...");
        const { data: aiData } = await api.post("/organizer/seatmap/describe", { text: describeText.trim() });
        applyAiResult(aiData);
      }
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Couldn't parse");
    } finally {
      setDetecting(false);
    }
  };

  const describeSeatmap = async () => {
    if (!describeText.trim()) { toast.error("Type a description first"); return; }
    setDetecting(true);
    setDetectResult(null);
    try {
      const { data } = await api.post("/organizer/seatmap/describe", { text: describeText.trim() });
      applyAiResult(data);
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "AI couldn't parse — try simpler wording");
    } finally {
      setDetecting(false);
    }
  };

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!form.image_url) { toast.error("Please upload a cover photo"); return; }
    if (!form.date) { toast.error("Please pick an event date and time"); return; }
    const parsedDate = new Date(form.date);
    if (Number.isNaN(parsedDate.getTime())) {
      toast.error("That date doesn't look right — please pick it again");
      return;
    }
    // Optional end_date — if provided, must be after the start.
    let parsedEnd = null;
    if (form.end_date) {
      parsedEnd = new Date(form.end_date);
      if (Number.isNaN(parsedEnd.getTime())) {
        toast.error("That end date doesn't look right — please pick it again");
        return;
      }
      if (parsedEnd.getTime() <= parsedDate.getTime()) {
        toast.error("End time must be after the start time");
        return;
      }
    }

    // Pricing sanity — block saves where the buyer would see "Free" or
    // "TBA" on the event card because the organizer forgot to set prices.
    // Allow $0 ONLY when EVERY price is explicitly 0 (intentional free event).
    if (form.has_seatmap) {
      const sp = Number(form.seat_price);
      if (!Number.isFinite(sp) || sp < 0) {
        toast.error("Seat price is required — set a number (use 0 for a free event)");
        return;
      }
    } else {
      if (!tiers.length) {
        toast.error("Add at least one ticket tier before saving");
        return;
      }
      const invalid = tiers.find((t) => !Number.isFinite(Number(t.price)) || Number(t.price) < 0);
      if (invalid) {
        toast.error(`Tier "${invalid.name || "(unnamed)"}" has no price — type a number (use 0 for a free tier)`);
        return;
      }
    }

    setSubmitting(true);
    try {
      const payload = {
        ...form,
        date: parsedDate.toISOString(),
        end_date: parsedEnd ? parsedEnd.toISOString() : null,
        tiers: form.has_seatmap ? [] : tiers,
        group_discount: (Number(form.group_discount_min_qty) > 0 && Number(form.group_discount_pct_off) > 0)
          ? { min_qty: Number(form.group_discount_min_qty), pct_off: Number(form.group_discount_pct_off) }
          : null,
      };
      delete payload.group_discount_min_qty;
      delete payload.group_discount_pct_off;
      // Admin-only: attribute the event to the chosen organizer instead of admin.
      if (isAdmin && !isEdit && onBehalfOf) {
        payload.on_behalf_of_organizer_id = onBehalfOf;
      }
      // Strip undefined values from category price map (cleared inputs)
      if (payload.seatmap_category_prices) {
        payload.seatmap_category_prices = Object.fromEntries(
          Object.entries(payload.seatmap_category_prices).filter(([, v]) => v !== undefined && v !== null && v !== "")
        );
      }
      if (isEdit) {
        const { data } = await api.patch(`/events/${eventId}`, payload);
        toast.success("Event updated");
        nav(`/organizer/events/${data.event_id}`);
      } else {
        const { data } = await api.post("/events", payload);
        toast.success("Event submitted! Pending approval.");
        nav(`/events/${data.event_id}`);
      }
    } catch (err) {
      // Surface the real reason instead of a generic "something went wrong".
      // Network/CORS failures (err.response undefined) get a friendlier hint;
      // server-side validation errors come through with err.response.data.detail.
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      const code = (detail && typeof detail === "object") ? detail.code : null;
      if (!err?.response) {
        toast.error("Couldn't reach the server. Check your connection and try again.");
      } else if (status === 401) {
        toast.error("Your session expired — please sign in again.");
      } else if (status === 402 && code === "stripe_payouts_required") {
        // Stripe Connect gate fired server-side. Surface a clear CTA — the
        // server already emailed the organizer the 1-click onboarding link.
        toast.error("Connect Stripe to publish a paid event — opening onboarding now.");
        // Refresh local status so the inline banner reflects reality, then
        // forward the organizer straight to onboarding.
        try {
          const { data: st } = await api.get("/stripe/connect/status");
          setStripeConnect(st);
        } catch { /* ignore */ }
        await onConnectStripe();
      } else if (status === 403) {
        toast.error("You need an organizer account to post events. Visit 'Become an organizer' first.");
      } else if (status === 422) {
        toast.error(formatApiErrorDetail(detail) || "Some fields look invalid — please review and try again.");
      } else {
        toast.error(formatApiErrorDetail(detail) || `Failed (HTTP ${status || "?"})`);
      }
    } finally { setSubmitting(false); }
  };

  return (
    <div className="max-w-3xl mx-auto px-6 py-12">
      <div className="mb-8">
        <div className="text-xs uppercase tracking-[0.3em] mb-2" style={{ color: "var(--accent)" }}>{isEdit ? "Edit event" : "New event"}</div>
        <h1 className="serif text-5xl">{isEdit ? "Update the details" : "Set the stage"}</h1>
      </div>
      {loading ? (
        <div className="py-10 text-center" style={{ color: "var(--text-dim)" }}>Loading…</div>
      ) : (
      <form onSubmit={onSubmit} className="space-y-6" data-testid="create-event-form">
        {needsStripeForPaidEvent && (
          <div
            className="border-2 rounded-2xl p-5 flex items-start gap-4"
            style={{ borderColor: "#E84B3C", background: "#FFF4F2" }}
            data-testid="stripe-required-banner"
          >
            <div
              className="shrink-0 mt-0.5 w-9 h-9 rounded-full flex items-center justify-center"
              style={{ background: "#E84B3C", color: "white", fontWeight: 700 }}
              aria-hidden
            >
              !
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-semibold text-base" style={{ color: "#7A1410" }}>
                Connect your bank to publish a paid event
              </div>
              <p className="text-sm mt-1" style={{ color: "#7A1410" }}>
                You&apos;ve set at least one paid ticket — Stripe is how we send you the
                ticket revenue. Add your bank + ID once (about 3 minutes) and your
                event publishes the moment you save.
              </p>
              <button
                type="button"
                onClick={onConnectStripe}
                className="mt-3 px-4 py-2 rounded-full text-sm font-semibold transition"
                style={{ background: "#E84B3C", color: "white" }}
                data-testid="stripe-required-connect-btn"
              >
                Connect Stripe now →
              </button>
              <p className="text-xs mt-2" style={{ color: "#A53428" }}>
                Tip: free events (all prices set to 0) don&apos;t need Stripe — skip this banner.
              </p>
            </div>
          </div>
        )}
        {isAdmin && !isEdit && (
          <div
            className="border rounded-2xl p-4 flex items-start gap-3"
            style={{ borderColor: "var(--border)", background: "rgba(255,79,0,0.05)" }}
            data-testid="admin-on-behalf-block"
          >
            <ShieldCheck className="w-5 h-5 mt-0.5" style={{ color: "var(--accent)" }} />
            <div className="flex-1">
              <div className="text-xs uppercase tracking-widest mb-1.5" style={{ color: "var(--text-dim)" }}>
                Admin · Create on behalf of organizer
              </div>
              <select
                value={onBehalfOf}
                onChange={(e) => setOnBehalfOf(e.target.value)}
                className="w-full"
                data-testid="admin-on-behalf-select"
              >
                <option value="">Myself ({user?.name || "Admin"})</option>
                {organizerOptions.map((o) => (
                  <option key={o.user_id} value={o.user_id}>
                    {o.name} — {o.email}
                  </option>
                ))}
              </select>
              <div className="text-xs mt-2" style={{ color: "var(--text-dim)" }}>
                When set, the event is attributed to the chosen organizer and they receive an email notification.
              </div>
            </div>
          </div>
        )}
        <div className="grid md:grid-cols-[2fr_1fr] gap-4">
          <Field label="Cover photo · 16:9">
            <ImageUploader
              value={form.image_url}
              onUploaded={(url) => { update("image_url", url); if (!form.banner_url) update("banner_url", url); }}
              label="Drop cover photo or click to upload"
              aspect="16/9"
              testid="cover-uploader"
            />
          </Field>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <div className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
                Vertical poster · 9:16
              </div>
              <span
                className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
                style={{ background: "rgba(240,138,42,0.15)", color: "var(--accent)" }}
              >
                RECOMMENDED
              </span>
            </div>
            <div
              style={{
                outline: form.poster_url ? "none" : "2px dashed rgba(240,138,42,0.35)",
                outlineOffset: 4,
                borderRadius: 12,
              }}
            >
              <ImageUploader
                value={form.poster_url}
                onUploaded={(url) => update("poster_url", url)}
                label="Drop poster or upload"
                aspect="9/16"
                testid="poster-uploader"
              />
            </div>
            <div className="text-xs mt-2" style={{ color: "var(--text-dim)" }}>
              Used on the event page sidebar, lightbox, and social flyer downloads — events with a poster see 2-3x better Instagram engagement.
            </div>
          </div>
        </div>
        <Field label="Promo video URL (optional)" hint="Paste a YouTube, Vimeo, Instagram, or direct .mp4 link. Plays embedded below the banner on the event page.">
          <input
            type="url"
            value={form.promo_video_url || ""}
            onChange={(e) => update("promo_video_url", e.target.value)}
            placeholder="https://www.youtube.com/watch?v=… or https://vimeo.com/… or https://….mp4"
            data-testid="promo-video-url-input"
          />
        </Field>
        <Field label="Title">
          <input required value={form.title} onChange={(e) => update("title", e.target.value)} data-testid="event-title-input" />
        </Field>
        <Field label="Description">
          <textarea required rows={4} value={form.description} onChange={(e) => update("description", e.target.value)} data-testid="event-desc-input" style={{ display: "none" }} />
          <RichTextEditor
            value={form.description}
            onChange={(html) => update("description", html)}
            placeholder="Describe the event — drop times, lineup, dress code, anything attendees should know. Use the toolbar to bold key info or add bullet points."
            testid="event-desc-rich"
          />
        </Field>
        <div className="grid md:grid-cols-2 gap-4">
          <Field label="Category">
            <select value={form.category} onChange={(e) => update("category", e.target.value)} data-testid="event-category-select">
              {CATEGORIES.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Currency">
            <select
              value={form.currency}
              onChange={(e) => update("currency", e.target.value)}
              data-testid="event-currency-select"
            >
              {SUPPORTED_CURRENCIES.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.flag} {c.code} — {c.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Date & time">
            <DateTimePicker value={form.date} onChange={(v) => update("date", v)} testid="event-datetime" />
          </Field>
          <Field label="End date & time (optional)" hint="Leave blank if unknown — we'll assume the event runs ~3 hours. Helps Google show your event in search results.">
            <DateTimePicker value={form.end_date} onChange={(v) => update("end_date", v)} testid="event-end-datetime" />
          </Field>
          <Field label="Venue">
            <input required value={form.venue} onChange={(e) => update("venue", e.target.value)} />
          </Field>
          <Field label="City">
            <input required value={form.city} onChange={(e) => update("city", e.target.value)} data-testid="event-city" />
          </Field>
          <Field label="Country">
            <select
              required
              value={form.country}
              onChange={(e) => {
                const code = e.target.value;
                // Auto-update timezone + currency when the country changes — the
                // organizer can still override afterwards.
                setForm(prev => ({
                  ...prev,
                  country: code,
                  timezone: timezoneForCountry(code),
                  // Only auto-switch currency if the user hasn't manually
                  // changed it from the previous country's default.
                  currency: prev.currency === currencyForCountry(prev.country)
                    ? currencyForCountry(code)
                    : prev.currency,
                }));
              }}
              data-testid="event-country"
            >
              {COUNTRIES.map(c => (
                <option key={c.code} value={c.code}>{c.flag} {c.name}</option>
              ))}
            </select>
          </Field>
          <Field label="Timezone" hint="Auto-picked from country; override for events that span timezones.">
            <input
              value={form.timezone || ""}
              onChange={(e) => update("timezone", e.target.value)}
              placeholder="e.g. Pacific/Auckland"
              data-testid="event-timezone"
            />
          </Field>
        </div>

        <div className="border rounded-xl p-5 space-y-4" style={{ borderColor: "var(--border)" }}>
          <label className="flex items-center justify-between cursor-pointer">
            <div>
              <div className="font-medium">Interactive seat map</div>
              <div className="text-xs" style={{ color: "var(--text-dim)" }}>Use this for cinemas, theaters and assigned-seating venues.</div>
            </div>
            <input type="checkbox" className="!w-5 !h-5" checked={form.has_seatmap} onChange={(e) => update("has_seatmap", e.target.checked)} data-testid="seatmap-toggle" />
          </label>

          {form.has_seatmap && (
            <>
              <div className="grid grid-cols-3 gap-3">
                <Field label="Rows"><input type="number" min={2} max={26} value={form.seat_rows} onChange={(e) => update("seat_rows", parseInt(e.target.value) || 2)} /></Field>
                <Field label="Cols"><input type="number" min={4} max={26} value={form.seat_cols} onChange={(e) => update("seat_cols", parseInt(e.target.value) || 4)} /></Field>
                <Field label={`Default price / seat (${form.currency})`} hint={Number(form.seat_price) === 0 ? "🎉 Set to 0 — this event will be marketed as Free" : null}><input type="number" step="0.01" min="0" value={form.seat_price} onChange={(e) => update("seat_price", parseFloat(e.target.value) || 0)} data-testid="seat-price-input" /></Field>
              </div>

              <SeatmapTemplateBar
                form={form}
                applyTemplate={(layout) => setForm((f) => ({ ...f, has_seatmap: true, ...layout }))}
                eventId={eventId}
              />

              {/* Per-category seat prices — only meaningful once at least one
                  category has actual seats assigned, so we surface this once
                  the categories map is non-empty. */}
              {Object.values(form.seatmap_categories || {}).some((arr) => (arr || []).length > 0) && (
                <Field label="Per-category seat prices (optional)" hint="Override the default price above for specific seat types.">
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3" data-testid="category-pricing-grid">
                    {[
                      { key: "vip", label: "VIP", icon: "👑", placeholder: "e.g. 80" },
                      { key: "premium", label: "Premium", icon: "✨", placeholder: "e.g. 60" },
                      { key: "wheelchair", label: "Wheelchair", icon: "♿", placeholder: "e.g. 40" },
                      { key: "disabled", label: "Disabled", icon: "👁", placeholder: "e.g. 40" },
                      { key: "house", label: "House (comp)", icon: "🏠", placeholder: "0" },
                    ].map((c) => {
                      const seatCount = (form.seatmap_categories?.[c.key] || []).length;
                      if (seatCount === 0) return null;
                      return (
                        <div key={c.key}>
                          <label className="text-xs uppercase tracking-widest block mb-1" style={{ color: "var(--text-dim)" }}>
                            {c.icon} {c.label} <span className="opacity-60">({seatCount})</span>
                          </label>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            placeholder={c.placeholder}
                            value={form.seatmap_category_prices?.[c.key] ?? ""}
                            onChange={(e) => {
                              const v = e.target.value;
                              setForm((f) => ({
                                ...f,
                                seatmap_category_prices: {
                                  ...(f.seatmap_category_prices || {}),
                                  ...(v === "" ? { [c.key]: undefined } : { [c.key]: parseFloat(v) || 0 }),
                                },
                              }));
                            }}
                            data-testid={`category-price-${c.key}`}
                          />
                        </div>
                      );
                    })}
                  </div>
                </Field>
              )}

              <Field label="Venue floor-plan (optional)">
                <ImageUploader
                  value={form.seat_map_image_url}
                  onUploaded={(url, fileId) => {
                    update("seat_map_image_url", url);
                    setSeatmapFileId(fileId || null);
                    setDetectResult(null);
                  }}
                  label="Upload a backdrop showing your venue layout"
                  aspect="16/7"
                  testid="seatmap-uploader"
                />
                {form.seat_map_image_url && (
                  <div className="mt-3 p-3 rounded-lg space-y-3" style={{ background: "var(--bg-elev)" }}>
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                      <div className="text-xs flex-1 min-w-[200px]" style={{ color: "var(--text-muted)" }}>
                        <strong style={{ color: "var(--accent)" }}>Option 1 — Auto-detect from image:</strong> let Gemini read your floor-plan. Works best for clear rectangular grids.
                      </div>
                      <button
                        type="button"
                        onClick={detectSeatmap}
                        disabled={detecting || !seatmapFileId}
                        className="btn-primary !py-2 !px-3 text-xs"
                        data-testid="detect-seatmap-btn"
                      >
                        {detecting ? "Working…" : (detectResult ? "Re-detect" : (seatmapFileId ? "Detect seats with AI" : "Re-upload to detect"))}
                      </button>
                    </div>
                    <div className="border-t pt-3" style={{ borderColor: "var(--border)" }}>
                      <button
                        type="button"
                        onClick={() => setShowDescribe((s) => !s)}
                        className="text-xs underline-offset-2 hover:underline"
                        style={{ color: "var(--accent)" }}
                        data-testid="toggle-describe-btn"
                      >
                        {showDescribe ? "Hide" : "✏️ Or just describe your layout in words (most reliable)"}
                      </button>
                      {showDescribe && (
                        <div className="mt-2 space-y-2">
                          <div className="text-[11px] p-2 rounded bg-black/20 font-mono leading-relaxed" style={{ color: "var(--text-muted)" }}>
                            <strong style={{ color: "var(--accent)" }}>Syntax:</strong> one row per line.<br />
                            <code>A: 1-15, disabled 1-5, house 6-11, disabled 12-15</code><br />
                            <code>B: 1-2 aisle, 3-12</code><br />
                            <code>C-E: 1-10</code> &nbsp;<span style={{ color: "var(--text-dim)" }}>(C, D, E same)</span><br />
                            <code>H: 1-4 disabled, 5 wheelchair, aisle 6-8, 9 wheelchair, 10 disabled</code><br />
                            <span style={{ color: "var(--text-dim)" }}>Keywords: <strong>aisle, wheelchair, disabled, house, vip, premium</strong></span>
                          </div>
                          <textarea
                            value={describeText}
                            onChange={(e) => setDescribeText(e.target.value)}
                            rows={6}
                            className="w-full font-mono text-xs"
                            placeholder={`A: 1-15, disabled 1-5, house 6-11, disabled 12-15\nB: 1-2 aisle, 3-12\nC-E: 1-10\nF-G: 1-10 disabled\nH: 1-4 disabled, 5 wheelchair, aisle 6-8, 9 wheelchair, 10 disabled`}
                            data-testid="describe-text-input"
                          />
                          <div className="flex gap-2 flex-wrap">
                            <button
                              type="button"
                              onClick={parseTextLayout}
                              disabled={detecting || describeText.trim().length < 5}
                              className="btn-primary !py-2 !px-3 text-xs"
                              data-testid="describe-submit-btn"
                            >
                              {detecting ? "Building layout…" : "⚡ Build layout from text"}
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setDescribeText(
                                  `A: 1-15, disabled 1-5, house 6-11, disabled 12-15\nB: 1-2 aisle, 3-12\nC-E: offset 2, 1-10\nF-G: offset 2, 1-10 disabled\nH: offset 2, 1-4 disabled, 5 wheelchair, aisle 6-8, 9 wheelchair, 10 disabled`
                                );
                              }}
                              className="btn-ghost !py-2 !px-3 text-xs"
                              data-testid="load-example-btn"
                            >
                              Load Hoyts example
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
                {detectResult && (
                  <div className="mt-2 text-xs p-3 rounded-lg border" style={{ borderColor: "var(--border)", color: "var(--text-muted)" }} data-testid="detect-result">
                    <strong style={{ color: "var(--text)" }}>AI result:</strong> {detectResult.rows} rows × {detectResult.cols} cols ·
                    {" "}{(detectResult.aisles || []).length} aisles ·
                    {" "}{(detectResult.sections || []).length} sections ·
                    {" "}<span style={{ color: detectResult.confidence > 0.7 ? "var(--success)" : "var(--warn)" }}>{Math.round((detectResult.confidence || 0) * 100)}% confidence</span>
                    {detectResult.notes && <div className="mt-1" style={{ color: "var(--text-dim)" }}>{detectResult.notes}</div>}
                  </div>
                )}
              </Field>

              {/* AI describe-in-words is also available WITHOUT an image */}
              {!form.seat_map_image_url && (
                <Field label="No floor-plan image? Describe your layout in words">
                  <div className="text-[11px] p-2 rounded bg-black/20 font-mono leading-relaxed mb-2" style={{ color: "var(--text-muted)" }}>
                    <strong style={{ color: "var(--accent)" }}>Syntax:</strong> one row per line. Examples:<br />
                    <code>A: 1-15, disabled 1-5, house 6-11, disabled 12-15</code><br />
                    <code>B: 1-2 aisle, 3-12</code><br />
                    <code>C-E: offset 2, 1-10</code> &nbsp;<span style={{ color: "var(--text-dim)" }}>(indent 2 cols, seats labeled 1-10)</span><br />
                    <code>H: offset 2, 1-4 disabled, 5 wheelchair, aisle 6-8, 9 wheelchair, 10 disabled</code><br />
                    <span style={{ color: "var(--text-dim)" }}>Keywords: <strong>aisle, offset N, wheelchair, disabled, house, vip, premium</strong></span>
                  </div>
                  <textarea
                    value={describeText}
                    onChange={(e) => setDescribeText(e.target.value)}
                    rows={6}
                    className="w-full font-mono text-xs"
                    placeholder={`A: 1-15, disabled 1-5, house 6-11, disabled 12-15\nB: 1-2 aisle, 3-12\nC-E: 1-10\nF-G: 1-10 disabled\nH: 1-4 disabled, 5 wheelchair, aisle 6-8, 9 wheelchair, 10 disabled`}
                    data-testid="describe-text-input-noimg"
                  />
                  <div className="flex gap-2 flex-wrap mt-2">
                    <button
                      type="button"
                      onClick={parseTextLayout}
                      disabled={detecting || describeText.trim().length < 5}
                      className="btn-primary !py-2 !px-3 text-xs"
                      data-testid="describe-submit-btn-noimg"
                    >
                      {detecting ? "Building…" : "⚡ Build layout from text"}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setDescribeText(
                          `A: 1-15, disabled 1-5, house 6-11, disabled 12-15\nB: 1-2 aisle, 3-12\nC-E: offset 2, 1-10\nF-G: offset 2, 1-10 disabled\nH: offset 2, 1-4 disabled, 5 wheelchair, aisle 6-8, 9 wheelchair, 10 disabled`
                        );
                      }}
                      className="btn-ghost !py-2 !px-3 text-xs"
                      data-testid="load-example-btn-noimg"
                    >
                      Load Hoyts example
                    </button>
                  </div>
                </Field>
              )}

              <Field label="Draw the seat arrangement">
                <div className="mb-3 flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    id="seatmap_numbering_rtl"
                    checked={form.seatmap_numbering_rtl}
                    onChange={(e) => update("seatmap_numbering_rtl", e.target.checked)}
                    data-testid="numbering-rtl-toggle"
                  />
                  <label htmlFor="seatmap_numbering_rtl" style={{ color: "var(--text-muted)" }}>
                    Number seats <strong>right to left</strong> (e.g. seat #1 is on the right — standard for many Indian/ME cinemas)
                  </label>
                </div>
                <SeatDesigner
                  rows={form.seat_rows}
                  cols={form.seat_cols}
                  aisles={form.aisles}
                  sections={form.seatmap_sections}
                  categories={form.seatmap_categories || {}}
                  rowOffsets={form.seatmap_row_offsets || {}}
                  customLabels={form.seatmap_custom_labels || {}}
                  onCustomLabelsChange={(next) => setForm((f) => ({ ...f, seatmap_custom_labels: next }))}
                  eventId={eventId}
                  curved={form.seatmap_curved}
                  numberingRtl={form.seatmap_numbering_rtl}
                  backdropUrl={form.seat_map_image_url}
                  backdropOpacity={form.seatmap_backdrop_opacity}
                  backdropOffsetY={form.seatmap_backdrop_offset_y}
                  backdropOffsetX={form.seatmap_backdrop_offset_x}
                  backdropScale={form.seatmap_backdrop_scale}
                  onChange={(next) => setForm((f) => ({
                    ...f,
                    aisles: next.aisles,
                    seatmap_sections: next.sections,
                    seatmap_categories: next.categories ?? f.seatmap_categories,
                    seatmap_curved: next.curved,
                    seatmap_backdrop_opacity: next.backdrop_opacity,
                    seatmap_backdrop_offset_y: next.backdrop_offset_y,
                    seatmap_backdrop_offset_x: next.backdrop_offset_x,
                    seatmap_backdrop_scale: next.backdrop_scale,
                  }))}
                />
              </Field>
              {form.seatmap_sections?.length > 0 && (
                <Field label="Section pricing (optional)">
                  <div className="rounded-xl p-4" style={{ background: "var(--bg-elev)", border: "1px solid var(--border)" }}>
                    <div className="space-y-2">
                      {form.seatmap_sections.map((s, i) => (
                        <div key={i} className="flex items-center gap-3" data-testid={`section-price-row-${i}`}>
                          <span className="text-sm flex-1 truncate">{s.label}</span>
                          <input
                            type="number" min="0" step="1"
                            placeholder={`Default: ${currencySymbol(form.currency)}${form.seat_price}`}
                            value={s.price ?? ""}
                            onChange={(e) => {
                              const v = e.target.value === "" ? null : parseFloat(e.target.value);
                              const next = [...form.seatmap_sections];
                              next[i] = { ...next[i], price: v };
                              update("seatmap_sections", next);
                            }}
                            className="w-32"
                            data-testid={`section-price-input-${i}`}
                          />
                        </div>
                      ))}
                    </div>
                    <p className="text-xs mt-3" style={{ color: "var(--text-dim)" }}>
                      Leave blank to use the base seat price for that section.
                    </p>
                  </div>
                </Field>
              )}
            </>
          )}
        </div>

        {!form.has_seatmap && (
          <div>
            <div className="flex items-center justify-between mb-3">
              <label className="text-xs uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>Ticket tiers</label>
              <button type="button" onClick={() => setTiers((t) => [...t, { name: "VIP", price: 100, capacity: 50 }])} className="text-xs flex items-center gap-1" style={{ color: "var(--accent)" }} data-testid="add-tier-btn">
                <Plus className="w-3 h-3" /> Add tier
              </button>
            </div>
            <div className="space-y-3">
              {tiers.map((t, i) => (
                <div key={i} className="grid grid-cols-[1fr_120px_120px_auto] gap-2">
                  <input placeholder="Name" value={t.name} onChange={(e) => { const n = [...tiers]; n[i].name = e.target.value; setTiers(n); }} />
                  <input type="number" step="0.01" min="0" placeholder={`Price (${form.currency})`} value={t.price} onChange={(e) => { const n = [...tiers]; n[i].price = parseFloat(e.target.value); setTiers(n); }} data-testid={`tier-price-${i}`} />
                  <input type="number" placeholder="Capacity" value={t.capacity} onChange={(e) => { const n = [...tiers]; n[i].capacity = parseInt(e.target.value); setTiers(n); }} />
                  <button type="button" onClick={() => setTiers((arr) => arr.filter((_, x) => x !== i))} className="px-3 rounded-lg border" style={{ borderColor: "var(--border-strong)" }}><Trash2 className="w-4 h-4" /></button>
                </div>
              ))}
            </div>
            {tiers.some((t) => Number(t.price) === 0) && (
              <div className="text-xs mt-2 flex items-center gap-1.5" style={{ color: "var(--accent)" }} data-testid="free-tier-hint">
                <span>🎉</span> One or more tiers are priced at 0 — these will display as <strong>Free</strong> to attendees and skip Stripe checkout.
              </div>
            )}
          </div>
        )}

        <FeePresentationToggle
          value={form.absorb_fees}
          onChange={(v) => update("absorb_fees", v)}
          samplePrice={
            form.has_seatmap
              ? Number(form.seat_price) || 0
              : Number(tiers[0]?.price) || 0
          }
          currency={form.currency}
        />

        <div data-testid="group-discount-section">
          <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>
            Group booking discount <span className="opacity-60">(optional)</span>
          </label>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <input
                type="number"
                min="0"
                placeholder="Min tickets (e.g. 10)"
                value={form.group_discount_min_qty || ""}
                onChange={(e) => update("group_discount_min_qty", parseInt(e.target.value) || 0)}
                data-testid="group-discount-min-qty"
              />
              <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>Min tickets to qualify</div>
            </div>
            <div>
              <input
                type="number"
                min="0"
                max="100"
                step="1"
                placeholder="% off (e.g. 15)"
                value={form.group_discount_pct_off || ""}
                onChange={(e) => update("group_discount_pct_off", parseFloat(e.target.value) || 0)}
                data-testid="group-discount-pct-off"
              />
              <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>Discount % off subtotal</div>
            </div>
          </div>
          <div className="text-xs mt-2" style={{ color: "var(--text-dim)" }}>
            Buyers automatically get the discount when their cart hits the threshold. Set both to 0 to disable.
          </div>
        </div>

        <button type="submit" disabled={submitting} className="btn-primary" data-testid="submit-event-btn">
          {submitting ? (isEdit ? "Saving..." : "Submitting...") : (isEdit ? "Save changes" : "Submit for approval")}
        </button>
      </form>
      )}
    </div>
  );
}

function Field({ label, children, hint }) {
  return (
    <div>
      <label className="text-xs uppercase tracking-widest mb-2 block" style={{ color: "var(--text-dim)" }}>{label}</label>
      {children}
      {hint && <div className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>{hint}</div>}
    </div>
  );
}

/**
 * SeatmapTemplateBar — save the current seatmap form as a reusable template
 * and load any of my saved templates back into the form. Lazily fetches the
 * organizer's templates on first render; refreshes after each save/delete.
 *
 * Lives under the rows/cols/price row so it sits naturally above the designer.
 */
const TEMPLATE_FIELDS = [
  "seat_rows", "seat_cols", "aisles",
  "seatmap_curved", "seatmap_numbering_rtl",
  "seatmap_sections", "seatmap_categories",
  "seatmap_category_prices",
  "seatmap_row_offsets", "seatmap_custom_labels",
  "seat_price", "seat_map_image_url",
  "seatmap_backdrop_opacity", "seatmap_backdrop_offset_y",
  "seatmap_backdrop_offset_x", "seatmap_backdrop_scale",
];

function SeatmapTemplateBar({ form, applyTemplate, eventId }) {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [picker, setPicker] = useState(false);

  const refresh = async () => {
    try {
      const { data } = await api.get("/organizer/seatmap-templates");
      setTemplates(data || []);
    } catch (e) {
      // 401/403 just means we're not logged in as organizer — silent.
    }
  };

  useEffect(() => { refresh(); }, []);

  const onSave = async () => {
    const name = window.prompt(
      "Name this layout (e.g. 'Comedy Club Main Stage'):",
      `${form.seat_rows}×${form.seat_cols} layout`
    );
    if (!name) return;
    const layout = Object.fromEntries(
      TEMPLATE_FIELDS.filter((k) => form[k] !== undefined).map((k) => [k, form[k]])
    );
    setLoading(true);
    try {
      await api.post("/organizer/seatmap-templates", { name: name.trim(), layout });
      toast.success(`Saved "${name.trim()}" — reuse it on your next show`);
      refresh();
    } catch (err) {
      toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Couldn't save template");
    } finally {
      setLoading(false);
    }
  };

  const onLoad = async (tmpl) => {
    if (eventId) {
      // We're editing an existing event — apply server-side so backend can
      // guard against overwriting a layout that already has bookings sold.
      if (!window.confirm(`Replace this event's seat layout with "${tmpl.name}"? Existing seat IDs may shift.`)) return;
      try {
        await api.post("/organizer/seatmap-templates/apply", {
          template_id: tmpl.template_id, event_id: eventId,
        });
        applyTemplate(tmpl.layout);
        toast.success(`Loaded "${tmpl.name}" — saved on the event`);
        setPicker(false);
      } catch (err) {
        toast.error(formatApiErrorDetail(err?.response?.data?.detail) || "Couldn't apply template");
      }
    } else {
      // New event — just hydrate the form. Saves the round-trip.
      applyTemplate(tmpl.layout);
      toast.success(`Loaded "${tmpl.name}" into the form`);
      setPicker(false);
    }
  };

  const onDelete = async (tmpl, e) => {
    e.stopPropagation();
    if (!window.confirm(`Delete template "${tmpl.name}"?`)) return;
    try {
      await api.delete(`/organizer/seatmap-templates/${tmpl.template_id}`);
      toast.success("Template deleted");
      refresh();
    } catch {
      toast.error("Couldn't delete");
    }
  };

  return (
    <div className="rounded-lg p-3 flex flex-wrap items-center gap-2" style={{ background: "var(--bg-elev)", border: "1px dashed var(--border)" }} data-testid="seatmap-templates-bar">
      <div className="text-xs flex items-center gap-1.5 mr-1" style={{ color: "var(--text-muted)" }}>
        <Bookmark className="w-3.5 h-3.5" /> Layout templates
      </div>
      <button
        type="button"
        onClick={() => setPicker((s) => !s)}
        disabled={!templates.length}
        className="text-xs px-2.5 py-1 rounded-md transition"
        style={{
          background: "transparent",
          border: "1px solid var(--border)",
          color: templates.length ? "var(--text)" : "var(--text-dim)",
          cursor: templates.length ? "pointer" : "not-allowed",
        }}
        data-testid="seatmap-templates-load"
      >
        Load {templates.length > 0 && <span className="opacity-60">({templates.length})</span>}
      </button>
      <button
        type="button"
        onClick={onSave}
        disabled={loading || !form.has_seatmap || !form.seat_rows || !form.seat_cols}
        className="text-xs px-2.5 py-1 rounded-md inline-flex items-center gap-1 transition"
        style={{ background: "var(--accent-soft)", color: "var(--accent)", border: "1px solid var(--accent)" }}
        data-testid="seatmap-templates-save"
      >
        <BookmarkPlus className="w-3 h-3" /> Save current as template
      </button>
      <div className="text-[10px] opacity-60 ml-auto" style={{ color: "var(--text-dim)" }}>
        Saves rows, aisles, categories, custom labels — not bookings.
      </div>

      {picker && templates.length > 0 && (
        <div className="w-full mt-2 rounded-lg overflow-hidden" style={{ background: "var(--bg)", border: "1px solid var(--border)" }} data-testid="seatmap-templates-picker">
          {templates.map((t) => (
            <button
              key={t.template_id}
              type="button"
              onClick={() => onLoad(t)}
              className="w-full text-left flex items-center justify-between px-3 py-2 hover:bg-[color:var(--bg-elev)] transition"
              data-testid={`seatmap-template-${t.template_id}`}
            >
              <div>
                <div className="text-sm font-medium">{t.name}</div>
                <div className="text-[10px]" style={{ color: "var(--text-dim)" }}>
                  {t.layout?.seat_rows || 0} × {t.layout?.seat_cols || 0}
                  {(t.layout?.aisles?.length || 0) > 0 && ` · ${t.layout.aisles.length} aisle(s)`}
                  {Object.keys(t.layout?.seatmap_custom_labels || {}).length > 0 &&
                    ` · ${Object.keys(t.layout.seatmap_custom_labels).length} custom label(s)`}
                  {" · "}saved {new Date(t.created_at).toLocaleDateString()}
                </div>
              </div>
              <span
                onClick={(e) => onDelete(t, e)}
                className="text-xs opacity-50 hover:opacity-100 px-2 py-1 rounded"
                title="Delete template"
                data-testid={`seatmap-template-delete-${t.template_id}`}
              >
                <X className="w-3 h-3" />
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
